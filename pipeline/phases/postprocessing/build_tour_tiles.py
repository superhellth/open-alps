#!/usr/bin/env python3
"""Builds tour_edges/'s PMTiles vector-tile archive + compact JSON stats file from
match_tour_edges.py's TOUR_LEG_DTYPE output (records.npy/geometry.npy/profiles.npy). Geometry is
every raw GPX point, unsimplified. Display ids for non-hut endpoint types (station/parking/partner
at a tour's start/end) resolve through the start-point id table.

Usage: python pipeline/phases/postprocessing/build_tour_tiles.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import orjson

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib import binfmt  # noqa: E402
from lib.pipeline import OSM_DIR, load_config  # noqa: E402
from lib.tippecanoe import build_pmtiles  # noqa: E402
from lib.timing import StepTimer, phase  # noqa: E402

SCRIPT_NAME = "build_tour_tiles.py"

TYPE_PREFIX = {
    binfmt.TYPE_HUT: "hut", binfmt.TYPE_STATION: "station", binfmt.TYPE_PARKING: "parking",
    binfmt.TYPE_PARTNER: "partner_betrieb",
}


def build_stats(records: np.ndarray, geometry: np.ndarray, profiles: np.ndarray, id_table: dict) -> tuple:
    inverse_id_table = {}
    for k, v in id_table.items():
        if ":" in k:
            prefix, raw_id = k.split(":", 1)
            inverse_id_table[(prefix, int(raw_id))] = v
        else:
            for raw_id in v:
                inverse_id_table[(k, int(raw_id))] = int(raw_id)

    def resolve(record_id, record_type):
        return inverse_id_table.get((TYPE_PREFIX[record_type], int(record_id)), int(record_id))

    lons, lats = geometry["lon"], geometry["lat"]
    stats = []
    point_counts = []
    all_points = []
    profile_counts = []
    all_profiles = []
    for edge_id in range(len(records)):
        r = records[edge_id]
        g_off, g_count = int(r["geom_offset"]), int(r["geom_count"])
        coords = np.column_stack([lons[g_off:g_off + g_count], lats[g_off:g_off + g_count]])
        point_counts.append(len(coords))
        all_points.append(coords)

        p_off, p_count = int(r["profile_offset"]), int(r["profile_count"])
        profile_counts.append(p_count)
        if p_count:
            all_profiles.append(profiles[p_off:p_off + p_count])

        stats.append({
            "edge_id": edge_id,
            "from_hut_id": resolve(r["from_id"], r["from_type"]),
            "to_hut_id": resolve(r["to_id"], r["to_type"]),
            "distance_m": float(r["distance_m"]),
            "ascent_m": float(r["ascent_m"]),
            "descent_m": float(r["descent_m"]),
            "duration_s": float(r["duration_s"]),
        })
    geometry_points = (
        np.concatenate(all_points, axis=0).astype("f4") if all_points else np.zeros((0, 2), dtype="f4")
    )
    elevation_values = (
        np.concatenate(all_profiles, axis=0).astype("f4") if all_profiles else np.zeros(0, dtype="f4")
    )
    return stats, point_counts, geometry_points, profile_counts, elevation_values


def main(argv=None):
    import argparse

    config = load_config()
    tiles_config = config.get("hutEdgeTiles", {})

    parser = argparse.ArgumentParser()
    parser.add_argument("--edges-dir", default=str(OSM_DIR / "tour_edges"))
    parser.add_argument("--id-table", default=str(OSM_DIR / "start_points_id_table.json"))
    parser.add_argument("--out-tiles", default=str(OSM_DIR / "tour-edges.pmtiles"))
    parser.add_argument("--out-stats", default=str(OSM_DIR / "tour-edge-stats.json"))
    parser.add_argument("--out-geometry-bin", default=str(OSM_DIR / "tour-edge-geometry.bin"))
    parser.add_argument("--out-geometry-json", default=str(OSM_DIR / "tour-edge-geometry.json"))
    parser.add_argument("--out-elevation-bin", default=str(OSM_DIR / "tour-edge-elevation.bin"))
    parser.add_argument("--out-elevation-json", default=str(OSM_DIR / "tour-edge-elevation.json"))
    parser.add_argument("--min-zoom", type=int, default=tiles_config.get("minZoom", 6))
    parser.add_argument("--max-zoom", type=int, default=tiles_config.get("maxZoom", 14))
    args = parser.parse_args(argv)

    edges_dir = Path(args.edges_dir)
    timer = StepTimer()
    with phase(SCRIPT_NAME, "build_tour_tiles", min_zoom=args.min_zoom, max_zoom=args.max_zoom) as meta:
        with timer.step("load_arrays"):
            records = binfmt.load_array(edges_dir / "records.npy", mmap=False)
            geometry = binfmt.load_array(edges_dir / "geometry.npy", mmap=False)
            profiles = binfmt.load_array(edges_dir / "profiles.npy", mmap=False)
            with open(args.id_table, encoding="utf-8") as f:
                id_table = json.load(f)

        print(f"streaming {len(records):,} tour legs -> tiling input + stats ...", flush=True)
        tiling_input = edges_dir / "tiling_input.geojsonseq"
        lons, lats = geometry["lon"], geometry["lat"]
        with timer.step("write_tiling_input"), open(tiling_input, "wb") as tf:
            for edge_id in range(len(records)):
                r = records[edge_id]
                g_off, g_count = int(r["geom_offset"]), int(r["geom_count"])
                coords = np.column_stack(
                    [lons[g_off:g_off + g_count], lats[g_off:g_off + g_count]]
                ).tolist()
                tf.write(orjson.dumps({
                    "type": "Feature",
                    "properties": {"edge_id": edge_id},
                    "geometry": {"type": "LineString", "coordinates": coords},
                }))
                tf.write(b"\n")

        with timer.step("build_stats"):
            stats, point_counts, geometry_points, profile_counts, elevation_values = build_stats(
                records, geometry, profiles, id_table
            )
        print(f"writing {args.out_stats} ...", flush=True)
        with timer.step("write_stats"), open(args.out_stats, "wb") as f:
            f.write(orjson.dumps(stats))

        print(f"writing {args.out_geometry_bin} and {args.out_geometry_json} ...", flush=True)
        with timer.step("write_geometry"):
            Path(args.out_geometry_bin).write_bytes(geometry_points.tobytes())
            with open(args.out_geometry_json, "wb") as f:
                f.write(orjson.dumps({"point_counts": point_counts}))

        print(f"writing {args.out_elevation_bin} and {args.out_elevation_json} ...", flush=True)
        with timer.step("write_elevation"):
            Path(args.out_elevation_bin).write_bytes(elevation_values.tobytes())
            with open(args.out_elevation_json, "wb") as f:
                f.write(orjson.dumps({"profile_counts": profile_counts}))

        mbtiles = edges_dir / "tiling_input.mbtiles"
        print(f"building vector tiles (z{args.min_zoom}-{args.max_zoom}) -> {mbtiles} "
              f"-> {args.out_tiles} ...", flush=True)
        build_pmtiles(timer, tiling_input, mbtiles, args.out_tiles, "tour_edges",
                      args.min_zoom, args.max_zoom)
        meta["n_edges"] = len(records)
        meta.update(timer.as_meta())
    print(f"step totals: {timer.summary()}", flush=True)
    print(f"written {args.out_tiles}, {args.out_stats}, {args.out_geometry_bin}, "
          f"{args.out_geometry_json}, {args.out_elevation_bin} and {args.out_elevation_json}")


if __name__ == "__main__":
    main()
