#!/usr/bin/env python3
"""Computes the "hub range" - a rectangle enclosing every hut in huts.geojson, padded by
graph.maxEdgeKm - and writes it to data/osm/hub_range.json. filter_trails.py clips each region's
trail extract to this rectangle: no trail node farther than maxEdgeKm beeline from every hut can
ever appear on a valid hut-to-hut/hut-to-start edge (build_hub_edges.py's real-distance cutoff can
only be >= beeline distance), so anything outside it is provably irrelevant - the same bound
filter_start_points.py already applies to station/parking points.

A single bounding rectangle (not a tighter per-hut-buffered union of circles) trades some over-
inclusion at the corners for a plain `osmium extract --bbox` in filter_trails.py - acceptable here
because the point is to stop paying for trail data (and, via the DEM footprint that depends on it)
terrain nowhere near any hut, not to hit a tight bound. See lib.pipeline.bbox_from_huts()'s
docstring for why this same rectangle shape is a poor fit for bavaria_dgm.py's tile-per-request DEM
fetch (which already uses a real per-point buffer via tiles_for_points()).

Usage: python pipeline/phases/preprocessing/compute_hub_range.py
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib.pipeline import OSM_DIR, bbox_from_huts, load_config  # noqa: E402

config = load_config()

parser = argparse.ArgumentParser()
parser.add_argument("--max-edge-km", type=float, default=config["graph"]["maxEdgeKm"])
args = parser.parse_args()

deg_per_km = 1 / 111.320  # same approximation filter_start_points.py uses
buffer_deg = args.max_edge_km * deg_per_km

hub_range = bbox_from_huts(OSM_DIR / "huts.geojson", buffer_deg=buffer_deg)

out_path = OSM_DIR / "hub_range.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(hub_range, f)
print(f"hub range (maxEdgeKm={args.max_edge_km} -> {buffer_deg:.3f} deg buffer): {hub_range}")
print(f"written {out_path}")
