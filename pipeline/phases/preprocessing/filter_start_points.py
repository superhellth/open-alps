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
from lib.pipeline import OSM_DIR, hut_points, load_config  # noqa: E402

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


def _load_layer(path: Path, point_type: str) -> list:
    with open(path, encoding="utf-8") as f:
        fc = json.load(f)
    points = []
    for feat in fc["features"]:
        # fetch_stations_parking.py's osmium export --add-unique-id=type_id puts the id on the
        # Feature itself (e.g. "n8091317" - type prefix + numeric OSM id), not inside
        # "properties" - properties only ever holds the tag fields KEEP_FIELDS lets through.
        raw_id = feat.get("id")
        if raw_id is None:
            continue
        lon, lat = feat["geometry"]["coordinates"]
        points.append({"lon": lon, "lat": lat, "osm_id": int(raw_id[1:]), "type": point_type})
    return points


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-edge-km", type=float, default=config["graph"]["maxEdgeKm"])
    args = parser.parse_args()

    hut_coords = np.array(hut_points(OSM_DIR / "huts.geojson"))
    all_points = (
        _load_layer(OSM_DIR / "stations.geojson", "station")
        + _load_layer(OSM_DIR / "parking.geojson", "parking")
    )
    print(f"start-point candidates: {len(all_points)}")

    kept = filter_to_hut_range(all_points, hut_coords, args.max_edge_km)
    print(f"kept within maxEdgeKm of a hut: {len(kept)}")

    arr = np.zeros(len(kept), dtype=[
        ("lon", "f8"), ("lat", "f8"), ("osm_id", "i8"), ("type", "u1"),
    ])
    type_code = {"station": binfmt.TYPE_STATION, "parking": binfmt.TYPE_PARKING}
    for i, p in enumerate(kept):
        arr[i] = (p["lon"], p["lat"], p["osm_id"], type_code[p["type"]])

    binfmt.save_array(OSM_DIR / "start_points.npy", arr)
    id_table = {f"{p['type']}:{p['osm_id']}": p["osm_id"] for p in kept}
    with open(OSM_DIR / "start_points_id_table.json", "w", encoding="utf-8") as f:
        json.dump(id_table, f)
    print(f"written {OSM_DIR / 'start_points.npy'}")
