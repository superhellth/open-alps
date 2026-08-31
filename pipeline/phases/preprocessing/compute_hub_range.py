#!/usr/bin/env python3
"""Computes the "hub range" - the union of a graph.maxEdgeKm-radius circle around every hut in
huts.geojson - and writes it as a GeoJSON Polygon/MultiPolygon to data/osm/hub_range.geojson.
filter_trails.py clips each region's trail extract to this shape via `osmium extract --polygon`:
no trail farther than maxEdgeKm beeline from every hut can ever appear on a valid hut-to-hut/
hut-to-start edge (build_hub_edges.py's real-distance cutoff can only be >= beeline distance) -
the same bound filter_start_points.py already applies to station/parking points.

The radius includes HUB_RANGE_SAFETY_MARGIN (lib.geo) so this shape and bavaria-dgm5's
per-hut DEM tile buffer (dem_providers/composite.py) are guaranteed to agree - see
docs/superpowers/specs/2026-08-22-hub-range-dem-coverage.md.

Usage: python pipeline/phases/preprocessing/compute_hub_range.py
"""

import argparse
import json
import sys
from pathlib import Path

from shapely.geometry import mapping

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib.geo import HUB_RANGE_SAFETY_MARGIN, hub_range_polygon  # noqa: E402
from lib.pipeline import OSM_DIR, load_config  # noqa: E402
from lib.timing import phase  # noqa: E402

SCRIPT_NAME = "compute_hub_range.py"

config = load_config()

parser = argparse.ArgumentParser()
parser.add_argument("--max-edge-km", type=float, default=config["graph"]["maxEdgeKm"],
                    help="longest hut-to-hut trail distance kept as an edge, used to size the hub-range radius (see pipeline.config.json's graph.maxEdgeKm)")
parser.add_argument("--osm-dir", type=Path, default=OSM_DIR,
                    help="directory holding huts.geojson and to write hub_range.geojson into")
args = parser.parse_args()

radius_km = args.max_edge_km * HUB_RANGE_SAFETY_MARGIN
with phase(SCRIPT_NAME, "compute_hub_range"):
    polygon = hub_range_polygon(args.osm_dir / "huts.geojson", radius_km)

out_path = args.osm_dir / "hub_range.geojson"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(mapping(polygon), f)
print(f"hub range (maxEdgeKm={args.max_edge_km} -> {radius_km:.3f} km radius, "
      f"{'MultiPolygon' if polygon.geom_type == 'MultiPolygon' else 'Polygon'}): "
      f"{len(polygon.geoms) if polygon.geom_type == 'MultiPolygon' else 1} piece(s)")
print(f"written {out_path}")
