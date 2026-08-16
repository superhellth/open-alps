#!/usr/bin/env python3
"""
Reprojects/merges the DEM tiles data/dem/fetch_manifest.json (07-fetch-dem.py's output) points at
into data/dem/dem.vrt, then materializes that into data/dem/dem.tif for 08-add-elevation.py to
sample - see pipeline/lib/pipeline.py's build_dem_vrt()/materialize_geotiff() docstrings for what
each step does. Split out from 07-fetch-dem.py so retuning a provider's to_4326_vrt() (e.g.
bavaria_dgm.py's -srcnodata fix) or the materialize step is a rerun of this script alone - no
network access, no re-running Bavaria's coverage-grid WMS tile-existence check, nothing but local
files already on disk.

Usage: python pipeline/07b-build-dem-vrt.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.pipeline import DEM_DIR, build_dem_vrt, materialize_geotiff  # noqa: E402
from lib.timing import phase  # noqa: E402

SCRIPT_NAME = "07b-build-dem-vrt.py"

manifest_path = DEM_DIR / "fetch_manifest.json"
if not manifest_path.exists():
    raise SystemExit(f"{manifest_path} not found - run 07-fetch-dem.py first")

with open(manifest_path, encoding="utf-8") as f:
    manifest = json.load(f)

n_tiles = sum(len(r["tile_paths"]) for r in manifest)
print(f"building dem.vrt from {n_tiles} tiles across {len(manifest)} region(s) ...")
vrt_path = build_dem_vrt(manifest, DEM_DIR)
print(f"written {vrt_path}")

tif_path = DEM_DIR / "dem.tif"
print(f"materializing {vrt_path} -> {tif_path} ...")
with phase(SCRIPT_NAME, "materialize_geotiff"):
    materialize_geotiff(vrt_path, tif_path)
print(f"written {tif_path}")
