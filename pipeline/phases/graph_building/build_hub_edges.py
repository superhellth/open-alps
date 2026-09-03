#!/usr/bin/env python3
"""Routing pass of the old build_hub_edges.py, now split into three tasks (see
docs/superpowers/plans/2026-08-23-split-build-hub-edges.md): snap_hubs.py (hub->base-graph
snapping, cached in hub_snaps.npy/hub_snap_interior.npy - lib/hub_snap.py) and
gather_route_subgraphs.py (per-cell max-edge-km-padded subgraphs, cached under
data/osm/route_subgraphs/ - lib/subgraph.py's save_local_subgraph/load_local_subgraph) both run
first and are independent of --max-edge-km/pipeline.config.json's graph.variants respectively (the
former) or of graph.variants alone (the latter - it DOES depend on --max-edge-km). This script
just reloads both caches and does the actual per-cell, per-variant routing (build_igraph +
distances + paths), the one stage whose cost genuinely scales with the variant grid. Writes
hut_edges/ (full geometry) and access_distances.npy (distance/time scalars only, no geometry -
spec 2026-09-02-hub-edge-scaling-design.md B3); a later select_approach_pairs.py +
build_access_edges.py pair materializes start_edges/ from the selected subset.

The igraph-building/path-walking primitives (BaseIgraphArrays, build_igraph_with_snaps,
accumulate_path, path_for, ...) live in lib/cell_igraph.py, not here - they're subgraph+snaps-only
plumbing with no dependency on this script's routing loop, and analysis/routing_probe.py already
needed to call them independently.

Usage: python pipeline/phases/graph_building/build_hub_edges.py [--max-edge-km 30] [--workers N]
"""

import argparse
import dataclasses
import os
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import binfmt  # noqa: E402
from lib import hub_snap  # noqa: E402
from lib import variants as variants_lib  # noqa: E402
from lib.cell_igraph import (  # noqa: E402
    accumulate_path, build_base_igraph_arrays, build_igraph_from_base,
)
from lib.edge_output import fold_endpoint_snaps, write_edge_records, write_access_distances  # noqa: E402
from lib.grid import Grid  # noqa: E402
from lib.hubs import bucket_by_cell, load_all_hubs  # noqa: E402
from lib.pipeline import OSM_DIR, load_config  # noqa: E402
from lib.progress import ProgressTracker, run_pool  # noqa: E402
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


def snap_hubs_for_cell(subgraph: LocalSubgraph, core_hubs: list, all_hubs: list,
                        max_snap_m: float, max_snap_ascent_m: float = None,
                        rejections: list = None) -> dict:
    """Standalone convenience for callers that don't have snap_hubs.py's precomputed
    hub_snaps.npy/hub_snap_interior.npy cache available (tests, `analysis/` scripts) - snaps every
    hub in core_hubs + the hut subset of all_hubs directly against `subgraph`, one
    snap_hub_to_subgraph call per hub. Production (build_hub_edges.py's own __main__) never calls
    this: it runs snap_hubs.py ahead of time and passes that cache straight into
    compute_hub_edges_for_cell's `snaps` param instead, so a hub only ever gets snapped once
    pipeline-wide (see snap_hubs.py's module docstring).

    rejections: optional list a caller can pass to collect every SnapRejection this cell produces
    (for write_unsnapped_report) - a hub that fails here is simply excluded from the returned dict.

    (spec 2026-09-02-hub-edge-scaling-design.md A1: every candidate in all_hubs needs a snap now,
    not just the hut subset - a hut source routes to huts AND access points in one pass)."""
    snaps = {}
    for hub in core_hubs + all_hubs:
        key = (hub["type"], hub["id"])
        if key in snaps:
            continue
        snap = snap_hub_to_subgraph(subgraph, hub["lon"], hub["lat"], max_snap_m,
                                    hub_ele_m=hub.get("ele"), max_snap_ascent_m=max_snap_ascent_m)
        if isinstance(snap, SnapResult):
            snaps[key] = snap
        elif rejections is not None:
            rejections.append(dataclasses.replace(
                snap, hub_id=hub["id"], hub_type=hub["type"], name=hub.get("name", "")
            ))
    return snaps


def compute_hub_edges_for_cell(subgraph: LocalSubgraph, core_hubs: list,
                                all_hubs: list, max_edge_km: float, snaps: dict,
                                variants: list, timer: StepTimer = None) -> tuple:
    """all_hubs: candidate targets already filtered (by the caller) to hubs whose straight-line
    distance to this cell could possibly be within max_edge_km of trail distance - trail distance
    is always >= straight-line distance, so a bbox padded by max_edge_km around the cell is a safe
    superset. Without that prefilter this used to snap every hub in the whole bbox against every
    cell's local subgraph (O(cells * total_hubs) snap calls), which is what made this step take
    hours instead of minutes.

    Direction inverted from the original build (spec 2026-09-02-hub-edge-scaling-design.md, A1):
    only HUTS among core_hubs are ever routed FROM. Dijkstra count is then driven by hut count
    (~846 total) instead of access-point count (76,669+), and adding more access points costs
    nothing in the distances step. A station/parking core hub of this cell is never itself a
    Dijkstra source - it is only ever a TARGET, reached from whichever cell holds the hut that
    can see it (A2's padded-bbox coverage argument is symmetric, so no pair is lost or
    duplicated by this).

    Returns (hut_records, access_rows):
      - hut_records: hut<->hut edges, full path geometry, same dict shape as before this change
        (from_id/from_type/to_id/to_type/variant/distance_m/road_m/ascent_m/descent_m/max_ele_m/
        ungraded_m/inferred_m/snap_m/sac_rank/via_ferrata/geometry/base_edge_ids).
      - access_rows: hut->access distance/time ONLY, no geometry, no path walk (spec B3):
        {hut_id, start_id, start_type, variant, distance_m, time_s}. distance_m already has both
        ends' snap gap folded in (SnapResult.gap_m is direction-free, so this needs no path walk);
        stored access->hut by the SAME convention start_edges/records.npy always used, even though
        the router itself walked hut->access (A3) - callers reading access_rows never see the
        router's own traversal direction.

    snaps: {(hub_type, hub_id): SnapResult}, already computed for every hub this cell could need -
    build_hub_edges.py's own __main__ gets this from snap_hubs.py's persisted cache
    (hub_snap.reconstruct_local_snaps); a standalone caller without that cache can build one via
    snap_hubs_for_cell(). A key missing from `snaps` is simply not routed - already reported by
    whichever caller built the dict (snap_hubs.py's unsnapped_huts.json, or snap_hubs_for_cell's
    own `rejections` param).

    variants: list of lib/variants.py Variant rows to route (spec C2). Snapping is shared across
    rows - a hub's location doesn't depend on a routing constraint - but each row gets its own
    masked igraph and its own cutoff/path pass, because a constrained row can only ever be a
    smaller subgraph than FAST_ANY (never the same distances).

    timer: optional lib/timing.py StepTimer, filled with the per-step split (snap /
    build_base_arrays / build_igraph / distances / paths) so the parent can merge every worker's
    totals and report where the run actually went."""
    if not core_hubs:
        return [], []
    timer = timer if timer is not None else StepTimer()

    hut_sources = [h for h in core_hubs if h["type"] == binfmt.TYPE_HUT]
    if not hut_sources:
        return [], []

    with timer.step("snap"):
        relevant_snaps = {}
        for hub in core_hubs + all_hubs:
            key = (hub["type"], hub["id"])
            if key in relevant_snaps:
                continue
            snap = snaps.get(key)
            if snap is not None:
                relevant_snaps[key] = snap
    snaps = relevant_snaps
    timer.count("snap_hubs", len(snaps))

    max_edge_m = max_edge_km * 1000
    hut_records = []
    access_rows = []
    # Built once for this cell+snap set - lib/cell_igraph.py's build_base_igraph_arrays' Python-
    # level column/interior/max_ele_m work doesn't depend on the variant, only which resulting
    # edges get kept does (opt #1: this used to rerun that work from scratch once per variant, see
    # BaseIgraphArrays' docstring).
    with timer.step("build_base_arrays"):
        base_arrays = build_base_igraph_arrays(subgraph, snaps)
    for variant in variants:
        mask = variants_lib.edge_mask(subgraph.local_edges, variant)
        with timer.step("build_igraph"):
            graph, hub_vertex, vertex_coords = build_igraph_from_base(base_arrays, edge_mask=mask)
        # a hut-hut pair where both ends are core hubs of this cell is visited from both sides
        # below (each is its own source); collapse it to the one record merge_and_dedup would
        # otherwise keep anyway - core_hubs of a single cell call all belong to the same shard, so
        # merge_and_dedup's cross-shard dedup never sees the in-shard duplicate to drop it. Reset
        # per variant: a pair dropped by one row must still be tried by the next.
        seen_hut_pairs = set()
        for hub in hut_sources:
            src_key = (hub["type"], hub["id"])
            if src_key not in hub_vertex:
                continue
            src_v = hub_vertex[src_key]
            targets = [t for t in all_hubs if (t["type"], t["id"]) != src_key
                       and (t["type"], t["id"]) in hub_vertex]
            if not targets:
                continue
            target_vs = [hub_vertex[(t["type"], t["id"])] for t in targets]
            # Two different hubs can snap to the same graph vertex (both within max_snap_m of one
            # existing node), so target_vs can contain duplicates - igraph's distances() rejects a
            # target list with duplicates, so query only the unique vertex set and fan the results
            # back out per-target by vertex id.
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

            in_cutoff = []
            for t, tv, cutoff_d in zip(targets, target_vs, cutoff_dists):
                if not np.isfinite(cutoff_d) or cutoff_d > max_edge_m:
                    continue
                if t["type"] == binfmt.TYPE_HUT:
                    pair_key = tuple(sorted([src_key, (t["type"], t["id"])]))
                    if pair_key in seen_hut_pairs:
                        continue
                    seen_hut_pairs.add(pair_key)
                in_cutoff.append((t, tv))
            if not in_cutoff:
                continue

            # B3: hut targets need a full path walk (hut_edges ships geometry); access targets
            # need only time_s, which a SECOND batched distances() call gives for free (same
            # O(E log V) class as the cutoff pass above) - no get_shortest_paths/path walk for
            # access at all, which is the whole point of splitting this from the old single pass.
            access_in_cutoff_vs = sorted(
                {tv for t, tv in in_cutoff if t["type"] != binfmt.TYPE_HUT}
            )
            if access_in_cutoff_vs:
                with timer.step("distances"):
                    access_time_dists = graph.distances(
                        source=[src_v], target=access_in_cutoff_vs, weights="weight"
                    )[0]
            else:
                access_time_dists = []
            time_by_vertex = dict(zip(access_in_cutoff_vs, access_time_dists))

            hut_in_cutoff = [(t, tv) for t, tv in in_cutoff if t["type"] == binfmt.TYPE_HUT]
            unique_path_vs = sorted({tv for _, tv in hut_in_cutoff if tv != src_v})
            with timer.step("paths"):
                epaths = (
                    graph.get_shortest_paths(src_v, to=unique_path_vs, weights="weight", output="epath")
                    if unique_path_vs else []
                )
            path_by_vertex = {
                tv: accumulate_path(graph, vertex_coords, src_v, tv, epath)
                for tv, epath in zip(unique_path_vs, epaths)
            }

            src_snap = snaps[src_key]
            for t, tv in in_cutoff:
                tgt_snap = snaps[(t["type"], t["id"])]
                if t["type"] != binfmt.TYPE_HUT:
                    # B3: no path walk for access targets - distance_m folds the (direction-free)
                    # snap gap onto the dist-cutoff distance directly.
                    snap_m = src_snap.gap_m + tgt_snap.gap_m
                    access_rows.append({
                        "hut_id": hub["id"], "start_id": t["id"], "start_type": t["type"],
                        "variant": variant.code,
                        "distance_m": float(dist_by_vertex[tv] + snap_m),
                        "time_s": float(time_by_vertex[tv]),
                    })
                    continue

                path = (path_by_vertex[tv] if tv != src_v
                        else accumulate_path(graph, vertex_coords, src_v, tv, []))
                # spec E3: the path sums only routed edges, so the hub-to-trail gap at both ends
                # is priced in here - it was contributing zero distance/ascent/descent otherwise.
                snap_m, ascent_m, descent_m = fold_endpoint_snaps(path, src_snap, tgt_snap)
                # spec C8: the cutoff above ran on `dist`, but the routed path is TIME-shortest,
                # whose distance_m (+ the snap gap folded in above, which is what's actually
                # shipped as distance_m below) can exceed the cap - re-check on that final value.
                if path.distance_m + snap_m > max_edge_m:
                    continue
                geometry = [(hub["lon"], hub["lat"]), *path.coords, (t["lon"], t["lat"])]
                hut_records.append({
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
                    "base_edge_ids": path.base_edge_ids,
                })
    return hut_records, access_rows


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


def merge_access_rows(shard_access_rows: list) -> list:
    """Flattens every worker's access_rows list into one - no dedup needed (spec A2: each hut is
    a core hub of exactly one cell, so each (hut, access, variant) row is emitted by exactly one
    worker; this is NOT true of hut_records, which merge_and_dedup above still dedups)."""
    return [row for shard in shard_access_rows for row in shard]


def _cell_workload_score(route_subgraphs_dir: Path, cell_id: int, n_huts: int) -> int:
    """Cheap LPT (longest-processing-time-first) scheduling proxy for a cell's __main__ task, read
    with no extra I/O beyond a stat() call: gather_route_subgraphs.py already cached this cell's
    local_edges.npy, and its on-disk byte size is an exact proxy for subgraph edge count - the
    dominant driver of build_igraph/distances/paths cost per variant (see
    compute_hub_edges_for_cell). Multiplying by n_huts (how many of this cell's HUTS get routed
    out of that subgraph as Dijkstra sources - spec A5: after the direction inversion, routing cost
    is driven by hut count, not total hub count, and the two are wildly uncorrelated; a cell can
    hold thousands of access-point hubs and a handful of huts) accounts for routing cost also
    scaling with source count, not just subgraph size. Sorting tasks by this score, largest first,
    before submitting to ProcessPoolExecutor minimizes makespan on the fixed worker pool: an
    unsorted or arbitrarily-ordered submission can leave a big cell as a straggler near the end,
    with every other worker idle waiting on it."""
    edges_path = cell_dir_for(route_subgraphs_dir, cell_id) / "local_edges.npy"
    try:
        size = edges_path.stat().st_size
    except OSError:
        size = 0
    return size * max(1, n_huts)


def _run_cell(args):
    route_subgraphs_dir, base_graph_dir, cell_id, core_hubs, candidate_hubs, max_edge_km, \
        variants, local_persisted = args
    t0 = time.time()
    timer = StepTimer()
    with timer.step("gather_subgraph"):
        subgraph = load_local_subgraph(cell_dir_for(route_subgraphs_dir, cell_id), base_graph_dir)
    # A4: every candidate in the padded cell needs a snap now (hut sources route to huts AND
    # access points), not just the hut subset - core_hubs is already a subset of candidate_hubs
    # (its own cell is inside its own padded bounds), so candidate_hubs alone covers both.
    keys = {(h["type"], h["id"]) for h in candidate_hubs}
    local_snaps = hub_snap.reconstruct_local_snaps(subgraph, keys, local_persisted)
    hut_records, access_rows = compute_hub_edges_for_cell(
        subgraph, core_hubs, candidate_hubs, max_edge_km, local_snaps, variants=variants,
        timer=timer,
    )
    n_huts = sum(1 for h in core_hubs if h["type"] == binfmt.TYPE_HUT)
    return {
        "cell_id": cell_id, "elapsed_s": time.time() - t0, "n_core_hubs": len(core_hubs),
        "n_core_huts": n_huts,
        "n_nodes": len(subgraph.local_nodes), "n_edges": len(subgraph.local_edges),
        "hut_records": hut_records, "access_rows": access_rows, "timer": timer,
    }


if __name__ == "__main__":
    config = load_config()
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-graph-dir", default=str(OSM_DIR / "base_graph"),
                         help="directory holding the persisted base graph (build_base_graph.py's output)")
    parser.add_argument("--route-subgraphs-dir", default=str(OSM_DIR / "route_subgraphs"),
                         help="directory holding gather_route_subgraphs.py's persisted per-cell gathers")
    parser.add_argument("--out-dir", default=str(OSM_DIR),
                         help="directory to write hut_edges/ and start_edges/ into")
    parser.add_argument("--max-edge-km", type=float, default=config["graph"]["maxEdgeKm"],
                         help="longest hut-to-hut trail distance kept as an edge (see pipeline.config.json's graph.maxEdgeKm)")
    parser.add_argument("--workers", type=int, default=None,
                         help="number of worker processes for the per-cell routing pass (default: os.cpu_count())")
    args = parser.parse_args()

    manifest = binfmt.load_manifest(Path(args.base_graph_dir) / "manifest.json")
    grid = Grid(manifest["bbox"], manifest["tile_size_km"])

    all_hubs_flat = load_all_hubs(OSM_DIR)

    print(f"loading persisted hub snaps from {args.out_dir} ...", flush=True)
    hub_snaps_arr = binfmt.load_array(Path(args.out_dir) / "hub_snaps.npy", mmap=False)
    hub_snap_interior_arr = binfmt.load_array(
        Path(args.out_dir) / "hub_snap_interior.npy", mmap=False
    )
    persisted_snaps = hub_snap.load_persisted_snaps(hub_snaps_arr, hub_snap_interior_arr)

    hubs_by_cell = bucket_by_cell(all_hubs_flat, grid)

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
        # A4: filter persisted-snaps down to EVERY candidate this cell could route to now (huts
        # and access points alike), not just this cell's own hubs + hut targets - see
        # snap_hubs_for_cell's docstring for why the candidate set widened.
        keys = {(h["type"], h["id"]) for h in candidate_hubs}
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
        key=lambda t: _cell_workload_score(
            route_subgraphs_dir_path, t[2], sum(1 for h in t[3] if h["type"] == binfmt.TYPE_HUT)
        ),
        reverse=True,
    )

    total = len(tasks)
    n_huts = sum(1 for h in all_hubs_flat if h["type"] == binfmt.TYPE_HUT)
    print(f"{total} cells with hubs to process "
          f"({n_huts:,} huts, {len(all_hubs_flat) - n_huts:,} access points)", flush=True)
    shard_hut_records = []
    shard_access_rows = []
    tracker = ProgressTracker(total)
    # Sums every worker's per-step totals. These are CPU-parallel seconds, so the columns add up
    # to more than the wall clock - the reading that matters is the ratio between steps (snap vs.
    # distances vs. paths), not the absolute number.
    run_timer = StepTimer()
    with phase(SCRIPT_NAME, "hub_edge_query", n_cells=total, n_huts=n_huts,
               n_access_points=len(all_hubs_flat) - n_huts,
               workers=args.workers or os.cpu_count(), max_edge_km=args.max_edge_km) as meta:
        for result in run_pool(tasks, _run_cell, workers=args.workers):
            shard_hut_records.append(result["hut_records"])
            shard_access_rows.append(result["access_rows"])
            run_timer.merge(result["timer"])
            eta = tracker.eta_suffix()
            cell_s = result["timer"].seconds
            print(
                f"[{tracker.completed}/{total}] cell {result['cell_id']}: "
                f"{result['elapsed_s']:.1f}s ({result['n_core_huts']} huts of "
                f"{result['n_core_hubs']} hubs, {result['n_nodes']:,} nodes, "
                f"{result['n_edges']:,} edges) -> {len(result['hut_records'])} hut edges, "
                f"{len(result['access_rows'])} access rows "
                f"| slice {cell_s.get('gather_subgraph', 0):.1f}s, snap "
                f"{cell_s.get('snap', 0):.1f}s, base_arrays "
                f"{cell_s.get('build_base_arrays', 0):.1f}s, igraph "
                f"{cell_s.get('build_igraph', 0):.1f}s, dist "
                f"{cell_s.get('distances', 0):.1f}s, paths {cell_s.get('paths', 0):.1f}s "
                f"| {eta}",
                flush=True,
            )
        meta.update(run_timer.as_meta())

    print(f"step totals (summed over workers): {run_timer.summary()}", flush=True)

    hut_records = merge_and_dedup(shard_hut_records)
    access_rows = merge_access_rows(shard_access_rows)

    print(f"hut-hut edges: {len(hut_records)}, "
          f"access distance rows (station/parking/partner -> hut, no geometry): {len(access_rows)}")
    # Per-variant breakdown (spec C2's grid, active_variants above) - build_hub_edges.py is the
    # one place that runs every row, so this is the cheapest place to sanity-check a variant's
    # row actually produced edges rather than reloading records.npy separately afterward.
    hut_counts_by_variant = Counter(r["variant"] for r in hut_records)
    access_counts_by_variant = Counter(r["variant"] for r in access_rows)
    for variant in active_variants:
        print(f"  {variant.name}: hut-hut {hut_counts_by_variant.get(variant.code, 0)}, "
              f"access {access_counts_by_variant.get(variant.code, 0)}")

    out_dir = Path(args.out_dir)
    write_edge_records(hut_records, out_dir / "hut_edges", write_edge_ids=True)
    write_access_distances(access_rows, out_dir / "access_distances.npy")
    print(f"written {out_dir / 'hut_edges'} and {out_dir / 'access_distances.npy'}")
