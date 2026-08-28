#!/usr/bin/env python3
"""
Filters each raw region extract down to hiking-relevant ways, using the tag filter from
pipeline.config.json, then clips to the hub range (data/osm/hub_range.geojson,
compute_hub_range.py's output - the union of a graph.maxEdgeKm-radius circle around every hut).
No trail farther than that from every hut can ever appear on a valid hut-to-hut/hut-to-start edge
(see compute_hub_range.py's docstring), so dropping it here means stream_osm/contract_structural
in build_base_graph.py never have to process it, and sample_base_elevation.py never needs DEM
coverage for it either.

Preserves full node/way topology at both steps (osmium tags-filter keeps referenced nodes by
default; `osmium extract`'s default "complete_ways" strategy keeps a way whole if any of its nodes
falls inside the polygon, rather than cutting through it) - required for graph-building later.
Requires osmium-tool installed natively (conda install -c conda-forge osmium-tool) and on PATH -
no Docker.

Usage: python pipeline/phases/preprocessing/filter_trails.py
"""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib.pipeline import OSM_DIR, load_config  # noqa: E402
from lib.timing import StepTimer, phase  # noqa: E402

SCRIPT_NAME = "filter_trails.py"

config = load_config()

parser = argparse.ArgumentParser()
parser.add_argument("--tag-filter", default=config["trailTagFilter"])
args = parser.parse_args()

hub_range_path = OSM_DIR / "hub_range.geojson"

timer = StepTimer()
with phase(SCRIPT_NAME, "filter_trails") as meta:
    for region in config["regions"]:
        name = region["name"]
        src = OSM_DIR / "raw" / f"{name}-latest.osm.pbf"
        tag_filtered = OSM_DIR / f"{name}-tag-filtered.osm.pbf"
        dst = OSM_DIR / f"{name}-trails.osm.pbf"

        print(f"tag-filtering {src} -> {tag_filtered}")
        with timer.step("tag_filter"):
            subprocess.run(
                ["osmium", "tags-filter", str(src), args.tag_filter, "-o", str(tag_filtered), "--overwrite"],
                check=True,
            )

        print(f"clipping {tag_filtered} to hub range {hub_range_path} -> {dst}")
        with timer.step("clip"):
            subprocess.run(
                ["osmium", "extract", "--polygon", str(hub_range_path), str(tag_filtered),
                 "-o", str(dst), "--overwrite"],
                check=True,
            )
        tag_filtered.unlink()
    meta.update(timer.as_meta())
print(f"step totals: {timer.summary()}", flush=True)
