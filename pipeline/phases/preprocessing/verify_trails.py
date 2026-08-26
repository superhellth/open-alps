#!/usr/bin/env python3
"""
Sanity-check a .osm.pbf file: bbox, node/way/relation counts. Exits nonzero if the file is
missing or empty, so run_all.py can gate on it automatically.
Usage: python pipeline/phases/preprocessing/verify_trails.py [filename]   (default: trails.osm.pbf)
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib.pipeline import OSM_DIR  # noqa: E402

filename = sys.argv[1] if len(sys.argv) > 1 else "trails.osm.pbf"
path = OSM_DIR / filename

if not path.exists() or path.stat().st_size == 0:
    print(f"verify failed: {path} missing or empty", file=sys.stderr)
    sys.exit(1)

subprocess.run(["osmium", "fileinfo", "-e", str(path)], check=True)
