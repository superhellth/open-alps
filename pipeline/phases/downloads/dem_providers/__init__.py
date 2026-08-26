"""Registry mapping a provider name (dem.providerConfig.regions[].provider) to its provider
module. See base.py for what every provider module must implement."""

from . import at_bev, bavaria_dgm, copernicus

_REGISTRY = {
    "copernicus-glo-30": copernicus,
    "at-bev-dgm": at_bev,
    "bavaria-dgm5": bavaria_dgm,
}

PROVIDER_NAMES = list(_REGISTRY)


def get_provider(name: str):
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"unknown DEM provider {name!r} - valid providers: {PROVIDER_NAMES}"
        ) from None


# Imported after get_provider() is defined, not alongside the other providers above: composite.py
# does `from . import get_provider` at module scope, which would be a circular import if composite
# were imported while this package's own __init__ was still assembling get_provider.
from . import composite  # noqa: E402

_REGISTRY["composite"] = composite
PROVIDER_NAMES = list(_REGISTRY)
