"""Copernicus GLO-30 DEM provider (AWS Open Data, no auth) - 30m global coverage, one tile per
whole degree of lat/lon. Already EPSG:4326, so to_4326_vrt is a plain gdalbuildvrt, no reprojection.
See pipeline/README.md's DEM section for why a higher-resolution regional provider (at_bev, bavaria_dgm)
might be preferred where available - this one's the default because it has global coverage and
needs no per-region tile-index lookup."""

import math
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = "https://copernicus-dem-30m.s3.amazonaws.com"


def tile_name(lat: int, lon: int) -> str:
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return f"Copernicus_DSM_COG_10_{ns}{abs(lat):02d}_00_{ew}{abs(lon):03d}_00_DEM"


def fetch(provider_config: dict, raw_dir: Path) -> list[Path]:
    bbox = provider_config["bbox"]
    raw_dir.mkdir(parents=True, exist_ok=True)

    lat_range = range(math.floor(bbox["minLat"]), math.floor(bbox["maxLat"]) + 1)
    lon_range = range(math.floor(bbox["minLng"]), math.floor(bbox["maxLng"]) + 1)

    names = [(lat, lon) for lat in lat_range for lon in lon_range]
    tile_paths = []
    for i, (lat, lon) in enumerate(names):
        name = tile_name(lat, lon)
        url = f"{BASE_URL}/{name}/{name}.tif"
        out_path = raw_dir / f"{name}.tif"
        if not out_path.exists():
            try:
                urllib.request.urlretrieve(url, out_path)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    continue
                raise
        tile_paths.append(out_path)
        if (i + 1) % 500 == 0:
            print(f"  {i + 1}/{len(names)} tiles checked, {len(tile_paths)} with coverage")
    print(f"{len(tile_paths)}/{len(names)} tiles had coverage")
    return tile_paths


def to_4326_vrt(tile_paths: list[Path], out_vrt_path: Path) -> Path:
    subprocess.run(
        ["gdalbuildvrt", "-overwrite", str(out_vrt_path), *[str(p) for p in tile_paths]],
        check=True,
    )
    return out_vrt_path
