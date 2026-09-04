"""Builds a routable igraph.Graph from a lib/subgraph.py LocalSubgraph + hub snaps, and walks/
accumulates a shortest path off the result. Extracted out of build_hub_edges.py (which still owns
the per-cell routing loop that calls this) because it's reusable, dependency-free plumbing that a
second caller - pipeline/analysis/routing_probe.py - already needed directly, the same reason
lib/hub_snap.py exists instead of hub-snapping living inline in a phase script.

build_base_igraph_arrays()/build_igraph_from_base() are split in two because only the topology
build (base) depends on the subgraph+snaps, while which edges survive (a variant's edge_mask) does
not - see build_base_igraph_arrays' docstring. build_igraph_with_snaps() is the thin single-call
convenience over both, for a caller routing exactly one variant."""

import dataclasses
from collections import namedtuple

import igraph as ig
import numpy as np

from lib.subgraph import LocalSubgraph


@dataclasses.dataclass
class BaseIgraphArrays:
    """Everything build_igraph_with_snaps used to recompute from scratch on EVERY variant, even
    though none of it actually depends on the variant - only which edges end up kept does (spec
    C2's masked-subgraph-per-row). Built once per cell by build_base_igraph_arrays; each variant
    then only needs to compute its own boolean kept-mask and re-run ig.Graph's cheap C-level
    filter/construction, instead of redoing the Python-level tolist()/max()/interior-list-comp
    work (subgraph.local_edges columns, once per variant = O(variants * edges) before this)."""
    next_vertex: int
    n_orig: int
    edges_uv: list
    dists: list
    times: list
    road_ms: list
    ungraded_ms: list
    inferred_ms: list
    ascent_ms: list
    descent_ms: list
    sac_ranks: list
    via_ferratas: list
    constrained_oks: list
    interiors: list
    max_ele_ms: list
    vertex_ele_ms: list
    vertex_coords: dict
    hub_vertex: dict
    edges_to_remove: set
    # edge_source[i] is which ORIGINAL local edge index (0..n_orig-1) edge i's mask value should
    # come from: i itself for i < n_orig, or the parent edge a synthetic (split) edge inherited
    # its terrain from for i >= n_orig - a variant's edge_mask() only covers the n_orig original
    # edges, so a synthetic edge has no mask entry of its own.
    edge_source: list
    # base_edge_ids[i] is the disambiguated global base-graph edge id for igraph edge i - see
    # this module's build_base_igraph_arrays for the split-half disambiguation (spec §1 of
    # docs/superpowers/specs/2026-08-29-avoid-overlapping-tracks-design.md): edge_id*3 for an
    # original edge, edge_id*3+1/+2 for the u-side/v-side half of a hub-split edge, so the two
    # halves of one split edge never collide.
    base_edge_ids: list


def _check_routable(subgraph: LocalSubgraph) -> None:
    """time_s becomes the igraph "weight" attribute every routing caller shortest-paths on, so a
    single UNSET (-1.0) edge left over from build_base_graph.py - i.e. compute_edge_profiles.py
    never ran against THIS base graph - poisons the whole cell. igraph does not reject that: it
    silently switches from Dijkstra to Bellman-Ford, and since every negative edge of an
    undirected graph is a negative cycle, it only reports one after re-queueing a vertex more than
    |V| times. On a real ~117k-vertex cell that is hours of 100%-CPU spinning per call with no
    output rather than an error, which is exactly how it went unnoticed for a whole run - so catch
    the sentinel here, at the one chokepoint every routing caller (build_hub_edges.py,
    match_tour_edges.py, analysis/routing_probe.py) passes through."""
    times = subgraph.local_edges["time_s"]
    n_unset = int((times < 0).sum())
    if n_unset:
        raise ValueError(
            f"{n_unset:,} of {len(times):,} edges have an UNSET/negative time_s - this subgraph "
            "was built from a base graph whose compute_edge_profiles pass never ran. Rerun "
            "`doit compute_edge_profiles`, then `doit gather_route_subgraphs` to rebuild the "
            "per-cell caches under data/osm/route_subgraphs/."
        )


def build_base_igraph_arrays(subgraph: LocalSubgraph, hub_snaps: dict) -> BaseIgraphArrays:
    """The variant-independent half of building a routable igraph for this cell: base edge
    columns + every mid-chain snap's inserted vertex/synthetic-edge pair (topology only - hub
    locations and split geometry don't depend on a routing constraint, only which resulting edges
    a given variant keeps does, see build_igraph_from_base).

    Raises ValueError if any edge still carries an UNSET (negative) time_s - see _check_routable."""
    _check_routable(subgraph)
    n_base = len(subgraph.local_nodes)
    edges_uv = list(zip(subgraph.local_edges["u"].tolist(), subgraph.local_edges["v"].tolist()))
    dists = subgraph.local_edges["dist"].tolist()
    times = subgraph.local_edges["time_s"].tolist()
    road_ms = subgraph.local_edges["road_m"].tolist()
    ungraded_ms = subgraph.local_edges["ungraded_m"].tolist()
    inferred_ms = subgraph.local_edges["inferred_m"].tolist()
    ascent_ms = subgraph.local_edges["ascent_m"].tolist()
    descent_ms = subgraph.local_edges["descent_m"].tolist()
    sac_ranks = subgraph.local_edges["sac_rank"].tolist()
    via_ferratas = subgraph.local_edges["via_ferrata"].tolist()
    constrained_oks = subgraph.local_edges["constrained_ok"].tolist()
    interiors = [
        [
            (subgraph.interior[j]["lon"], subgraph.interior[j]["lat"])
            for j in range(e["interior_offset"], e["interior_offset"] + e["interior_count"])
        ]
        for e in subgraph.local_edges
    ]
    # Absolute elevation, not a delta - max over the edge's own two endpoints plus every interior
    # point, so a col strictly between two graph nodes (not itself a vertex, after
    # build_base_graph.py's structural contraction) is still caught. A mid-chain snap inherits its
    # parent's value on both synthetic halves rather than re-deriving one per half (no per-point
    # elevation survives split_edge_at_point's distance-ratio apportionment, same limitation
    # ascent_m/descent_m already accept there - spec C9).
    node_ele = subgraph.local_node_ele
    max_ele_ms = [
        float(max(
            node_ele[e["u"]], node_ele[e["v"]],
            *(subgraph.interior_ele[e["interior_offset"]:e["interior_offset"] + e["interior_count"]]
              .tolist() or [float("-inf")]),
        ))
        for e in subgraph.local_edges
    ]

    vertex_coords = {i: (float(n["lon"]), float(n["lat"])) for i, n in enumerate(subgraph.local_nodes)}
    # Per-vertex absolute elevation, keyed by igraph vertex id - not derivable from edge attrs
    # alone (accumulate_path's trivial src_v == tgt_v case walks zero edges), so it has to be
    # its own array. A mid-chain snap gets its parent edge's max_ele_m (same apportionment
    # limitation max_ele_ms already accepts above - no per-point elevation survives
    # split_edge_at_point).
    vertex_ele_ms = node_ele.tolist()

    n_orig = len(subgraph.local_edges)
    edge_source = list(range(n_orig))
    edge_ids_col = subgraph.local_edges["edge_id"]
    base_edge_ids = [int(edge_ids_col[i]) * 3 for i in range(n_orig)]

    hub_vertex = {}
    next_vertex = n_base
    edges_to_remove = set()
    for hub_key, snap in hub_snaps.items():
        if snap.node_index is not None:
            hub_vertex[hub_key] = snap.node_index
            continue
        ei = snap.edge_local_index
        u, v = edges_uv[ei]
        edges_to_remove.add(ei)
        split = snap.split
        vid = next_vertex
        next_vertex += 1
        vertex_coords[vid] = split.split_coord
        base_sac_rank = int(subgraph.local_edges["sac_rank"][ei])
        base_via_ferrata = bool(subgraph.local_edges["via_ferrata"][ei])
        base_constrained_ok = bool(subgraph.local_edges["constrained_ok"][ei])
        base_max_ele = max_ele_ms[ei]
        edges_uv.append((u, vid))
        dists.append(split.dist_to_u)
        times.append(split.dist_to_u)
        road_ms.append(split.road_m_to_u)
        ungraded_ms.append(split.ungraded_m_to_u)
        inferred_ms.append(split.inferred_m_to_u)
        ascent_ms.append(0.0)
        descent_ms.append(0.0)
        sac_ranks.append(base_sac_rank)
        via_ferratas.append(base_via_ferrata)
        constrained_oks.append(base_constrained_ok)
        interiors.append(list(split.interior_to_u))
        max_ele_ms.append(base_max_ele)
        vertex_ele_ms.append(base_max_ele)
        edge_source.append(ei)
        base_edge_ids.append(int(edge_ids_col[ei]) * 3 + 1)
        edges_uv.append((vid, v))
        dists.append(split.dist_to_v)
        times.append(split.dist_to_v)
        road_ms.append(split.road_m_to_v)
        ungraded_ms.append(split.ungraded_m_to_v)
        inferred_ms.append(split.inferred_m_to_v)
        ascent_ms.append(0.0)
        descent_ms.append(0.0)
        sac_ranks.append(base_sac_rank)
        via_ferratas.append(base_via_ferrata)
        constrained_oks.append(base_constrained_ok)
        interiors.append(list(split.interior_to_v))
        max_ele_ms.append(base_max_ele)
        edge_source.append(ei)
        base_edge_ids.append(int(edge_ids_col[ei]) * 3 + 2)
        hub_vertex[hub_key] = vid

    return BaseIgraphArrays(
        next_vertex=next_vertex, n_orig=n_orig, edges_uv=edges_uv, dists=dists, times=times,
        road_ms=road_ms, ungraded_ms=ungraded_ms, inferred_ms=inferred_ms, ascent_ms=ascent_ms,
        descent_ms=descent_ms, sac_ranks=sac_ranks, via_ferratas=via_ferratas,
        constrained_oks=constrained_oks, interiors=interiors, max_ele_ms=max_ele_ms,
        vertex_ele_ms=vertex_ele_ms,
        vertex_coords=vertex_coords, hub_vertex=hub_vertex, edges_to_remove=edges_to_remove,
        edge_source=edge_source, base_edge_ids=base_edge_ids,
    )


def build_igraph_from_base(base: BaseIgraphArrays, edge_mask: np.ndarray = None):
    """The per-variant half: apply this variant's edge_mask (lib/variants.py's edge_mask(), over
    just the n_orig ORIGINAL edges) to base's precomputed topology and construct the igraph.
    Cheap (one bool-list build + igraph's own C-level filtering), unlike build_base_igraph_arrays -
    see that function's docstring for why the split exists.

    edge_mask: ANDed into the mid-chain-snap `_filter` so a constrained row's igraph never
    contains an edge that row forbids. A snap that split a masked-out edge inherits its parent's
    mask value on both synthetic halves (via base.edge_source) - a hub cannot snap its way onto
    forbidden terrain."""
    orig_kept = [True] * base.n_orig if edge_mask is None else edge_mask.tolist()
    kept_mask = [orig_kept[s] for s in base.edge_source]

    def _filter(lst):
        kept = [
            x for i, x in enumerate(lst[:base.n_orig])
            if i not in base.edges_to_remove and kept_mask[i]
        ]
        return kept + [
            x for i, x in enumerate(lst[base.n_orig:], start=base.n_orig) if kept_mask[i]
        ]

    # igraph canonicalizes an undirected edge's (source, target) to ascending vertex-id order at
    # construction time, discarding which side of edges_uv was actually "u" - so an edge whose
    # local u-index happens to be greater than its v-index comes back with source/target swapped
    # relative to insertion. `interior`/ascent_m/descent_m are stored in the ORIGINAL u->v
    # direction, so accumulate_path needs this untouched-by-igraph copy of u to detect true
    # traversal direction rather than trusting e.source (see accumulate_path's `forward`).
    orig_u = _filter([uv[0] for uv in base.edges_uv])
    graph = ig.Graph(n=base.next_vertex, edges=_filter(base.edges_uv), edge_attrs={
        "weight": _filter(base.times), "dist": _filter(base.dists), "time_s": _filter(base.times),
        "road_m": _filter(base.road_ms), "ungraded_m": _filter(base.ungraded_ms),
        "inferred_m": _filter(base.inferred_ms), "ascent_m": _filter(base.ascent_ms),
        "descent_m": _filter(base.descent_ms), "max_ele_m": _filter(base.max_ele_ms),
        "sac_rank": _filter(base.sac_ranks), "via_ferrata": _filter(base.via_ferratas),
        "constrained_ok": _filter(base.constrained_oks), "interior": _filter(base.interiors),
        "base_edge_id": _filter(base.base_edge_ids), "orig_u": orig_u,
    }, directed=False)
    graph.vs["ele_m"] = base.vertex_ele_ms
    return graph, base.hub_vertex, base.vertex_coords


def build_igraph_with_snaps(subgraph: LocalSubgraph, hub_snaps: dict, edge_mask: np.ndarray = None):
    """hub_snaps: {hub_key: SnapResult}. Returns (graph, hub_key -> igraph vertex id,
    vertex_id -> (lon, lat) for every vertex including virtual snap points), inserting a
    virtual vertex per mid-chain snap (edge_local_index != None). Edge attrs carry everything
    pass-2 path reconstruction needs (dist/road_m/ungraded_m/inferred_m/ascent_m/descent_m/
    sac_rank/via_ferrata/interior polyline), same fields build_hut_graph.py's pass2 reads off its
    contracted chain edges.

    Routes on time_s (spec A3/A1) - EDGE_DTYPE dropped the road-penalised `weight` column and
    add_base_elevation.py fills time_s for every edge.

    Thin single-variant convenience wrapper over build_base_igraph_arrays + build_igraph_from_base
    (kept for tests/callers routing exactly one variant); a caller routing several variants over
    the same subgraph+snaps should call build_base_igraph_arrays ONCE and reuse it across
    build_igraph_from_base calls instead - see build_hub_edges.py's compute_hub_edges_for_cell."""
    base = build_base_igraph_arrays(subgraph, hub_snaps)
    return build_igraph_from_base(base, edge_mask=edge_mask)


PathResult = namedtuple(
    "PathResult",
    "coords distance_m road_m ungraded_m inferred_m ascent_m descent_m max_ele_m sac_rank "
    "via_ferrata base_edge_ids",
)


def accumulate_path(graph, vertex_coords: dict, src_v: int, tgt_v: int, epath: list) -> PathResult | None:
    """Shared by path_for (one src->tgt pair) and build_hub_edges.py's batched path query (opt #2:
    one src_v -> many targets get_shortest_paths call instead of one call per target - igraph's
    single-target get_shortest_paths still runs a full one-to-many Dijkstra from src_v internally,
    so N separate per-target calls from the same source repeated that Dijkstra N times for no
    reason; graph.distances() already batches this way for a cutoff pass, this makes the path pass
    do the same). Accumulates every scalar RECORD_DTYPE needs off the SAME edges the router used
    (spec B3: routing and display cannot disagree, because they are the same numbers). `coords`
    excludes the hub endpoints themselves, which the caller prepends/appends.

    ascent_m/descent_m are stored per base-graph edge in a fixed u->v direction (spec-neutral, not
    tied to any particular traversal), so a path walking an edge v->u must swap them - otherwise a
    descent reported for the forward direction would silently become the reported ascent for the
    reverse one.

    Returns None if tgt_v is unreachable from src_v on this (possibly variant-masked) graph -
    igraph's get_shortest_paths reports that the same way it reports the trivial src_v==tgt_v case
    (an empty epath), so callers that don't already know reachability (e.g. a variant-agnostic
    target list routed against several differently-masked graphs) MUST check for None rather than
    treat an empty epath as a real zero-distance path."""
    if src_v == tgt_v:
        return PathResult([], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, float(graph.vs[src_v]["ele_m"]), -1, False, [])
    if not epath:
        return None
    trail_coords = []
    distance_m = 0.0
    road_m = 0.0
    ungraded_m = 0.0
    inferred_m = 0.0
    ascent_m = 0.0
    descent_m = 0.0
    max_ele_m = float("-inf")
    max_sac_rank = -1
    has_via_ferrata = False
    base_edge_ids = []
    cur = src_v
    for eid in epath:
        e = graph.es[eid]
        # e.source is igraph's canonicalized endpoint (ascending vertex id), NOT necessarily the
        # side inserted as "u" - compare against orig_u instead, see build_igraph_from_base.
        # nxt is "whichever endpoint isn't cur", independent of that canonicalization.
        forward = e["orig_u"] == cur
        nxt = e.target if cur == e.source else e.source
        interior = e["interior"] if forward else list(reversed(e["interior"]))
        trail_coords.append(vertex_coords[cur])
        trail_coords.extend(interior)
        distance_m += e["dist"]
        road_m += e["road_m"]
        ungraded_m += e["ungraded_m"]
        inferred_m += e["inferred_m"]
        ascent_m += e["ascent_m"] if forward else e["descent_m"]
        descent_m += e["descent_m"] if forward else e["ascent_m"]
        if e["max_ele_m"] > max_ele_m:
            max_ele_m = e["max_ele_m"]
        if e["sac_rank"] > max_sac_rank:
            max_sac_rank = e["sac_rank"]
        if e["via_ferrata"]:
            has_via_ferrata = True
        # base_edge_id is direction-independent (it identifies physical ground, not a signed
        # delta), so unlike ascent_m/descent_m it needs no forward swap.
        base_edge_ids.append(e["base_edge_id"])
        cur = nxt
    trail_coords.append(vertex_coords[cur])
    return PathResult(
        trail_coords, distance_m, road_m, ungraded_m, inferred_m, ascent_m, descent_m,
        max_ele_m, max_sac_rank, has_via_ferrata, base_edge_ids,
    )


def path_for(graph, vertex_coords: dict, src_v: int, tgt_v: int) -> PathResult | None:
    """Walks the time-shortest src_v->tgt_v path (spec A3/A1 - `weight` == `time_s`). Single-pair
    convenience wrapper over accumulate_path - a caller walking several targets from the same
    src_v (build_hub_edges.py's compute_hub_edges_for_cell) should batch one get_shortest_paths
    call across all of them instead of calling this once per target, see accumulate_path's
    docstring. Returns None if tgt_v is unreachable - see accumulate_path."""
    if src_v == tgt_v:
        return accumulate_path(graph, vertex_coords, src_v, tgt_v, [])
    epath = graph.get_shortest_paths(src_v, to=tgt_v, weights="weight", output="epath")[0]
    return accumulate_path(graph, vertex_coords, src_v, tgt_v, epath)
