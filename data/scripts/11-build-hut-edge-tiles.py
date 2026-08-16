#!/usr/bin/env python3
"""
Builds two small static assets from data/osm/hut-edges.geojson (script 06/08's output) instead of
shipping that file to the browser directly: at ~6,000 edges averaging ~1,170 vertices each, it's
~184MB of GeoJSON - fetching, parsing and rendering that as one <Polyline> per edge is what was
making the trail-graph view slow.

Output:
    1. hut-edges.pmtiles - a PMTiles vector-tile archive of the full-resolution edge geometry
       (properties trimmed to just `edge_id`, everything else lives in file 2), built the same
       way as trails.pmtiles (09-build-trail-tiles.py): tippecanoe zoomed tiles -> pmtiles convert.
       Rendered client-side via protomaps-leaflet, same "no backend" shape as the raw-trails
       layer - no per-edge React component, no 184MB fetch, tippecanoe's own zoom-dependent
       simplification instead of shipping one fixed resolution.
    2. hut-edge-stats.json - one compact JSON array, index = edge_id, holding everything that
       isn't geometry (from_hut_id, to_hut_id, distance_m, road_m, ascent_m, descent_m,
       elevation_profile, sac_scale, via_ferrata) plus a heavily Ramer-Douglas-Peucker-simplified
       copy of the line
       ([lng, lat] pairs, hutEdgeTiles.hoverSimplifyToleranceDeg tolerance - default ~11m, far
       below anything visible at the stroke width this renders at). The frontend's hover
       hit-test needs *some* geometry to measure cursor distance against, but not full
       resolution - PMTiles has no feature-level query API to reuse for that, so this ships a
       separate, much smaller copy just for that purpose.

Usage:
    python data/scripts/11-build-hut-edge-tiles.py
    python data/scripts/11-build-hut-edge-tiles.py --min-zoom 6 --max-zoom 14
"""

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import orjson
from pmtiles.convert import mbtiles_to_pmtiles

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.pipeline import OSM_DIR, load_config, run_tippecanoe  # noqa: E402

config = load_config()
tiles_config = config.get("hutEdgeTiles", {})

parser = argparse.ArgumentParser()
parser.add_argument("--edges", default=str(OSM_DIR / "hut-edges.geojson"))
parser.add_argument("--out-tiles", default=str(OSM_DIR / "hut-edges.pmtiles"))
parser.add_argument("--out-stats", default=str(OSM_DIR / "hut-edge-stats.json"))
parser.add_argument("--min-zoom", type=int, default=tiles_config.get("minZoom", 6))
parser.add_argument("--max-zoom", type=int, default=tiles_config.get("maxZoom", 14))
parser.add_argument("--hover-simplify-tolerance-deg", type=float,
                     default=tiles_config.get("hoverSimplifyToleranceDeg", 0.0001))
args = parser.parse_args()


def rdp_keep_indices(coords: np.ndarray, epsilon: float) -> np.ndarray:
    """Ramer-Douglas-Peucker, iterative (recursive blows Python's stack on a 4000+-vertex line)
    and vectorized per segment (numpy does the per-point distance check, not a Python loop)."""
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


print(f"reading {args.edges} ...")
with open(args.edges, encoding="utf-8") as f:
    edges_fc = json.load(f)

print(f"streaming {len(edges_fc['features']):,} edges -> tiling input + stats ...")
tiling_input = OSM_DIR / "hut-edges.geojsonseq"
stats = []
with open(tiling_input, "wb") as tf:
    for edge_id, feat in enumerate(edges_fc["features"]):
        props = feat["properties"]
        coords = np.array(feat["geometry"]["coordinates"], dtype=np.float64)

        tf.write(orjson.dumps({
            "type": "Feature",
            "properties": {"edge_id": edge_id},
            "geometry": feat["geometry"],
        }))
        tf.write(b"\n")

        keep = rdp_keep_indices(coords, args.hover_simplify_tolerance_deg)
        stats.append({
            "edge_id": edge_id,
            "from_hut_id": props.get("from_hut_id"),
            "to_hut_id": props.get("to_hut_id"),
            "distance_m": props.get("distance_m"),
            "road_m": props.get("road_m"),
            "ascent_m": props.get("ascent_m"),
            "descent_m": props.get("descent_m"),
            "elevation_profile": props.get("elevation_profile"),
            "sac_scale": props.get("sac_scale"),
            "via_ferrata": props.get("via_ferrata"),
            "positions": coords[keep].tolist(),
        })

print(f"writing {args.out_stats} ...")
with open(args.out_stats, "wb") as f:
    f.write(orjson.dumps(stats))

mbtiles = OSM_DIR / "hut-edges.mbtiles"
print(f"building vector tiles (z{args.min_zoom}-{args.max_zoom}) -> {mbtiles} ...")
run_tippecanoe(
    [
        "-o", str(mbtiles),
        "-l", "hut_edges",
        "-Z", str(args.min_zoom),
        "-z", str(args.max_zoom),
        "--drop-densest-as-needed",
        "--force",
        str(tiling_input),
    ]
)

print(f"converting {mbtiles} -> {args.out_tiles} ...")
mbtiles_to_pmtiles(str(mbtiles), str(args.out_tiles), args.max_zoom)

tiling_input.unlink(missing_ok=True)
mbtiles.unlink(missing_ok=True)
print(f"written {args.out_tiles} and {args.out_stats}")
