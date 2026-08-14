"""Meta-provider that stitches per-sub-region VRTs from different providers into one final
dem.vrt, e.g. Austria via at-bev-dgm + Bavaria via bavaria-dgm5. Doesn't fit the plain
fetch()/to_4326_vrt() split every other provider uses (it needs to run each region's *entire*
fetch+reproject pipeline, not just download raw tiles) - see fetch_and_build below, which
07-fetch-dem.py calls directly for provider == "composite" instead of the usual two-step
sequence.

gdalbuildvrt takes the first-listed source for overlapping pixels, so region order in
providerConfig.regions is meaningful where two regions' bboxes overlap - list the
higher-resolution/higher-priority source first.

Regions built from different sources can end up with different band color interpretation (e.g.
a GeoTIFF-derived VRT comes out ColorInterp=Gray, while a VRT built by warping an ungeoreferenced
ASCII XYZ grid - as bavaria_dgm.py does - comes out ColorInterp=Undefined). gdalbuildvrt does not
error on that mismatch; it silently *drops* whichever source(s) disagree with the first one from
the merged VRT, so a naive final gdalbuildvrt call can produce a dem.vrt that looks fine but is
missing an entire region. _normalize_colorinterp() below rewrites each region VRT with an explicit
Gray band before the final merge so this can't happen."""

import subprocess
from pathlib import Path

from . import get_provider


def _normalize_colorinterp(region_vrt: Path) -> Path:
    """Rewrites region_vrt as a thin VRT with ColorInterp explicitly forced to Gray, so the final
    gdalbuildvrt merge (see module docstring) doesn't silently drop it. A no-op passthrough when
    region_vrt doesn't exist on disk (e.g. under test doubles that don't perform real I/O)."""
    if not region_vrt.exists():
        return region_vrt
    normalized = region_vrt.with_name(region_vrt.stem + "_normalized.vrt")
    subprocess.run(
        ["gdal_translate", "-of", "VRT", "-colorinterp", "gray",
         str(region_vrt), str(normalized)],
        check=True,
    )
    return normalized


def fetch_and_build(provider_config: dict, dem_dir: Path) -> Path:
    region_vrts = []
    for i, region_config in enumerate(provider_config["regions"]):
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
