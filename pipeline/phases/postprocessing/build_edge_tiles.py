#!/usr/bin/env python3
"""Generalized from build_hut_edge_tiles.py: builds a PMTiles vector-tile archive + a compact
JSON stats file from a build_hub_edges.py edge set (records.npy/geometry.npy/profiles.npy),
instead of shipping full-resolution edge geometry to the browser. Called twice by dodo.py - once
for hut-edges, once for start-edges - same script, different --edges-dir/--layer-name. See
docs/superpowers/specs/2026-08-19-pipeline-v2-design.md.

Usage:
    python pipeline/phases/postprocessing/build_edge_tiles.py --edges-dir data/build/hut-edges --layer-name hut_edges \
        --out-tiles data/build/hut-edges/edges.pmtiles --out-stats data/build/hut-edges/stats.json
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import orjson
import shapely

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib import binfmt  # noqa: E402
from lib.pipeline import load_config  # noqa: E402
from lib.tippecanoe import build_pmtiles  # noqa: E402
from lib.timing import StepTimer, phase  # noqa: E402

SCRIPT_NAME = "build_edge_tiles.py"

TYPE_PREFIX = {
    binfmt.TYPE_HUT: "hut", binfmt.TYPE_STATION: "station", binfmt.TYPE_PARKING: "parking",
    binfmt.TYPE_PARTNER: "partner_betrieb",
}


def _gather_indices(offsets: np.ndarray, counts: np.ndarray) -> np.ndarray:
    """Flat indices of the concatenated slices [offset, offset + count) - one array op instead of
    a Python loop over slices."""
    total = int(counts.sum())
    starts = np.cumsum(counts) - counts
    return np.repeat(offsets - starts, counts) + np.arange(total)


# Edges simplified per GEOS call. Peak memory grows ~110 KB per edge on start-edges (whole-array
# passes over 400k edges need tens of GB); throughput is flat up to ~1000 edges and drops beyond.
SIMPLIFY_CHUNK_EDGES = 1000


def simplify_edges(records: np.ndarray, geometry: np.ndarray, tolerance_deg: float,
                   chunk_edges: int = SIMPLIFY_CHUNK_EDGES) -> tuple:
    """Douglas-Peucker-simplifies every edge's geometry, chunk_edges edges per GEOS call. Returns
    the concatenated (n, 2) f8 [lon, lat] points and the per-edge point counts. Edges with fewer
    than two points are passed through unsimplified. geometry may be memory-mapped: only each
    chunk's own points are read."""
    if len(records) == 0:
        return np.zeros((0, 2), dtype=np.float64), np.zeros(0, dtype=np.int64)
    chunks = [
        _simplify_chunk(records[start:start + chunk_edges], geometry, tolerance_deg)
        for start in range(0, len(records), chunk_edges)
    ]
    return np.concatenate([c[0] for c in chunks]), np.concatenate([c[1] for c in chunks])


def _simplify_chunk(records: np.ndarray, geometry: np.ndarray, tolerance_deg: float) -> tuple:
    offsets = records["geom_offset"].astype(np.int64)
    counts = records["geom_count"].astype(np.int64)
    gathered = geometry[_gather_indices(offsets, counts)]
    coords = np.column_stack([gathered["lon"], gathered["lat"]])
    edge_of_point = np.repeat(np.arange(len(records)), counts)

    long_edges = counts >= 2
    long_mask = long_edges[edge_of_point]
    # shapely wants consecutive line indices, so number the long edges among themselves.
    line_of_edge = np.cumsum(long_edges) - 1
    lines = shapely.linestrings(coords[long_mask], indices=line_of_edge[edge_of_point[long_mask]])
    simplified = shapely.simplify(lines, tolerance_deg, preserve_topology=False)
    simplified_coords, line_of_point = shapely.get_coordinates(simplified, return_index=True)
    simplified_counts = np.bincount(line_of_point, minlength=len(lines))

    out_counts = counts.copy()
    out_counts[long_edges] = simplified_counts
    out_starts = np.cumsum(out_counts) - out_counts
    points = np.empty((int(out_counts.sum()), 2), dtype=np.float64)
    points[_gather_indices(out_starts[long_edges], simplified_counts)] = simplified_coords
    # coords is in edge order, so dropping the long edges' points leaves the short ones in order.
    points[_gather_indices(out_starts[~long_edges], counts[~long_edges])] = coords[~long_mask]
    return points, out_counts


def build_stats(records: np.ndarray, profiles: np.ndarray, id_table: dict,
                 point_counts: np.ndarray, points: np.ndarray) -> tuple:
    inverse_id_table = {}
    for k, v in id_table.items():
        if ":" in k:
            prefix, raw_id = k.split(":", 1)
            inverse_id_table[(prefix, int(raw_id))] = v
        else:
            # filter_start_points.build_id_table's shape: {type: {str(id): {tag: value, ...}}}.
            # The display id was always the numeric id itself (no separate display value), so
            # resolve to that directly instead of the tag dict.
            for raw_id in v:
                inverse_id_table[(k, int(raw_id))] = int(raw_id)

    # Resolve each distinct (type, id) once, then broadcast back over both endpoint columns.
    n = len(records)
    endpoint_keys = np.column_stack([
        np.concatenate([records["from_type"], records["to_type"]]).astype(np.int64),
        np.concatenate([records["from_id"], records["to_id"]]),
    ])
    unique_keys, inverse = np.unique(endpoint_keys, axis=0, return_inverse=True)
    resolved = [
        inverse_id_table.get((TYPE_PREFIX[int(t)], int(i)), int(i)) for t, i in unique_keys
    ]
    endpoint_ids = [resolved[j] for j in inverse.ravel()]
    from_ids, to_ids = endpoint_ids[:n], endpoint_ids[n:]

    ascent = [a if a != binfmt.UNSET else None for a in records["ascent_m"].tolist()]
    descent = [d if d != binfmt.UNSET else None for d in records["descent_m"].tolist()]
    sac = [s if s >= 0 else None for s in records["sac_rank"].tolist()]
    stats = [
        {
            "edge_id": edge_id,
            "from_hut_id": from_id,
            "to_hut_id": to_id,
            "distance_m": distance,
            "road_m": road,
            "ascent_m": asc,
            "descent_m": desc,
            "sac_scale": sac_scale,
            "via_ferrata": via_ferrata,
        }
        for edge_id, (from_id, to_id, distance, road, asc, desc, sac_scale, via_ferrata) in enumerate(zip(
            from_ids, to_ids, records["distance_m"].tolist(), records["road_m"].tolist(),
            ascent, descent, sac, records["via_ferrata"].tolist(),
        ))
    ]

    profile_counts = records["profile_count"].astype(np.int64)
    elevation_values = profiles[
        _gather_indices(records["profile_offset"].astype(np.int64), profile_counts)
    ].astype("f4")
    return (stats, point_counts.tolist(), points.astype("f4"), profile_counts.tolist(),
            elevation_values)


if __name__ == "__main__":
    config = load_config()
    tiles_config = config.get("hutEdgeTiles", {})

    parser = argparse.ArgumentParser()
    parser.add_argument("--edges-dir", required=True,
                         help="directory holding the edge records to tile (hut-edges/ or start-edges/)")
    parser.add_argument("--id-table", required=True,
                         help="path to the id table for the edge set being tiled (build_edge_ids.py's output)")
    parser.add_argument("--layer-name", required=True,
                         help="vector-tile layer name to write the edges into")
    parser.add_argument("--out-tiles", required=True,
                         help="path to write the output PMTiles archive")
    parser.add_argument("--out-stats", required=True,
                         help="path to write the per-edge stats JSON")
    parser.add_argument("--out-geometry-bin", required=True,
                         help="path to write the packed edge-geometry binary")
    parser.add_argument("--out-geometry-json", required=True,
                         help="path to write the edge-geometry manifest")
    parser.add_argument("--out-elevation-bin", required=True,
                         help="path to write the packed edge-elevation binary")
    parser.add_argument("--out-elevation-json", required=True,
                         help="path to write the edge-elevation manifest")
    parser.add_argument("--min-zoom", type=int, default=tiles_config.get("minZoom", 6),
                         help="lowest zoom level tippecanoe builds tiles for")
    parser.add_argument("--max-zoom", type=int, default=tiles_config.get("maxZoom", 14),
                         help="highest zoom level tippecanoe builds tiles for")
    parser.add_argument("--simplify-tolerance-deg", type=float,
                         default=tiles_config.get("simplifyToleranceDeg", 0.0003),
                         help="geometry simplification tolerance (degrees) applied before tiling")
    args = parser.parse_args()

    edges_dir = Path(args.edges_dir)
    # Four very different costs live in this script - our own geometry/stats Python loops, an
    # external tippecanoe run, and the mbtiles->pmtiles conversion. Splitting them is the only
    # way to tell "our code got slower" from "there are simply more edges to tile".
    timer = StepTimer()
    with phase(SCRIPT_NAME, "build_edge_tiles", layer=args.layer_name,
               min_zoom=args.min_zoom, max_zoom=args.max_zoom) as meta:
        with timer.step("load_arrays"):
            records = binfmt.load_array(edges_dir / "records.npy", mmap=False)
            geometry = binfmt.load_array(edges_dir / "geometry.npy")
            profiles = binfmt.load_array(edges_dir / "profiles.npy", mmap=False)
            with open(args.id_table, encoding="utf-8") as f:
                id_table = json.load(f)

        print(f"simplifying {len(records):,} edges ...", flush=True)
        with timer.step("simplify"):
            points, point_counts = simplify_edges(records, geometry, args.simplify_tolerance_deg)

        with timer.step("build_stats"):
            stats, point_counts, geometry_points, profile_counts, elevation_values = build_stats(
                records, profiles, id_table, point_counts, points
            )

        print("writing tiling input ...", flush=True)
        tiling_input = edges_dir / "tiling_input.geojsonseq"
        with timer.step("write_tiling_input"), open(tiling_input, "wb") as tf:
            ends = np.cumsum(point_counts)
            for edge_id, (start, end) in enumerate(zip(ends - point_counts, ends)):
                tf.write(orjson.dumps({
                    "type": "Feature",
                    "properties": {"edge_id": edge_id},
                    "geometry": {"type": "LineString", "coordinates": points[start:end].tolist()},
                }))
                tf.write(b"\n")

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
        build_pmtiles(timer, tiling_input, mbtiles, args.out_tiles, args.layer_name,
                      args.min_zoom, args.max_zoom)
        meta["n_edges"] = len(records)
        meta.update(timer.as_meta())
    print(f"step totals: {timer.summary()}", flush=True)
    print(f"written {args.out_tiles}, {args.out_stats}, {args.out_geometry_bin}, "
          f"{args.out_geometry_json}, {args.out_elevation_bin} and {args.out_elevation_json}")
