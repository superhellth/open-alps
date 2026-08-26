#!/usr/bin/env python3
"""Standalone analysis module - not part of the doit task graph, not imported by any phase script.

Rebuilds the raw (pre-contraction) node/edge arrays by un-contracting the already-persisted
data/osm/base_graph/, so contraction cost can be measured at any graph size without re-running
stream_osm (914s per attempt). Each chain edge e is the raw path u -> interior[offset..offset+
count) -> v; interior_offset is monotone in edge order, so raw node ids fall out as
n_junctions + flat_interior_index with no bookkeeping.

TIMING ONLY - NOT AN EQUIVALENCE FIXTURE. Three fields cannot be recovered at per-segment
granularity: which segments of a partially-road/ungraded/inferred chain carried that flag (chain
totals survive contraction; per-segment attribution does not, same reasoning as
lib/contraction.py's docstring). This sets each per-segment flag from the corresponding chain
total > 0, so reconstructed road_m/ungraded_m/inferred_m totals differ from the originals.
constrained_ok is chain-level already (an AND-fold, not a sum), so it broadcasts exactly.
Topology, coordinates, per-segment distances, sac_rank and via_ferrata are exact, which is
everything contraction's cost depends on.

See docs/superpowers/plans/2026-08-20-contraction-measurement-spike.md.

Usage: python pipeline/analysis/reconstruct_raw_graph.py [--base-graph data/osm/base_graph]
       (running it directly reconstructs the full graph and prints a size/consistency report)
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import binfmt  # noqa: E402
from lib.pipeline import OSM_DIR  # noqa: E402


@dataclass
class RawGraph:
    """Exactly contract_structural's ten positional arguments, in order."""
    coords: np.ndarray
    edges_i: np.ndarray
    edges_j: np.ndarray
    edges_dist: np.ndarray
    edges_road: np.ndarray
    edges_ungraded: np.ndarray
    edges_inferred: np.ndarray
    edges_sac_rank: np.ndarray
    edges_via_ferrata: np.ndarray
    edges_constrained_ok: np.ndarray

    def as_args(self):
        return (self.coords, self.edges_i, self.edges_j, self.edges_dist, self.edges_road,
                self.edges_ungraded, self.edges_inferred, self.edges_sac_rank,
                self.edges_via_ferrata, self.edges_constrained_ok)


def _haversine_m_vec(lon1, lat1, lon2, lat2):
    # same formula and earth radius as build_base_graph.py's haversine_m_vec, so reconstructed
    # segment distances sum back to the persisted chain distances
    r = 6_371_000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlambda / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def select_edges_in_cells(nodes, edges, cell_ids) -> np.ndarray:
    """Chain edge ids whose u endpoint's home cell is in cell_ids. Selecting by u (not by both
    endpoints) keeps boundary-crossing chains in the subset, which is what makes a subset look
    like a real region rather than a set of disconnected cell interiors."""
    wanted = np.zeros(int(np.asarray(nodes["cell_id"]).max()) + 1, dtype=bool)
    for cid in cell_ids:
        if 0 <= cid < len(wanted):
            wanted[cid] = True
    u_cells = np.asarray(nodes["cell_id"])[np.asarray(edges["u"])]
    return np.flatnonzero(wanted[u_cells]).astype(np.int64)


def reconstruct_raw(nodes, edges, interior, edge_ids) -> RawGraph:
    edge_ids = np.asarray(edge_ids, dtype=np.int64)
    sel = edges[edge_ids]
    n_j = len(nodes)

    starts = np.asarray(sel["interior_offset"], dtype=np.int64)
    counts = np.asarray(sel["interior_count"], dtype=np.int64)

    # --- provisional raw node ids: junctions keep 0..n_j-1, interior point k of the flat
    # interior array becomes n_j + k. Sparse for a subset; compacted at the end. ---
    seg_counts = counts + 1                      # a chain of c interior points has c+1 segments
    pos = binfmt.ragged_positions(seg_counts)    # 0..counts[e] within each chain
    eidx = np.repeat(np.arange(len(sel), dtype=np.int64), seg_counts)

    tail = np.where(pos == 0,
                    np.asarray(sel["u"], dtype=np.int64)[eidx],
                    n_j + starts[eidx] + pos - 1)
    head = np.where(pos == counts[eidx],
                    np.asarray(sel["v"], dtype=np.int64)[eidx],
                    n_j + starts[eidx] + pos)

    # --- compact the sparse id space, and gather coords for exactly the nodes used ---
    used = np.unique(np.concatenate([tail, head]))
    edges_i = np.searchsorted(used, tail)
    edges_j = np.searchsorted(used, head)

    coords = np.empty((len(used), 2), dtype=np.float64)
    is_junction = used < n_j
    j_ids = used[is_junction]
    coords[is_junction, 0] = np.asarray(nodes["lon"])[j_ids]
    coords[is_junction, 1] = np.asarray(nodes["lat"])[j_ids]
    i_ids = used[~is_junction] - n_j
    coords[~is_junction, 0] = np.asarray(interior["lon"])[i_ids]
    coords[~is_junction, 1] = np.asarray(interior["lat"])[i_ids]

    edges_dist = _haversine_m_vec(coords[edges_i, 0], coords[edges_i, 1],
                                  coords[edges_j, 0], coords[edges_j, 1])

    # per-chain fields broadcast to that chain's segments; road/ungraded/inferred are lossy (see
    # docstring) - only their per-chain totals survive contraction, not per-segment attribution.
    edges_road = (np.asarray(sel["road_m"]) > 0)[eidx]
    edges_ungraded = np.where((np.asarray(sel["ungraded_m"]) > 0)[eidx], edges_dist, 0.0)
    edges_inferred = np.where((np.asarray(sel["inferred_m"]) > 0)[eidx], edges_dist, 0.0)
    edges_sac_rank = np.asarray(sel["sac_rank"], dtype=np.int8)[eidx]
    edges_via_ferrata = np.asarray(sel["via_ferrata"], dtype=bool)[eidx]
    edges_constrained_ok = np.asarray(sel["constrained_ok"], dtype=bool)[eidx]

    return RawGraph(coords, edges_i, edges_j, edges_dist, edges_road, edges_ungraded,
                    edges_inferred, edges_sac_rank, edges_via_ferrata, edges_constrained_ok)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-graph", default=str(OSM_DIR / "base_graph"))
    args = parser.parse_args(argv)

    d = Path(args.base_graph)
    nodes = binfmt.load_array(d / "nodes.npy")
    edges = binfmt.load_array(d / "edges.npy")
    interior = binfmt.load_array(d / "interior.npy")
    print(f"base_graph: {len(nodes):,} nodes, {len(edges):,} chain edges, "
          f"{len(interior):,} interior points", flush=True)

    raw = reconstruct_raw(nodes, edges, interior, np.arange(len(edges)))
    print(f"reconstructed raw: {len(raw.coords):,} nodes, {len(raw.edges_i):,} edges", flush=True)

    expected_nodes = len(nodes) + len(interior)
    expected_edges = len(edges) + len(interior)
    print(f"  node count identity: {len(raw.coords):,} vs expected {expected_nodes:,} "
          f"({'OK' if len(raw.coords) == expected_nodes else 'MISMATCH'})", flush=True)
    print(f"  edge count identity: {len(raw.edges_i):,} vs expected {expected_edges:,} "
          f"({'OK' if len(raw.edges_i) == expected_edges else 'MISMATCH'})", flush=True)

    got, want = float(raw.edges_dist.sum()), float(np.asarray(edges["dist"]).sum())
    rel = abs(got - want) / want
    print(f"  distance identity: {got:,.1f} m vs {want:,.1f} m, rel err {rel:.2e} "
          f"({'OK' if rel < 1e-6 else 'MISMATCH'})", flush=True)


if __name__ == "__main__":
    main()
