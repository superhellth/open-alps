import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from elevation import compute_edge_profiles as cep  # noqa: E402
from lib import binfmt, speed  # noqa: E402
from lib.timing import StepTimer  # noqa: E402

# longitude degrees shrink by cos(latitude) away from the equator - a flat "/111320.0" (the
# equatorial metres-per-degree constant) understates east-west distance at 47 deg N by ~32%.
_M_PER_DEG_LON_AT_47 = 111320.0 * np.cos(np.radians(47.0))


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


def _make_synthetic_edges(edge_rows):
    edges = np.zeros(len(edge_rows), dtype=binfmt.EDGE_DTYPE)
    for i, row in enumerate(edge_rows):
        for key, value in row.items():
            edges[key][i] = value
    return edges


def test_fill_edge_time_picks_technical_model_for_via_ferrata_and_applies_floor():
    # Edge 0: ordinary T1 trail, 2 points 100 m apart, 5 m climb - Tobler-walkable, no floor hit.
    # Edge 1: via_ferrata, 2 points 70 m apart (horizontal), 50 m climb - steep enough that Tobler
    # would imply an absurd time, but (unlike a much shorter/steeper pitch) still shallow enough
    # that neither the 30 m smoothing kernel (70 m > kernel width, so smoothing is a no-op here)
    # nor the min_speed_ms floor kick in - isolating the technical-model selection from those two
    # other mechanisms, which get their own dedicated coverage elsewhere (merge_segments' own
    # tests, and the floor-clamp test below).
    nodes = np.zeros(4, dtype=binfmt.NODE_DTYPE)
    # node 0 -> node 1 (edge 0, ordinary): straight line ~100 m east
    nodes["lon"][0], nodes["lat"][0] = 11.0, 47.0
    nodes["lon"][1], nodes["lat"][1] = 11.0 + 100.0 / _M_PER_DEG_LON_AT_47, 47.0
    # node 2 -> node 3 (edge 1, via_ferrata): straight line ~70 m east
    nodes["lon"][2], nodes["lat"][2] = 11.0, 47.0
    nodes["lon"][3], nodes["lat"][3] = 11.0 + 70.0 / _M_PER_DEG_LON_AT_47, 47.0
    interior = np.zeros(0, dtype=binfmt.COORD_DTYPE)
    node_ele = np.array([1000.0, 1005.0, 1000.0, 1050.0])
    interior_ele = np.zeros(0, dtype=np.float64)

    edges = _make_synthetic_edges([
        {"u": 0, "v": 1, "dist": 100.0, "sac_rank": 1, "via_ferrata": False,
         "interior_offset": 0, "interior_count": 0, "edge_id": 0},
        {"u": 2, "v": 3, "dist": 70.0, "sac_rank": 0, "via_ferrata": True,
         "interior_offset": 0, "interior_count": 0, "edge_id": 1},
    ])

    speed_model = dict(v0=4.013, k=3.5, s0=0.05)
    time_s, ascent, descent = cep._fill_edge_time_and_elevation(
        edges, nodes, interior, node_ele, interior_ele, kernel_m=30.0,
        speed_model=speed_model, timer=StepTimer(),
        min_slope_segment_m=30.0, technical_pace_ms=0.2, min_speed_ms=0.15,
    )

    dist_ordinary = cep.bbg.haversine_m_vec(
        nodes["lon"][0:1], nodes["lat"][0:1], nodes["lon"][1:2], nodes["lat"][1:2])[0]
    expected_ordinary = speed.edge_time_s(np.array([dist_ordinary]), np.array([5.0]), **speed_model)[0]
    assert time_s[0] == pytest.approx(expected_ordinary)

    dist_technical = cep.bbg.haversine_m_vec(
        nodes["lon"][2:3], nodes["lat"][2:3], nodes["lon"][3:4], nodes["lat"][3:4])[0]
    expected_technical = speed.technical_time_s(np.array([dist_technical]), np.array([50.0]), pace_ms=0.2)[0]
    assert time_s[1] == pytest.approx(expected_technical)
    # sanity: technical model implies a speed at/above the floor, so the floor isn't what produced
    # this time_s value
    assert dist_technical / time_s[1] > 0.15
    # sanity: technical model is dramatically cheaper here than the ordinary Tobler model would be
    # on the same segment - confirms is_technical actually routed to technical_time_s
    assert time_s[1] < speed.edge_time_s(np.array([dist_technical]), np.array([50.0]), **speed_model)[0]


def test_fill_edge_time_floor_clamps_residual_steep_ordinary_edges():
    # Ordinary (non-via_ferrata, sac_rank < 5) edge with an extreme short pitch that survives
    # aggregation (it's the edge's only segment, nothing to merge with) - must be clamped by the
    # floor rather than left at an impossible implied speed.
    nodes = np.zeros(2, dtype=binfmt.NODE_DTYPE)
    nodes["lon"][0], nodes["lat"][0] = 11.0, 47.0
    nodes["lon"][1], nodes["lat"][1] = 11.0 + 5.0 / _M_PER_DEG_LON_AT_47, 47.0
    interior = np.zeros(0, dtype=binfmt.COORD_DTYPE)
    node_ele = np.array([1000.0, 1500.0])  # 500 m climb over 5 m horizontal - absurd for Tobler
    interior_ele = np.zeros(0, dtype=np.float64)

    edges = _make_synthetic_edges([
        {"u": 0, "v": 1, "dist": 5.0, "sac_rank": 1, "via_ferrata": False,
         "interior_offset": 0, "interior_count": 0, "edge_id": 0},
    ])

    speed_model = dict(v0=4.013, k=3.5, s0=0.05)
    time_s, _, _ = cep._fill_edge_time_and_elevation(
        edges, nodes, interior, node_ele, interior_ele, kernel_m=30.0,
        speed_model=speed_model, timer=StepTimer(),
        min_slope_segment_m=30.0, technical_pace_ms=0.2, min_speed_ms=0.15,
    )

    dist = cep.bbg.haversine_m_vec(
        nodes["lon"][0:1], nodes["lat"][0:1], nodes["lon"][1:2], nodes["lat"][1:2])[0]
    assert time_s[0] == pytest.approx(dist / 0.15)
