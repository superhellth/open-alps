import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.edge_split import nearest_point_on_polyline, split_edge_at_point  # noqa: E402


def test_nearest_point_on_polyline_picks_closest_segment():
    polyline = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]
    seg_idx, frac = nearest_point_on_polyline(polyline, (1.5, 0.1))
    assert seg_idx == 1
    assert 0.4 < frac < 0.6


def test_nearest_point_on_polyline_clamps_before_first_vertex():
    polyline = [(0.0, 0.0), (1.0, 0.0)]
    seg_idx, frac = nearest_point_on_polyline(polyline, (-1.0, 0.0))
    assert seg_idx == 0
    assert frac == 0.0


def test_split_at_midpoint_divides_distance_evenly():
    result = split_edge_at_point(
        u_coord=(0.0, 0.0), v_coord=(2.0, 0.0), interior=[(1.0, 0.0)],
        dist_m=200.0, road_m=0.0, ungraded_m=0.0, inferred_m=0.0,
        segment_index=0, frac=0.5,  # midpoint of segment u->interior[0]
    )
    assert abs(result.dist_to_u - 50.0) < 1e-6
    assert abs(result.dist_to_v - 150.0) < 1e-6
    assert abs(result.dist_to_u + result.dist_to_v - 200.0) < 1e-6


def test_split_preserves_interior_points_on_each_side():
    result = split_edge_at_point(
        u_coord=(0.0, 0.0), v_coord=(3.0, 0.0), interior=[(1.0, 0.0), (2.0, 0.0)],
        dist_m=300.0, road_m=0.0, ungraded_m=0.0, inferred_m=0.0,
        segment_index=1, frac=0.5,  # midpoint of segment interior[0]->interior[1]
    )
    assert result.interior_to_u == [(1.0, 0.0)]
    assert result.interior_to_v == [(2.0, 0.0)]


def test_split_road_m_proportional_to_distance_when_whole_edge_is_road():
    result = split_edge_at_point(
        u_coord=(0.0, 0.0), v_coord=(2.0, 0.0), interior=[(1.0, 0.0)],
        dist_m=200.0, road_m=200.0, ungraded_m=0.0, inferred_m=0.0,
        segment_index=0, frac=0.5,
    )
    assert abs(result.road_m_to_u + result.road_m_to_v - 200.0) < 1e-6


def test_split_apportions_grading_metres_by_distance_ratio():
    split = split_edge_at_point(
        u_coord=(0.0, 0.0), v_coord=(0.002, 0.0), interior=[],
        dist_m=200.0, road_m=0.0, ungraded_m=200.0, inferred_m=0.0,
        segment_index=0, frac=0.25,
    )
    assert split.ungraded_m_to_u == 50.0
    assert split.ungraded_m_to_v == 150.0
    assert not hasattr(split, "weight_to_u")
