#!/usr/bin/env python3
"""
Merges the per-region filtered extracts (one per region in pipeline.config.json) into one
file: trails.osm.pbf. Requires osmium-tool on PATH (see filter_trails.py).
Usage: python pipeline/phases/preprocessing/merge_trails.py
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib.pipeline import OSM_DIR, load_config  # noqa: E402
from lib.timing import phase  # noqa: E402

SCRIPT_NAME = "merge_trails.py"

config = load_config()
inputs = [str(OSM_DIR / f"{r['name']}-trails.osm.pbf") for r in config["regions"]]
out = OSM_DIR / "trails.osm.pbf"

with phase(SCRIPT_NAME, "merge_trails"):
    subprocess.run(["osmium", "merge", *inputs, "-o", str(out), "--overwrite"], check=True)
print(f"written {out}")
