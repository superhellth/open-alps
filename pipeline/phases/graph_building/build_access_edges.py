#!/usr/bin/env python3
"""B5/B6 of docs/superpowers/specs/2026-09-02-hub-edge-scaling-design.md: materializes full path
geometry ONLY for the pairs select_approach_pairs.py selected, writing the final start_edges/. This
is the second (and last) igraph pass over each cell's cached subgraph - build_hub_edges.py's own
first pass already proved which pairs are within max_edge_km (access_distances.npy); this one pays
for get_shortest_paths only on the survivors.

Routes with huts as sources, same direction as build_hub_edges.py (A1), then reorients each result
into the access->hut storage convention every consumer of start_edges/ expects (A3: reverse
path.coords, swap ascent_m/descent_m, THEN fold_endpoint_snaps with (access_snap, hut_snap) order -
see route_selected_pairs_for_cell's docstring for why the order matters).

Usage: python pipeline/phases/graph_building/build_access_edges.py [--max-edge-km 30] [--workers N]
Requires data/osm/selected_access_pairs.npy (select_approach_pairs.py), data/osm/hub_snaps.npy +
hub_snap_interior.npy (snap_hubs.py), data/osm/route_subgraphs/ (gather_route_subgraphs.py).
"""

import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import binfmt  # noqa: E402
from lib import hub_snap  # noqa: E402
from lib import variants as variants_lib  # noqa: E402
from lib.cell_igraph import accumulate_path, build_base_igraph_arrays, build_igraph_from_base  # noqa: E402
from lib.edge_output import fold_endpoint_snaps, write_edge_records  # noqa: E402
from lib.grid import Grid  # noqa: E402
from lib.hubs import bucket_by_cell, load_all_hubs  # noqa: E402
from lib.pipeline import OSM_DIR, load_config  # noqa: E402
from lib.progress import ProgressTracker, run_pool  # noqa: E402
from lib.subgraph import load_local_subgraph  # noqa: E402
from lib.timing import StepTimer, phase  # noqa: E402
from graph_building.gather_route_subgraphs import cell_dir_for  # noqa: E402

SCRIPT_NAME = "build_access_edges.py"


def route_selected_pairs_for_cell(subgraph, hut_sources: list, selected_targets_by_hut: dict,
                                   snaps: dict, variants: list, max_edge_km: float,
                                   timer: StepTimer = None) -> tuple:
    """hut_sources: this cell's core huts (build_hub_edges.py already proved these are the only
    valid Dijkstra sources for access edges, A1). selected_targets_by_hut: {hut_id: [access hub
    dict, ...]} - EXACTLY the targets select_approach_pairs.py kept for that hut; a hut with an
    empty or missing list here is simply not routed.

    max_edge_km: select_approach_pairs.py already filtered candidates on access_distances.npy's
    dist-weighted cutoff, but the path materialized here is TIME-shortest (weights="weight") and
    can exceed that cap once its own distance_m is computed (same C8 divergence build_hub_edges.py
    guards against for hut_edges) - re-checked below on the final, snap-gap-inclusive distance_m.

    Returns (records, n_unreachable_skipped). records: one dict per materialized record,
    access->hut oriented (A3): the path is walked hut->access (matching build_hub_edges.py's own
    direction, so both passes agree on which subgraph/snap state produced a given distance), then
    reversed before being packed - reverse path.coords, SWAP ascent_m/descent_m (base-graph
    ascent/descent is stored in a fixed u->v direction; a path walking v->u must swap them, same
    rule accumulate_path already applies per edge), THEN call fold_endpoint_snaps with
    (access_snap, hut_snap) order - fold_endpoint_snaps attributes each end's gap differently for
    departure vs. arrival, so it must see the already-reoriented path and the two snaps in the
    SAME (access-first) order the caller will store the record in.

    n_unreachable_skipped counts (hut, access, variant) tries where the target was unreachable
    under that variant's masked graph - expected, since selected_targets_by_hut is variant-agnostic
    (see __main__'s targets_by_hut) while reachability isn't; see accumulate_path's docstring."""
    timer = timer if timer is not None else StepTimer()
    if not hut_sources:
        return [], 0
    max_edge_m = max_edge_km * 1000

    with timer.step("build_base_arrays"):
        base_arrays = build_base_igraph_arrays(subgraph, snaps)

    records = []
    unreachable_skipped = [0]
    for variant in variants:
        mask = variants_lib.edge_mask(subgraph.local_edges, variant)
        with timer.step("build_igraph"):
            graph, hub_vertex, vertex_coords = build_igraph_from_base(base_arrays, edge_mask=mask)

        for hub in hut_sources:
            src_key = (hub["type"], hub["id"])
            targets = selected_targets_by_hut.get(hub["id"], [])
            if src_key not in hub_vertex or not targets:
                continue
            src_v = hub_vertex[src_key]
            routable = [t for t in targets if (t["type"], t["id"]) in hub_vertex]
            if not routable:
                continue
            target_vs = [hub_vertex[(t["type"], t["id"])] for t in routable]
            unique_path_vs = sorted({tv for tv in target_vs if tv != src_v})
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
            for t, tv in zip(routable, target_vs):
                path = (path_by_vertex[tv] if tv != src_v
                        else accumulate_path(graph, vertex_coords, src_v, tv, []))
                if path is None:
                    # selected_targets_by_hut is variant-agnostic (targets_by_hut's docstring in
                    # __main__): a pair select_approach_pairs.py kept because it was reachable
                    # under ONE variant (or pulled in by the reverse-closure) can be genuinely
                    # disconnected under a more restrictive variant's edge mask here. Skip it
                    # rather than let accumulate_path's empty-epath case masquerade as a real
                    # zero-distance edge.
                    unreachable_skipped[0] += 1
                    continue
                tgt_snap = snaps[(t["type"], t["id"])]
                # A3: reverse before folding - fold_endpoint_snaps' gap attribution depends on
                # traversal direction, so it must see the path already reoriented access->hut.
                reversed_path = path._replace(
                    coords=list(reversed(path.coords)),
                    ascent_m=path.descent_m, descent_m=path.ascent_m,
                    base_edge_ids=list(reversed(path.base_edge_ids)),
                )
                snap_m, ascent_m, descent_m = fold_endpoint_snaps(reversed_path, tgt_snap, src_snap)
                if reversed_path.distance_m + snap_m > max_edge_m:
                    continue
                geometry = [(t["lon"], t["lat"]), *reversed_path.coords, (hub["lon"], hub["lat"])]
                records.append({
                    "from_id": t["id"], "from_type": t["type"],
                    "to_id": hub["id"], "to_type": hub["type"],
                    "variant": variant.code,
                    "distance_m": float(reversed_path.distance_m + snap_m),
                    "road_m": float(reversed_path.road_m),
                    "ascent_m": float(ascent_m), "descent_m": float(descent_m),
                    "max_ele_m": (float(reversed_path.max_ele_m)
                                  if np.isfinite(reversed_path.max_ele_m) else 0.0),
                    "ungraded_m": float(reversed_path.ungraded_m),
                    "inferred_m": float(reversed_path.inferred_m),
                    "snap_m": float(snap_m),
                    "sac_rank": int(reversed_path.sac_rank),
                    "via_ferrata": bool(reversed_path.via_ferrata),
                    "geometry": geometry,
                    "base_edge_ids": reversed_path.base_edge_ids,
                })
    return records, unreachable_skipped[0]


def _run_cell(args):
    route_subgraphs_dir, base_graph_dir, cell_id, hut_sources, selected_targets_by_hut, \
        variants, local_persisted, max_edge_km = args
    t0 = time.time()
    timer = StepTimer()
    with timer.step("gather_subgraph"):
        subgraph = load_local_subgraph(cell_dir_for(route_subgraphs_dir, cell_id), base_graph_dir)
    keys = {(h["type"], h["id"]) for h in hut_sources}
    for targets in selected_targets_by_hut.values():
        keys.update((t["type"], t["id"]) for t in targets)
    with timer.step("snap"):
        local_snaps = hub_snap.reconstruct_local_snaps(subgraph, keys, local_persisted)
    records, unreachable_skipped = route_selected_pairs_for_cell(
        subgraph, hut_sources, selected_targets_by_hut, local_snaps, variants=variants,
        max_edge_km=max_edge_km, timer=timer,
    )
    return {
        "cell_id": cell_id, "elapsed_s": time.time() - t0, "records": records,
        "unreachable_skipped": unreachable_skipped, "timer": timer,
    }


if __name__ == "__main__":
    config = load_config()
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-graph-dir", default=str(OSM_DIR / "base_graph"))
    parser.add_argument("--route-subgraphs-dir", default=str(OSM_DIR / "route_subgraphs"))
    parser.add_argument("--selected-pairs", default=str(OSM_DIR / "selected_access_pairs.npy"))
    parser.add_argument("--out-dir", default=str(OSM_DIR),
                         help="directory to write start_edges/ into")
    parser.add_argument("--max-edge-km", type=float, default=config["graph"]["maxEdgeKm"],
                         help="longest hut-to-access trail distance kept as an edge (see pipeline.config.json's graph.maxEdgeKm)")
    parser.add_argument("--workers", type=int, default=None)
    args = parser.parse_args()

    manifest = binfmt.load_manifest(Path(args.base_graph_dir) / "manifest.json")
    grid = Grid(manifest["bbox"], manifest["tile_size_km"])

    all_hubs_flat = load_all_hubs(OSM_DIR)
    hub_by_key = {(h["type"], h["id"]): h for h in all_hubs_flat}
    huts_by_cell = bucket_by_cell([h for h in all_hubs_flat if h["type"] == binfmt.TYPE_HUT], grid)

    selected = binfmt.load_array(Path(args.selected_pairs), mmap=False)
    print(f"selected pairs to materialize: {len(selected):,}", flush=True)

    hub_snaps_arr = binfmt.load_array(Path(args.out_dir) / "hub_snaps.npy", mmap=False)
    hub_snap_interior_arr = binfmt.load_array(
        Path(args.out_dir) / "hub_snap_interior.npy", mmap=False
    )
    persisted_snaps = hub_snap.load_persisted_snaps(hub_snaps_arr, hub_snap_interior_arr)

    active_variants = variants_lib.enabled_variants(config)

    # {hut_id: {access hub dict, ...}} across every variant - a cell's routing pass reroutes every
    # active variant regardless of which one(s) selected the pair (spec B5: it re-runs one
    # Dijkstra per (hut, variant), the same shape as build_hub_edges.py's first pass).
    targets_by_hut = {}
    for r in selected:
        hut_id = int(r["hut_id"])
        key = (int(r["start_type"]), int(r["start_id"]))
        targets_by_hut.setdefault(hut_id, {})[key] = hub_by_key[key]

    tasks = []
    for cell_id, cell_huts in huts_by_cell.items():
        selected_targets_by_hut = {
            h["id"]: list(targets_by_hut.get(h["id"], {}).values())
            for h in cell_huts if h["id"] in targets_by_hut
        }
        if not selected_targets_by_hut:
            continue
        keys = {(h["type"], h["id"]) for h in cell_huts}
        for targets in selected_targets_by_hut.values():
            keys.update((t["type"], t["id"]) for t in targets)
        local_persisted = {k: persisted_snaps[k] for k in keys if k in persisted_snaps}
        tasks.append((
            Path(args.route_subgraphs_dir), Path(args.base_graph_dir), cell_id, cell_huts,
            selected_targets_by_hut, active_variants, local_persisted, args.max_edge_km,
        ))

    total = len(tasks)
    print(f"{total} cells with selected pairs to materialize", flush=True)
    shard_records = []
    total_unreachable_skipped = 0
    tracker = ProgressTracker(total)
    run_timer = StepTimer()
    with phase(SCRIPT_NAME, "build_access_edges", n_cells=total,
               n_pairs=len(selected), workers=args.workers) as meta:
        for result in run_pool(tasks, _run_cell, workers=args.workers):
            shard_records.append(result["records"])
            total_unreachable_skipped += result["unreachable_skipped"]
            run_timer.merge(result["timer"])
            eta = tracker.eta_suffix()
            print(
                f"[{tracker.completed}/{total}] cell {result['cell_id']}: "
                f"{result['elapsed_s']:.1f}s -> {len(result['records'])} records "
                f"({result['unreachable_skipped']} unreachable skipped) | {eta}",
                flush=True,
            )
        meta.update(run_timer.as_meta(), unreachable_skipped=total_unreachable_skipped)

    print(f"step totals (summed over workers): {run_timer.summary()}", flush=True)

    access_records = [r for shard in shard_records for r in shard]
    print(f"materialized access edges: {len(access_records)} "
          f"({total_unreachable_skipped} unreachable pairs skipped)", flush=True)

    out_dir = Path(args.out_dir)
    write_edge_records(access_records, out_dir / "start_edges", write_edge_ids=False)
    print(f"written {out_dir / 'start_edges'}")
