import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import binfmt  # noqa: E402
from lib import hub_snap  # noqa: E402
from lib.subgraph import LocalSubgraph  # noqa: E402

TYPE_HUT = binfmt.TYPE_HUT


def _line_subgraph(global_node_ids, edge_id):
    # Two nodes 1000m apart (roughly, at these latitudes), one edge - a hub snapping anywhere on
    # it lands mid-chain (segment_index=0). edge_id is the STABLE global id (EDGE_DTYPE's own
    # field), independent of this subgraph's local ordering.
    nodes = np.zeros(2, dtype=binfmt.NODE_DTYPE)
    nodes[0] = (0.0, 0.0, 0)
    nodes[1] = (0.009, 0.0, 0)
    edges = np.zeros(1, dtype=binfmt.EDGE_DTYPE)
    edges[0] = (0, 1, 1000.0, 0.0, 0.0, 0.0, 1000.0, binfmt.UNSET, binfmt.UNSET, -1, False, True,
                0, 0, edge_id)
    interior = np.zeros(0, dtype=binfmt.COORD_DTYPE)
    return LocalSubgraph(
        global_node_ids=np.array(global_node_ids), local_nodes=nodes, local_edges=edges,
        interior=interior,
        local_node_ele=np.zeros(len(nodes), dtype=np.float32),
        interior_ele=np.zeros(len(interior), dtype=np.float32),
    )


def test_node_snap_round_trips_through_pack_and_load(tmp_path):
    subgraph = _line_subgraph([100, 101], edge_id=7)
    result = hub_snap.snap_hub_to_subgraph(subgraph, hub_lon=0.0001, hub_lat=0.0, max_snap_m=50.0)
    assert result.node_index == 0

    persisted = hub_snap.to_persisted(subgraph, result)
    assert persisted.kind == binfmt.SNAP_KIND_NODE
    assert persisted.global_node_id == 100   # global_node_ids[0]

    hub_snap.pack_hub_snaps({(TYPE_HUT, 1): persisted}, tmp_path)
    arr = binfmt.load_array(tmp_path / "hub_snaps.npy", mmap=False)
    interior_arr = binfmt.load_array(tmp_path / "hub_snap_interior.npy", mmap=False)
    reloaded = hub_snap.load_persisted_snaps(arr, interior_arr)
    assert reloaded[(TYPE_HUT, 1)].global_node_id == 100


def test_edge_split_snap_round_trips_through_pack_and_load(tmp_path):
    subgraph = _line_subgraph([100, 101], edge_id=7)
    result = hub_snap.snap_hub_to_subgraph(subgraph, hub_lon=0.0045, hub_lat=0.0002, max_snap_m=50.0)
    assert result.split is not None

    persisted = hub_snap.to_persisted(subgraph, result)
    assert persisted.kind == binfmt.SNAP_KIND_EDGE
    assert persisted.global_edge_id == 7   # local_edges["edge_id"][0], NOT the local index 0

    hub_snap.pack_hub_snaps({(TYPE_HUT, 2): persisted}, tmp_path)
    arr = binfmt.load_array(tmp_path / "hub_snaps.npy", mmap=False)
    interior_arr = binfmt.load_array(tmp_path / "hub_snap_interior.npy", mmap=False)
    reloaded = hub_snap.load_persisted_snaps(arr, interior_arr)
    got = reloaded[(TYPE_HUT, 2)]
    assert got.global_edge_id == 7
    assert got.split_coord == result.split.split_coord
    assert got.dist_to_u == result.split.dist_to_u


def test_reconstruct_local_snaps_survives_a_different_subgraph_ordering():
    # The whole point of persisting by GLOBAL id: a node snap computed against one gather (small
    # buffer, node landing at LOCAL index 0) must still resolve correctly against a totally
    # different gather (large buffer) where the same GLOBAL node sits at a different local index
    # (here: index 1, with an extra unrelated node inserted before it).
    small_subgraph = _line_subgraph([100, 101], edge_id=7)
    result = hub_snap.snap_hub_to_subgraph(small_subgraph, hub_lon=0.0001, hub_lat=0.0, max_snap_m=50.0)
    assert result.node_index == 0
    persisted = {(TYPE_HUT, 1): hub_snap.to_persisted(small_subgraph, result)}

    # A "larger" gather with an extra node (global id 99) inserted before global id 100 - global
    # id 100 now sits at local index 1, not 0.
    nodes = np.zeros(3, dtype=binfmt.NODE_DTYPE)
    nodes[0] = (5.0, 5.0, 0)     # unrelated extra node, global id 99
    nodes[1] = (0.0, 0.0, 0)     # global id 100 - same node the small gather snapped to
    nodes[2] = (0.009, 0.0, 0)   # global id 101
    edges = np.zeros(1, dtype=binfmt.EDGE_DTYPE)
    edges[0] = (1, 2, 1000.0, 0.0, 0.0, 0.0, 1000.0, binfmt.UNSET, binfmt.UNSET, -1, False, True,
                0, 0, 7)
    interior = np.zeros(0, dtype=binfmt.COORD_DTYPE)
    large_subgraph = LocalSubgraph(
        global_node_ids=np.array([99, 100, 101]), local_nodes=nodes, local_edges=edges,
        interior=interior,
        local_node_ele=np.zeros(3, dtype=np.float32),
        interior_ele=np.zeros(0, dtype=np.float32),
    )

    local_snaps = hub_snap.reconstruct_local_snaps(large_subgraph, [(TYPE_HUT, 1)], persisted)
    assert local_snaps[(TYPE_HUT, 1)].node_index == 1  # NOT 0 - correctly re-resolved


def test_reconstruct_local_snaps_omits_a_key_missing_from_persisted():
    # A hub that snap_hubs.py rejected (SnapRejection) never gets a PersistedSnap entry - a
    # route-task cell asking for it must just skip it, not raise.
    subgraph = _line_subgraph([100, 101], edge_id=7)
    out = hub_snap.reconstruct_local_snaps(subgraph, [(TYPE_HUT, 999)], {})
    assert out == {}
