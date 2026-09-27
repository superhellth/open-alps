import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from shapely.geometry import MultiPolygon, box  # noqa: E402

from downloads.dem_providers import bavaria_dgm  # noqa: E402


def test_tiles_for_utm_bounds_single_tile():
    # Bounds entirely inside one 1km cell -> just that cell's tile ID. 589_5256 is a real,
    # confirmed-live Bavaria DGM5 tile (curl -I: HTTP 200, ~200KB zip).
    result = bavaria_dgm.tiles_for_utm_bounds(589200, 5256200, 589800, 5256800)
    assert result == ["589_5256"]


def test_tiles_for_utm_bounds_spans_multiple_tiles():
    # Bounds spanning two easting cells at the same northing.
    result = bavaria_dgm.tiles_for_utm_bounds(589000, 5256000, 590500, 5256000)
    assert result == ["589_5256", "590_5256"]


def test_tiles_for_utm_bounds_spans_grid():
    # Bounds spanning 2 easting x 2 northing cells -> 4 tiles, northing-then-easting order.
    result = bavaria_dgm.tiles_for_utm_bounds(589500, 5256500, 590500, 5257500)
    assert result == ["589_5256", "590_5256", "589_5257", "590_5257"]


def test_tiles_for_area_only_returns_tiles_touching_the_polygon():
    # Square ~10.50-10.55E, 47.55-47.58N (alpine south): its UTM32N bounds span easting cells
    # 612..616 x northing cells 5267..5270 (hand-verified via rasterio.warp.transform_bounds).
    area = box(10.50, 47.55, 10.55, 47.58)

    result = bavaria_dgm.tiles_for_area(area)

    assert "612_5267" in result and "616_5270" in result
    assert len(result) <= 20
    assert all(t.split("_")[0].isdigit() and t.split("_")[1].isdigit() for t in result)


def test_tiles_for_area_skips_empty_space_between_pieces():
    # Two small pieces ~100 km apart: a bounding rectangle would cover thousands of tiles.
    area = MultiPolygon([box(10.50, 47.55, 10.51, 47.56), box(10.50, 48.55, 10.51, 48.56)])

    result = bavaria_dgm.tiles_for_area(area)

    assert 0 < len(result) < 100


def test_tile_url_uses_bayernwolke_direct_tile_download():
    assert bavaria_dgm.tile_url("589_5256") == (
        "https://download1.bayernwolke.de/a/dgm/dgm5xyz/589_5256.zip"
    )
