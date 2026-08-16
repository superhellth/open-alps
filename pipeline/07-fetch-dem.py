#!/usr/bin/env python3
"""
Fetches DEM tiles for the region(s) configured in pipeline.config.json, builds a single
EPSG:4326 GDAL VRT (data/dem/dem.vrt), then materializes it into a real GeoTIFF
(data/dem/dem.tif) that 08-add-elevation.py samples - see pipeline/dem_providers/base.py for
the provider contract, and pipeline/README.md's DEM section for why this is pluggable (Copernicus
GLO-30's global 30m coverage is the default; Austria/Bavaria have higher-resolution regional
alternatives with their own coverage limits).

Materializing (rather than having 08-add-elevation.py read dem.vrt directly) is what keeps step
08 cheap to rerun - see materialize_geotiff()'s docstring in lib/pipeline.py.

Usage: python pipeline/07-fetch-dem.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dem_providers import get_provider  # noqa: E402
from lib.pipeline import DEM_DIR, load_config, materialize_geotiff  # noqa: E402
from lib.timing import phase  # noqa: E402

SCRIPT_NAME = "07-fetch-dem.py"

config = load_config()
dem_config = config["dem"]
provider_name = dem_config.get("provider", "copernicus-glo-30")
provider = get_provider(provider_name)

provider_config = dict(dem_config.get("providerConfig", {}))
provider_config.setdefault("bbox", config["bbox"])

raw_dir = DEM_DIR / "raw"
vrt_path = DEM_DIR / "dem.vrt"

if provider_name == "composite":
    from dem_providers.composite import fetch_and_build  # noqa: E402
    vrt_path = fetch_and_build(provider_config, DEM_DIR)
    print(f"written {vrt_path}")
else:
    print(f"fetching DEM tiles via provider {provider_name!r} ...")
    tile_paths = provider.fetch(provider_config, raw_dir)
    print(f"{len(tile_paths)} tiles present, building EPSG:4326 VRT ...")
    provider.to_4326_vrt(tile_paths, vrt_path)
    print(f"written {vrt_path}")

tif_path = DEM_DIR / "dem.tif"
print(f"materializing {vrt_path} -> {tif_path} ...")
with phase(SCRIPT_NAME, "materialize_geotiff"):
    materialize_geotiff(vrt_path, tif_path)
print(f"written {tif_path}")
