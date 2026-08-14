"""Bavaria DGM5 (5m grid, Bayerische Vermessungsverwaltung, CC BY 4.0) via geodaten.bayern.de.

The brief this module was originally written from assumed a downloadable tile-index
(shapefile/geojson) mapping bbox -> tile IDs via geometric intersection, plus Metalink-based bulk
download. Hands-on research replaced that design:

- Bavaria's Metalink bulk download is organized per Regierungsbezirk (administrative district), not
  per-tile - each district's Metalink is ~14GB
  (https://geodaten.bayern.de/odd/a/dgm/dgm5xyz/meta/metalink/09.meta4, "09" = district code). Too
  large and the wrong granularity for a small alpine-trail bbox - not used here.
- There is instead a direct per-1km-tile download at
  https://download1.bayernwolke.de/a/dgm/dgm5xyz/{tile_id}.zip, confirmed live via `curl -I`
  (HTTP 200, application/zip, ~200KB for tile 589_5256.zip).
- The tile ID is `{easting_km}_{northing_km}`, a coordinate in EPSG:25832 (UTM32N) in whole
  kilometers - Germany's standard AdV 1km-grid tile-naming convention. That means tile IDs for any
  bbox can be computed directly with no tile-index file at all: transform the bbox corners from
  EPSG:4326 to EPSG:25832 and floor each corner to whole kilometers, then enumerate every tile
  whose [e, e+1) x [n, n+1) cell the transformed bbox touches.

5m rather than DGM1's 1m: already well past the resolution needed to resolve trail switchbacks
(see docs/osm-trail-pipeline.md), at a fraction of DGM1's storage/download volume.

providerConfig: {"bbox": {...}} (bbox falls back to the top-level pipeline.config.json bbox if
omitted, same as every other provider).
"""

import math
import subprocess
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from rasterio.warp import transform_bounds

TILE_URL_TEMPLATE = "https://download1.bayernwolke.de/a/dgm/dgm5xyz/{tile_id}.zip"


def tile_url(tile_id: str) -> str:
    return TILE_URL_TEMPLATE.format(tile_id=tile_id)


def tiles_for_utm_bounds(min_e: float, min_n: float, max_e: float, max_n: float) -> list[str]:
    """Pure grid computation: min_e/min_n/max_e/max_n are EPSG:25832 meters. Returns every
    1km-tile ID (as "{easting_km}_{northing_km}") whose cell the bounds touch, in ascending
    northing-then-easting order."""
    e_start = math.floor(min_e / 1000)
    e_end = math.floor(max_e / 1000)
    n_start = math.floor(min_n / 1000)
    n_end = math.floor(max_n / 1000)

    return [
        f"{e}_{n}"
        for n in range(n_start, n_end + 1)
        for e in range(e_start, e_end + 1)
    ]


def tiles_for_bbox(bbox: dict) -> list[str]:
    """bbox: {"minLng", "minLat", "maxLng", "maxLat"} in EPSG:4326. Transforms to EPSG:25832 and
    delegates to tiles_for_utm_bounds()."""
    min_e, min_n, max_e, max_n = transform_bounds(
        "EPSG:4326", "EPSG:25832",
        bbox["minLng"], bbox["minLat"], bbox["maxLng"], bbox["maxLat"],
    )
    return tiles_for_utm_bounds(min_e, min_n, max_e, max_n)


def _download_tile(tile_id: str, raw_dir: Path) -> Path | None:
    """Downloads and extracts one tile's zip, skipping work already done. Returns None (rather
    than raising) for a 404 - some 1km cells over water/borders/no-data areas simply don't exist,
    same tolerance as copernicus.py's per-tile 404 handling.

    Despite the "dgm5xyz" URL path and ".zip" extension suggesting a GeoTIFF, each tile's zip
    actually contains a single ungeoreferenced ASCII XYZ grid (one "easting northing elevation"
    row per 5m post, 200x200 = 40000 rows per 1km tile - confirmed by hand-inspecting a downloaded
    tile). GDAL's XYZ driver reads this directly (autodetected even with a .txt extension, no
    rename needed) but it carries no CRS of its own - to_4326_vrt() supplies -s_srs EPSG:25832
    when warping."""
    zip_path = raw_dir / f"{tile_id}.zip"
    extract_dir = raw_dir / tile_id

    if extract_dir.exists():
        grids = sorted(extract_dir.rglob("*.txt"))
        if grids:
            return grids[0]

    if not zip_path.exists():
        url = tile_url(tile_id)
        print(f"downloading {url} ...")
        try:
            urllib.request.urlretrieve(url, zip_path)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                print(f"  no tile at {tile_id} (likely no coverage there), skipping")
                return None
            raise

    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extract_dir)

    grids = sorted(extract_dir.rglob("*.txt"))
    return grids[0] if grids else None


def fetch(provider_config: dict, raw_dir: Path) -> list[Path]:
    raw_dir.mkdir(parents=True, exist_ok=True)

    tile_ids = tiles_for_bbox(provider_config["bbox"])
    print(f"{len(tile_ids)} Bavaria DGM5 tiles cover the configured bbox")

    tile_paths = []
    for tile_id in tile_ids:
        tif = _download_tile(tile_id, raw_dir)
        if tif is not None:
            tile_paths.append(tif)
    return tile_paths


def to_4326_vrt(tile_paths: list[Path], out_vrt_path: Path) -> Path:
    # Source is an ungeoreferenced ASCII XYZ grid, implicitly in EPSG:25832 (UTM 32N) - unlike
    # at_bev.py's GeoTIFF source, gdalwarp needs -s_srs since the XYZ driver can't read a CRS off
    # the file itself. Same warp-then-mosaic pattern otherwise.
    warped_dir = out_vrt_path.parent / "bavaria_dgm_warped"
    warped_dir.mkdir(exist_ok=True)
    warped_paths = []
    for tile in tile_paths:
        warped = warped_dir / f"{tile.stem}_4326.vrt"
        subprocess.run(
            ["gdalwarp", "-s_srs", "EPSG:25832", "-t_srs", "EPSG:4326", "-of", "VRT", "-overwrite",
             str(tile), str(warped)],
            check=True,
        )
        warped_paths.append(warped)

    subprocess.run(
        ["gdalbuildvrt", "-overwrite", str(out_vrt_path), *[str(p) for p in warped_paths]],
        check=True,
    )
    return out_vrt_path
