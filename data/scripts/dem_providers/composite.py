"""Meta-provider that stitches per-sub-region VRTs from different providers into one final
dem.vrt, e.g. Austria via at-bev-dgm + Bavaria via bavaria-dgm5. Doesn't fit the plain
fetch()/to_4326_vrt() split every other provider uses (it needs to run each region's *entire*
fetch+reproject pipeline, not just download raw tiles) - see fetch_and_build below, which
07-fetch-dem.py calls directly for provider == "composite" instead of the usual two-step
sequence.

gdalbuildvrt takes the LAST-listed source for overlapping pixels (not the first - easy to get
backwards), so region order in providerConfig.regions is meaningful where two regions' bboxes
overlap - list the higher-resolution/higher-priority source last. This only matters where two
regions both have *real* data at a pixel; a region's own genuine NoData (see bavaria_dgm.py's
VRT_NODATA) is treated as transparent by gdalbuildvrt's default nodata handling, so a gap in the
last-listed source still lets an earlier source's real data show through.

Regions built from different sources can end up with different band color interpretation (e.g.
a GeoTIFF-derived VRT comes out ColorInterp=Gray, while a VRT built by warping an ungeoreferenced
ASCII XYZ grid - as bavaria_dgm.py does - comes out ColorInterp=Undefined). gdalbuildvrt does not
error on that mismatch; it silently *drops* whichever source(s) disagree with the first one from
the merged VRT, so a naive final gdalbuildvrt call can produce a dem.vrt that looks fine but is
missing an entire region. _normalize_colorinterp() below rewrites each region VRT with an explicit
Gray band before the final merge so this can't happen."""

import subprocess
import sys
from pathlib import Path

import rasterio

from . import get_provider

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.pipeline import OSM_DIR, bbox_from_huts, edge_points, hut_points  # noqa: E402


def _points_for_region(filter_bbox: dict) -> list[list[float]]:
    """Prefers real trail-polyline vertices (hut-edges.geojson, script 06's output) over bare hut
    points - run_all.py always runs step 6 before step 7, so this is normally on disk. Falls back
    to hut points for standalone/manual runs of this provider before step 6 has ever produced
    hut-edges.geojson (e.g. `run_all.py --only 7`)."""
    edges_path = OSM_DIR / "hut-edges.geojson"
    if edges_path.exists():
        return edge_points(edges_path, filter_bbox=filter_bbox)
    return hut_points(OSM_DIR / "huts.geojson", filter_bbox=filter_bbox)


def _normalize_colorinterp(region_vrt: Path) -> Path:
    """Rewrites region_vrt as a thin VRT with ColorInterp explicitly forced to Gray, so the final
    gdalbuildvrt merge (see module docstring) doesn't silently drop it. A no-op passthrough when
    region_vrt doesn't exist on disk (e.g. under test doubles that don't perform real I/O).

    gdal_translate carries over the source's NoDataValue by default, but that default has proven
    fragile across GDAL builds - passed through explicitly here (rather than trusted implicitly)
    so a region's real NoData (e.g. bavaria_dgm.py's VRT_NODATA marking its tile gaps) can never
    silently turn into an opaque value in the merge gdalbuildvrt does downstream."""
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


def _resolve_region_bbox(region_config: dict) -> dict:
    """A region's configured "bbox" is the coarse political-boundary box used only to pick out
    which huts belong to this region (huts.geojson covers the whole pipeline scope, both
    countries) - not necessarily the box actually fetched. When "bboxFromHuts" is set, the real
    fetch bbox is tightened to just those huts' extent (+ bufferDeg padding), so a
    tile-per-request provider like bavaria_dgm.py doesn't pay for empty terrain the pipeline's
    huts never cover. Providers whose fetch() ignores bbox entirely (e.g. at_bev.py, a single
    national download) are unaffected either way."""
    if not region_config.get("bboxFromHuts"):
        return region_config["bbox"]
    return bbox_from_huts(
        OSM_DIR / "huts.geojson",
        filter_bbox=region_config["bbox"],
        buffer_deg=region_config.get("bufferDeg", 0.05),
    )


def fetch_and_build(provider_config: dict, dem_dir: Path) -> Path:
    region_vrts = []
    for i, region_config in enumerate(provider_config["regions"]):
        if region_config.get("bboxFromHuts"):
            region_config = {**region_config, "points": _points_for_region(region_config["bbox"])}
        if "bbox" in region_config:
            region_config = {**region_config, "bbox": _resolve_region_bbox(region_config)}
        provider = get_provider(region_config["provider"])
        raw_dir = dem_dir / "raw" / f"region_{i}_{region_config['provider']}"
        region_vrt = dem_dir / f"region_{i}_{region_config['provider']}.vrt"

        print(f"composite region {i}: {region_config['provider']} ...")
        tile_paths = provider.fetch(region_config, raw_dir)
        provider.to_4326_vrt(tile_paths, region_vrt)
        region_vrts.append(_normalize_colorinterp(region_vrt))

    out_vrt_path = dem_dir / "dem.vrt"
    subprocess.run(
        ["gdalbuildvrt", "-overwrite", str(out_vrt_path), *[str(v) for v in region_vrts]],
        check=True,
    )
    return out_vrt_path
