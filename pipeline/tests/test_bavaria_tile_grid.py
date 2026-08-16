import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dem_providers import bavaria_dgm  # noqa: E402


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


def test_tiles_for_bbox_transforms_and_covers_expected_grid():
    # A small real bbox in Bavaria's alpine south (~10.50-10.55E, 47.55-47.58N). Expected UTM32N
    # bounds hand-verified via rasterio.warp.transform_bounds:
    # (612797.28, 5267376.77, 616623.69, 5270784.69) -> easting cells 612..616, northing
    # cells 5267..5270 -> 5 x 4 = 20 tiles.
    bbox = {"minLng": 10.50, "maxLng": 10.55, "minLat": 47.55, "maxLat": 47.58}

    result = bavaria_dgm.tiles_for_bbox(bbox)

    assert len(result) == 20
    assert "612_5267" in result
    assert "616_5270" in result
    assert all(
        tile_id.split("_")[0].isdigit() and tile_id.split("_")[1].isdigit()
        for tile_id in result
    )


def test_tile_url_uses_bayernwolke_direct_tile_download():
    assert bavaria_dgm.tile_url("589_5256") == (
        "https://download1.bayernwolke.de/a/dgm/dgm5xyz/589_5256.zip"
    )
