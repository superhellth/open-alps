#!/usr/bin/env python3
"""
Filters each raw region extract down to hiking-relevant ways, using the tag filter from
pipeline.config.json. Preserves full node/way topology (osmium tags-filter keeps referenced
nodes by default) - required for graph-building later. Requires osmium-tool installed natively
(conda install -c conda-forge osmium-tool) and on PATH - no Docker.
Usage: python pipeline/preprocessing/filter_trails.py
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.pipeline import OSM_DIR, load_config  # noqa: E402

config = load_config()
tag_filter = config["trailTagFilter"]

for region in config["regions"]:
    name = region["name"]
    src = OSM_DIR / "raw" / f"{name}-latest.osm.pbf"
    dst = OSM_DIR / f"{name}-trails.osm.pbf"
    print(f"filtering {src} -> {dst}")
    subprocess.run(
        ["osmium", "tags-filter", str(src), tag_filter, "-o", str(dst), "--overwrite"],
        check=True,
    )
