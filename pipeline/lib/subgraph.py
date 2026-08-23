"""Slices a persisted base graph (lib/binfmt.py, built by build_base_graph.py) down to one
worker's padded region (cell + buffer_km), for build_hub_edges.py's per-cell processes. Gather
is: (1) cell-union over grid.cell_ids_overlapping(padded_bounds) via cell_index.npy - a handful
of contiguous node-array slices, no full scan; (2) one-hop edge-incidence closure via
node_edge_index.npy/node_edge_ids.npy, pulling in any edge's far endpoint even if that
endpoint's own cell wasn't part of the cell union. See docs/superpowers/specs/
2026-08-19-pipeline-v2-design.md's correctness argument for why no further closure is needed:
every point on a valid <=maxEdgeKm path from a core-cell hub already lies within the padded
rectangle by construction (buffer_km == maxEdgeKm), this closure only catches the boundary case
where a node's cell falls just outside the padded rectangle while the node's coordinate is
still connected via an edge whose other endpoint is inside it."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from lib import binfmt


@dataclass
class LocalSubgraph:
    global_node_ids: np.ndarray
    local_nodes: np.ndarray
    local_edges: np.ndarray
    interior: np.ndarray
    # Absolute elevation (m) per point, aligned with local_nodes / the full interior array
    # respectively - not deltas (those live on local_edges as ascent_m/descent_m already).
    # Needed separately because a path's max elevation (max_ele_m, spec D1) can't be recovered
    # from per-edge ascent/descent sums alone: a col midway along a chain edge would be invisible
    # to a signed-delta sum, only to the absolute profile. Zeros (never None) when
    # node_ele.npy/interior_ele.npy don't exist yet (pre-elevation-pass base graph, or a test
    # fixture) so callers never need a None check.
    local_node_ele: np.ndarray
    interior_ele: np.ndarray


def gather_padded_subgraph(base_graph_dir: Path, grid, cell_id: int, buffer_km: float) -> LocalSubgraph:
    base_graph_dir = Path(base_graph_dir)
    nodes = binfmt.load_array(base_graph_dir / "nodes.npy")
    cell_index = binfmt.load_array(base_graph_dir / "cell_index.npy")
    node_edge_index = binfmt.load_array(base_graph_dir / "node_edge_index.npy")
    node_edge_ids = binfmt.load_array(base_graph_dir / "node_edge_ids.npy")
    edges = binfmt.load_array(base_graph_dir / "edges.npy")
    interior = binfmt.load_array(base_graph_dir / "interior.npy")
    node_ele_path = base_graph_dir / "node_ele.npy"
    interior_ele_path = base_graph_dir / "interior_ele.npy"
    node_ele = (binfmt.load_array(node_ele_path) if node_ele_path.exists()
                else np.zeros(len(nodes), dtype=np.float32))
    interior_ele = (binfmt.load_array(interior_ele_path) if interior_ele_path.exists()
                     else np.zeros(len(interior), dtype=np.float32))

    padded = grid.padded_bounds(cell_id, buffer_km)
    overlapping_cells = grid.cell_ids_overlapping(padded)

    if overlapping_cells:
        base_node_ids = np.unique(np.concatenate([
            np.arange(int(cell_index["start_offset"][cid]),
                      int(cell_index["start_offset"][cid] + cell_index["count"][cid]))
            for cid in overlapping_cells
        ]))
    else:
        base_node_ids = np.zeros(0, dtype=np.int64)

    # one-hop edge-incidence closure, vectorized via binfmt.gather_ragged over
    # node_edge_index/node_edge_ids's CSR layout instead of a per-node Python loop + tolist() -
    # was O(nodes in cell) at Python speed on a 60km cell (10^4-10^5 nodes).
    incident_edge_ids, _ = binfmt.gather_ragged(
        node_edge_ids, node_edge_index["start_offset"][base_node_ids],
        node_edge_index["count"][base_node_ids],
    )
    frontier_edge_ids = np.unique(incident_edge_ids)

    if len(frontier_edge_ids):
        # Every frontier edge's endpoints are unioned in here, so global_node_ids is guaranteed to
        # contain both u and v for every frontier edge below - no membership filter needed (the
        # old per-edge `if u in global_to_local and v in global_to_local` was always true).
        global_node_ids = np.unique(np.concatenate([
            base_node_ids, edges["u"][frontier_edge_ids], edges["v"][frontier_edge_ids],
        ]))
    else:
        global_node_ids = base_node_ids

    local_nodes = np.array(nodes[global_node_ids])

    local_edges = np.array(edges[frontier_edge_ids], dtype=binfmt.EDGE_DTYPE)
    if len(local_edges):
        # global_node_ids is sorted (np.unique), so searchsorted vectorizes the old
        # {global_id: local_index} dict + per-edge scalar lookup.
        local_edges["u"] = np.searchsorted(global_node_ids, local_edges["u"])
        local_edges["v"] = np.searchsorted(global_node_ids, local_edges["v"])

    return LocalSubgraph(
        global_node_ids=global_node_ids,
        local_nodes=local_nodes,
        local_edges=local_edges,
        # interior_offset/interior_count on local_edges index into the *global* interior array
        # unchanged (never remapped per-subgraph), so this can stay a lazy mmap view instead of
        # copying the whole (hundreds of MB for AT+Bayern) array on every call - only the slices
        # snap_hub_to_subgraph actually touches get paged in.
        interior=interior,
        local_node_ele=np.array(node_ele[global_node_ids]),
        # same "stay a lazy view, indexed by the untouched global offsets" reasoning as interior.
        interior_ele=interior_ele,
    )
