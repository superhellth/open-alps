#!/usr/bin/env python3
"""Split out of build_hub_edges.py (see docs/superpowers/plans/2026-08-23-split-build-hub-edges.md):
gathers and persists, once per hub-bearing cell, the max-edge-km-padded LocalSubgraph
(lib/subgraph.py's gather_padded_subgraph) that build_hub_edges.py's routing pass needs.

Why this is its own task: gather_padded_subgraph's cell-union + one-hop-closure + array-copy work
(see lib/subgraph.py's module docstring) depends only on --max-edge-km (and the base graph
itself) - NOT on pipeline.config.json's graph.variants grid, which build_hub_edges.py's routing
pass loops over separately. Before this split, retuning graph.variants (a real, common workflow -
see pipeline/CLAUDE.md's "pending run" note) forced every cell's gather to rerun too, even though
nothing about the gather depends on it. This task's own output is keyed (via dodo.py's
TaskOptionsChanged) on --max-edge-km/tile_size_km/schema_version only, so a variants-only retune
of build_hub_edges leaves it untouched and build_hub_edges.py just reloads the cached subgraphs.

Usage: python pipeline/phases/graph_building/gather_route_subgraphs.py [--max-edge-km 30]
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import binfmt  # noqa: E402
from lib.grid import Grid  # noqa: E402
from lib.hubs import bucket_by_cell, load_all_hubs  # noqa: E402
from lib.pipeline import OSM_DIR, load_config  # noqa: E402
from lib.progress import ProgressTracker  # noqa: E402
from lib.subgraph import gather_padded_subgraph, save_local_subgraph  # noqa: E402
from lib.timing import phase  # noqa: E402

SCRIPT_NAME = "gather_route_subgraphs.py"


def cell_dir_for(out_dir: Path, cell_id: int) -> Path:
    return out_dir / f"cell_{cell_id}"


if __name__ == "__main__":
    config = load_config()
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-graph-dir", default=str(OSM_DIR / "base_graph"))
    parser.add_argument("--out-dir", default=str(OSM_DIR / "route_subgraphs"))
    parser.add_argument("--max-edge-km", type=float, default=config["graph"]["maxEdgeKm"])
    args = parser.parse_args()

    manifest = binfmt.load_manifest(Path(args.base_graph_dir) / "manifest.json")
    grid = Grid(manifest["bbox"], manifest["tile_size_km"])

    hub_cells = set(bucket_by_cell(load_all_hubs(OSM_DIR), grid))

    out_dir = Path(args.out_dir)
    total = len(hub_cells)
    print(f"gathering {total} cell subgraphs (buffer_km={args.max_edge_km}) ...", flush=True)
    tracker = ProgressTracker(total)
    with phase(SCRIPT_NAME, "gather_route_subgraphs", n_cells=total, max_edge_km=args.max_edge_km):
        for cell_id in sorted(hub_cells):
            t0 = time.time()
            subgraph = gather_padded_subgraph(args.base_graph_dir, grid, cell_id, args.max_edge_km)
            save_local_subgraph(subgraph, cell_dir_for(out_dir, cell_id))
            elapsed = time.time() - t0
            eta = tracker.eta_suffix()
            print(
                f"[{tracker.completed}/{total}] cell {cell_id}: {elapsed:.1f}s "
                f"({len(subgraph.local_nodes):,} nodes, {len(subgraph.local_edges):,} edges) "
                f"| {eta}",
                flush=True,
            )

    manifest_out = {"cell_ids": sorted(hub_cells), "max_edge_km": args.max_edge_km}
    (out_dir).mkdir(parents=True, exist_ok=True)
    (out_dir / "manifest.json").write_text(json.dumps(manifest_out), encoding="utf-8")
    print(f"written {total} cell subgraphs to {out_dir}")
