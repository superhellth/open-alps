"""Meta-provider that fetches per-sub-region tiles from different providers, e.g. Austria via
at-bev-dgm + Bavaria via bavaria-dgm5. Doesn't fit the plain fetch()/to_4326_vrt() split every
other provider uses (it needs to resolve each region's own area and run its own fetch()),
so fetch_dem.py calls fetch_regions() below directly for provider == "composite" instead of the
usual single fetch() call - see that script and build_dem_vrt.py (which does the actual
reprojection/merge, via lib.dem.build_dem_vrt(), from fetch_regions()'s manifest) for why
fetch and build are split into separate scripts.

gdalbuildvrt takes the LAST-listed source for overlapping pixels (not the first - easy to get
backwards), so region order in providerConfig.regions is meaningful where two regions' areas
overlap - list the higher-resolution/higher-priority source last. This only matters where two
regions both have *real* data at a pixel; a region's own genuine NoData (see bavaria_dgm.py's
VRT_NODATA) is treated as transparent by gdalbuildvrt's default nodata handling, so a gap in the
last-listed source still lets an earlier source's real data show through - see
lib.dem.normalize_colorinterp() for why each region VRT needs a rewrite before that merge."""

from pathlib import Path

from . import get_provider


def region_area(region_config: dict, hub_range, boundaries: dict):
    """The (Multi)Polygon a region must cover: the hub range, clipped to the named boundary
    polygon if the region config has a "boundary" (a name from config["regions"]). Raises if the
    result is empty, so a region never silently fetches nothing."""
    boundary_name = region_config.get("boundary")
    area = hub_range if boundary_name is None else hub_range.intersection(boundaries[boundary_name])
    if area.is_empty:
        raise ValueError(
            f"{region_config['provider']}: hub range does not intersect boundary {boundary_name!r}"
        )
    return area


def fetch_regions(provider_config: dict, dem_dir: Path, hub_range, boundaries: dict) -> list[dict]:
    """Resolves each configured region's area (region_area()) and downloads its raw tiles,
    returning a JSON-serializable manifest ([{"provider", "raw_dir", "region_vrt", "tile_paths"},
    ...]) - lib.dem.build_dem_vrt() consumes this to do the actual reprojection/merge, with no
    network access of its own. hub_range is the (Multi)Polygon filter_trails.py clips trails to, so
    DEM coverage of every base-graph node holds by construction. See module docstring for why
    fetch and build are separate scripts."""
    manifest = []
    for i, region_config in enumerate(provider_config["regions"]):
        region_config = {**region_config, "area": region_area(region_config, hub_range, boundaries)}
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
