import sys
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon, box

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from lib import binfmt  # noqa: E402
from quality.check_preprocessing import (  # noqa: E402
    check_id_table_coverage, check_source_layer_in_region, check_start_point_integrity,
)

_TYPE_STATION, _TYPE_PARKING = binfmt.TYPE_STATION, binfmt.TYPE_PARKING
_REGION = box(8.9, 46.3, 17.2, 50.6)


def _start_points(rows):
    arr = np.zeros(len(rows), dtype=[("lon", "f8"), ("lat", "f8"), ("osm_id", "i8"), ("type", "u1")])
    for i, (lon, lat, osm_id, type_) in enumerate(rows):
        arr[i] = (lon, lat, osm_id, type_)
    return arr


def test_clean_points_are_not_flagged():
    points = _start_points([(11.0, 47.0, 1, _TYPE_STATION), (12.0, 48.0, 2, _TYPE_PARKING)])
    check = check_start_point_integrity(points, _REGION, max_flagged=500)
    assert check["summary"]["flagged"] == 0


def test_non_finite_coordinate_is_flagged():
    points = _start_points([(float("nan"), 47.0, 1, _TYPE_STATION)])
    check = check_start_point_integrity(points, _REGION, max_flagged=500)
    assert check["summary"]["flagged"] == 1
    assert check["flagged"][0]["reason"] == "non_finite"


def test_coordinate_outside_region_is_flagged():
    points = _start_points([(200.0, 47.0, 1, _TYPE_STATION)])
    check = check_start_point_integrity(points, _REGION, max_flagged=500)
    assert check["summary"]["flagged"] == 1
    assert check["flagged"][0]["reason"] == "outside_region"


def test_duplicate_type_osm_id_pair_is_flagged():
    points = _start_points([
        (11.0, 47.0, 1, _TYPE_STATION), (11.0, 47.0, 1, _TYPE_STATION),
        (12.0, 48.0, 1, _TYPE_PARKING),  # same osm_id, different type - NOT a duplicate
    ])
    check = check_start_point_integrity(points, _REGION, max_flagged=500)
    assert check["summary"]["flagged"] == 1
    assert check["flagged"][0]["reason"] == "duplicate"


def test_id_table_coverage_flags_unresolvable_osm_id():
    points = _start_points([(11.0, 47.0, 1, _TYPE_STATION)])
    check = check_id_table_coverage(points, id_table={"station": {}}, max_flagged=500)
    assert check["summary"]["flagged"] == 1
    assert check["flagged"][0] == {"row": 0, "type": "station", "osm_id": 1}


def test_id_table_coverage_passes_when_resolvable():
    points = _start_points([(11.0, 47.0, 1, _TYPE_STATION)])
    check = check_id_table_coverage(points, id_table={"station": {"1": {}}}, max_flagged=500)
    assert check["summary"]["flagged"] == 0


def test_point_inside_bounding_box_but_outside_polygon_is_flagged():
    triangle = Polygon([(8.0, 46.0), (18.0, 46.0), (8.0, 51.0)])
    points = _start_points([(9.0, 47.0, 1, _TYPE_STATION), (17.0, 50.0, 2, _TYPE_STATION)])
    check = check_start_point_integrity(points, triangle, max_flagged=500)
    assert [f["osm_id"] for f in check["flagged"]] == [2]
    assert check["flagged"][0]["reason"] == "outside_region"


def _feature(x, y, id_="n1"):
    return {"id": id_, "geometry": {"type": "Point", "coordinates": [x, y]}, "properties": {}}


def test_source_layer_flags_point_outside_region():
    features = [_feature(11.0, 47.0, "in"), _feature(200.0, 47.0, "out")]
    check = check_source_layer_in_region("huts", features, _REGION, max_flagged=500)
    assert check["check"] == "source_layer_in_region_huts"
    assert [f["id"] for f in check["flagged"]] == ["out"]
    assert check["flagged"][0]["reason"] == "outside_region"


def test_source_layer_flags_missing_geometry():
    check = check_source_layer_in_region(
        "huts", [{"id": "x", "geometry": None, "properties": {}}], _REGION, max_flagged=500)
    assert check["flagged"][0]["reason"] == "no_geometry"


def test_source_layer_clean_points_are_not_flagged():
    check = check_source_layer_in_region("parking", [_feature(11.0, 47.0)], _REGION, max_flagged=500)
    assert check["summary"]["flagged"] == 0
