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
