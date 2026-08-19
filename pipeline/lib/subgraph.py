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


def gather_padded_subgraph(base_graph_dir: Path, grid, cell_id: int, buffer_km: float) -> LocalSubgraph:
    base_graph_dir = Path(base_graph_dir)
    nodes = binfmt.load_array(base_graph_dir / "nodes.npy")
    cell_index = binfmt.load_array(base_graph_dir / "cell_index.npy")
    node_edge_index = binfmt.load_array(base_graph_dir / "node_edge_index.npy")
    node_edge_ids = binfmt.load_array(base_graph_dir / "node_edge_ids.npy")
    edges = binfmt.load_array(base_graph_dir / "edges.npy")
    interior = binfmt.load_array(base_graph_dir / "interior.npy")

    padded = grid.padded_bounds(cell_id, buffer_km)
    overlapping_cells = grid.cell_ids_overlapping(padded)

    node_id_set = set()
    for cid in overlapping_cells:
        start, count = cell_index["start_offset"][cid], cell_index["count"][cid]
        node_id_set.update(range(int(start), int(start + count)))

    # one-hop edge-incidence closure
    frontier_edge_ids = set()
    for node_id in list(node_id_set):
        start, count = node_edge_index["start_offset"][node_id], node_edge_index["count"][node_id]
        frontier_edge_ids.update(node_edge_ids[start:start + count].tolist())
    for edge_id in frontier_edge_ids:
        e = edges[edge_id]
        node_id_set.add(int(e["u"]))
        node_id_set.add(int(e["v"]))

    global_node_ids = np.array(sorted(node_id_set), dtype=np.int64)
    global_to_local = {int(g): i for i, g in enumerate(global_node_ids)}

    local_nodes = np.array(nodes[global_node_ids])

    local_edges_list = [
        edges[edge_id] for edge_id in sorted(frontier_edge_ids)
        if int(edges[edge_id]["u"]) in global_to_local and int(edges[edge_id]["v"]) in global_to_local
    ]
    local_edges = np.array(local_edges_list, dtype=binfmt.EDGE_DTYPE)
    if len(local_edges):
        local_edges["u"] = [global_to_local[int(u)] for u in local_edges["u"]]
        local_edges["v"] = [global_to_local[int(v)] for v in local_edges["v"]]

    return LocalSubgraph(
        global_node_ids=global_node_ids,
        local_nodes=local_nodes,
        local_edges=local_edges,
        interior=np.array(interior),
    )
