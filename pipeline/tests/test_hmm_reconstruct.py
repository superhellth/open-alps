import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.hmm_match import LegMap, SubEdge
from lib.hmm_reconstruct import reconstruct_matched_path


def _line_leg_map():
    # 0 -(a)-> 1 -(b)-> 2, plus a dead-end spur 1 -(c)-> 3, all bidirectional.
    def se(frm, to, base_id, direction, dist, road=0.0, ungraded=0.0, inferred=None):
        return SubEdge(
            from_node=frm, to_node=to, base_edge_id=base_id, direction=direction,
            segment_index=0, dist_m=dist, road_m=road, ungraded_m=ungraded,
            inferred_m=dist if inferred is None else inferred,
            ascent_m=10.0 if direction == 1 else 4.0, descent_m=4.0 if direction == 1 else 10.0,
            max_ele_m=1500.0, sac_rank=1, via_ferrata=False,
        )
    sub_edges = [
        se(0, 1, 3, 1, 200.0), se(1, 0, 3, -1, 200.0),
        se(1, 2, 6, 1, 300.0), se(2, 1, 6, -1, 300.0),
        se(1, 3, 9, 1, 150.0), se(3, 1, 9, -1, 150.0),
    ]
    node_coords = {0: (0.0, 0.0), 1: (0.002, 0.0), 2: (0.005, 0.0), 3: (0.002, 0.002)}
    return LegMap(inmem_map=None, sub_edges=sub_edges, src_anchor=0, tgt_anchor=2), node_coords


def test_reconstruct_matched_path_walks_a_simple_through_path():
    leg_map, node_coords = _line_leg_map()
    path = reconstruct_matched_path(leg_map, node_path=[0, 1, 2])
    assert path.distance_m == 500.0
    assert path.base_edge_ids == [3, 6]
    assert path.ascent_m == 20.0 and path.descent_m == 8.0  # both forward segments


def test_reconstruct_matched_path_does_not_dedupe_an_out_and_back_spur():
    leg_map, node_coords = _line_leg_map()
    # trace out to the spur (node 3) and back through 1 before continuing to 2.
    path = reconstruct_matched_path(leg_map, node_path=[0, 1, 3, 1, 2])
    assert path.distance_m == 200.0 + 150.0 + 150.0 + 300.0  # spur walked twice, not collapsed
    assert path.base_edge_ids == [3, 9, 9, 6]
    # outbound spur (dir +1): ascent 10/descent 4; inbound (dir -1): ascent 4/descent 10.
    assert path.ascent_m == 10.0 + 10.0 + 4.0 + 10.0  # 0->1, 1->3, 3->1, 1->2 in order
    assert path.descent_m == 4.0 + 4.0 + 10.0 + 4.0


def test_reconstruct_matched_path_apportions_a_turnaround_mid_edge():
    # An edge with 2 interior points expands (Task 5) into 3 segments per direction; a decode
    # that turns around at the middle interior node walks only 2 of those 3 segments each way -
    # exactly spec §5's apportionment, achieved for free by segment-level expansion.
    from lib.hmm_match import SubEdge

    leg_map, _ = _line_leg_map()
    seg_a = SubEdge(from_node=1, to_node=10, base_edge_id=6, direction=1, segment_index=0,
                     dist_m=100.0, road_m=0.0, ungraded_m=0.0, inferred_m=100.0,
                     ascent_m=5.0, descent_m=1.0, max_ele_m=1400.0, sac_rank=1, via_ferrata=False)
    seg_b = SubEdge(from_node=10, to_node=2, base_edge_id=6, direction=1, segment_index=1,
                     dist_m=200.0, road_m=0.0, ungraded_m=0.0, inferred_m=200.0,
                     ascent_m=15.0, descent_m=3.0, max_ele_m=1500.0, sac_rank=1, via_ferrata=False)
    leg_map.sub_edges = [se for se in leg_map.sub_edges if se.base_edge_id != 6] + [seg_a, seg_b]

    # turnaround happens exactly at node 10 (the middle interior point) - only seg_a is walked.
    path = reconstruct_matched_path(leg_map, node_path=[0, 1, 10])
    assert path.distance_m == 200.0 + 100.0  # edge 0->1 (200) + partial edge 6 up to node 10
    assert path.base_edge_ids == [3, 6]
    assert path.ascent_m == 10.0 + 5.0  # 0->1's ascent + seg_a's own apportioned ascent


def test_reconcile_endpoints_no_op_when_anchor_already_first_and_last():
    from lib.hmm_reconstruct import reconcile_endpoints

    leg_map, _ = _line_leg_map()  # src_anchor=0, tgt_anchor=2
    result = reconcile_endpoints(subgraph=None, leg_map=leg_map, node_path=[0, 1, 2],
                                  endpoint_bridge_max_m=250.0)
    assert result == [0, 1, 2]


def test_reconcile_endpoints_trims_states_before_the_anchor():
    from lib.hmm_reconstruct import reconcile_endpoints

    leg_map, _ = _line_leg_map()
    # decode ran past node 0 before turning up the real leg direction - anchor 0 appears mid-path.
    result = reconcile_endpoints(subgraph=None, leg_map=leg_map, node_path=[3, 1, 0, 1, 2],
                                  endpoint_bridge_max_m=250.0)
    assert result == [0, 1, 2]


import numpy as np
from lib import binfmt
from lib.subgraph import LocalSubgraph


def _corridor_with_gap_to_anchor():
    """Anchor node 0 sits 80m off the decoded path's own start (node 1) via a short connector
    edge 0->1 - short enough to bridge (spec §2's bridge case)."""
    nodes = np.zeros(3, dtype=binfmt.NODE_DTYPE)
    nodes[0] = (0.0, 0.0, 0)
    nodes[1] = (0.0007, 0.0, 0)  # ~80m east
    nodes[2] = (0.005, 0.0, 0)
    edges = np.zeros(2, dtype=binfmt.EDGE_DTYPE)
    edges[0] = (0, 1, 80.0, 0.0, 0.0, 0.0, 80.0, 2.0, 0.0, 1, False, True, 0, 0, 100)
    edges[1] = (1, 2, 300.0, 0.0, 0.0, 0.0, 300.0, 10.0, 2.0, 1, False, True, 0, 0, 101)
    return LocalSubgraph(
        global_node_ids=np.array([0, 1, 2]), local_nodes=nodes, local_edges=edges,
        interior=np.zeros(0, dtype=binfmt.COORD_DTYPE),
        local_node_ele=np.zeros(3, dtype=np.float32), interior_ele=np.zeros(0, dtype=np.float32),
    )


def test_reconcile_endpoints_bridges_when_anchor_is_off_the_decoded_path():
    from lib.hmm_reconstruct import reconcile_endpoints

    subgraph = _corridor_with_gap_to_anchor()
    leg_map = LegMap(inmem_map=None, sub_edges=[
        SubEdge(from_node=1, to_node=2, base_edge_id=303, direction=1, segment_index=0,
                dist_m=300.0, road_m=0.0, ungraded_m=0.0, inferred_m=300.0,
                ascent_m=10.0, descent_m=2.0, max_ele_m=1000.0, sac_rank=1, via_ferrata=False),
    ], src_anchor=0, tgt_anchor=2)

    result = reconcile_endpoints(subgraph=subgraph, leg_map=leg_map, node_path=[1, 2],
                                  endpoint_bridge_max_m=250.0)
    assert result[0] == 0  # bridged in from anchor 0
    assert result[-1] == 2


def test_reconcile_endpoints_reports_bridge_too_long_past_the_cap():
    from lib.hmm_reconstruct import reconcile_endpoints, BridgeTooLong

    subgraph = _corridor_with_gap_to_anchor()
    leg_map = LegMap(inmem_map=None, sub_edges=[
        SubEdge(from_node=1, to_node=2, base_edge_id=303, direction=1, segment_index=0,
                dist_m=300.0, road_m=0.0, ungraded_m=0.0, inferred_m=300.0,
                ascent_m=10.0, descent_m=2.0, max_ele_m=1000.0, sac_rank=1, via_ferrata=False),
    ], src_anchor=0, tgt_anchor=2)

    result = reconcile_endpoints(subgraph=subgraph, leg_map=leg_map, node_path=[1, 2],
                                  endpoint_bridge_max_m=50.0)  # cap below the 80m gap
    assert isinstance(result, BridgeTooLong)
    assert result.endpoint == "from"
    assert result.cap_m == 50.0
    assert result.bridge_m > 50.0
