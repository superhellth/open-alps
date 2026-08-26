import json
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shapely.geometry import MultiPolygon, Point, Polygon  # noqa: E402

from lib.pipeline import circle_polygon, hub_range_polygon  # noqa: E402


def _write_huts(tmp_path, coords):
    fc = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": c}}
            for c in coords
        ],
    }
    path = tmp_path / "huts.geojson"
    path.write_text(json.dumps(fc), encoding="utf-8")
    return path


def test_circle_polygon_at_equator_has_equal_lat_lng_extent():
    poly = circle_polygon(0.0, 0.0, radius_km=10.0, n_points=64)
    minx, miny, maxx, maxy = poly.bounds
    lng_extent = maxx - minx
    lat_extent = maxy - miny
    assert lng_extent == pytest.approx(lat_extent, rel=0.01)


def test_circle_polygon_compensates_longitude_shrinkage_at_high_latitude():
    lat = 60.0
    poly = circle_polygon(0.0, lat, radius_km=10.0, n_points=64)
    minx, miny, maxx, maxy = poly.bounds
    lng_extent = maxx - minx
    lat_extent = maxy - miny
    expected_ratio = 1 / math.cos(math.radians(lat))
    assert (lng_extent / lat_extent) == pytest.approx(expected_ratio, rel=0.01)


def test_circle_polygon_contains_center_point():
    poly = circle_polygon(11.0, 47.0, radius_km=5.0)
    assert poly.contains(Point(11.0, 47.0))


def test_circle_polygon_does_not_reach_a_point_well_outside_the_radius():
    poly = circle_polygon(11.0, 47.0, radius_km=5.0)
    assert not poly.contains(Point(11.0, 47.5))


def test_hub_range_polygon_contains_every_hut(tmp_path):
    huts_path = _write_huts(tmp_path, [(11.0, 47.0), (11.2, 47.1), (13.0, 50.0)])
    polygon = hub_range_polygon(huts_path, radius_km=30.0)
    for lng, lat in [(11.0, 47.0), (11.2, 47.1), (13.0, 50.0)]:
        assert polygon.contains(Point(lng, lat))


def test_hub_range_polygon_unions_overlapping_circles_into_one_polygon(tmp_path):
    huts_path = _write_huts(tmp_path, [(11.0, 47.0), (11.05, 47.0)])
    polygon = hub_range_polygon(huts_path, radius_km=30.0)
    assert isinstance(polygon, Polygon)


def test_hub_range_polygon_keeps_disjoint_circles_separate(tmp_path):
    huts_path = _write_huts(tmp_path, [(11.0, 47.0), (16.0, 50.5)])
    polygon = hub_range_polygon(huts_path, radius_km=30.0)
    assert isinstance(polygon, MultiPolygon)
    assert len(polygon.geoms) == 2
