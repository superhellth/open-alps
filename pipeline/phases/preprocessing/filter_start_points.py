#!/usr/bin/env python3
"""Filters stations.geojson/parking.geojson down to points within graph.maxEdgeKm beeline of
some hut - a correct filter (not an approximation), since no point farther than that can produce
an edge under build_hub_edges.py's existing real-distance cutoff regardless of how the trail
actually routes. trailTagFilter already includes residential/service/unclassified/tertiary roads
across the whole Austria+Bavaria extract, so trail-snap distance alone would not exclude urban
parking - this beeline-to-hut filter is what actually bounds the hub count before it reaches the
expensive graph query. See docs/superpowers/specs/2026-08-19-pipeline-v2-design.md.

Usage: python pipeline/phases/preprocessing/filter_start_points.py
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib import binfmt  # noqa: E402
from lib.geo import hut_points  # noqa: E402
from lib.pipeline import OSM_DIR, load_config  # noqa: E402
from lib.timing import phase  # noqa: E402

SCRIPT_NAME = "filter_start_points.py"

config = load_config()


def filter_to_hut_range(start_points: list, hut_coords: np.ndarray, max_edge_km: float) -> list:
    if not start_points or len(hut_coords) == 0:
        return []
    hut_tree = cKDTree(hut_coords)
    deg_per_km = 1 / 111.320
    kept = []
    for p in start_points:
        dist_deg, _ = hut_tree.query((p["lon"], p["lat"]), k=1)
        if dist_deg <= max_edge_km * deg_per_km:
            kept.append(p)
    return kept


def _points_from_features(fc: dict, point_type: str, extract_id) -> list:
    points = []
    for feat in fc["features"]:
        osm_id = extract_id(feat)
        if osm_id is None:
            continue
        lon, lat = feat["geometry"]["coordinates"]
        points.append({
            "lon": lon, "lat": lat, "osm_id": osm_id, "type": point_type,
            "properties": feat.get("properties", {}),
        })
    return points


def _load_osm_export_layer(path: Path, point_type: str) -> list:
    """stations.geojson/parking.geojson, fetch_stations_parking.py's osmium export
    --add-unique-id=type_id: the id is on the Feature itself, OSM-export shaped ("n8091317" -
    type-prefix char + numeric id), not inside "properties" - properties only ever holds the tag
    fields KEEP_FIELDS lets through."""
    with open(path, encoding="utf-8") as f:
        fc = json.load(f)

    def extract_id(feat):
        raw_id = feat.get("id")
        return None if raw_id is None else int(raw_id[1:])

    return _points_from_features(fc, point_type, extract_id)


def _load_arcgis_layer(path: Path, point_type: str) -> list:
    """partner_betriebe.geojson, from fetch_huts.py/the Alpenverein ArcGIS layer - not OSM data at
    all: the id is a plain int already sitting in properties["id"] (the ArcGIS layer's OBJECTID,
    see fetch_huts.py's split_features), no prefix character to strip."""
    with open(path, encoding="utf-8") as f:
        fc = json.load(f)

    def extract_id(feat):
        raw_id = feat.get("properties", {}).get("id")
        return None if raw_id is None else int(raw_id)

    return _points_from_features(fc, point_type, extract_id)


def build_id_table(points: list) -> dict:
    """type -> str(id) -> {access, motor_vehicle, barrier}, None (not absent) where a tag is
    missing (spec E1) so build_approach_table.py can tell "unknown" apart from "open"."""
    table = {}
    for p in points:
        pid = str(p["osm_id"])
        props = p.get("properties", {})
        table.setdefault(p["type"], {})[pid] = {
            "access": props.get("access"),
            "motor_vehicle": props.get("motor_vehicle"),
            "barrier": props.get("barrier"),
        }
    return table


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-edge-km", type=float, default=config["graph"]["maxEdgeKm"])
    args = parser.parse_args()

    with phase(SCRIPT_NAME, "filter_start_points"):
        hut_coords = np.array(hut_points(OSM_DIR / "huts.geojson"))
        all_points = (
            _load_osm_export_layer(OSM_DIR / "stations.geojson", "station")
            + _load_osm_export_layer(OSM_DIR / "parking.geojson", "parking")
            + _load_arcgis_layer(OSM_DIR / "partner_betriebe.geojson", "partner_betrieb")
        )
        print(f"start-point candidates: {len(all_points)}")

        kept = filter_to_hut_range(all_points, hut_coords, args.max_edge_km)
        print(f"kept within maxEdgeKm of a hut: {len(kept)}")

        arr = np.zeros(len(kept), dtype=[
            ("lon", "f8"), ("lat", "f8"), ("osm_id", "i8"), ("type", "u1"),
        ])
        type_code = {
            "station": binfmt.TYPE_STATION, "parking": binfmt.TYPE_PARKING,
            "partner_betrieb": binfmt.TYPE_PARTNER,
        }
        for i, p in enumerate(kept):
            arr[i] = (p["lon"], p["lat"], p["osm_id"], type_code[p["type"]])

        binfmt.save_array(OSM_DIR / "start_points.npy", arr)
        id_table = build_id_table(kept)
        with open(OSM_DIR / "start_points_id_table.json", "w", encoding="utf-8") as f:
            json.dump(id_table, f)
    print(f"written {OSM_DIR / 'start_points.npy'}")
