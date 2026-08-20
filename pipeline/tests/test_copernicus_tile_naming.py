import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from downloads.dem_providers import copernicus  # noqa: E402


def test_tile_name_positive_lat_lon():
    assert copernicus.tile_name(47, 12) == "Copernicus_DSM_COG_10_N47_00_E012_00_DEM"


def test_tile_name_negative_lat_lon():
    assert copernicus.tile_name(-5, -3) == "Copernicus_DSM_COG_10_S05_00_W003_00_DEM"
