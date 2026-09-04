#!/usr/bin/env python3
"""Split out of build_hub_edges.py (see docs/superpowers/plans/2026-08-23-split-build-hub-edges.md):
snaps every hub (hut/station/parking) onto the persisted base graph (build_base_graph.py,
lib/binfmt.py) ONCE, independent of --max-edge-km and pipeline.config.json's graph.variants grid,
and persists the result (lib/hub_snap.py's PersistedSnap, keyed by globally-stable node/edge ids)
to hub_snaps.npy/hub_snap_interior.npy for build_hub_edges.py's routing pass to reuse.

Why this is its own task: a hub only ever needs to snap once (docstring precedent already in
build_hub_edges.py's old __main__ - "the same real-world geometry gives the same outcome each
time"), and snapping itself only needs trail data within max_snap_m, not max_edge_km. The old
single-task pipeline snapped every hub inside build_hub_edges.py's own max_edge_km-sized cell
gather, so retuning --max-edge-km (the single most commonly retuned knob per pipeline/README.md's
own usage example) or pipeline.config.json's graph.variants forced a full hub-snapping pass to
rerun for no reason - snapping doesn't depend on either. Splitting it out means:
  - This task's own subgraph gather uses a MUCH smaller buffer_km (sized off max_snap_m, a few
    hundred metres, not max_edge_km's tens of km) - cheaper per cell, and a pure function of
    --max-snap-m/--max-snap-ascent-m so it's untouched by edge-km/variant retunes.
  - build_hub_edges.py's routing pass gathers its own (large, max_edge_km-sized) subgraph as
    before, but looks up precomputed snaps instead of recomputing them.

Usage: python pipeline/phases/graph_building/snap_hubs.py [--max-snap-m 100] [--workers N]
"""

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import binfmt  # noqa: E402
from lib import hub_snap  # noqa: E402
from lib.grid import Grid  # noqa: E402
from lib.hubs import bucket_by_cell, load_all_hubs  # noqa: E402
from lib.pipeline import DEM_DIR, OSM_DIR, load_config  # noqa: E402
from lib.progress import ProgressTracker, run_pool  # noqa: E402
from lib.subgraph import gather_padded_subgraph  # noqa: E402
from lib.timing import StepTimer, phase  # noqa: E402

SCRIPT_NAME = "snap_hubs.py"

# Snapping only ever needs trail data within max_snap_m of a hub, so this task's subgraph gather
# can use a buffer sized off that (converted m -> km, generously padded) instead of
# build_hub_edges.py's max_edge_km-sized one - see this module's docstring. The 1.0km floor covers
# a chain-contracted edge's longest single segment possibly running to that scale even when
# max_snap_m itself is small (_build_edge_spatial_index's own query radius already pads by that
# segment length, but the subgraph has to actually contain the data first).
SNAP_BUFFER_FLOOR_KM = 1.0
SNAP_BUFFER_MULTIPLIER = 3.0


def _buffer_km_for(max_snap_m: float) -> float:
    return max(max_snap_m / 1000.0 * SNAP_BUFFER_MULTIPLIER, SNAP_BUFFER_FLOOR_KM)


def _run_cell(args):
    base_graph_dir, grid, cell_id, buffer_km, hubs, max_snap_m, max_snap_ascent_m = args
    t0 = time.time()
    timer = StepTimer()
    with timer.step("gather_subgraph"):
        subgraph = gather_padded_subgraph(base_graph_dir, grid, cell_id, buffer_km)
    persisted = {}
    rejections = []
    with timer.step("snap"):
        for h in hubs:
            result = hub_snap.snap_hub_to_subgraph(
                subgraph, h["lon"], h["lat"], max_snap_m,
                hub_ele_m=h.get("ele"), max_snap_ascent_m=max_snap_ascent_m,
            )
            if isinstance(result, hub_snap.SnapResult):
                persisted[(h["type"], h["id"])] = hub_snap.to_persisted(subgraph, result)
            else:
                rejections.append(
                    hub_snap.SnapRejection(
                        gap_m=result.gap_m, dz_m=result.dz_m, reason=result.reason,
                        hub_id=h["id"], hub_type=h["type"], name=h.get("name", ""),
                    )
                )
    return {
        "cell_id": cell_id, "elapsed_s": time.time() - t0, "n_hubs": len(hubs),
        "n_nodes": len(subgraph.local_nodes), "n_edges": len(subgraph.local_edges),
        "persisted": persisted, "rejections": rejections, "timer": timer,
    }


if __name__ == "__main__":
    config = load_config()
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-graph-dir", default=str(OSM_DIR / "base_graph"),
                         help="directory holding the persisted base graph (build_base_graph.py's output)")
    parser.add_argument("--out-dir", default=str(OSM_DIR),
                         help="directory to write the persisted hub-snap cache into")
    parser.add_argument("--max-snap-m", type=float, default=config["graph"]["maxSnapM"],
                         help="max distance (m) a hub may be from the nearest trail node to count as on-network (see pipeline.config.json's graph.maxSnapM)")
    parser.add_argument("--max-snap-ascent-m", type=float,
                         default=config["graph"]["maxSnapAscentM"],
                         help="max vertical distance (m) a candidate snap point may sit from the hub's own DEM elevation (see pipeline.config.json's graph.maxSnapAscentM)")
    parser.add_argument("--dem", default=str(DEM_DIR / "dem.tif"),
                         help="path to the materialized DEM GeoTIFF (build_dem_vrt.py's output)")
    parser.add_argument("--workers", type=int, default=None,
                         help="number of worker processes for the snap pass (default: os.cpu_count())")
    args = parser.parse_args()

    manifest = binfmt.load_manifest(Path(args.base_graph_dir) / "manifest.json")
    grid = Grid(manifest["bbox"], manifest["tile_size_km"])

    all_hubs_flat = load_all_hubs(OSM_DIR)

    dem_path = Path(args.dem)
    if dem_path.exists():
        print(f"sampling {len(all_hubs_flat):,} hub elevations from {dem_path} ...", flush=True)
        hub_snap.sample_hub_elevations(dem_path, all_hubs_flat, grid)
    else:
        print(f"WARNING: {dem_path} not found - snap gaps priced without a vertical component",
              flush=True)

    hubs_by_cell = bucket_by_cell(all_hubs_flat, grid)

    buffer_km = _buffer_km_for(args.max_snap_m)
    tasks = [
        (args.base_graph_dir, grid, cid, buffer_km, hubs, args.max_snap_m, args.max_snap_ascent_m)
        for cid, hubs in hubs_by_cell.items()
    ]

    total = len(tasks)
    n_huts = sum(1 for h in all_hubs_flat if h["type"] == binfmt.TYPE_HUT)
    print(f"{total} cells with hubs to snap "
          f"({n_huts:,} huts, {len(all_hubs_flat) - n_huts:,} access points), "
          f"buffer_km={buffer_km:.2f}", flush=True)

    all_persisted = {}
    all_rejections = []
    tracker = ProgressTracker(total)
    run_timer = StepTimer()
    with phase(SCRIPT_NAME, "hub_snap", n_cells=total, n_huts=n_huts,
               n_access_points=len(all_hubs_flat) - n_huts,
               workers=args.workers or os.cpu_count(), max_snap_m=args.max_snap_m,
               max_snap_ascent_m=args.max_snap_ascent_m, buffer_km=buffer_km) as meta:
        for result in run_pool(tasks, _run_cell, workers=args.workers):
            all_persisted.update(result["persisted"])
            all_rejections.extend(result["rejections"])
            run_timer.merge(result["timer"])
            eta = tracker.eta_suffix()
            print(
                f"[{tracker.completed}/{total}] cell {result['cell_id']}: "
                f"{result['elapsed_s']:.1f}s ({result['n_hubs']} hubs, {result['n_nodes']:,} "
                f"nodes, {result['n_edges']:,} edges) -> {len(result['persisted'])} snapped "
                f"| {eta}",
                flush=True,
            )
        meta.update(run_timer.as_meta())

    print(f"step totals (summed over workers): {run_timer.summary()}", flush=True)
    reason_counts = {}
    for r in all_rejections:
        reason_counts[r.reason] = reason_counts.get(r.reason, 0) + 1
    print(f"snapped {len(all_persisted)}, unsnapped {len(all_rejections)} ({reason_counts})",
          flush=True)

    out_dir = Path(args.out_dir)
    hub_snap.pack_hub_snaps(all_persisted, out_dir)
    hub_snap.write_unsnapped_report(out_dir / "unsnapped_huts.json", all_rejections)
    print(f"written {out_dir / 'hub_snaps.npy'}, {out_dir / 'hub_snap_interior.npy'} and "
          f"{out_dir / 'unsnapped_huts.json'}")
