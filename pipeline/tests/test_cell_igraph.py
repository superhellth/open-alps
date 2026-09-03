import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import binfmt  # noqa: E402
from lib.cell_igraph import accumulate_path, build_igraph_with_snaps  # noqa: E402
from lib.hub_snap import SnapResult  # noqa: E402
from lib.subgraph import LocalSubgraph  # noqa: E402


def _one_edge_subgraph(u: int, v: int, ascent_m: float, descent_m: float) -> LocalSubgraph:
    """Two local nodes joined by one edge inserted as (u, v) - callers pick which of {0, 1} is u
    to control whether it's > or < the local v index, which is exactly what determines whether
    igraph's undirected-edge canonicalization swaps source/target relative to insertion (see
    lib/cell_igraph.py's build_igraph_from_base). Node 0 sits at (10.0, 50.0), node 1 at
    (10.01, 50.0); the edge's one interior point sits near node 1's side, so a correct forward/
    reverse walk is distinguishable by which end of `interior` comes out first."""
    local_nodes = np.zeros(2, dtype=binfmt.NODE_DTYPE)
    local_nodes["lon"] = [10.0, 10.01]
    local_nodes["lat"] = [50.0, 50.0]

    local_edges = np.zeros(1, dtype=binfmt.EDGE_DTYPE)
    local_edges[0] = (u, v, 1000.0, 0.0, 0.0, 0.0, 1000.0, ascent_m, descent_m,
                       1, False, True, 0, 1, 42)

    interior = np.zeros(1, dtype=binfmt.COORD_DTYPE)
    interior[0] = (10.0066, 50.0)  # near node 1's side, when walked u(1)->v(0)

    return LocalSubgraph(
        global_node_ids=np.array([100, 101]),
        local_nodes=local_nodes,
        local_edges=local_edges,
        interior=interior,
        local_node_ele=np.zeros(2, dtype=np.float32),
        interior_ele=np.zeros(1, dtype=np.float32),
    )


def _route(subgraph, src_vertex, tgt_vertex):
    hub_snaps = {
        "src": SnapResult(node_index=src_vertex, edge_local_index=None, split=None,
                           gap_m=0.0, gap_dz_m=0.0),
        "tgt": SnapResult(node_index=tgt_vertex, edge_local_index=None, split=None,
                           gap_m=0.0, gap_dz_m=0.0),
    }
    graph, hub_vertex, vertex_coords = build_igraph_with_snaps(subgraph, hub_snaps)
    src_v, tgt_v = hub_vertex["src"], hub_vertex["tgt"]
    epath = graph.get_shortest_paths(src_v, to=tgt_v, weights="weight", output="epath")[0]
    return accumulate_path(graph, vertex_coords, src_v, tgt_v, epath)


def test_interior_direction_survives_igraph_source_target_canonicalization():
    # local u=1 > local v=0: igraph canonicalizes this edge's (source, target) to (0, 1),
    # the opposite of insertion order - accumulate_path must still walk 1->0 with the interior
    # UN-reversed (it was recorded in the 1->0 direction here).
    subgraph = _one_edge_subgraph(u=1, v=0, ascent_m=100.0, descent_m=50.0)

    forward_result = _route(subgraph, src_vertex=1, tgt_vertex=0)
    assert forward_result.coords == [(10.01, 50.0), (10.0066, 50.0), (10.0, 50.0)]
    assert forward_result.ascent_m == 100.0
    assert forward_result.descent_m == 50.0

    reverse_result = _route(subgraph, src_vertex=0, tgt_vertex=1)
    assert reverse_result.coords == [(10.0, 50.0), (10.0066, 50.0), (10.01, 50.0)]
    assert reverse_result.ascent_m == 50.0
    assert reverse_result.descent_m == 100.0


def test_interior_direction_when_local_u_is_already_the_smaller_index():
    # local u=0 < local v=1: igraph's canonical (source, target) already matches insertion order
    # here, so this is the case that was never broken - kept as a control alongside the swapped
    # case above.
    subgraph = _one_edge_subgraph(u=0, v=1, ascent_m=100.0, descent_m=50.0)

    forward_result = _route(subgraph, src_vertex=0, tgt_vertex=1)
    assert forward_result.coords == [(10.0, 50.0), (10.0066, 50.0), (10.01, 50.0)]
    assert forward_result.ascent_m == 100.0
    assert forward_result.descent_m == 50.0
