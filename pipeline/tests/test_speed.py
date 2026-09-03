import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import speed  # noqa: E402

CONSTANTS = dict(v0=6.0, k=3.5, s0=0.05)  # spec A1 starting point; Task 11 calibrates


def test_speed_peaks_on_a_gentle_descent_not_on_the_flat():
    v_flat = speed.speed_kmh(np.array([0.0]), **CONSTANTS)[0]
    v_peak = speed.speed_kmh(np.array([-0.05]), **CONSTANTS)[0]
    assert v_peak > v_flat
    assert v_peak == pytest.approx(6.0)


def test_time_is_additive_across_a_split_segment():
    # the entire point of a pointwise model: splitting a segment must not change its cost
    whole = speed.edge_time_s(np.array([100.0]), np.array([10.0]), **CONSTANTS).sum()
    halves = speed.edge_time_s(np.array([50.0, 50.0]), np.array([5.0, 5.0]), **CONSTANTS).sum()
    assert whole == pytest.approx(halves)


def test_uphill_is_slower_than_the_same_grade_downhill():
    up = speed.edge_time_s(np.array([100.0]), np.array([20.0]), **CONSTANTS)[0]
    down = speed.edge_time_s(np.array([100.0]), np.array([-20.0]), **CONSTANTS)[0]
    assert up > down


def test_zero_length_segment_costs_nothing_and_does_not_divide_by_zero():
    assert speed.edge_time_s(np.array([0.0]), np.array([0.0]), **CONSTANTS)[0] == 0.0


def test_din_duration_blends_horizontal_and_vertical():
    # 8 km with 600 m up / 500 m down: t_h = 2.0, t_v = 2.0 + 1.0 = 3.0 -> 3.0 + 1.0 = 4.0 h
    assert speed.din_duration_h(8000.0, 600.0, 500.0) == pytest.approx(4.0)


def test_technical_time_matches_3d_distance_over_pace():
    dist_m, dz_m, pace_ms = 30.0, 40.0, 0.2
    expected = np.hypot(dist_m, dz_m) / pace_ms  # 50 m / 0.2 m/s = 250 s
    got = speed.technical_time_s(np.array([dist_m]), np.array([dz_m]), pace_ms=pace_ms)[0]
    assert got == pytest.approx(expected)


def test_technical_time_is_symmetric_in_the_sign_of_dz():
    # unlike edge_time_s's Tobler model, technical_time_s must not favour descent over ascent
    up = speed.technical_time_s(np.array([30.0]), np.array([40.0]), pace_ms=0.2)[0]
    down = speed.technical_time_s(np.array([30.0]), np.array([-40.0]), pace_ms=0.2)[0]
    assert up == pytest.approx(down)
