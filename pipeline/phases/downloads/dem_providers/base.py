"""The contract every DEM provider module must implement. Not an abstract base class - providers
are plain modules (functions, not classes), matching this pipeline's existing style (see
scripts/lib/pipeline.py). This Protocol exists purely so `get_provider()`'s return type is
documented and IDEs/type-checkers can verify a new provider module actually implements it; nothing
here is instantiated.

Every provider's `to_4326_vrt` must return a VRT in EPSG:4326 - that's the one hard requirement
that lets add_elevation.py stay provider-agnostic, since it samples DEM pixels directly at
hut/trail lon/lat coordinates with no reprojection step of its own.
"""

from pathlib import Path
from typing import Protocol


class DemProvider(Protocol):
    def fetch(self, provider_config: dict, raw_dir: Path) -> list[Path]:
        """Downloads whatever raw tiles/files this source needs for provider_config's region
        (bbox, or a named region key - each provider defines its own provider_config shape) into
        raw_dir, skipping any that already exist there. Returns the paths it downloaded or found
        already present, in no particular order."""
        ...

    def to_4326_vrt(self, tile_paths: list[Path], out_vrt_path: Path) -> Path:
        """Builds a single GDAL VRT at out_vrt_path covering all of tile_paths, reprojected to
        EPSG:4326 if the source's native CRS differs. Returns out_vrt_path."""
        ...
