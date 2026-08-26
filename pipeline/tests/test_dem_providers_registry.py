import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from downloads.dem_providers import get_provider, PROVIDER_NAMES  # noqa: E402


def test_registry_lists_copernicus_by_default():
    assert "copernicus-glo-30" in PROVIDER_NAMES


def test_get_provider_returns_module_with_fetch_and_to_4326_vrt():
    provider = get_provider("copernicus-glo-30")
    assert hasattr(provider, "fetch")
    assert hasattr(provider, "to_4326_vrt")


def test_get_provider_unknown_name_raises_with_valid_names_listed():
    try:
        get_provider("not-a-real-provider")
        assert False, "expected KeyError"
    except KeyError as e:
        assert "copernicus-glo-30" in str(e)
