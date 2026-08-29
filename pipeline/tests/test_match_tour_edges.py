import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from graph_building.match_tour_edges import build_tour_legs  # noqa: E402


def _tour(hut_indices, is_loop=False):
    return {"tourId": 0, "hutIndices": hut_indices, "isLoop": is_loop}


def test_open_tour_yields_n_minus_one_legs():
    legs = build_tour_legs(_tour([0, 1, 2, 3]))
    assert legs == [(0, 0, 1), (1, 1, 2), (2, 2, 3)]


def test_loop_tour_yields_n_legs_with_contiguous_leg_index():
    # spec §2.1 / Testing: a loop tour yields N legs, not N-1, and leg_index is contiguous -
    # the closing leg (last hut -> first hut) is appended.
    legs = build_tour_legs(_tour([0, 1, 2], is_loop=True))
    assert legs == [(0, 0, 1), (1, 1, 2), (2, 2, 0)]
    assert [leg[0] for leg in legs] == [0, 1, 2]


def test_unresolved_hut_sentinel_splits_the_chain():
    # -1 (fetch_tours.py's unresolved-GUID sentinel) drops BOTH legs touching it, not just one -
    # never silently fuses the two real stages on either side into one leg (spec §1).
    legs = build_tour_legs(_tour([0, 1, -1, 3, 4]))
    assert legs == [(0, 0, 1), (3, 3, 4)]


def test_empty_hut_list_yields_no_legs():
    assert build_tour_legs(_tour([])) == []


def test_single_hut_yields_no_legs():
    assert build_tour_legs(_tour([0])) == []


import numpy as np

from lib import binfmt  # noqa: E402
from lib.grid import Grid  # noqa: E402
from lib.hub_snap import PersistedSnap  # noqa: E402
from lib.subgraph import LocalSubgraph  # noqa: E402
from graph_building.match_tour_edges import corridor_bounds, match_leg  # noqa: E402

BBOX = {"minLng": 0.0, "maxLng": 1.0, "minLat": 0.0, "maxLat": 1.0}


def test_corridor_bounds_pads_the_points_bbox():
    grid = Grid(BBOX, tile_size_km=20.0)
    points = [(0.5, 0.5), (0.51, 0.5), (0.52, 0.5)]
    bounds = corridor_bounds(points, buffer_m=150.0, grid=grid)
    assert bounds["minLng"] < 0.5
    assert bounds["maxLng"] > 0.52
    assert bounds["minLat"] < 0.5
    assert bounds["maxLat"] > 0.5


def _line_subgraph_1000m():
    nodes = np.zeros(2, dtype=binfmt.NODE_DTYPE)
    nodes[0] = (0.0, 0.0, 0)
    nodes[1] = (0.009, 0.0, 0)  # ~1000m east at the equator
    edges = np.zeros(1, dtype=binfmt.EDGE_DTYPE)
    edges[0] = (0, 1, 1000.0, 0.0, 0.0, 0.0, 1000.0, 30.0, 10.0, -1, False, True, 0, 0, 0)
    interior = np.zeros(0, dtype=binfmt.COORD_DTYPE)
    return LocalSubgraph(
        global_node_ids=np.array([100, 101]), local_nodes=nodes, local_edges=edges,
        interior=interior,
        local_node_ele=np.zeros(2, dtype=np.float32), interior_ele=np.zeros(0, dtype=np.float32),
    )


def _node_snap(global_node_id, gap_m=0.0, gap_dz_m=0.0):
    return PersistedSnap(kind=binfmt.SNAP_KIND_NODE, global_node_id=global_node_id,
                          gap_m=gap_m, gap_dz_m=gap_dz_m)


def test_match_leg_routes_a_simple_corridor():
    subgraph = _line_subgraph_1000m()
    src_key, tgt_key = (binfmt.TYPE_HUT, 0), (binfmt.TYPE_HUT, 1)
    persisted = {src_key: _node_snap(100), tgt_key: _node_snap(101)}
    result = match_leg(subgraph, src_key, tgt_key, persisted, trace_length_m=1000.0,
                        length_divergence_ratio=2.0)
    assert result["ok"] is True
    assert result["path"].distance_m == 1000.0


def test_match_leg_reports_hut_unsnapped_when_src_missing():
    subgraph = _line_subgraph_1000m()
    src_key, tgt_key = (binfmt.TYPE_HUT, 0), (binfmt.TYPE_HUT, 1)
    persisted = {tgt_key: _node_snap(101)}  # src_key never snapped
    result = match_leg(subgraph, src_key, tgt_key, persisted, trace_length_m=1000.0,
                        length_divergence_ratio=2.0)
    assert result == {"ok": False, "reason": "hut_unsnapped", "detail": {"missing": [src_key]}}


def test_match_leg_reports_outside_extract_when_corridor_is_empty():
    empty = LocalSubgraph(
        global_node_ids=np.zeros(0, dtype=np.int64),
        local_nodes=np.zeros(0, dtype=binfmt.NODE_DTYPE),
        local_edges=np.zeros(0, dtype=binfmt.EDGE_DTYPE),
        interior=np.zeros(0, dtype=binfmt.COORD_DTYPE),
        local_node_ele=np.zeros(0, dtype=np.float32), interior_ele=np.zeros(0, dtype=np.float32),
    )
    src_key, tgt_key = (binfmt.TYPE_HUT, 0), (binfmt.TYPE_HUT, 1)
    result = match_leg(empty, src_key, tgt_key, {}, trace_length_m=1000.0,
                        length_divergence_ratio=2.0)
    assert result["reason"] == "outside_extract"


def test_match_leg_reports_length_divergent_when_routed_far_exceeds_trace():
    subgraph = _line_subgraph_1000m()
    src_key, tgt_key = (binfmt.TYPE_HUT, 0), (binfmt.TYPE_HUT, 1)
    persisted = {src_key: _node_snap(100), tgt_key: _node_snap(101)}
    # routed 1000m vs a trace of only 100m - ratio 10x, past the 2.0 divergence ratio.
    result = match_leg(subgraph, src_key, tgt_key, persisted, trace_length_m=100.0,
                        length_divergence_ratio=2.0)
    assert result["reason"] == "length_divergent"
