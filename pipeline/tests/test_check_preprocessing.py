import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from lib import binfmt  # noqa: E402
from quality.check_preprocessing import (  # noqa: E402
    check_id_table_coverage, check_start_point_integrity,
)

_TYPE_STATION, _TYPE_PARKING = binfmt.TYPE_STATION, binfmt.TYPE_PARKING
_BBOX = {"minLng": 8.9, "maxLng": 17.2, "minLat": 46.3, "maxLat": 50.6}


def _start_points(rows):
    arr = np.zeros(len(rows), dtype=[("lon", "f8"), ("lat", "f8"), ("osm_id", "i8"), ("type", "u1")])
    for i, (lon, lat, osm_id, type_) in enumerate(rows):
        arr[i] = (lon, lat, osm_id, type_)
    return arr


def test_clean_points_are_not_flagged():
    points = _start_points([(11.0, 47.0, 1, _TYPE_STATION), (12.0, 48.0, 2, _TYPE_PARKING)])
    check = check_start_point_integrity(points, _BBOX, max_flagged=500)
    assert check["summary"]["flagged"] == 0


def test_non_finite_coordinate_is_flagged():
    points = _start_points([(float("nan"), 47.0, 1, _TYPE_STATION)])
    check = check_start_point_integrity(points, _BBOX, max_flagged=500)
    assert check["summary"]["flagged"] == 1
    assert check["flagged"][0]["reason"] == "non_finite"


def test_out_of_bbox_coordinate_is_flagged():
    points = _start_points([(200.0, 47.0, 1, _TYPE_STATION)])
    check = check_start_point_integrity(points, _BBOX, max_flagged=500)
    assert check["summary"]["flagged"] == 1
    assert check["flagged"][0]["reason"] == "outside_bbox"


def test_duplicate_type_osm_id_pair_is_flagged():
    points = _start_points([
        (11.0, 47.0, 1, _TYPE_STATION), (11.0, 47.0, 1, _TYPE_STATION),
        (12.0, 48.0, 1, _TYPE_PARKING),  # same osm_id, different type - NOT a duplicate
    ])
    check = check_start_point_integrity(points, _BBOX, max_flagged=500)
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
