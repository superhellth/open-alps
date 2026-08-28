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

Coverage index, so candidate tiles aren't discovered by 404-probing the download server: Bayern
publishes the DGM5 tile grid itself as a WMS layer ("dgm5xyz" on
geoservices.bayern.de/od/wms/grid/v1/opendatagrid, the same service BayernAtlas's own download
picker renders) - each 1km cell with data is drawn as a filled/outlined grid square, transparent
otherwise. Rendering that layer over our whole candidate extent in EPSG:25832 (one image, pixels
line up 1:1 with the km grid) and testing each candidate tile's pixel block for any non-transparent
pixel tells us definitively which tiles exist, in a small handful of large WMS requests instead of
one probe request per candidate tile - see existing_tile_ids() below. Confirmed by hand: a known-
covered tile (Zugspitze, 649_5253) comes back with alpha up to 255 in its block; a tile whose
window crosses the Austrian border (605_5222) comes back all-zero alpha, matching its real 404 from
the download server."""

import math
import os
import subprocess
import threading
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import rasterio
from rasterio.io import MemoryFile
from rasterio.warp import transform_bounds, transform

TILE_URL_TEMPLATE = "https://download1.bayernwolke.de/a/dgm/dgm5xyz/{tile_id}.zip"
DEFAULT_WORKERS = 16

GRID_WMS_URL = "https://geoservices.bayern.de/od/wms/grid/v1/opendatagrid"
GRID_LAYER = "dgm5xyz"
GRID_PX_PER_KM = 6  # matches the resolution hand-verified against known good/bad tiles above
GRID_MAX_PX = 2400  # WMS request image dimension cap - chunk bbox requests to stay under this


def tile_url(tile_id: str) -> str:
    return TILE_URL_TEMPLATE.format(tile_id=tile_id)


def _chunk_ranges(lo_km: int, hi_km: int, step_km: int) -> list[tuple[int, int]]:
    ranges = []
    km = lo_km
    while km < hi_km:
        ranges.append((km, min(km + step_km, hi_km)))
        km += step_km
    return ranges


def _fetch_grid_alpha(min_e_km: int, min_n_km: int, max_e_km: int, max_n_km: int):
    """One WMS GetMap call for the coverage-grid layer over [min_e_km,max_e_km) x
    [min_n_km,max_n_km) (whole km, EPSG:25832). Returns the alpha band as a numpy array, with
    row 0 = max_n_km (WMS image rows run top-to-bottom = north-to-south)."""
    width = (max_e_km - min_e_km) * GRID_PX_PER_KM
    height = (max_n_km - min_n_km) * GRID_PX_PER_KM
    params = {
        "SERVICE": "WMS", "REQUEST": "GetMap", "VERSION": "1.1.1",
        "LAYERS": GRID_LAYER, "STYLES": "", "FORMAT": "image/png", "TRANSPARENT": "TRUE",
        "SRS": "EPSG:25832", "WIDTH": width, "HEIGHT": height,
        "BBOX": f"{min_e_km * 1000},{min_n_km * 1000},{max_e_km * 1000},{max_n_km * 1000}",
    }
    url = f"{GRID_WMS_URL}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url) as resp:
        png_bytes = resp.read()
    with MemoryFile(png_bytes) as memfile, memfile.open() as ds:
        return ds.read(4)  # alpha band


def existing_tile_ids(tile_ids: list[str]) -> list[str]:
    """Filters tile_ids (as produced by tiles_for_bbox()/tiles_for_points()) down to the ones that
    actually have DGM5 coverage, using the coverage-grid WMS layer instead of probing the download
    server per tile (see module docstring). Candidates are grouped into WMS-request-sized chunks
    covering their full extent, so a candidate set spanning all of Bavaria costs a handful of large
    image requests rather than one HTTP request per tile."""
    if not tile_ids:
        return []

    parsed = [(t, int(t.split("_")[0]), int(t.split("_")[1])) for t in tile_ids]
    min_e = min(e for _, e, _ in parsed)
    max_e = max(e for _, e, _ in parsed) + 1
    min_n = min(n for _, _, n in parsed)
    max_n = max(n for _, _, n in parsed) + 1

    chunk_km = GRID_MAX_PX // GRID_PX_PER_KM
    e_chunks = _chunk_ranges(min_e, max_e, chunk_km)
    n_chunks = _chunk_ranges(min_n, max_n, chunk_km)

    existing = []
    for ce_lo, ce_hi in e_chunks:
        for cn_lo, cn_hi in n_chunks:
            in_chunk = [(t, e, n) for t, e, n in parsed if ce_lo <= e < ce_hi and cn_lo <= n < cn_hi]
            if not in_chunk:
                continue
            alpha = _fetch_grid_alpha(ce_lo, cn_lo, ce_hi, cn_hi)
            height = (cn_hi - cn_lo) * GRID_PX_PER_KM
            for t, e, n in in_chunk:
                x0 = (e - ce_lo) * GRID_PX_PER_KM
                x1 = x0 + GRID_PX_PER_KM
                # image rows run north-to-south, tile rows run south-to-north - flip
                y0 = height - (n + 1 - cn_lo) * GRID_PX_PER_KM
                y1 = y0 + GRID_PX_PER_KM
                if alpha[y0:y1, x0:x1].any():
                    existing.append(t)
    return existing


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


def tiles_for_points(points: list[list[float]], buffer_km: float = 1.0) -> list[str]:
    """points: list of [lng, lat] (EPSG:4326), e.g. huts. Returns the union of every 1km-tile ID
    touched by a buffer_km-radius square around each point, instead of one rectangle enclosing
    every point.

    A single enclosing bbox (tiles_for_bbox) is the wrong shape when points cluster tightly with a
    few far-flung outliers - e.g. Bavaria's Alpine-Verein huts are ~90% clustered at the southern
    alpine fringe, with a handful of non-alpine AV huts up near the Bavarian Forest 300km north.
    An enclosing rectangle over both would cover a huge swath of empty lowland with no huts or
    trails, ballooning the tile count by two orders of magnitude and burying real hits under a long
    run of 404s for terrain nobody needs. Per-point windows only fetch what's actually near a hut."""
    lngs = [p[0] for p in points]
    lats = [p[1] for p in points]
    xs, ys = transform("EPSG:4326", "EPSG:25832", lngs, lats)

    tile_ids = set()
    for x, y in zip(xs, ys):
        tile_ids.update(tiles_for_utm_bounds(
            x - buffer_km * 1000, y - buffer_km * 1000,
            x + buffer_km * 1000, y + buffer_km * 1000,
        ))
    return sorted(tile_ids, key=lambda t: (int(t.split("_")[1]), int(t.split("_")[0])))


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
        try:
            urllib.request.urlretrieve(tile_url(tile_id), zip_path)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise

    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extract_dir)

    grids = sorted(extract_dir.rglob("*.txt"))
    return grids[0] if grids else None


def fetch(provider_config: dict, raw_dir: Path) -> list[Path]:
    raw_dir.mkdir(parents=True, exist_ok=True)

    points = provider_config.get("points")
    if points:
        buffer_km = provider_config.get("bufferKm", 1.0)
        tile_ids = tiles_for_points(points, buffer_km)
        print(f"{len(tile_ids)} Bavaria DGM5 tiles cover {len(points)} points (+{buffer_km}km buffer)")
    else:
        tile_ids = tiles_for_bbox(provider_config["bbox"])
        print(f"{len(tile_ids)} Bavaria DGM5 tiles cover the configured bbox")

    tile_ids = existing_tile_ids(tile_ids)
    print(f"{len(tile_ids)} of those confirmed to exist via the coverage-grid WMS")

    workers = provider_config.get("downloadWorkers", DEFAULT_WORKERS)
    tile_paths = []
    checked = 0
    lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for tif in pool.map(lambda tid: _download_tile(tid, raw_dir), tile_ids):
            with lock:
                checked += 1
                if tif is not None:
                    tile_paths.append(tif)
                if checked % 500 == 0:
                    print(f"  {checked}/{len(tile_ids)} tiles downloaded, {len(tile_paths)} succeeded")
    if len(tile_paths) != len(tile_ids):
        print(f"warning: {len(tile_ids) - len(tile_paths)} tiles the coverage grid marked as "
              f"existing 404'd on the real download server anyway")
    return tile_paths


VRT_NODATA = -9999.0


def to_4326_vrt(tile_paths: list[Path], out_vrt_path: Path) -> Path:
    # Source is an ungeoreferenced ASCII XYZ grid, implicitly in EPSG:25832 (UTM 32N) - unlike
    # at_bev.py's GeoTIFF source, gdalwarp needs -s_srs since the XYZ driver can't read a CRS off
    # the file itself.
    #
    # Mosaic-then-warp, not warp-then-mosaic: each tile has real UTM32N easting/northing posts, so
    # it carries a valid geotransform without needing a CRS tag - gdalbuildvrt only needs
    # consistent extents/pixel size to mosaic, not SRS, so the raw (still-25832) tiles can be
    # merged into one mosaic VRT for free (no pixel data touched) before the one reprojection that
    # actually costs CPU. This used to be one gdalwarp subprocess per tile (tens of thousands for a
    # full-coverage run) - at ~11 tiles/sec even with a 12-way thread pool, that process-spawn
    # overhead alone dominated the runtime (data/timings.jsonl). A single gdalwarp over the merged
    # mosaic does the same reprojection work in 2 process spawns total instead of tens of
    # thousands. Since output here is -of VRT (a lazy warped VRT, not materialized pixels), the
    # actual resampling doesn't run at this call - it's deferred to whenever something reads real
    # pixels through it (materialize_geotiff() in lib/dem.py). -wo NUM_THREADS=ALL_CPUS is a
    # warp option, though, and GDAL persists warp options into the output VRT's XML - so it's not
    # wasted, it configures that later, deferred read to multithread the real resampling when it
    # finally happens (-multi, by contrast, only affects immediate chunked I/O at call time, which
    # doesn't exist for a VRT-output call - left out as dead weight).
    #
    # This also shrinks a correctness issue, not just speed: a UTM square doesn't stay
    # axis-aligned once reprojected to EPSG:4326 (it becomes a slightly rotated quadrilateral), but
    # gdalwarp's output is always an axis-aligned rectangle - the corner slivers outside that
    # rotated footprint get filled with 0 unless -dstnodata is set. Warping per-tile (the old
    # approach) hit this at *every one* of tens of thousands of tile boundaries, injecting fake
    # sea-level readings throughout the coverage (a trail edge sampling one showed up as a ~1500m
    # round-trip to/from 0m, wildly inflating ascent_m/descent_m). Warping the merged mosaic once
    # means only the *outer* boundary of the whole region has rotated corners - internal tile-to-
    # tile seams no longer exist to leak nodata at all.
    #
    # The XYZ grid has no NoData tag of its own (the ASCII driver can't carry one), but the
    # *values* aren't all real either: a downloaded tile's own void/no-coverage posts are written
    # right into the data as literal -9999.00 rows (checked a raw tile - 1335/1530 posts were
    # -9999.00). -srcnodata on the mosaic build is what turns those into recognized gaps instead of
    # elevation readings of about -9999m; without it gdalwarp used to nudge each one by a tiny
    # epsilon to *keep* it as data (its "Value -9999 ... has been changed" warning), feeding a wall
    # of fake sub-sea-level elevation into add_elevation.py's ascent/descent calc downstream.
    # Passed again on the warp step too rather than trusted to propagate implicitly through the
    # VRT's NoDataValue metadata (see materialize_geotiff()'s docstring on why this codebase
    # doesn't trust NoData passthrough across a GDAL step without saying so explicitly).
    #
    # Separate issue, also handled below: existing_tile_ids() only downloads tiles that actually
    # exist - 1km cells with no coverage (e.g. ones straddling the Austrian border, see module
    # docstring) are simply absent from tile_paths. The mosaic's overall extent still spans the
    # bounding rectangle of every tile, so those absent cells are gaps *inside* that rectangle.
    # -vrtnodata makes gdalbuildvrt fill those with VRT_NODATA instead of 0, so they read as proper
    # NoData throughout the rest of the pipeline rather than silently stomping valid data from
    # other sources composite.py merges this with.
    #
    # Mosaicking is NOT free the way it first looked: the XYZ ASCII format has no header, so
    # gdalbuildvrt must open and scan *every* tile's full row set just to learn its extent, before
    # it can even start mosaicking - benchmarked at ~123ms/tile. gdalbuildvrt itself has no
    # multithreading option, so a single gdalbuildvrt call over all tiles serializes that scan onto
    # one core (~76min projected for a full run - worse than the old all-per-tile-gdalwarp
    # approach, because that at least spread the same scan cost across a 12-way process pool).
    # Fix: chunk the tile list across workers, gdalbuildvrt each chunk in parallel (restores the
    # scan parallelism), then one more gdalbuildvrt to combine the N partial mosaics - still only
    # ~N+2 process spawns total (N chunk builds + 1 combine + 1 warp) instead of tens of thousands,
    # but the actual scanning work is spread across all cores again.
    warped_dir = out_vrt_path.parent / "bavaria_dgm_warped"
    warped_dir.mkdir(exist_ok=True)

    def build_chunk_mosaic(item: tuple[int, list[Path]]) -> Path:
        idx, chunk = item
        list_path = warped_dir / f"chunk_{idx:03d}_files.txt"
        list_path.write_text("\n".join(str(p) for p in chunk), encoding="utf-8")
        mosaic_path = warped_dir / f"chunk_{idx:03d}_25832.vrt"
        subprocess.run(
            ["gdalbuildvrt", "-overwrite", "-srcnodata", str(VRT_NODATA), "-vrtnodata", str(VRT_NODATA),
             "-input_file_list", str(list_path), str(mosaic_path)],
            check=True,
        )
        return mosaic_path

    workers = os.cpu_count() or 4
    chunk_size = math.ceil(len(tile_paths) / workers)
    chunks = list(enumerate(
        [tile_paths[i:i + chunk_size] for i in range(0, len(tile_paths), chunk_size)]
    ))
    print(f"mosaicking {len(tile_paths)} raw Bavaria DGM5 tiles (EPSG:25832) "
          f"across {len(chunks)} parallel chunks ...", flush=True)
    chunk_count = 0
    lock = threading.Lock()
    chunk_mosaics = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for mosaic_path in pool.map(build_chunk_mosaic, chunks):
            chunk_mosaics.append(mosaic_path)
            with lock:
                chunk_count += 1
                print(f"  chunk mosaic {chunk_count}/{len(chunks)} done", flush=True)

    combined_list_path = warped_dir / "chunk_mosaics.txt"
    combined_list_path.write_text("\n".join(str(p) for p in chunk_mosaics), encoding="utf-8")
    raw_mosaic_path = warped_dir / "raw_mosaic_25832.vrt"
    subprocess.run(
        ["gdalbuildvrt", "-overwrite", "-vrtnodata", str(VRT_NODATA),
         "-input_file_list", str(combined_list_path), str(raw_mosaic_path)],
        check=True,
    )

    print(f"reprojecting mosaic {raw_mosaic_path} -> {out_vrt_path} (EPSG:25832 -> EPSG:4326) ...",
          flush=True)
    subprocess.run(
        ["gdalwarp", "-s_srs", "EPSG:25832", "-t_srs", "EPSG:4326",
         "-srcnodata", str(VRT_NODATA), "-dstnodata", str(VRT_NODATA),
         "-wo", "NUM_THREADS=ALL_CPUS",
         "-of", "VRT", "-overwrite", str(raw_mosaic_path), str(out_vrt_path)],
        check=True,
    )
    return out_vrt_path
