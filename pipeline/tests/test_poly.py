import sys
from pathlib import Path

from shapely.geometry import Point

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shapely.geometry import box  # noqa: E402

from lib.poly import filter_to_boundary, parse_poly_file, region_boundary  # noqa: E402

_SQUARE_NO_HOLE = """test_square
1
   0.0 0.0
   0.0 10.0
   10.0 10.0
   10.0 0.0
   0.0 0.0
END
END
"""

_SQUARE_WITH_HOLE = """test_square_with_hole
1
   0.0 0.0
   0.0 10.0
   10.0 10.0
   10.0 0.0
   0.0 0.0
END
!2
   4.0 4.0
   4.0 6.0
   6.0 6.0
   6.0 4.0
   4.0 4.0
END
END
"""


def test_parse_poly_file_simple_square(tmp_path):
    path = tmp_path / "square.poly"
    path.write_text(_SQUARE_NO_HOLE, encoding="utf-8")

    polygon = parse_poly_file(path)

    assert polygon.contains(Point(5.0, 5.0))
    assert not polygon.contains(Point(15.0, 5.0))


def test_parse_poly_file_subtracts_hole(tmp_path):
    path = tmp_path / "square_with_hole.poly"
    path.write_text(_SQUARE_WITH_HOLE, encoding="utf-8")

    polygon = parse_poly_file(path)

    assert polygon.contains(Point(1.0, 1.0))
    assert not polygon.contains(Point(5.0, 5.0))  # inside the hole


_SQUARE_FAR_AWAY = """test_square_far_away
1
   20.0 0.0
   20.0 10.0
   30.0 10.0
   30.0 0.0
   20.0 0.0
END
END
"""


def test_region_boundary_unions_multiple_files(tmp_path):
    left = tmp_path / "left.poly"
    left.write_text(_SQUARE_NO_HOLE, encoding="utf-8")

    right = tmp_path / "right.poly"
    right.write_text(_SQUARE_FAR_AWAY, encoding="utf-8")

    boundary = region_boundary([left, right])

    assert boundary.contains(Point(5.0, 5.0))
    assert boundary.contains(Point(25.0, 5.0))
    assert not boundary.contains(Point(15.0, 5.0))  # gap between the two squares


def _feature_xy(feature):
    return feature.get("xy")


def test_filter_to_boundary_keeps_only_features_inside():
    inside = {"name": "in", "xy": (0.5, 0.5)}
    outside = {"name": "out", "xy": (2.0, 0.5)}

    kept = filter_to_boundary([inside, outside], box(0, 0, 1, 1), _feature_xy)

    assert [f["name"] for f in kept] == ["in"]


def test_filter_to_boundary_drops_features_without_a_point():
    assert filter_to_boundary([{"name": "none"}], box(0, 0, 1, 1), _feature_xy) == []
