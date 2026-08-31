#!/usr/bin/env python3
"""Standalone analysis script - not part of the doit task graph, not imported by any phase script.

Answers the one question docs/superpowers/specs/2026-08-20-tiled-contraction-design.md never asks:
is contract_structural's 3963s CPU-bound or memory-bound? 3963s over 41.4M raw edges is ~96us per
edge, roughly 30x what the walk body's Python work should cost, on a box with 17.1 GB RAM and
20.1 GB of swap behind it.

Contracts increasingly large subsets of the REAL graph (rebuilt by reconstruct_raw_graph.py) and
records seconds-per-raw-edge next to peak RSS for each:
  - flat us/edge, RSS well under RAM     -> CPU-bound  -> tiling is the right fix (ceiling: 6
                                                          physical cores, not 88 cells)
  - us/edge climbing as RSS nears 17 GB  -> memory-bound -> fix memory first, re-measure

Subsets are densest-cell-first and nested, so the worst-case alpine cell - the one that would set
a tiled design's wall-clock floor - is present at every size.

See docs/superpowers/plans/2026-08-20-contraction-measurement-spike.md.

Usage: python pipeline/analysis/contraction_scaling.py [--fractions 0.05,0.1,0.25,0.5,0.75,1.0]
       python pipeline/analysis/contraction_scaling.py --profile-fraction 0.05
Runtime: the densest cell alone (3.7% of raw nodes, 1.6M raw edges) contracts in 6.2s = 3.83us per
edge, so at that rate the WHOLE graph is ~160s and the default sweep is ~6 min total. The recorded
full-run figure is 3963s (96us/edge, 25x worse), so any large fraction taking dramatically longer
than the linear projection IS the finding - budget for it running much longer than 6 min.
"""

import argparse
import cProfile
import io
import json
import pstats
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import binfmt  # noqa: E402
from lib.contraction import contract_structural  # noqa: E402
from lib.grid import Grid  # noqa: E402
from lib.memtrace import rss_sampler  # noqa: E402
from lib.pipeline import DATA_DIR, OSM_DIR  # noqa: E402
from reconstruct_raw_graph import reconstruct_raw, select_edges_in_cells  # noqa: E402


def cells_by_density(nodes, n_cells: int) -> list[int]:
    counts = np.bincount(np.asarray(nodes["cell_id"]), minlength=n_cells)
    order = np.argsort(-counts, kind="stable")
    return [int(c) for c in order if counts[c] > 0]


def pick_cell_sets(nodes, n_cells: int, fractions) -> list[tuple[float, list[int]]]:
    """Densest-first nested prefixes: the cells needed to cover each target fraction of all nodes.
    Nested so each larger measurement is a strict superset of the smaller ones - otherwise a
    size-vs-time curve would also be measuring a change of terrain.

    Sorted and de-duplicated here rather than trusted from the caller: --fractions is free text,
    and out-of-order values would break both the nesting above and run_sweep's
    last/first us-per-edge ratio, silently and with plausible-looking output."""
    fractions = sorted(set(fractions))
    ranked = cells_by_density(nodes, n_cells)
    counts = np.bincount(np.asarray(nodes["cell_id"]), minlength=n_cells)
    total = counts.sum()
    cum = np.cumsum([counts[c] for c in ranked])

    out = []
    for f in fractions:
        k = int(np.searchsorted(cum, f * total) + 1)
        out.append((f, ranked[:min(k, len(ranked))]))
    return out


def _load(base_graph_dir):
    d = Path(base_graph_dir)
    nodes = binfmt.load_array(d / "nodes.npy")
    edges = binfmt.load_array(d / "edges.npy")
    interior = binfmt.load_array(d / "interior.npy")
    manifest = binfmt.load_manifest(d / "manifest.json")
    grid = Grid(manifest["bbox"], manifest["tile_size_km"])
    return nodes, edges, interior, grid


def run_sweep(base_graph_dir, fractions, out_path):
    nodes, edges, interior, grid = _load(base_graph_dir)
    n_cells = len(grid.all_cell_ids())

    results = []
    sets = pick_cell_sets(nodes, n_cells, fractions)
    for step, (frac, cells) in enumerate(sets, start=1):
        edge_ids = select_edges_in_cells(nodes, edges, set(cells))
        raw = reconstruct_raw(nodes, edges, interior, edge_ids)
        print(f"[{step}/{len(sets)}] fraction {frac:.0%}: {len(cells)} cells -> "
              f"{len(raw.coords):,} raw nodes / {len(raw.edges_i):,} raw edges, "
              f"contracting ...", flush=True)

        t0 = time.monotonic()
        with rss_sampler() as sample:
            contract_structural(*raw.as_args())
        seconds = time.monotonic() - t0

        rec = {
            "fraction": frac,
            "n_cells": len(cells),
            "raw_nodes": int(len(raw.coords)),
            "raw_edges": int(len(raw.edges_i)),
            "seconds": round(seconds, 2),
            "us_per_edge": round(seconds * 1e6 / max(1, len(raw.edges_i)), 2),
            **sample.as_meta(),
        }
        results.append(rec)
        with open(out_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"    {seconds:,.1f}s | {rec['us_per_edge']} us/edge | "
              f"peak RSS {rec['peak_rss_gb']} GB of {rec['total_ram_gb']} GB | "
              f"swap-in {rec['swap_in_delta_mb']} MB", flush=True)

        del raw

    print("\nfraction  raw_edges     seconds  us/edge  peak_rss_gb  swap_in_mb", flush=True)
    for r in results:
        print(f"{r['fraction']:>7.0%}  {r['raw_edges']:>10,}  {r['seconds']:>9,.1f}  "
              f"{r['us_per_edge']:>7.2f}  {r['peak_rss_gb']:>11.2f}  "
              f"{r['swap_in_delta_mb']:>10.1f}", flush=True)
    if len(results) >= 2:
        # safe because pick_cell_sets sorted the fractions, so results runs smallest -> largest
        ratio = results[-1]["us_per_edge"] / results[0]["us_per_edge"]
        print(f"\nus/edge ratio (largest / smallest): {ratio:.2f}x", flush=True)
        print("  < 1.3x  -> linear, CPU-bound          -> tiling justified (ceiling ~6 cores)",
              flush=True)
        print("  > 2.0x  -> super-linear, memory-bound -> fix memory first, re-measure",
              flush=True)
    return results


def profile_one(base_graph_dir, fraction, out_path):
    """One contraction under cProfile at a deliberately small fraction - cProfile's per-call
    overhead makes long runs pointless, and what matters here is the SHARE of time in the walk's
    hot spots (_neighbors' per-node .tolist(), the two scalar coords[] reads per interior node),
    not the absolute seconds."""
    nodes, edges, interior, grid = _load(base_graph_dir)

    _, cells = pick_cell_sets(nodes, len(grid.all_cell_ids()), [fraction])[0]
    edge_ids = select_edges_in_cells(nodes, edges, set(cells))
    raw = reconstruct_raw(nodes, edges, interior, edge_ids)
    print(f"profiling contraction over {len(raw.edges_i):,} raw edges "
          f"({len(cells)} cells) ...", flush=True)

    profiler = cProfile.Profile()
    profiler.enable()
    contract_structural(*raw.as_args())
    profiler.disable()

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    profiler.dump_stats(str(out_path))

    buf = io.StringIO()
    pstats.Stats(profiler, stream=buf).sort_stats("cumulative").print_stats(20)
    table = buf.getvalue()
    print(table, flush=True)
    print(f"raw stats written to {out_path} (open with: python -m pstats {out_path})", flush=True)
    return table


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-graph", default=str(OSM_DIR / "base_graph"),
                        help="directory holding the persisted base graph (build_base_graph.py's output)")
    parser.add_argument("--fractions", default="0.05,0.1,0.25,0.5,0.75,1.0",
                        help="comma-separated fractions of the base graph to contract, for the scaling sweep")
    parser.add_argument("--out", default=str(DATA_DIR / "contraction_scaling.jsonl"),
                        help="path to write the scaling results as JSON lines")
    parser.add_argument("--profile-fraction", type=float, default=None,
                        help="skip the sweep; cProfile one contraction at this fraction")
    parser.add_argument("--profile-out", default=str(DATA_DIR / "contraction.prof"),
                        help="path to write the cProfile output when --profile-fraction is set")
    args = parser.parse_args(argv)

    if args.profile_fraction is not None:
        profile_one(args.base_graph, args.profile_fraction, Path(args.profile_out))
        return

    fractions = [float(x) for x in args.fractions.split(",")]
    run_sweep(args.base_graph, fractions, Path(args.out))


if __name__ == "__main__":
    main()
