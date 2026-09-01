import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from lib.geo import haversine_m
from lib.hmm_match import resample_trace


def _line_points(n, spacing_m):
    # straight east-west line at the equator; 1 degree of longitude ~= 111320m there
    step_deg = spacing_m / 111320.0
    return [(i * step_deg, 0.0) for i in range(n)]


def test_resample_decimates_a_dense_trace_to_target_spacing():
    dense = _line_points(300, spacing_m=3.0)  # ~900m total, 3m/point
    out = resample_trace(dense, resample_m=25.0)
    assert out[0] == dense[0]
    assert out[-1] == dense[-1]
    for a, b in zip(out, out[1:]):
        d = haversine_m(a[0], a[1], b[0], b[1])
        assert d >= 25.0 - 1e-6 or (a, b) == (out[-2], out[-1])
    assert len(out) < len(dense)


def test_resample_leaves_a_sparse_trace_unchanged():
    sparse = _line_points(5, spacing_m=100.0)  # 100m/point, sparser than the 25m target
    out = resample_trace(sparse, resample_m=25.0)
    assert out == sparse


def test_resample_preserves_endpoints_of_a_dense_trace():
    dense = _line_points(50, spacing_m=5.0)
    out = resample_trace(dense, resample_m=25.0)
    assert out[0] == dense[0]
    assert out[-1] == dense[-1]


def test_inmem_map_round_trips_lon_lat_through_the_lat_lon_boundary():
    from lib.hmm_match import build_inmem_map

    nodes = {0: (11.123, 47.456), 1: (11.130, 47.460)}
    m = build_inmem_map(nodes)
    lat0, lon0 = m.node_coordinates(0)
    assert (lon0, lat0) == nodes[0]
    lat1, lon1 = m.node_coordinates(1)
    assert (lon1, lat1) == nodes[1]


import numpy as np
from lib import binfmt
from lib.subgraph import LocalSubgraph


def _curved_edge_subgraph():
    # 2 nodes ~200m apart at the equator, with 3 interior points bending the real path away from
    # the straight chord - the "curvature the chord would discard" case (spec §2).
    nodes = np.zeros(2, dtype=binfmt.NODE_DTYPE)
    nodes[0] = (0.0, 0.0, 0)
    nodes[1] = (0.0018, 0.0, 0)  # ~200m east
    interior = np.zeros(3, dtype=binfmt.COORD_DTYPE)
    interior[0] = (0.0004, 0.0005)
    interior[1] = (0.0009, 0.0008)
    interior[2] = (0.0013, 0.0003)
    edges = np.zeros(1, dtype=binfmt.EDGE_DTYPE)
    # dist/inferred_m (272.073...) is the actual haversine length of [u, *interior, v] above -
    # expand_edge_interiors recomputes segment lengths from that same polyline, so this must match
    # what it will sum back to, not an arbitrary round number.
    edges[0] = (0, 1, 272.07343961346197, 0.0, 0.0, 272.07343961346197, 240.0, 15.0, 5.0,
                1, False, True, 0, 3, 42)
    return LocalSubgraph(
        global_node_ids=np.array([10, 11]), local_nodes=nodes, local_edges=edges,
        interior=interior,
        local_node_ele=np.array([1000.0, 1010.0], dtype=np.float32),
        interior_ele=np.array([1002.0, 1006.0, 1008.0], dtype=np.float32),
    )


def test_expand_edge_interiors_produces_tagged_bidirectional_chain():
    from lib.hmm_match import expand_edge_interiors

    subgraph = _curved_edge_subgraph()
    sub_edges, extra_nodes, next_id = expand_edge_interiors(subgraph, next_node_id=2)

    # 1 base edge with 3 interior points -> 4 segments (u->i0->i1->i2->v), doubled for direction.
    assert len(sub_edges) == 8
    assert next_id == 2 + 3  # 3 new interior-point node labels minted
    assert set(extra_nodes.keys()) == {2, 3, 4}

    forward = [se for se in sub_edges if se.direction == 1]
    backward = [se for se in sub_edges if se.direction == -1]
    assert len(forward) == 4 and len(backward) == 4
    assert [se.from_node for se in forward] == [0, 2, 3, 4]
    assert [se.to_node for se in forward] == [2, 3, 4, 1]
    assert [se.from_node for se in backward] == [1, 4, 3, 2]
    assert [se.to_node for se in backward] == [4, 3, 2, 0]

    # base_edge_id namespace: edge_id 42 -> 126, on every sub-edge regardless of direction/segment.
    assert all(se.base_edge_id == 126 for se in sub_edges)

    # distances sum back to the parent edge's own dist, both directions.
    assert abs(sum(se.dist_m for se in forward) - 272.07343961346197) < 1e-6
    assert abs(sum(se.dist_m for se in backward) - 272.07343961346197) < 1e-6

    # ascent/descent swap on the reverse direction (spec §2 / accumulate_path's convention).
    fwd_ascent = sum(se.ascent_m for se in forward)
    fwd_descent = sum(se.descent_m for se in forward)
    bwd_ascent = sum(se.ascent_m for se in backward)
    bwd_descent = sum(se.descent_m for se in backward)
    assert bwd_ascent == pytest.approx(fwd_descent)
    assert bwd_descent == pytest.approx(fwd_ascent)


from lib.edge_split import nearest_point_on_polyline


def test_filter_sub_edges_near_trace_drops_far_edges_keeps_near_ones():
    from lib.hmm_match import (
        SubEdge, filter_sub_edges_near_trace,
    )

    node_coords = {0: (0.0, 0.0), 1: (0.0, 0.001), 2: (0.01, 0.0), 3: (0.01, 0.001)}
    near = SubEdge(from_node=0, to_node=1, base_edge_id=3, direction=1, segment_index=0,
                    dist_m=100.0, road_m=0.0, ungraded_m=0.0, inferred_m=100.0,
                    ascent_m=0.0, descent_m=0.0, max_ele_m=1000.0, sac_rank=1, via_ferrata=False)
    far = SubEdge(from_node=2, to_node=3, base_edge_id=6, direction=1, segment_index=0,
                   dist_m=100.0, road_m=0.0, ungraded_m=0.0, inferred_m=100.0,
                   ascent_m=0.0, descent_m=0.0, max_ele_m=1000.0, sac_rank=1, via_ferrata=False)
    trace = [(0.0, 0.0), (0.0, 0.001)]  # right on top of `near`, ~1km+ from `far`

    kept, kept_nodes = filter_sub_edges_near_trace(
        [near, far], extra_nodes={}, trace=trace, max_dist_m=150.0, node_coords=node_coords,
    )
    assert kept == [near]


from lib.hub_snap import SnapResult
from lib.edge_split import SplitResult


def test_materialize_anchor_node_snap_reuses_existing_node_label():
    from lib.hmm_match import materialize_anchor

    subgraph = _curved_edge_subgraph()
    snap = SnapResult(node_index=0, gap_m=5.0, gap_dz_m=0.0)
    anchor, extra_edges, extra_nodes, next_id = materialize_anchor(subgraph, snap, next_node_id=2)
    assert anchor == 0
    assert extra_edges == []
    assert extra_nodes == {}
    assert next_id == 2


def test_materialize_anchor_mid_chain_snap_splits_parent_edge():
    from lib.hmm_match import materialize_anchor

    subgraph = _curved_edge_subgraph()
    split = SplitResult(
        split_coord=(0.0009, 0.0004), dist_to_u=110.0, dist_to_v=130.0,
        road_m_to_u=0.0, road_m_to_v=0.0, ungraded_m_to_u=0.0, ungraded_m_to_v=0.0,
        inferred_m_to_u=110.0, inferred_m_to_v=130.0,
        interior_to_u=[(0.0004, 0.0005)], interior_to_v=[(0.0013, 0.0003)],
    )
    snap = SnapResult(node_index=None, edge_local_index=0, split=split, gap_m=8.0, gap_dz_m=1.0)
    anchor, extra_edges, extra_nodes, next_id = materialize_anchor(subgraph, snap, next_node_id=2)

    # 3 new nodes minted: the split point itself, plus one per half's own interior point (each
    # half is expanded into its own segments the same way expand_edge_interiors expands a whole
    # parent edge, so its interior points need labels of their own too).
    assert next_id == 5
    assert extra_nodes[anchor] == split.split_coord
    ids = {se.base_edge_id for se in extra_edges}
    assert ids == {126 + 1, 126 + 2}  # edge_id 42 -> 126 base; +1/+2 halves, never plain 126
    # bidirectional: 2 halves x 2 directions each = 4 sub-edges, but each half's own interior
    # (1 point) means 2 segments per direction -> 2 halves x 2 segments x 2 directions = 8.
    assert len(extra_edges) == 8
    forward_from_u = [se for se in extra_edges if se.direction == 1 and se.base_edge_id == 127]
    assert forward_from_u[0].from_node == 0  # u-side half starts at the parent's u (label 0)
