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

import shapely
from shapely.geometry import box

BASE_URL = "https://copernicus-dem-30m.s3.amazonaws.com"


def tile_name(lat: int, lon: int) -> str:
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return f"Copernicus_DSM_COG_10_{ns}{abs(lat):02d}_00_{ew}{abs(lon):03d}_00_DEM"


def tiles_for_area(area) -> list[tuple[int, int]]:
    """Every whole-degree (lat, lon) tile whose box intersects area (a shapely (Multi)Polygon in
    EPSG:4326), in ascending latitude-then-longitude order. Touching tiles count, so a node on the
    area's boundary is covered."""
    min_lng, min_lat, max_lng, max_lat = area.bounds
    candidates = [
        (lat, lon)
        for lat in range(math.floor(min_lat), math.floor(max_lat) + 1)
        for lon in range(math.floor(min_lng), math.floor(max_lng) + 1)
    ]
    shapely.prepare(area)
    boxes = [box(lon, lat, lon + 1, lat + 1) for lat, lon in candidates]
    hits = shapely.intersects(area, boxes)
    return [t for t, hit in zip(candidates, hits) if hit]


def fetch(provider_config: dict, raw_dir: Path) -> list[Path]:
    """provider_config["area"]: shapely (Multi)Polygon in EPSG:4326 the tiles must cover."""
    raw_dir.mkdir(parents=True, exist_ok=True)

    names = tiles_for_area(provider_config["area"])
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
