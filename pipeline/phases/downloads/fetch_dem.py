#!/usr/bin/env python3
"""
Downloads whatever raw DEM tiles the region(s) configured in pipeline.config.json need, then
writes data/raw/dem/fetch_manifest.json recording exactly what was fetched (provider name, raw tile
paths, and where each region's reprojected VRT will go) - see
pipeline/phases/downloads/dem_providers/base.py for the provider contract, and pipeline/README.md's DEM
section for why this is pluggable.

Deliberately does NOT reproject/merge/materialize - that's build_dem_vrt.py, split out so
retuning a provider's to_4326_vrt() (e.g. a NoData-handling fix) or retuning materialize_geotiff
never has to touch the network or re-run tile-existence checks (Bavaria's coverage-grid WMS query
in particular) against data that's already downloaded. Every provider's fetch() already skips
tiles that already exist on disk, but this split also skips the *tile-selection* network calls
entirely on a build-only rerun, not just the actual downloads.

The area each region must cover comes from data/build/hub-range/hub-range.geojson (the same polygon
filter_trails.py clips trails to), clipped to a region's `boundary` .poly where configured.

Usage: python pipeline/phases/downloads/fetch_dem.py
"""

import json
import sys
from pathlib import Path

from shapely.geometry import shape

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dem_providers.composite import fetch_regions  # noqa: E402
from lib.pipeline import HUB_RANGE_DIR, RAW_DEM_DIR, RAW_OSM_DIR, load_config  # noqa: E402
from lib.poly import parse_poly_file  # noqa: E402
from lib.timing import phase  # noqa: E402

SCRIPT_NAME = "fetch_dem.py"

config = load_config()

provider_config = config["dem"]["providerConfig"]

with open(HUB_RANGE_DIR / "hub-range.geojson", encoding="utf-8") as f:
    hub_range = shape(json.load(f))
boundaries = {r["name"]: parse_poly_file(RAW_OSM_DIR / f"{r['name']}.poly") for r in config["regions"]}

RAW_DEM_DIR.mkdir(parents=True, exist_ok=True)

with phase(SCRIPT_NAME, "fetch_dem") as meta:
    manifest = fetch_regions(provider_config, RAW_DEM_DIR, hub_range, boundaries)
    meta["n_regions"] = len(manifest)

manifest_path = RAW_DEM_DIR / "fetch_manifest.json"
with open(manifest_path, "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2)
n_tiles = sum(len(r["tile_paths"]) for r in manifest)
print(f"written {manifest_path} ({n_tiles} tiles across {len(manifest)} region(s))")
