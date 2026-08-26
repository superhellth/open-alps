#!/usr/bin/env python3
"""
Downloads whatever raw DEM tiles the region(s) configured in pipeline.config.json need, then
writes data/dem/fetch_manifest.json recording exactly what was fetched (provider name, raw tile
paths, and where each region's reprojected VRT will go) - see
pipeline/phases/downloads/dem_providers/base.py for the provider contract, and pipeline/README.md's DEM
section for why this is pluggable.

Deliberately does NOT reproject/merge/materialize - that's build_dem_vrt.py, split out so
retuning a provider's to_4326_vrt() (e.g. a NoData-handling fix) or retuning materialize_geotiff
never has to touch the network or re-run tile-existence checks (Bavaria's coverage-grid WMS query
in particular) against data that's already downloaded. Every provider's fetch() already skips
tiles that already exist on disk, but this split also skips the *tile-selection* network calls
entirely on a build-only rerun, not just the actual downloads.

Usage: python pipeline/phases/downloads/fetch_dem.py
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dem_providers.composite import fetch_regions  # noqa: E402
from lib.pipeline import DEM_DIR, load_config  # noqa: E402

config = load_config()

parser = argparse.ArgumentParser()
parser.add_argument("--max-edge-km", type=float, default=config["graph"]["maxEdgeKm"])
args = parser.parse_args()

provider_config = dict(config["dem"]["providerConfig"])
provider_config.setdefault("bbox", config["bbox"])

DEM_DIR.mkdir(parents=True, exist_ok=True)

manifest = fetch_regions(provider_config, DEM_DIR, max_edge_km=args.max_edge_km)

manifest_path = DEM_DIR / "fetch_manifest.json"
with open(manifest_path, "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2)
n_tiles = sum(len(r["tile_paths"]) for r in manifest)
print(f"written {manifest_path} ({n_tiles} tiles across {len(manifest)} region(s))")
