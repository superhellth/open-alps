#!/usr/bin/env python3
"""
Downloads Copernicus GLO-30 DEM tiles (30m global elevation, AWS Open Data, no auth) covering
the bbox in ../pipeline.config.json, then builds a single mosaic (data/dem/dem.vrt) over them
via gdalbuildvrt. The VRT is a small XML index, not a copy of the data - GDAL/rasterio reads the
underlying tiles lazily, so this step doesn't need to hold the whole mosaic in memory.

Tile naming/grid: Copernicus_DSM_COG_10_{N|S}{lat:02d}_00_{E|W}{lon:03d}_00_DEM, one tile per
whole degree of lat/lon, tile (lat, lon) covering [lat, lat+1) x [lon, lon+1). EPSG:4326, same
CRS as the hut/trail lon/lat already used throughout the pipeline - no reprojection needed.

Usage: python data/scripts/07-fetch-dem.py
Requires gdalbuildvrt on PATH (ships with the alpen-osm conda env's rasterio/GDAL install).
"""

import math
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.pipeline import DEM_DIR, load_config  # noqa: E402

bbox = load_config()["bbox"]
raw_dir = DEM_DIR / "raw"
raw_dir.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://copernicus-dem-30m.s3.amazonaws.com"


def tile_name(lat, lon):
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return f"Copernicus_DSM_COG_10_{ns}{abs(lat):02d}_00_{ew}{abs(lon):03d}_00_DEM"


lat_range = range(math.floor(bbox["minLat"]), math.floor(bbox["maxLat"]) + 1)
lon_range = range(math.floor(bbox["minLng"]), math.floor(bbox["maxLng"]) + 1)

tile_paths = []
missing = []
for lat in lat_range:
    for lon in lon_range:
        name = tile_name(lat, lon)
        url = f"{BASE_URL}/{name}/{name}.tif"
        out_path = raw_dir / f"{name}.tif"
        if not out_path.exists():
            missing.append((name, url, out_path))
        tile_paths.append(out_path)

print(f"{len(tile_paths)} tiles in bbox, {len(missing)} to download")
for name, url, out_path in missing:
    print(f"downloading {name} ...")
    try:
        urllib.request.urlretrieve(url, out_path)
    except urllib.error.HTTPError as e:
        # Copernicus GLO-30 has no ocean-only tiles for some grid cells (e.g. far from any
        # land); a 404 there is expected, not a failure - skip it rather than aborting the run.
        if e.code == 404:
            print(f"  no tile at {name} (likely no land coverage there), skipping")
        else:
            raise

present_tiles = [p for p in tile_paths if p.exists()]
print(f"{len(present_tiles)}/{len(tile_paths)} tiles present, building mosaic ...")

vrt_path = DEM_DIR / "dem.vrt"
subprocess.run(
    ["gdalbuildvrt", "-overwrite", str(vrt_path), *[str(p) for p in present_tiles]],
    check=True,
)
print(f"written {vrt_path}")
