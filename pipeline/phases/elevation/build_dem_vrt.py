#!/usr/bin/env python3
"""
Reprojects/merges the DEM tiles data/dem/fetch_manifest.json (fetch_dem.py's output) points at
into data/dem/dem.vrt, then materializes that into data/dem/dem.tif for add_elevation.py to
sample - see pipeline/lib/dem.py's build_dem_vrt()/materialize_geotiff() docstrings for what
each step does. Split out from fetch_dem.py so retuning a provider's to_4326_vrt() (e.g.
bavaria_dgm.py's -srcnodata fix) or the materialize step is a rerun of this script alone - no
network access, no re-running Bavaria's coverage-grid WMS tile-existence check, nothing but local
files already on disk.

Usage: python pipeline/phases/elevation/build_dem_vrt.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.dem import build_dem_vrt, materialize_geotiff  # noqa: E402
from lib.pipeline import DEM_DIR  # noqa: E402
from lib.timing import phase  # noqa: E402

SCRIPT_NAME = "build_dem_vrt.py"

manifest_path = DEM_DIR / "fetch_manifest.json"
if not manifest_path.exists():
    raise SystemExit(f"{manifest_path} not found - run fetch_dem.py first")

with open(manifest_path, encoding="utf-8") as f:
    manifest = json.load(f)

n_tiles = sum(len(r["tile_paths"]) for r in manifest)
print(f"building dem.vrt from {n_tiles} tiles across {len(manifest)} region(s) ...")
with phase(SCRIPT_NAME, "materialize_regions", n_regions=len(manifest)):
    vrt_path = build_dem_vrt(manifest, DEM_DIR)
print(f"written {vrt_path}")

# Cheap by this point: build_dem_vrt() already materialized every region to real pixels, so this
# is just a mosaic compress+copy, not a reprojection - see materialize_geotiff()'s docstring.
tif_path = DEM_DIR / "dem.tif"
print(f"materializing {vrt_path} -> {tif_path} ...")
with phase(SCRIPT_NAME, "materialize_geotiff"):
    materialize_geotiff(vrt_path, tif_path)
print(f"written {tif_path}")
