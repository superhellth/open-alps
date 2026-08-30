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


def gather_subgraph_for_bounds(base_graph_dir: Path, grid, bounds: dict) -> LocalSubgraph:
    """Gathers every base-graph node/edge whose cell overlaps `bounds`, plus the one-hop edge-
    incidence closure (see module docstring) - the bbox-driven half of gather_padded_subgraph,
    factored out so a caller with its own bbox (match_tour_edges.py's per-leg corridor, sized off
    a chain slice rather than a grid cell) can reuse the exact same gather instead of re-deriving
    it from a cell_id it doesn't have."""
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

    overlapping_cells = grid.cell_ids_overlapping(bounds)

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


def gather_padded_subgraph(base_graph_dir: Path, grid, cell_id: int, buffer_km: float) -> LocalSubgraph:
    return gather_subgraph_for_bounds(base_graph_dir, grid, grid.padded_bounds(cell_id, buffer_km))


def clip_subgraph_to_bounds(subgraph: LocalSubgraph, bounds: dict) -> LocalSubgraph:
    """Narrows an already-gathered subgraph down to `bounds` at node/edge granularity, plus a
    one-hop edge-incidence closure (same reasoning as gather_subgraph_for_bounds's cell-level
    closure) so a path can still leave through an edge whose far endpoint sits just outside the
    box. Needed because gather_subgraph_for_bounds only filters by whole grid cell - fine for
    build_hub_edges.py (buffer_km == maxEdgeKm, so a padded cell IS the correct extent), but a
    no-op for match_tour_edges.py's per-leg corridor (spec section 2.3): a tour leg's chain-slice
    bbox plus a ~150m buffer is almost always far smaller than one 60km base-graph cell, so
    without this step every leg of a tour routes over the SAME whole cell(s) regardless of the
    corridor buffer, degenerating into the free shortest path section 2.3 exists to prevent."""
    lon, lat = subgraph.local_nodes["lon"], subgraph.local_nodes["lat"]
    in_bounds = ((lon >= bounds["minLng"]) & (lon <= bounds["maxLng"])
                 & (lat >= bounds["minLat"]) & (lat <= bounds["maxLat"]))

    if len(subgraph.local_edges):
        edge_mask = in_bounds[subgraph.local_edges["u"]] | in_bounds[subgraph.local_edges["v"]]
        kept_edges = subgraph.local_edges[edge_mask]
    else:
        kept_edges = subgraph.local_edges

    core_ids = np.nonzero(in_bounds)[0]
    if len(kept_edges):
        keep_local_ids = np.unique(np.concatenate([core_ids, kept_edges["u"], kept_edges["v"]]))
    else:
        keep_local_ids = core_ids

    local_edges = np.array(kept_edges, dtype=binfmt.EDGE_DTYPE)
    if len(local_edges):
        local_edges["u"] = np.searchsorted(keep_local_ids, local_edges["u"])
        local_edges["v"] = np.searchsorted(keep_local_ids, local_edges["v"])

    return LocalSubgraph(
        global_node_ids=subgraph.global_node_ids[keep_local_ids],
        local_nodes=subgraph.local_nodes[keep_local_ids],
        local_edges=local_edges,
        interior=subgraph.interior,
        local_node_ele=subgraph.local_node_ele[keep_local_ids],
        interior_ele=subgraph.interior_ele,
    )


def save_local_subgraph(subgraph: LocalSubgraph, cell_dir: Path) -> None:
    """Persists one gather_padded_subgraph() result so a later process can reload it without
    re-running the cell union / one-hop closure / array-copy work (gather_route_subgraphs.py's
    whole point - see its module docstring). Only global_node_ids/local_nodes/local_edges/
    local_node_ele are written - these are the real per-cell COPIES gather_padded_subgraph makes.
    `interior`/`interior_ele` are deliberately NOT duplicated here (they stay the lazy, shared
    mmap view over the whole base graph's interior.npy/interior_ele.npy - see this module's
    top-of-file docstring on gather's cost breakdown); load_local_subgraph reopens those globally
    instead."""
    cell_dir = Path(cell_dir)
    cell_dir.mkdir(parents=True, exist_ok=True)
    binfmt.save_array(cell_dir / "global_node_ids.npy", subgraph.global_node_ids)
    binfmt.save_array(cell_dir / "local_nodes.npy", subgraph.local_nodes)
    binfmt.save_array(cell_dir / "local_edges.npy", subgraph.local_edges)
    binfmt.save_array(cell_dir / "local_node_ele.npy", subgraph.local_node_ele)


def load_local_subgraph(cell_dir: Path, base_graph_dir: Path) -> LocalSubgraph:
    """Inverse of save_local_subgraph - reloads a cached per-cell gather, re-attaching the shared
    global interior/interior_ele arrays (never persisted per-cell, see save_local_subgraph)."""
    cell_dir = Path(cell_dir)
    base_graph_dir = Path(base_graph_dir)
    interior = binfmt.load_array(base_graph_dir / "interior.npy")
    interior_ele_path = base_graph_dir / "interior_ele.npy"
    interior_ele = (binfmt.load_array(interior_ele_path) if interior_ele_path.exists()
                     else np.zeros(len(interior), dtype=np.float32))
    return LocalSubgraph(
        global_node_ids=binfmt.load_array(cell_dir / "global_node_ids.npy", mmap=False),
        local_nodes=binfmt.load_array(cell_dir / "local_nodes.npy", mmap=False),
        local_edges=binfmt.load_array(cell_dir / "local_edges.npy", mmap=False),
        interior=interior,
        local_node_ele=binfmt.load_array(cell_dir / "local_node_ele.npy", mmap=False),
        interior_ele=interior_ele,
    )
