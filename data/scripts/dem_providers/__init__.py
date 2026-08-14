"""Registry mapping a dem.provider config name to its provider module. See base.py for what every
provider module must implement."""

from . import copernicus

_REGISTRY = {
    "copernicus-glo-30": copernicus,
}

PROVIDER_NAMES = list(_REGISTRY)


def get_provider(name: str):
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"unknown DEM provider {name!r} - valid providers: {PROVIDER_NAMES}"
        ) from None
