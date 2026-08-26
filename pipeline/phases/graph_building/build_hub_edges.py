#!/usr/bin/env python3
"""Routing pass of the old build_hub_edges.py, now split into three tasks (see
docs/superpowers/plans/2026-08-23-split-build-hub-edges.md): snap_hubs.py (hub->base-graph
snapping, cached in hub_snaps.npy/hub_snap_interior.npy - lib/hub_snap.py) and
gather_route_subgraphs.py (per-cell max-edge-km-padded subgraphs, cached under
data/osm/route_subgraphs/ - lib/subgraph.py's save_local_subgraph/load_local_subgraph) both run
first and are independent of --max-edge-km/pipeline.config.json's graph.variants respectively (the
former) or of graph.variants alone (the latter - it DOES depend on --max-edge-km). This script
just reloads both caches and does the actual per-cell, per-variant routing (build_igraph +
distances + paths), the one stage whose cost genuinely scales with the variant grid.

Usage: python pipeline/phases/graph_building/build_hub_edges.py [--max-edge-km 30] [--workers N]
"""

import argparse
import dataclasses
import hashlib
import os
import sys
import time
from collections import Counter, namedtuple
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import igraph as ig
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import binfmt  # noqa: E402
from lib import hub_snap  # noqa: E402
from lib import variants as variants_lib  # noqa: E402
from lib.grid import Grid  # noqa: E402
from lib.pipeline import OSM_DIR, hut_points, load_config  # noqa: E402
from lib.subgraph import LocalSubgraph, load_local_subgraph  # noqa: E402
from lib.timing import StepTimer, phase  # noqa: E402
from graph_building.gather_route_subgraphs import cell_dir_for  # noqa: E402

# Re-exported for callers/tests that used to import these off this module (they moved to
# lib/hub_snap.py when snap_hubs.py split out - see this module's docstring).
SnapResult = hub_snap.SnapResult
SnapRejection = hub_snap.SnapRejection
snap_hub_to_subgraph = hub_snap.snap_hub_to_subgraph
write_unsnapped_report = hub_snap.write_unsnapped_report

SCRIPT_NAME = "build_hub_edges.py"


@dataclasses.dataclass
class _BaseIgraphArrays:
    """Everything _build_igraph_with_snaps used to recompute from scratch on EVERY variant, even
    though none of it actually depends on the variant - only which edges end up kept does (spec
    C2's masked-subgraph-per-row). Built once per cell by _build_base_igraph_arrays; each variant
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
    vertex_coords: dict
    hub_vertex: dict
    edges_to_remove: set
    # edge_source[i] is which ORIGINAL local edge index (0..n_orig-1) edge i's mask value should
    # come from: i itself for i < n_orig, or the parent edge a synthetic (split) edge inherited
    # its terrain from for i >= n_orig - a variant's edge_mask() only covers the n_orig original
    # edges, so a synthetic edge has no mask entry of its own.
    edge_source: list


def _build_base_igraph_arrays(subgraph: LocalSubgraph, hub_snaps: dict) -> _BaseIgraphArrays:
    """The variant-independent half of building a routable igraph for this cell: base edge
    columns + every mid-chain snap's inserted vertex/synthetic-edge pair (topology only - hub
    locations and split geometry don't depend on a routing constraint, only which resulting edges
    a given variant keeps does, see _build_igraph_from_base)."""
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

    n_orig = len(subgraph.local_edges)
    edge_source = list(range(n_orig))

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
        edge_source.append(ei)
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
        hub_vertex[hub_key] = vid

    return _BaseIgraphArrays(
        next_vertex=next_vertex, n_orig=n_orig, edges_uv=edges_uv, dists=dists, times=times,
        road_ms=road_ms, ungraded_ms=ungraded_ms, inferred_ms=inferred_ms, ascent_ms=ascent_ms,
        descent_ms=descent_ms, sac_ranks=sac_ranks, via_ferratas=via_ferratas,
        constrained_oks=constrained_oks, interiors=interiors, max_ele_ms=max_ele_ms,
        vertex_coords=vertex_coords, hub_vertex=hub_vertex, edges_to_remove=edges_to_remove,
        edge_source=edge_source,
    )


def _build_igraph_from_base(base: _BaseIgraphArrays, edge_mask: np.ndarray = None):
    """The per-variant half: apply this variant's edge_mask (lib/variants.py's edge_mask(), over
    just the n_orig ORIGINAL edges) to base's precomputed topology and construct the igraph.
    Cheap (one bool-list build + igraph's own C-level filtering), unlike _build_base_igraph_arrays
    - see that function's docstring for why the split exists.

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

    graph = ig.Graph(n=base.next_vertex, edges=_filter(base.edges_uv), edge_attrs={
        "weight": _filter(base.times), "dist": _filter(base.dists), "time_s": _filter(base.times),
        "road_m": _filter(base.road_ms), "ungraded_m": _filter(base.ungraded_ms),
        "inferred_m": _filter(base.inferred_ms), "ascent_m": _filter(base.ascent_ms),
        "descent_m": _filter(base.descent_ms), "max_ele_m": _filter(base.max_ele_ms),
        "sac_rank": _filter(base.sac_ranks), "via_ferrata": _filter(base.via_ferratas),
        "constrained_ok": _filter(base.constrained_oks), "interior": _filter(base.interiors),
    }, directed=False)
    return graph, base.hub_vertex, base.vertex_coords


def _build_igraph_with_snaps(subgraph: LocalSubgraph, hub_snaps: dict, edge_mask: np.ndarray = None):
    """hub_snaps: {hub_key: SnapResult}. Returns (graph, hub_key -> igraph vertex id,
    vertex_id -> (lon, lat) for every vertex including virtual snap points), inserting a
    virtual vertex per mid-chain snap (edge_local_index != None). Edge attrs carry everything
    pass-2 path reconstruction needs (dist/road_m/ungraded_m/inferred_m/ascent_m/descent_m/
    sac_rank/via_ferrata/interior polyline), same fields build_hut_graph.py's pass2 reads off its
    contracted chain edges.

    Routes on time_s (spec A3/A1) - EDGE_DTYPE dropped the road-penalised `weight` column and
    add_base_elevation.py fills time_s for every edge.

    Thin single-variant convenience wrapper over _build_base_igraph_arrays +
    _build_igraph_from_base (kept for tests/callers routing exactly one variant); a caller routing
    several variants over the same subgraph+snaps should call _build_base_igraph_arrays ONCE and
    reuse it across _build_igraph_from_base calls instead - see compute_hub_edges_for_cell."""
    base = _build_base_igraph_arrays(subgraph, hub_snaps)
    return _build_igraph_from_base(base, edge_mask=edge_mask)


PathResult = namedtuple(
    "PathResult",
    "coords distance_m road_m ungraded_m inferred_m ascent_m descent_m max_ele_m sac_rank "
    "via_ferrata",
)


def _accumulate_path(graph, vertex_coords: dict, src_v: int, tgt_v: int, epath: list) -> PathResult:
    """Shared by _path_for (one src->tgt pair) and compute_hub_edges_for_cell's batched path query
    (opt #2: one src_v -> many targets get_shortest_paths call instead of one call per target -
    igraph's single-target get_shortest_paths still runs a full one-to-many Dijkstra from src_v
    internally, so N separate per-target calls from the same source repeated that Dijkstra N times
    for no reason; graph.distances() already batches this way for the cutoff pass above, this
    makes the path pass do the same). Accumulates every scalar RECORD_DTYPE needs off the SAME
    edges the router used (spec B3: routing and display cannot disagree, because they are the same
    numbers). `coords` excludes the hub endpoints themselves, which the caller prepends/appends.

    ascent_m/descent_m are stored per base-graph edge in a fixed u->v direction (spec-neutral, not
    tied to any particular traversal), so a path walking an edge v->u must swap them - otherwise a
    descent reported for the forward direction would silently become the reported ascent for the
    reverse one."""
    if src_v == tgt_v:
        return PathResult([], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -1, False)
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
    cur = src_v
    for eid in epath:
        e = graph.es[eid]
        forward = e.source == cur
        nxt = e.target if forward else e.source
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
        cur = nxt
    trail_coords.append(vertex_coords[cur])
    return PathResult(
        trail_coords, distance_m, road_m, ungraded_m, inferred_m, ascent_m, descent_m,
        max_ele_m, max_sac_rank, has_via_ferrata,
    )


def _path_for(graph, vertex_coords: dict, src_v: int, tgt_v: int) -> PathResult:
    """Walks the time-shortest src_v->tgt_v path (spec A3/A1 - `weight` == `time_s`). Single-pair
    convenience wrapper over _accumulate_path - a caller walking several targets from the same
    src_v (compute_hub_edges_for_cell's per-hub loop) should batch one get_shortest_paths call
    across all of them instead of calling this once per target, see _accumulate_path's docstring."""
    if src_v == tgt_v:
        return _accumulate_path(graph, vertex_coords, src_v, tgt_v, [])
    epath = graph.get_shortest_paths(src_v, to=tgt_v, weights="weight", output="epath")[0]
    return _accumulate_path(graph, vertex_coords, src_v, tgt_v, epath)


def compute_hub_edges_for_cell(subgraph: LocalSubgraph, core_hubs: list,
                                all_hubs: list, max_edge_km: float,
                                max_snap_m: float = None, variants: list = None,
                                timer: StepTimer = None, max_snap_ascent_m: float = None,
                                rejections: list = None, precomputed_snaps: dict = None) -> list:
    """all_hubs: candidate targets already filtered (by the caller) to hubs whose straight-line
    distance to this cell could possibly be within max_edge_km of trail distance - trail distance
    is always >= straight-line distance, so a bbox padded by max_edge_km around the cell is a safe
    superset. Without that prefilter this used to snap every hub in the whole bbox against every
    cell's local subgraph (O(cells * total_hubs) snap calls), which is what made this step take
    hours instead of minutes.

    Only huts are ever routed *to*: the edge sets this pipeline ships are hut-hut and
    access-point-to-hut (see __main__), so a station->station or parking->parking pair is work
    whose result nothing consumes, and a hut->access-point pair duplicates the access->hut record
    the access point's own cell already emits. Restricting targets to huts also keeps the
    non-core access points out of the snap loop entirely.

    variants: list of lib/variants.py Variant rows to route (spec C2). Snapping is shared across
    rows - a hub's location doesn't depend on a routing constraint - but each row gets its own
    masked igraph and its own cutoff/path pass, because a constrained row can only ever be a
    smaller subgraph than FAST_ANY (never the same distances).

    timer: optional lib/timing.py StepTimer, filled with the per-step split (snap / build_igraph /
    distances / paths) so the parent can merge every worker's totals and report where the run
    actually went - snapping and graph traversal scale with different things (hub count vs.
    subgraph size x pair count), so a single per-cell wall-clock number cannot tell them apart.

    max_snap_ascent_m: forwarded to snap_hub_to_subgraph (spec E3). rejections: optional list a
    caller can pass to collect every SnapRejection this cell produces (for
    write_unsnapped_report) - a hub that fails here is simply excluded from routing, same as
    before, but is now a counted fact instead of a silent drop. Both max_snap_m/max_snap_ascent_m/
    rejections are only used when precomputed_snaps is None (the self-snapping fallback, kept for
    tests and any standalone caller); build_hub_edges.py's own __main__ always passes
    precomputed_snaps (snap_hubs.py's job now - see this module's docstring), in which case a hub
    key missing from it is simply not routed (already reported by snap_hubs.py's own
    unsnapped_huts.json)."""
    if not core_hubs:
        return []
    timer = timer if timer is not None else StepTimer()

    hut_targets = [h for h in all_hubs if h["type"] == binfmt.TYPE_HUT]

    snaps = {}
    with timer.step("snap"):
        for hub in core_hubs + hut_targets:
            key = (hub["type"], hub["id"])
            if key in snaps:
                continue
            if precomputed_snaps is not None:
                snap = precomputed_snaps.get(key)
                if snap is not None:
                    snaps[key] = snap
                continue
            snap = snap_hub_to_subgraph(subgraph, hub["lon"], hub["lat"], max_snap_m,
                                        hub_ele_m=hub.get("ele"),
                                        max_snap_ascent_m=max_snap_ascent_m)
            if isinstance(snap, SnapResult):
                snaps[key] = snap
            elif rejections is not None:
                rejections.append(dataclasses.replace(
                    snap, hub_id=hub["id"], hub_type=hub["type"], name=hub.get("name", "")
                ))
    timer.count("snap_hubs", len(snaps))

    max_edge_m = max_edge_km * 1000
    records = []
    # Built once for this cell+snap set - _build_base_igraph_arrays' Python-level column/interior/
    # max_ele_m work doesn't depend on the variant, only which resulting edges get kept does (opt
    # #1: this used to rerun that work from scratch once per variant, see
    # _BaseIgraphArrays' docstring).
    base_arrays = _build_base_igraph_arrays(subgraph, snaps)
    for variant in variants:
        mask = variants_lib.edge_mask(subgraph.local_edges, variant)
        with timer.step("build_igraph"):
            graph, hub_vertex, vertex_coords = _build_igraph_from_base(base_arrays, edge_mask=mask)
        # a hut-hut pair where both ends are core hubs of this cell is visited from both sides
        # below (hub->target and target->hub); collapse it to the one record merge_and_dedup
        # would otherwise keep anyway - core_hubs of a single cell call all belong to the same
        # shard, so merge_and_dedup's cross-shard dedup never sees the in-shard duplicate to drop
        # it. Reset per variant: a pair dropped by one row must still be tried by the next.
        seen_hut_pairs = set()
        for hub in core_hubs:
            src_key = (hub["type"], hub["id"])
            if src_key not in hub_vertex:
                continue
            src_v = hub_vertex[src_key]
            targets = [h for h in hut_targets if (h["type"], h["id"]) != (hub["type"], hub["id"])
                       and (h["type"], h["id"]) in hub_vertex]
            if not targets:
                continue
            target_vs = [hub_vertex[(t["type"], t["id"])] for t in targets]
            # Two different hubs can snap to the same graph vertex (both within max_snap_m of one
            # existing node), so target_vs can contain duplicates - igraph's distances() rejects a
            # target list with duplicates, so query only the unique vertex set and fan the results
            # back out per-hub by vertex id.
            unique_target_vs = sorted(set(target_vs))
            # cutoff uses real-distance ("dist") weights on THIS variant's masked subgraph - a
            # constrained row's cutoff can only be a subset of FAST_ANY's, never wider (spec C2).
            with timer.step("distances"):
                unique_dists = graph.distances(
                    source=[src_v], target=unique_target_vs, weights="dist"
                )[0]
            timer.count("distance_targets", len(unique_target_vs))
            dist_by_vertex = dict(zip(unique_target_vs, unique_dists))
            cutoff_dists = [dist_by_vertex[tv] for tv in target_vs]

            # opt #2: decide which targets even need a path FIRST (cutoff + hut-pair dedup), then
            # fetch every surviving path for this hub in ONE get_shortest_paths call instead of
            # one call per target - see _accumulate_path's docstring for why that matters
            # (igraph's single-target get_shortest_paths still runs a full source-wide Dijkstra
            # internally, so N per-target calls from the same src_v repeated that Dijkstra N
            # times).
            in_cutoff = []
            for t, tv, cutoff_d in zip(targets, target_vs, cutoff_dists):
                if not np.isfinite(cutoff_d) or cutoff_d > max_edge_m:
                    continue
                if hub["type"] == binfmt.TYPE_HUT and t["type"] == binfmt.TYPE_HUT:
                    pair_key = tuple(sorted([(hub["type"], hub["id"]), (t["type"], t["id"])]))
                    if pair_key in seen_hut_pairs:
                        continue
                    seen_hut_pairs.add(pair_key)
                in_cutoff.append((t, tv))
            if not in_cutoff:
                continue

            unique_path_vs = sorted({tv for _, tv in in_cutoff if tv != src_v})
            with timer.step("paths"):
                epaths = (
                    graph.get_shortest_paths(src_v, to=unique_path_vs, weights="weight", output="epath")
                    if unique_path_vs else []
                )
            path_by_vertex = {
                tv: _accumulate_path(graph, vertex_coords, src_v, tv, epath)
                for tv, epath in zip(unique_path_vs, epaths)
            }

            for t, tv in in_cutoff:
                path = (path_by_vertex[tv] if tv != src_v
                        else _accumulate_path(graph, vertex_coords, src_v, tv, []))
                # spec C8: the cutoff above ran on `dist`, but the routed path is TIME-shortest,
                # whose distance_m can exceed the cap - re-check on the routed path itself.
                if path.distance_m > max_edge_m:
                    continue
                # spec E3: the path sums only routed edges, so the hub-to-trail gap at both ends
                # is priced in here - it was contributing zero distance/ascent/descent otherwise.
                src_snap = snaps[src_key]
                tgt_snap = snaps[(t["type"], t["id"])]
                snap_m = src_snap.gap_m + tgt_snap.gap_m
                # Departure (src): climbing from hub up to the trail (hub below its snap point,
                # gap_dz_m < 0) is ascent; descending down to the trail (gap_dz_m > 0) is descent.
                # Arrival (tgt): climbing from the trail up to the hub (gap_dz_m > 0) is ascent;
                # descending down off the trail to the hub (gap_dz_m < 0) is descent.
                ascent_m = path.ascent_m + max(0.0, -src_snap.gap_dz_m) + max(0.0, tgt_snap.gap_dz_m)
                descent_m = path.descent_m + max(0.0, src_snap.gap_dz_m) + max(0.0, -tgt_snap.gap_dz_m)
                geometry = [(hub["lon"], hub["lat"]), *path.coords, (t["lon"], t["lat"])]
                records.append({
                    "from_id": hub["id"], "from_type": hub["type"],
                    "to_id": t["id"], "to_type": t["type"],
                    "variant": variant.code,
                    "distance_m": float(path.distance_m + snap_m),
                    "road_m": float(path.road_m),
                    "ascent_m": float(ascent_m), "descent_m": float(descent_m),
                    "max_ele_m": float(path.max_ele_m) if np.isfinite(path.max_ele_m) else 0.0,
                    "ungraded_m": float(path.ungraded_m), "inferred_m": float(path.inferred_m),
                    "snap_m": float(snap_m),
                    "sac_rank": int(path.sac_rank),
                    "via_ferrata": bool(path.via_ferrata),
                    "geometry": geometry,
                })
    return records


def merge_and_dedup(shard_records: list) -> list:
    seen = set()
    merged = []
    for shard in shard_records:
        for r in shard:
            if r["from_type"] == binfmt.TYPE_HUT and r["to_type"] == binfmt.TYPE_HUT:
                key = (r["variant"], tuple(sorted(
                    [(r["from_type"], r["from_id"]), (r["to_type"], r["to_id"])]
                )))
                if key in seen:
                    continue
                seen.add(key)
            merged.append(r)
    return merged


def _write_edge_output(records: list, out_dir: Path) -> None:
    """Packs merge_and_dedup's dict records into binfmt.RECORD_DTYPE + a flat geometry.npy
    (binfmt.COORD_DTYPE), mirroring how build_base_graph.py packs contracted-edge interior
    polylines: one growing geometry array, each record's geom_offset/geom_count pointing into
    it. profile_offset/profile_count stay 0 here - the elevation profile pass fills those in a
    later pass over this same records.npy.

    A constrained row frequently routes the exact same polyline as FAST_ANY (spec C7) - identical
    coordinate runs are deduplicated by content hash so those variants share one geom_offset
    instead of the geometry file growing linearly in variant count for zero new information.
    No collision re-check against the stored run: blake2b-128 over the run counts this pipeline
    will ever see has a collision probability far below floating-point noise in the coordinates
    themselves - deliberate, not an oversight."""
    records_arr = np.zeros(len(records), dtype=binfmt.RECORD_DTYPE)
    flat_geometry = []
    cursor = 0
    seen_geoms = {}   # blake2b of the packed coordinate run -> geom_offset
    for i, r in enumerate(records):
        geom = r["geometry"]
        key = hashlib.blake2b(
            np.asarray(geom, dtype=np.float64).tobytes(), digest_size=16
        ).digest()
        offset = seen_geoms.get(key)
        if offset is None:
            offset = cursor
            seen_geoms[key] = offset
            flat_geometry.extend(geom)
            cursor += len(geom)
        records_arr[i] = (
            r["from_id"], r["to_id"], r["from_type"], r["to_type"], r["variant"],
            r["distance_m"], r["road_m"], r["ascent_m"], r["descent_m"], r["max_ele_m"],
            r["ungraded_m"], r["inferred_m"], r["snap_m"], r["sac_rank"],
            r["via_ferrata"], offset, len(geom), 0, 0,
        )

    geometry_arr = np.zeros(len(flat_geometry), dtype=binfmt.COORD_DTYPE)
    if flat_geometry:
        geometry_arr["lon"] = [p[0] for p in flat_geometry]
        geometry_arr["lat"] = [p[1] for p in flat_geometry]

    binfmt.save_array(out_dir / "records.npy", records_arr)
    binfmt.save_array(out_dir / "geometry.npy", geometry_arr)


def _cell_workload_score(route_subgraphs_dir: Path, cell_id: int, n_hubs: int) -> int:
    """Cheap LPT (longest-processing-time-first) scheduling proxy for a cell's __main__ task, read
    with no extra I/O beyond a stat() call: gather_route_subgraphs.py already cached this cell's
    local_edges.npy, and its on-disk byte size is an exact proxy for subgraph edge count - the
    dominant driver of build_igraph/distances/paths cost per variant (see
    compute_hub_edges_for_cell). Multiplying by n_hubs (how many of this cell's hubs get routed
    out of that subgraph) accounts for routing cost also scaling with hub count, not just subgraph
    size. Sorting tasks by this score, largest first, before submitting to ProcessPoolExecutor
    minimizes makespan on the fixed worker pool: an unsorted or arbitrarily-ordered submission can
    leave a big cell as a straggler near the end, with every other worker idle waiting on it."""
    edges_path = cell_dir_for(route_subgraphs_dir, cell_id) / "local_edges.npy"
    try:
        size = edges_path.stat().st_size
    except OSError:
        size = 0
    return size * max(1, n_hubs)


def _run_cell(args):
    route_subgraphs_dir, base_graph_dir, cell_id, core_hubs, candidate_hubs, max_edge_km, \
        variants, local_persisted = args
    t0 = time.time()
    timer = StepTimer()
    with timer.step("gather_subgraph"):
        subgraph = load_local_subgraph(cell_dir_for(route_subgraphs_dir, cell_id), base_graph_dir)
    hut_targets = [h for h in candidate_hubs if h["type"] == binfmt.TYPE_HUT]
    keys = {(h["type"], h["id"]) for h in core_hubs} | {(h["type"], h["id"]) for h in hut_targets}
    local_snaps = hub_snap.reconstruct_local_snaps(subgraph, keys, local_persisted)
    records = compute_hub_edges_for_cell(subgraph, core_hubs, candidate_hubs, max_edge_km,
                                          variants=variants, timer=timer,
                                          precomputed_snaps=local_snaps)
    return {
        "cell_id": cell_id, "elapsed_s": time.time() - t0, "n_core_hubs": len(core_hubs),
        "n_nodes": len(subgraph.local_nodes), "n_edges": len(subgraph.local_edges),
        "records": records, "timer": timer,
    }


if __name__ == "__main__":
    config = load_config()
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-graph-dir", default=str(OSM_DIR / "base_graph"))
    parser.add_argument("--route-subgraphs-dir", default=str(OSM_DIR / "route_subgraphs"))
    parser.add_argument("--out-dir", default=str(OSM_DIR))
    parser.add_argument("--max-edge-km", type=float, default=config["graph"]["maxEdgeKm"])
    parser.add_argument("--workers", type=int, default=None)
    args = parser.parse_args()

    manifest = binfmt.load_manifest(Path(args.base_graph_dir) / "manifest.json")
    grid = Grid(manifest["bbox"], manifest["tile_size_km"])

    hut_coords = hut_points(OSM_DIR / "huts.geojson")
    hut_coords_by_id = {i: tuple(c) for i, c in enumerate(hut_coords)}
    start_points = binfmt.load_array(OSM_DIR / "start_points.npy", mmap=False)
    start_by_id = {}
    for p in start_points:
        start_by_id.setdefault(int(p["type"]), {})[int(p["osm_id"])] = (float(p["lon"]), float(p["lat"]))

    all_hub_coords_by_type = {binfmt.TYPE_HUT: hut_coords_by_id, **start_by_id}

    all_hubs_flat = [
        {"id": hid, "type": htype, "lon": lon, "lat": lat}
        for htype, coords_by_id in all_hub_coords_by_type.items()
        for hid, (lon, lat) in coords_by_id.items()
    ]

    print(f"loading persisted hub snaps from {args.out_dir} ...", flush=True)
    hub_snaps_arr = binfmt.load_array(Path(args.out_dir) / "hub_snaps.npy", mmap=False)
    hub_snap_interior_arr = binfmt.load_array(
        Path(args.out_dir) / "hub_snap_interior.npy", mmap=False
    )
    persisted_snaps = hub_snap.load_persisted_snaps(hub_snaps_arr, hub_snap_interior_arr)

    hubs_by_cell = {}
    for hub in all_hubs_flat:
        cid = grid.cell_id_for_point(hub["lon"], hub["lat"])
        hubs_by_cell.setdefault(cid, []).append(hub)

    def _candidate_hubs_for_cell(cid):
        # Trail distance is always >= straight-line distance, so a bbox padded by max_edge_km
        # around the cell is a safe superset of every hub that could end up within max_edge_km
        # trail distance of a hub in this cell - see compute_hub_edges_for_cell's docstring.
        b = grid.padded_bounds(cid, args.max_edge_km)
        return [
            h for h in all_hubs_flat
            if b["minLng"] <= h["lon"] <= b["maxLng"] and b["minLat"] <= h["lat"] <= b["maxLat"]
        ]

    active_variants = variants_lib.enabled_variants(config)

    tasks = []
    for cid, hubs in hubs_by_cell.items():
        candidate_hubs = _candidate_hubs_for_cell(cid)
        hut_targets = [h for h in candidate_hubs if h["type"] == binfmt.TYPE_HUT]
        keys = {(h["type"], h["id"]) for h in hubs} | {(h["type"], h["id"]) for h in hut_targets}
        # Filter the persisted-snaps dict down to just this cell's relevant hubs before pickling
        # it into the worker - the full dict is small (one row per hub, not per edge), but there's
        # no reason to ship every other cell's rows to this one.
        local_persisted = {k: persisted_snaps[k] for k in keys if k in persisted_snaps}
        tasks.append((
            Path(args.route_subgraphs_dir), Path(args.base_graph_dir), cid, hubs, candidate_hubs,
            args.max_edge_km, active_variants, local_persisted,
        ))

    # Largest cells first (LPT scheduling, see _cell_workload_score's docstring) - the fixed-km
    # Grid produces very unevenly loaded cells (hub/hut density isn't uniform), and the plain
    # hubs_by_cell insertion order above has no relationship to per-cell cost, so a big cell
    # could otherwise land near the end and straggle with every other worker idle.
    route_subgraphs_dir_path = Path(args.route_subgraphs_dir)
    tasks.sort(
        key=lambda t: _cell_workload_score(route_subgraphs_dir_path, t[2], len(t[3])),
        reverse=True,
    )

    total = len(tasks)
    n_huts = sum(1 for h in all_hubs_flat if h["type"] == binfmt.TYPE_HUT)
    print(f"{total} cells with hubs to process "
          f"({n_huts:,} huts, {len(all_hubs_flat) - n_huts:,} access points)", flush=True)
    shard_records = []
    completed = 0
    t_start = time.time()
    # Sums every worker's per-step totals. These are CPU-parallel seconds, so the columns add up
    # to more than the wall clock - the reading that matters is the ratio between steps (snap vs.
    # distances vs. paths), not the absolute number.
    run_timer = StepTimer()
    with phase(SCRIPT_NAME, "hub_edge_query", n_cells=total, n_huts=n_huts,
               n_access_points=len(all_hubs_flat) - n_huts,
               workers=args.workers or os.cpu_count(), max_edge_km=args.max_edge_km) as meta:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(_run_cell, t) for t in tasks]
            for fut in as_completed(futures):
                result = fut.result()
                shard_records.append(result["records"])
                run_timer.merge(result["timer"])
                completed += 1
                overall_elapsed = time.time() - t_start
                avg_s = overall_elapsed / completed
                remaining_s = avg_s * (total - completed)
                cell_s = result["timer"].seconds
                print(
                    f"[{completed}/{total}] cell {result['cell_id']}: {result['elapsed_s']:.1f}s "
                    f"({result['n_core_hubs']} hubs, {result['n_nodes']:,} nodes, "
                    f"{result['n_edges']:,} edges) -> {len(result['records'])} edge records "
                    f"| slice {cell_s.get('gather_subgraph', 0):.1f}s, snap "
                    f"{cell_s.get('snap', 0):.1f}s, igraph "
                    f"{cell_s.get('build_igraph', 0):.1f}s, dist "
                    f"{cell_s.get('distances', 0):.1f}s, paths {cell_s.get('paths', 0):.1f}s "
                    f"| elapsed {overall_elapsed/60:.1f}m, ~{remaining_s/60:.1f}m remaining",
                    flush=True,
                )
        meta.update(run_timer.as_meta())

    print(f"step totals (summed over workers): {run_timer.summary()}", flush=True)

    merged = merge_and_dedup(shard_records)
    hut_records = [r for r in merged if r["to_type"] == binfmt.TYPE_HUT and r["from_type"] == binfmt.TYPE_HUT]
    # "access edges": station/parking <-> hut. Stored access->hut by convention (that is the
    # direction compute_hub_edges_for_cell emits), but the edge is undirected - the same record
    # serves a trip that starts at the station and one that ends there. The on-disk directory
    # and tile layer keep their original "start_edges" name.
    access_records = [r for r in merged if r["from_type"] != binfmt.TYPE_HUT]

    print(f"hut-hut edges: {len(hut_records)}, "
          f"access edges (station/parking <-> hut): {len(access_records)}")
    # Per-variant breakdown (spec C2's grid, active_variants above) - build_hub_edges.py is the
    # one place that runs every row, so this is the cheapest place to sanity-check a variant's
    # row actually produced edges rather than reloading records.npy separately afterward.
    hut_counts_by_variant = Counter(r["variant"] for r in hut_records)
    access_counts_by_variant = Counter(r["variant"] for r in access_records)
    for variant in active_variants:
        print(f"  {variant.name}: hut-hut {hut_counts_by_variant.get(variant.code, 0)}, "
              f"access {access_counts_by_variant.get(variant.code, 0)}")

    out_dir = Path(args.out_dir)
    _write_edge_output(hut_records, out_dir / "hut_edges")
    _write_edge_output(access_records, out_dir / "start_edges")
    print(f"written {out_dir / 'hut_edges'} and {out_dir / 'start_edges'}")
