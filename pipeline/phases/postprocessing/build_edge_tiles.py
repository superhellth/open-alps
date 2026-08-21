#!/usr/bin/env python3
"""Generalized from build_hut_edge_tiles.py: builds a PMTiles vector-tile archive + a compact
JSON stats file from a build_hub_edges.py edge set (records.npy/geometry.npy/profiles.npy),
instead of shipping full-resolution edge geometry to the browser. Called twice by dodo.py - once
for hut-edges, once for start-edges - same script, different --edges-dir/--layer-name. See
docs/superpowers/specs/2026-08-19-pipeline-v2-design.md.

Usage:
    python pipeline/phases/postprocessing/build_edge_tiles.py --edges-dir data/osm/hut_edges --layer-name hut_edges \
        --out-tiles data/osm/hut-edges.pmtiles --out-stats data/osm/hut-edge-stats.json
"""

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import orjson
from pmtiles.convert import mbtiles_to_pmtiles

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib import binfmt  # noqa: E402
from lib.pipeline import load_config, run_tippecanoe  # noqa: E402
from lib.timing import StepTimer, phase  # noqa: E402

SCRIPT_NAME = "build_edge_tiles.py"

TYPE_PREFIX = {binfmt.TYPE_HUT: "hut", binfmt.TYPE_STATION: "station", binfmt.TYPE_PARKING: "parking"}


def rdp_keep_indices(coords: np.ndarray, epsilon: float) -> np.ndarray:
    n = len(coords)
    if n < 3:
        return np.arange(n)
    keep = np.zeros(n, dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        start, end = stack.pop()
        if end <= start + 1:
            continue
        p1, p2 = coords[start], coords[end]
        seg = coords[start + 1:end]
        dxy = p2 - p1
        norm = math.hypot(dxy[0], dxy[1])
        if norm == 0:
            d = np.hypot(seg[:, 0] - p1[0], seg[:, 1] - p1[1])
        else:
            d = np.abs(dxy[1] * (seg[:, 0] - p1[0]) - dxy[0] * (seg[:, 1] - p1[1])) / norm
        idx = int(np.argmax(d))
        if d[idx] > epsilon:
            real_idx = start + 1 + idx
            keep[real_idx] = True
            stack.append((start, real_idx))
            stack.append((real_idx, end))
    return np.nonzero(keep)[0]


def build_stats(records: np.ndarray, geometry: np.ndarray, profiles: np.ndarray, id_table: dict,
                 hover_tolerance_deg: float) -> list:
    inverse_id_table = {}
    for k, v in id_table.items():
        prefix, raw_id = k.split(":", 1)
        inverse_id_table[(prefix, int(raw_id))] = v

    def resolve(record_id, record_type):
        return inverse_id_table.get((TYPE_PREFIX[record_type], int(record_id)), int(record_id))

    lons, lats = geometry["lon"], geometry["lat"]
    stats = []
    for edge_id in range(len(records)):
        r = records[edge_id]
        g_off, g_count = int(r["geom_offset"]), int(r["geom_count"])
        coords = np.column_stack([lons[g_off:g_off + g_count], lats[g_off:g_off + g_count]])
        keep = rdp_keep_indices(coords, hover_tolerance_deg)

        p_off, p_count = int(r["profile_offset"]), int(r["profile_count"])
        profile = profiles[p_off:p_off + p_count].tolist() if p_count else []

        stats.append({
            "edge_id": edge_id,
            "from_hut_id": resolve(r["from_id"], r["from_type"]),
            "to_hut_id": resolve(r["to_id"], r["to_type"]),
            "distance_m": float(r["distance_m"]),
            "road_m": float(r["road_m"]),
            "ascent_m": float(r["ascent_m"]) if r["ascent_m"] != binfmt.UNSET else None,
            "descent_m": float(r["descent_m"]) if r["descent_m"] != binfmt.UNSET else None,
            "elevation_profile": profile,
            "sac_scale": int(r["sac_rank"]) if r["sac_rank"] >= 0 else None,
            "via_ferrata": bool(r["via_ferrata"]),
            "positions": coords[keep].tolist(),
        })
    return stats


if __name__ == "__main__":
    config = load_config()
    tiles_config = config.get("hutEdgeTiles", {})

    parser = argparse.ArgumentParser()
    parser.add_argument("--edges-dir", required=True)
    parser.add_argument("--id-table", required=True)
    parser.add_argument("--layer-name", required=True)
    parser.add_argument("--out-tiles", required=True)
    parser.add_argument("--out-stats", required=True)
    parser.add_argument("--min-zoom", type=int, default=tiles_config.get("minZoom", 6))
    parser.add_argument("--max-zoom", type=int, default=tiles_config.get("maxZoom", 14))
    parser.add_argument("--hover-simplify-tolerance-deg", type=float,
                         default=tiles_config.get("hoverSimplifyToleranceDeg", 0.0001))
    args = parser.parse_args()

    edges_dir = Path(args.edges_dir)
    # Four very different costs live in this script - our own geometry/stats Python loops, an
    # external tippecanoe run, and the mbtiles->pmtiles conversion. Splitting them is the only
    # way to tell "our code got slower" from "there are simply more edges to tile".
    timer = StepTimer()
    with timer.step("load_arrays"):
        records = binfmt.load_array(edges_dir / "records.npy", mmap=False)
        geometry = binfmt.load_array(edges_dir / "geometry.npy", mmap=False)
        profiles = binfmt.load_array(edges_dir / "profiles.npy", mmap=False)
        with open(args.id_table, encoding="utf-8") as f:
            id_table = json.load(f)

    print(f"streaming {len(records):,} edges -> tiling input + stats ...", flush=True)
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
        stats = build_stats(records, geometry, profiles, id_table,
                            args.hover_simplify_tolerance_deg)
    print(f"writing {args.out_stats} ...", flush=True)
    with timer.step("write_stats"), open(args.out_stats, "wb") as f:
        f.write(orjson.dumps(stats))

    mbtiles = edges_dir / "tiling_input.mbtiles"
    print(f"building vector tiles (z{args.min_zoom}-{args.max_zoom}) -> {mbtiles} ...", flush=True)
    with timer.step("tippecanoe"):
        run_tippecanoe([
            "-o", str(mbtiles), "-l", args.layer_name,
            "-Z", str(args.min_zoom), "-z", str(args.max_zoom),
            "--drop-densest-as-needed", "--force", str(tiling_input),
        ])

    print(f"converting {mbtiles} -> {args.out_tiles} ...", flush=True)
    with timer.step("mbtiles_to_pmtiles"):
        mbtiles_to_pmtiles(str(mbtiles), args.out_tiles, args.max_zoom)

    tiling_input.unlink(missing_ok=True)
    mbtiles.unlink(missing_ok=True)
    # Nothing left to time - phase() here exists only to land the split in timings.jsonl next to
    # every other phase, keyed by layer so hut_edges and start_edges stay distinguishable.
    with phase(SCRIPT_NAME, "build_edge_tiles", layer=args.layer_name, n_edges=len(records),
               min_zoom=args.min_zoom, max_zoom=args.max_zoom, **timer.as_meta()):
        pass
    print(f"step totals: {timer.summary()}", flush=True)
    print(f"written {args.out_tiles} and {args.out_stats}")
