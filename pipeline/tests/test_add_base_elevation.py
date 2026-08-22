import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from elevation import add_base_elevation as abe  # noqa: E402


def test_ascent_descent_are_plain_sums_of_signed_deltas():
    # +10, -4, +6 -> ascent 16, descent 4. No threshold, no hysteresis: eleNoiseThresholdM is
    # retired and the smoothing kernel is the replacement tunable (spec B2).
    smoothed = np.array([1000.0, 1010.0, 1006.0, 1012.0])
    asc, desc = abe.edge_ascent_descent(smoothed, np.array([0]), np.array([4]))
    assert asc[0] == pytest.approx(16.0)
    assert desc[0] == pytest.approx(4.0)


def test_ascent_descent_vectorises_over_many_edges_without_bleeding():
    # two edges back to back; the +90 jump BETWEEN them belongs to neither
    smoothed = np.array([100.0, 110.0, 200.0, 190.0])
    asc, desc = abe.edge_ascent_descent(smoothed, np.array([0, 2]), np.array([2, 2]))
    assert asc.tolist() == pytest.approx([10.0, 0.0])
    assert desc.tolist() == pytest.approx([0.0, 10.0])


def test_single_point_edge_has_zero_ascent():
    asc, desc = abe.edge_ascent_descent(np.array([1500.0]), np.array([0]), np.array([1]))
    assert asc[0] == 0.0 and desc[0] == 0.0


def test_smoothing_removes_a_single_point_dem_spike():
    elev = np.full(11, 1000.0)
    elev[5] = 1020.0
    seg = np.full(10, 10.0)          # 10 m spacing, 30 m kernel
    out = abe.smooth_profile(elev, seg, kernel_m=30.0)
    assert out.max() - out.min() < 20.0
    assert len(out) == len(elev)


def test_smoothing_kernel_is_metres_not_points():
    # point spacing varies 7x between p25 (19.7 m) and p75 (133.7 m), so a point-count kernel
    # would smooth wildly different distances on different edges
    dense = abe.smooth_profile(np.array([0.0, 20.0, 0.0]), np.array([5.0, 5.0]), kernel_m=30.0)
    sparse = abe.smooth_profile(np.array([0.0, 20.0, 0.0]), np.array([200.0, 200.0]), kernel_m=30.0)
    assert dense.max() < sparse.max()


def test_bilinear_sampling_interpolates_between_cells():
    from affine import Affine
    window = np.array([[0.0, 10.0], [20.0, 30.0]], dtype=np.float32)
    transform = Affine(1.0, 0.0, 0.0, 0.0, -1.0, 0.0)
    got = abe.sample_bilinear(window, transform, np.array([1.0]), np.array([-1.0]))
    assert got[0] == pytest.approx(15.0)
