import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import binfmt  # noqa: E402
from lib.anchors import (  # noqa: E402
    ANCHOR_UNIT_DEG, anchor_column_names, decode_offsets, decode_row, distance_to_polyline_m,
    edge_anchor_columns, points_at_fractions, quantise_offsets,
)


def test_column_names_follow_fraction_order():
    assert anchor_column_names() == ["a25_dlat", "a25_dlng", "a50_dlat", "a50_dlng", "a75_dlat", "a75_dlng"]
    assert anchor_column_names((0.5,)) == ["a50_dlat", "a50_dlng"]


def test_straight_line_quarters_are_evenly_spaced():
    pts = points_at_fractions([11.0, 11.4], [47.0, 47.0])
    assert pts[:, 1] == pytest.approx([47.0] * 3)
    assert pts[:, 0] == pytest.approx([11.1, 11.2, 11.3], abs=1e-4)


def test_l_shape_puts_the_midpoint_on_the_corner():
    # equal-length legs: east then north; 50 % is the corner
    lat = 47.0
    dlon = 0.01
    dlat = dlon * np.cos(np.radians(lat))
    pts = points_at_fractions([11.0, 11.0 + dlon, 11.0 + dlon], [lat, lat, lat + dlat])
    assert pts[1] == pytest.approx([11.0 + dlon, lat], abs=1e-6)


def test_zero_length_segments_do_not_break_interpolation():
    pts = points_at_fractions([11.0, 11.0, 11.0, 11.2], [47.0, 47.0, 47.0, 47.0])
    assert np.isfinite(pts).all()
    assert pts[1, 0] == pytest.approx(11.1, abs=1e-4)


@pytest.mark.parametrize("lons,lats", [([11.0], [47.0]), ([11.0, 11.0], [47.0, 47.0])])
def test_degenerate_geometry_collapses_to_the_point(lons, lats):
    pts = points_at_fractions(lons, lats)
    assert np.isfinite(pts).all()
    assert pts == pytest.approx(np.tile([11.0, 47.0], (3, 1)))


def test_empty_geometry_is_an_error():
    with pytest.raises(ValueError):
        points_at_fractions([], [])


def test_quantise_round_trips_within_one_unit():
    ref = np.array([11.0, 47.0])
    pts = np.array([[11.01234, 47.02345], [10.99, 46.98]])
    dlat, dlng = quantise_offsets(pts, ref)
    assert dlat.dtype == np.dtype("i2") and dlng.dtype == np.dtype("i2")
    back = decode_offsets(ref, dlat, dlng)
    assert np.abs(back - pts).max() <= ANCHOR_UNIT_DEG


def test_quantise_rejects_offsets_beyond_i2():
    with pytest.raises(ValueError):
        quantise_offsets(np.array([[11.0 + 4.0, 47.0]]), np.array([11.0, 47.0]))


def _geometry(points):
    g = np.zeros(len(points), dtype=binfmt.COORD_DTYPE)
    g["lon"] = [p[0] for p in points]
    g["lat"] = [p[1] for p in points]
    return g


def test_edge_anchor_columns_decode_back_to_the_polyline():
    geometry = _geometry([(11.0, 47.0), (11.4, 47.0), (11.0, 47.1), (11.0, 47.2)])
    records = np.zeros(2, dtype=binfmt.RECORD_DTYPE)
    records["geom_offset"] = [0, 2]
    records["geom_count"] = [2, 2]
    ref = np.array([[11.0, 47.0], [11.0, 47.1]])
    cols = edge_anchor_columns(records, geometry, np.array([0, 1]), ref)
    assert set(cols) == set(anchor_column_names())
    assert all(c.dtype == np.dtype("i2") for c in cols.values())
    row0 = decode_row(cols, 0, ref[0])
    assert row0[1] == pytest.approx([11.2, 47.0], abs=1e-4)
    row1 = decode_row(cols, 1, ref[1])
    assert row1[1] == pytest.approx([11.0, 47.15], abs=1e-3)


def test_distance_to_polyline_is_zero_on_the_line_and_positive_off_it():
    poly = np.array([[11.0, 47.0], [11.1, 47.0]])
    assert distance_to_polyline_m(11.05, 47.0, poly) == pytest.approx(0.0, abs=0.5)
    assert distance_to_polyline_m(11.05, 47.001, poly) == pytest.approx(111.3, abs=2.0)
    assert distance_to_polyline_m(11.2, 47.0, poly) == pytest.approx(0.1 * 111_320 * np.cos(np.radians(47.0)), rel=0.01)
