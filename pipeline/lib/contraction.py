"""Pure structural chain contraction: collapses every run of degree-2 nodes (pass-through, no
route choice) into one edge carrying summed distance/road/ungraded/inferred length, the max
sac_scale rank walked, an OR'd via_ferrata flag, an AND-folded constrained_ok flag, and the full
interior polyline - lossless, since a degree-2 node has no alternate route through it. Unlike
build_hut_graph.py's version, this has NO knowledge of hub-snap points: V2 defers hub snapping to
lib/edge_split.py, which can split any contracted edge mid-chain, so the base graph this produces
is reusable across arbitrary future hub sets without rebuilding.

constrained_ok is AND-folded (not OR'd, unlike via_ferrata): one ungraded/excluded/via-ferrata
segment anywhere in the chain poisons the whole contracted edge for every constrained row (spec
C4) - the same reasoning as lib/grading.py's excluded_from_constrained docstring."""

from dataclasses import dataclass, field

import numpy as np


@dataclass
class ContractedGraph:
    coords: np.ndarray  # (n_nodes, 2) float64, (lon, lat)
    edges_u: np.ndarray
    edges_v: np.ndarray
    edges_dist: np.ndarray
    edges_road_m: np.ndarray
    edges_ungraded_m: np.ndarray
    edges_inferred_m: np.ndarray
    edges_sac_rank: np.ndarray
    edges_via_ferrata: np.ndarray
    edges_constrained_ok: np.ndarray
    interior_coords: list = field(default_factory=list)  # list[list[(lon, lat)]]


def contract_structural(coords, edges_i, edges_j, edges_dist, edges_road, edges_ungraded,
                         edges_inferred, edges_sac_rank, edges_via_ferrata, edges_constrained_ok,
                         progress_every: int = 0) -> ContractedGraph:
    """progress_every: print a progress line every N processed junction (keep) nodes - 0 (default)
    prints nothing, kept quiet for tests/callers that don't want console output. Junction-node
    count is much smaller than raw node count (the whole point of contraction), so a much smaller
    interval than stream_osm's way-count one makes sense here."""
    n_nodes = len(coords)
    n_edges = len(edges_i)
    edge_ids = np.arange(n_edges, dtype=np.int64)

    end_node = np.concatenate([edges_i, edges_j])
    end_other = np.concatenate([edges_j, edges_i])
    end_edge = np.concatenate([edge_ids, edge_ids])
    order = np.argsort(end_node, kind="stable")
    end_other = end_other[order]
    end_edge = end_edge[order]
    degree = np.bincount(end_node, minlength=n_nodes)
    offsets = np.zeros(n_nodes + 1, dtype=np.int64)
    np.cumsum(degree, out=offsets[1:])

    keep = degree != 2

    def _neighbors(node):
        s, e = offsets[node], offsets[node + 1]
        return end_other[s:e].tolist(), end_edge[s:e].tolist()

    visited_edge = np.zeros(n_edges, dtype=bool)
    c_u, c_v = [], []
    c_dist, c_road_m, c_ungraded_m, c_inferred_m = [], [], [], []
    c_sac_rank, c_via_ferrata, c_constrained_ok = [], [], []
    c_interior = []

    keep_idxs_list = np.flatnonzero(keep).tolist()
    total_keep = len(keep_idxs_list)
    for processed, k in enumerate(keep_idxs_list, start=1):
        if progress_every and processed % progress_every == 0:
            print(f"  contract_structural: {processed:,}/{total_keep:,} junction nodes "
                  f"processed -> {len(c_u):,} chain edges so far", flush=True)
        nbrs, edges_here = _neighbors(k)
        for nb, e in zip(nbrs, edges_here):
            if visited_edge[e]:
                continue
            visited_edge[e] = True
            d_sum = float(edges_dist[e])
            road_sum = d_sum if edges_road[e] else 0.0
            ungraded_sum = float(edges_ungraded[e])
            inferred_sum = float(edges_inferred[e])
            sac_max = int(edges_sac_rank[e])
            vf_any = bool(edges_via_ferrata[e])
            ok_all = bool(edges_constrained_ok[e])
            interior = []
            cur = nb
            prev_edge = e
            while not keep[cur]:
                interior.append((float(coords[cur, 0]), float(coords[cur, 1])))
                cnbrs, cedges = _neighbors(cur)
                nxt = None
                for nb2, e2 in zip(cnbrs, cedges):
                    if e2 != prev_edge:
                        nxt = (nb2, e2)
                        break
                if nxt is None:
                    break
                nb2, e2 = nxt
                visited_edge[e2] = True
                d_sum += edges_dist[e2]
                if edges_road[e2]:
                    road_sum += edges_dist[e2]
                ungraded_sum += edges_ungraded[e2]
                inferred_sum += edges_inferred[e2]
                if edges_sac_rank[e2] > sac_max:
                    sac_max = int(edges_sac_rank[e2])
                if edges_via_ferrata[e2]:
                    vf_any = True
                if not edges_constrained_ok[e2]:
                    ok_all = False
                prev_edge, cur = e2, nb2
            c_u.append(k)
            c_v.append(cur)
            c_dist.append(d_sum)
            c_road_m.append(road_sum)
            c_ungraded_m.append(ungraded_sum)
            c_inferred_m.append(inferred_sum)
            c_sac_rank.append(sac_max)
            c_via_ferrata.append(vf_any)
            c_constrained_ok.append(ok_all)
            c_interior.append(interior)

    keep_idxs = np.flatnonzero(keep)
    new_index = np.full(n_nodes, -1, dtype=np.int64)
    new_index[keep_idxs] = np.arange(len(keep_idxs))

    return ContractedGraph(
        coords=coords[keep_idxs],
        edges_u=new_index[np.array(c_u, dtype=np.int64)],
        edges_v=new_index[np.array(c_v, dtype=np.int64)],
        edges_dist=np.array(c_dist),
        edges_road_m=np.array(c_road_m),
        edges_ungraded_m=np.array(c_ungraded_m),
        edges_inferred_m=np.array(c_inferred_m),
        edges_sac_rank=np.array(c_sac_rank, dtype=np.int8),
        edges_via_ferrata=np.array(c_via_ferrata, dtype=bool),
        edges_constrained_ok=np.array(c_constrained_ok, dtype=bool),
        interior_coords=c_interior,
    )
