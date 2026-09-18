import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import elevation_profile as ep  # noqa: E402


def test_smooth_profile_returns_input_unchanged_for_single_point():
    got = ep.smooth_profile([1000.0], [], kernel_m=30.0)
    assert list(got) == [1000.0]


def test_smooth_profile_returns_input_unchanged_when_kernel_is_zero():
    elevations = [1000.0, 1010.0, 990.0]
    got = ep.smooth_profile(elevations, [10.0, 10.0], kernel_m=0.0)
    assert list(got) == elevations


def test_smooth_profile_flattens_a_single_point_spike():
    # a spike surrounded by flat ground, kernel wide relative to point spacing, should pull the
    # spike's smoothed value well below its raw value.
    elevations = [1000.0, 1000.0, 1050.0, 1000.0, 1000.0]
    seg_len = [10.0, 10.0, 10.0, 10.0]
    got = ep.smooth_profile(elevations, seg_len, kernel_m=60.0)
    assert got[2] < 1050.0
    assert got[2] > 1000.0


def test_merge_segments_accumulates_until_min_segment_m():
    seg_len = [10.0, 10.0, 10.0, 10.0]
    dz = [5.0, 5.0, 5.0, 5.0]
    merged_len, merged_dz = ep.merge_segments(seg_len, dz, min_segment_m=25.0)
    assert list(merged_len) == [30.0, 10.0]
    assert list(merged_dz) == [15.0, 5.0]


def test_merge_segments_keeps_a_short_trailing_remainder():
    seg_len = [30.0, 5.0]
    dz = [10.0, 1.0]
    merged_len, merged_dz = ep.merge_segments(seg_len, dz, min_segment_m=25.0)
    assert list(merged_len) == [30.0, 5.0]
    assert list(merged_dz) == [10.0, 1.0]


def test_ascent_descent_sums_positive_and_negative_deltas():
    elevations = [1000.0, 1050.0, 1020.0, 1080.0]
    ascent_m, descent_m = ep.ascent_descent(elevations)
    assert ascent_m == pytest.approx(50.0 + 60.0)
    assert descent_m == pytest.approx(30.0)


def test_ascent_descent_of_single_point_is_zero():
    ascent_m, descent_m = ep.ascent_descent([1000.0])
    assert (ascent_m, descent_m) == (0.0, 0.0)


def test_resample_to_points_interpolates_onto_n_points():
    lon = np.array([11.0, 11.001, 11.002])
    lat = np.array([47.0, 47.0, 47.0])
    elevations = np.array([1000.0, 1010.0, 1020.0])
    got = ep.resample_to_points(lon, lat, elevations, n_points=5)
    assert len(got) == 5
    assert got[0] == pytest.approx(1000.0)
    assert got[-1] == pytest.approx(1020.0)


def test_resample_to_points_returns_empty_for_single_point_trace():
    got = ep.resample_to_points(np.array([11.0]), np.array([47.0]), np.array([1000.0]), n_points=5)
    assert got == []
