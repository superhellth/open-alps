"""DEM VRT reprojection/materialization: turns a fetch_dem.py/composite.py manifest of raw,
possibly-lazily-reprojecting region tiles into a real, tiled/compressed dem.tif build_dem_vrt.py
can hand to sample_base_elevation.py."""

import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def materialize_geotiff(vrt_path: Path, out_path: Path) -> Path:
    """Bakes a (possibly lazily-reprojecting) VRT into a real, tiled/compressed GeoTIFF.

    Called twice per build_dem_vrt.py run, at two different costs: once per region inside
    build_dem_vrt() (in parallel, one call per provider - see that function's docstring for why),
    where it pays whichever region's own warp cost; and once more at the end of build_dem_vrt.py
    on the merged dem.vrt, which by then is just a mosaic of already-real region GeoTIFFs (no warp
    left to do, so that final call is cheap regardless of how many regions there are).

    The underlying cost this exists to avoid: reading a lazily-reprojecting VRT (as the old
    add_elevation.py used to do directly against dem.vrt) re-runs that reprojection math for every
    pixel touched, on every read. Almost all CPU, not I/O, since the underlying GeoTIFF/XYZ tiles
    are already local.

    -a_nodata copies NoDataValue from vrt_path explicitly (see composite.py's
    _normalize_colorinterp for why this isn't left to gdal_translate's implicit passthrough).
    PREDICTOR=3 is the floating-point predictor, which improves DEFLATE's ratio on elevation
    data specifically (vs. the integer predictor default)."""
    import rasterio

    with rasterio.open(vrt_path) as src:
        nodata = src.nodata

    args = [
        "gdal_translate", "-of", "GTiff",
        "-co", "TILED=YES", "-co", "COMPRESS=DEFLATE", "-co", "PREDICTOR=3",
        "-co", "BIGTIFF=IF_SAFER", "-co", "NUM_THREADS=ALL_CPUS",
        "--config", "GDAL_NUM_THREADS", "ALL_CPUS",
    ]
    if nodata is not None:
        args += ["-a_nodata", str(nodata)]
    args += [str(vrt_path), str(out_path)]
    print(f"materializing {vrt_path} -> {out_path} ...", flush=True)
    subprocess.run(args, check=True)
    return out_path


def normalize_colorinterp(region_vrt: Path) -> Path:
    """Rewrites region_vrt as a thin VRT with ColorInterp explicitly forced to Gray, so the final
    gdalbuildvrt merge in build_dem_vrt() doesn't silently drop it. A no-op passthrough when
    region_vrt doesn't exist on disk (e.g. under test doubles that don't perform real I/O).

    Regions built from different DEM sources can end up with different band color interpretation
    (e.g. a GeoTIFF-derived VRT comes out ColorInterp=Gray, while a VRT built by warping an
    ungeoreferenced ASCII XYZ grid - as bavaria_dgm.py does - comes out ColorInterp=Undefined).
    gdalbuildvrt does not error on that mismatch; it silently *drops* whichever source(s) disagree
    with the first one from the merged VRT, so a naive final gdalbuildvrt call can produce a
    dem.vrt that looks fine but is missing an entire region. This rewrite is what prevents that.

    gdal_translate carries over the source's NoDataValue by default, but that default has proven
    fragile across GDAL builds - passed through explicitly here (rather than trusted implicitly)
    so a region's real NoData (e.g. bavaria_dgm.py's VRT_NODATA marking its tile gaps) can never
    silently turn into an opaque value in the merge gdalbuildvrt does downstream."""
    import rasterio

    if not region_vrt.exists():
        return region_vrt
    normalized = region_vrt.with_name(region_vrt.stem + "_normalized.vrt")
    translate_args = ["gdal_translate", "-of", "VRT", "-colorinterp", "gray"]
    with rasterio.open(region_vrt) as src:
        if src.nodata is not None:
            translate_args += ["-a_nodata", str(src.nodata)]
    translate_args += [str(region_vrt), str(normalized)]
    subprocess.run(translate_args, check=True)
    return normalized


def build_dem_vrt(manifest: list[dict], dem_dir: Path) -> Path:
    """Reprojects each manifest region's already-downloaded tiles and merges them into
    dem_dir/dem.vrt. manifest is a list of {"provider", "raw_dir", "region_vrt", "tile_paths"}
    dicts - produced by dem_providers.composite.fetch_regions() for provider == "composite", or
    written directly by fetch_dem.py's single-region branch otherwise. Touches only local
    files (no network), so it's safe - and fast - to rerun on its own after tweaking a provider's
    to_4326_vrt() (e.g. bavaria_dgm.py's -srcnodata fix) without re-fetching. See
    fetch_dem.py / build_dem_vrt.py for why fetching and building are split into separate
    scripts in the first place.

    Each region is materialized to a real GeoTIFF here, one at a time per region but all regions
    in parallel (ThreadPoolExecutor around subprocess.run - threads, not processes, since the
    actual parallel work happens in each child gdal_translate process; the GIL isn't held while a
    thread blocks on subprocess.run). This is what makes the regions' warp cost (bavaria/at-bev's
    CRS reprojection, the expensive part - see materialize_geotiff()'s docstring) run on multiple
    cores at once. Before this, dem.vrt merged the regions' still-lazy warped VRTs directly, so
    ALL of that warp math was deferred onto materialize_geotiff()'s single final gdal_translate
    call, on one core - measured at 8462s wall time for a 3-region AT+Bavaria+Copernicus run
    (data/timings.jsonl, 2026-08-23), pegging one core at ~99% the whole time despite
    NUM_THREADS=ALL_CPUS (that flag only threads the GTiff compression step, never gdal's
    warp/resample read path - confirmed live: 43s of CPU burned in a 45s window while dem.tif's
    byte size didn't move at all, i.e. genuine single-core compute, not I/O wait). Once every
    region is real pixels, this function's own final gdalbuildvrt merge is just mosaic bookkeeping
    (no resampling), and build_dem_vrt.py's later materialize_geotiff(dem.vrt, dem.tif) call
    becomes a cheap compress+copy instead of the multi-hour step."""
    # local import: dem_providers.composite imports lib.dem at module level, so importing
    # dem_providers back at this module's top level would be a circular import
    from downloads.dem_providers import get_provider

    region_vrts = []
    for entry in manifest:
        provider = get_provider(entry["provider"])
        tile_paths = [Path(p) for p in entry["tile_paths"]]
        region_vrt = Path(entry["region_vrt"])
        provider.to_4326_vrt(tile_paths, region_vrt)
        region_vrts.append(normalize_colorinterp(region_vrt))

    region_tifs = [v.with_suffix(".tif") for v in region_vrts]

    def _timed_materialize(args: tuple[Path, Path]) -> float:
        region_vrt, region_tif = args
        t0 = time.monotonic()
        materialize_geotiff(region_vrt, region_tif)
        return time.monotonic() - t0

    print(f"materializing {len(region_vrts)} region(s) in parallel ...", flush=True)
    with ThreadPoolExecutor(max_workers=len(region_vrts)) as pool:
        elapsed = list(pool.map(_timed_materialize, zip(region_vrts, region_tifs)))
    for entry, secs in zip(manifest, elapsed):
        print(f"  {entry['provider']}: materialized in {secs:.1f}s", flush=True)

    out_vrt_path = dem_dir / "dem.vrt"
    subprocess.run(
        ["gdalbuildvrt", "-overwrite", str(out_vrt_path), *[str(t) for t in region_tifs]],
        check=True,
    )
    return out_vrt_path
