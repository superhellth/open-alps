import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from elevation import compute_edge_profiles as cep  # noqa: E402


def test_ascent_descent_are_plain_sums_of_signed_deltas():
    # +10, -4, +6 -> ascent 16, descent 4. No threshold, no hysteresis: eleNoiseThresholdM is
    # retired and the smoothing kernel is the replacement tunable (spec B2).
    smoothed = np.array([1000.0, 1010.0, 1006.0, 1012.0])
    asc, desc = cep.edge_ascent_descent(smoothed, np.array([0]), np.array([4]))
    assert asc[0] == pytest.approx(16.0)
    assert desc[0] == pytest.approx(4.0)


def test_ascent_descent_vectorises_over_many_edges_without_bleeding():
    # two edges back to back; the +90 jump BETWEEN them belongs to neither
    smoothed = np.array([100.0, 110.0, 200.0, 190.0])
    asc, desc = cep.edge_ascent_descent(smoothed, np.array([0, 2]), np.array([2, 2]))
    assert asc.tolist() == pytest.approx([10.0, 0.0])
    assert desc.tolist() == pytest.approx([0.0, 10.0])


def test_single_point_edge_has_zero_ascent():
    asc, desc = cep.edge_ascent_descent(np.array([1500.0]), np.array([0]), np.array([1]))
    assert asc[0] == 0.0 and desc[0] == 0.0


def test_smoothing_removes_a_single_point_dem_spike():
    elev = np.full(11, 1000.0)
    elev[5] = 1020.0
    seg = np.full(10, 10.0)          # 10 m spacing, 30 m kernel
    out = cep.smooth_profile(elev, seg, kernel_m=30.0)
    assert out.max() - out.min() < 20.0
    assert len(out) == len(elev)


def test_smoothing_kernel_is_metres_not_points():
    # point spacing varies 7x between p25 (19.7 m) and p75 (133.7 m), so a point-count kernel
    # would smooth wildly different distances on different edges
    dense = cep.smooth_profile(np.array([0.0, 20.0, 0.0]), np.array([5.0, 5.0]), kernel_m=30.0)
    sparse = cep.smooth_profile(np.array([0.0, 20.0, 0.0]), np.array([200.0, 200.0]), kernel_m=30.0)
    assert dense.max() < sparse.max()


def test_merge_segments_combines_short_runs_up_to_the_window():
    # 4 segments of 10 m each, window 30 m -> merges into [30, 10] (a 20 m staircase digitized as
    # short segments becomes one slope computation over 30 m, plus a kept 10 m remainder)
    seg_len = np.array([10.0, 10.0, 10.0, 10.0])
    dz = np.array([-1.0, -30.0, -2.0, -1.0])
    merged_len, merged_dz = cep.merge_segments(seg_len, dz, min_segment_m=30.0)
    assert merged_len.tolist() == pytest.approx([30.0, 10.0])
    assert merged_dz.tolist() == pytest.approx([-33.0, -1.0])


def test_merge_segments_keeps_a_final_under_window_remainder():
    # single 5 m segment, window 30 m -> nothing to merge with, kept as-is rather than dropped
    seg_len = np.array([5.0])
    dz = np.array([-2.0])
    merged_len, merged_dz = cep.merge_segments(seg_len, dz, min_segment_m=30.0)
    assert merged_len.tolist() == pytest.approx([5.0])
    assert merged_dz.tolist() == pytest.approx([-2.0])


def test_merge_segments_handles_empty_input():
    merged_len, merged_dz = cep.merge_segments(np.array([]), np.array([]), min_segment_m=30.0)
    assert len(merged_len) == 0
    assert len(merged_dz) == 0


def test_merge_segments_leaves_already_wide_segments_alone():
    seg_len = np.array([40.0, 50.0])
    dz = np.array([-5.0, 3.0])
    merged_len, merged_dz = cep.merge_segments(seg_len, dz, min_segment_m=30.0)
    assert merged_len.tolist() == pytest.approx([40.0, 50.0])
    assert merged_dz.tolist() == pytest.approx([-5.0, 3.0])
