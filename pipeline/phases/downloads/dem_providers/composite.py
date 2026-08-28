"""Meta-provider that fetches per-sub-region tiles from different providers, e.g. Austria via
at-bev-dgm + Bavaria via bavaria-dgm5. Doesn't fit the plain fetch()/to_4326_vrt() split every
other provider uses (it needs to resolve each region's own bbox/points and run its own fetch()),
so fetch_dem.py calls fetch_regions() below directly for provider == "composite" instead of the
usual single fetch() call - see that script and build_dem_vrt.py (which does the actual
reprojection/merge, via lib.dem.build_dem_vrt(), from fetch_regions()'s manifest) for why
fetch and build are split into separate scripts.

gdalbuildvrt takes the LAST-listed source for overlapping pixels (not the first - easy to get
backwards), so region order in providerConfig.regions is meaningful where two regions' bboxes
overlap - list the higher-resolution/higher-priority source last. This only matters where two
regions both have *real* data at a pixel; a region's own genuine NoData (see bavaria_dgm.py's
VRT_NODATA) is treated as transparent by gdalbuildvrt's default nodata handling, so a gap in the
last-listed source still lets an earlier source's real data show through - see
lib.dem.normalize_colorinterp() for why each region VRT needs a rewrite before that merge."""

import sys
from pathlib import Path

from . import get_provider

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from lib.geo import HUB_RANGE_SAFETY_MARGIN, hut_points  # noqa: E402
from lib.pipeline import OSM_DIR  # noqa: E402


def _points_for_region(filter_bbox: dict) -> list[list[float]]:
    """Hut points to buffer bavaria-dgm5's per-hut tile selection around. Used to prefer real
    trail-polyline vertices (a V1-era hut-edges.geojson) when that file existed, so a trail's
    mid-edge wander was covered without over-sizing bufferKm - that file is no longer produced by
    any task in the current DAG (see git history), so this is hut points only now."""
    return hut_points(OSM_DIR / "huts.geojson", filter_bbox=filter_bbox)


def fetch_regions(provider_config: dict, dem_dir: Path, max_edge_km: float) -> list[dict]:
    """Resolves each configured region's bbox/points and downloads its raw tiles, returning a
    JSON-serializable manifest ([{"provider", "raw_dir", "region_vrt", "tile_paths"}, ...]) -
    lib.dem.build_dem_vrt() consumes this to do the actual reprojection/merge, with no
    network access of its own. max_edge_km (graph.maxEdgeKm) sizes any bboxFromHuts region's
    per-hut buffer - see HUB_RANGE_SAFETY_MARGIN's docstring for why this must be the same value
    compute_hub_range.py uses for filter_trails.py's clip, not an independently-set number. See
    module docstring for why fetch and build are separate scripts."""
    manifest = []
    for i, region_config in enumerate(provider_config["regions"]):
        if region_config.get("bboxFromHuts"):
            # "bbox" stays as-is once bboxFromHuts sets "points" - bavaria_dgm.fetch() (the only
            # provider using bboxFromHuts) always prefers points over bbox when both are present,
            # so a resolved/tightened bbox here would just be computed and discarded. A previous
            # `_resolve_region_bbox()` did that dead work anyway (removed 2026-08-22, found while
            # debugging sample_base_elevation's DEM-coverage gap - see
            # docs/superpowers/specs/2026-08-22-hub-range-dem-coverage.md open question 5).
            region_config = {
                **region_config,
                "points": _points_for_region(region_config["bbox"]),
                "bufferKm": max_edge_km * HUB_RANGE_SAFETY_MARGIN,
            }
        provider = get_provider(region_config["provider"])
        raw_dir = dem_dir / "raw" / f"region_{i}_{region_config['provider']}"
        region_vrt = dem_dir / f"region_{i}_{region_config['provider']}.vrt"

        print(f"composite region {i}: {region_config['provider']} ...")
        tile_paths = provider.fetch(region_config, raw_dir)
        # Relative to dem_dir, not absolute: an absolute path baked in here goes stale the moment
        # the pipeline runs on a different machine/OS (e.g. a native-Windows -> WSL migration -
        # see pipeline/lib/pipeline.py's DATA_DIR docstring for the same class of problem in
        # doit's own path keys). build_dem_vrt() resolves these back against its own dem_dir.
        manifest.append({
            "provider": region_config["provider"],
            "raw_dir": str(raw_dir.relative_to(dem_dir)),
            "region_vrt": str(region_vrt.relative_to(dem_dir)),
            "tile_paths": [str(p.relative_to(dem_dir)) for p in tile_paths],
        })
    return manifest
