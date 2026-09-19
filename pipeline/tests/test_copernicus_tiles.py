import sys
from pathlib import Path

from shapely.geometry import MultiPolygon, Polygon, box

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from downloads.dem_providers import copernicus  # noqa: E402


def test_tiles_for_area_returns_only_intersecting_tiles():
    # Polygon with a hole spanning tiles (47,10)..(48,11); the hole must not drop the tile it
    # lies in because the ring around it still intersects.
    outer = [(10.1, 47.1), (11.9, 47.1), (11.9, 48.9), (10.1, 48.9)]
    hole = [(10.5, 47.5), (10.6, 47.5), (10.6, 47.6), (10.5, 47.6)]
    island = box(15.2, 46.2, 15.3, 46.3)
    area = MultiPolygon([Polygon(outer, [hole]), island])

    tiles = copernicus.tiles_for_area(area)

    assert set(tiles) == (
        {(lat, lon) for lat in (47, 48) for lon in (10, 11)} | {(46, 15)}
    )


def test_tiles_for_area_includes_touching_tile():
    # Polygon edge exactly on a tile boundary still covers the tile on the far side.
    tiles = copernicus.tiles_for_area(box(10.0, 47.0, 11.0, 48.0))

    assert (47, 10) in tiles and (47, 11) in tiles and (48, 10) in tiles
