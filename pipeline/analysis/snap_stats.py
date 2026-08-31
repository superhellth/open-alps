#!/usr/bin/env python3
"""Standalone analysis script — not part of the doit task graph, not imported by any phase
script. Quantifies snap_hub_to_subgraph()'s three outcomes (existing-node, mid-chain split,
unsnapped) over the real hub set, calling that real production function directly against the
already-persisted base_graph/ output — no reimplementation of the snap logic, no changes to
build_hub_edges.py or dodo.py.

Answers: how many hubs snap to an existing node vs. a mid-chain point vs. nothing at all; how
expensive is the mid-chain search relative to the cheap node-only check; and how many of the
already-computed hut_edges/start_edges would lose an endpoint if mid-chain snapping were dropped
in favor of a simpler node-or-drop rule.

Requires data/osm/base_graph/ (build_base_graph.py) and, for the edge-impact section,
data/osm/hut_edges/ + start_edges/ (build_hub_edges.py) to already exist.

Usage: python pipeline/analysis/snap_stats.py [--max-snap-m 200]
"""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

# Import the real build_hub_edges.py module (not a copy) so snap_hub_to_subgraph, Grid,
# gather_padded_subgraph etc. are the exact functions the pipeline runs — this script never
# reimplements snap logic, only times and buckets it. build_hub_edges.py inserts pipeline/ onto
# sys.path itself at import time, so lib.* becomes importable afterward too.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases" / "graph_building"))
import build_hub_edges as bhe  # noqa: E402

DATA_DIR = bhe.OSM_DIR.parent
TYPE_NAMES = {
    bhe.binfmt.TYPE_HUT: "hut",
    bhe.binfmt.TYPE_STATION: "station",
    bhe.binfmt.TYPE_PARKING: "parking",
}


def assemble_hubs() -> list:
    """Same hub assembly as build_hub_edges.py's __main__ block (not extracted there as a
    function, so duplicated here rather than touching that script)."""
    hut_coords = bhe.hut_points(bhe.OSM_DIR / "huts.geojson")
    hut_coords_by_id = {i: tuple(c) for i, c in enumerate(hut_coords)}
    start_points = bhe.binfmt.load_array(bhe.OSM_DIR / "start_points.npy", mmap=False)
    start_by_id = {}
    for p in start_points:
        start_by_id.setdefault(int(p["type"]), {})[int(p["osm_id"])] = (
            float(p["lon"]), float(p["lat"]),
        )
    all_hub_coords_by_type = {bhe.binfmt.TYPE_HUT: hut_coords_by_id, **start_by_id}
    return [
        {"id": hid, "type": htype, "lon": lon, "lat": lat}
        for htype, coords_by_id in all_hub_coords_by_type.items()
        for hid, (lon, lat) in coords_by_id.items()
    ]


def group_by_cell(grid, hubs: list) -> dict:
    by_cell = {}
    for h in hubs:
        cid = grid.cell_id_for_point(h["lon"], h["lat"])
        by_cell.setdefault(cid, []).append(h)
    return by_cell


def percentile(sorted_values: list, pct: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, int(len(sorted_values) * pct))
    return sorted_values[idx]


def summarize_timing(elapsed_s_list: list) -> dict:
    if not elapsed_s_list:
        return {"n": 0, "mean_us": 0.0, "median_us": 0.0, "p95_us": 0.0, "total_s": 0.0}
    sorted_us = sorted(e * 1e6 for e in elapsed_s_list)
    return {
        "n": len(elapsed_s_list),
        "mean_us": statistics.mean(sorted_us),
        "median_us": statistics.median(sorted_us),
        "p95_us": percentile(sorted_us, 0.95),
        "total_s": sum(elapsed_s_list),
    }


def edge_impact(per_hub: list) -> dict:
    """For each already-computed edge set, counts how many edge records have an endpoint that
    only reached the graph via mid-chain snapping — i.e. how many real edges would silently
    vanish if mid-chain snapping were replaced by a simpler node-or-drop rule."""
    mid_chain_keys = {(h["type"], h["id"]) for h in per_hub if h["outcome"] == "mid_chain"}
    if not mid_chain_keys:
        return {}
    result = {}
    for name in ("hut_edges", "start_edges"):
        path = bhe.OSM_DIR / name / "records.npy"
        if not path.exists():
            continue
        records = bhe.binfmt.load_array(path, mmap=False)
        touched = 0
        for r in records:
            from_key = (int(r["from_type"]), int(r["from_id"]))
            to_key = (int(r["to_type"]), int(r["to_id"]))
            if from_key in mid_chain_keys or to_key in mid_chain_keys:
                touched += 1
        result[name] = {"total_edges": int(len(records)), "edges_touching_mid_chain_hub": touched}
    return result


def report(per_hub: list, total_elapsed_s: float, args) -> dict:
    by_outcome = {"node": [], "mid_chain": [], "unsnapped": []}
    by_outcome_type = {}
    for h in per_hub:
        by_outcome[h["outcome"]].append(h["elapsed_s"])
        by_outcome_type.setdefault((h["outcome"], TYPE_NAMES[h["type"]]), []).append(h["elapsed_s"])

    n_total = len(per_hub)
    print(f"{n_total} hubs, snap phase wall time {total_elapsed_s:.2f}s "
          f"(max-snap-m={args.max_snap_m})\n")
    print(f"{'outcome':<12}{'count':>8}{'%':>7}{'mean_us':>10}{'median_us':>10}"
          f"{'p95_us':>10}{'total_s':>10}")
    summary = {}
    for outcome in ("node", "mid_chain", "unsnapped"):
        s = summarize_timing(by_outcome[outcome])
        summary[outcome] = s
        pct = 100 * s["n"] / n_total if n_total else 0
        print(f"{outcome:<12}{s['n']:>8}{pct:>6.1f}%{s['mean_us']:>10.1f}"
              f"{s['median_us']:>10.1f}{s['p95_us']:>10.1f}{s['total_s']:>10.3f}")

    print("\nby hub type:")
    for outcome in ("node", "mid_chain", "unsnapped"):
        for type_name in ("hut", "station", "parking"):
            elapsed = by_outcome_type.get((outcome, type_name), [])
            if elapsed:
                print(f"  {outcome:<10} {type_name:<8} {len(elapsed)}")

    impact = edge_impact(per_hub)
    if impact:
        print("\nedge impact of mid-chain snapping (edges that would lose an endpoint if dropped):")
        for name, stats in impact.items():
            total = stats["total_edges"]
            pct = 100 * stats["edges_touching_mid_chain_hub"] / total if total else 0
            print(f"  {name}: {stats['edges_touching_mid_chain_hub']}/{total} ({pct:.1f}%)")

    return {
        "n_hubs": n_total,
        "total_elapsed_s": total_elapsed_s,
        "max_snap_m": args.max_snap_m,
        "summary_by_outcome": summary,
        "edge_impact": impact,
        "per_hub": per_hub,
    }


def main():
    config = bhe.load_config()
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-graph-dir", default=str(bhe.OSM_DIR / "base_graph"),
                        help="directory holding the persisted base graph (build_base_graph.py's output)")
    parser.add_argument("--max-snap-m", type=float, default=config["graph"]["maxSnapM"],
                        help="max distance (m) a hub may be from the nearest trail node to count as on-network (see pipeline.config.json's graph.maxSnapM)")
    parser.add_argument("--out", default=str(DATA_DIR / "analysis" / "snap_stats.json"),
                        help="path to write the snap-statistics report as JSON")
    args = parser.parse_args()

    manifest = bhe.binfmt.load_manifest(Path(args.base_graph_dir) / "manifest.json")
    grid = bhe.Grid(manifest["bbox"], manifest["tile_size_km"])

    hubs = assemble_hubs()
    by_cell = group_by_cell(grid, hubs)

    # Snapping only ever looks at nodes/edges within max_snap_m (plus a small margin for
    # mid-chain segment length) of the hub itself — nothing like build_hub_edges.py's
    # max_edge_km-sized buffer is needed here, since this script never computes a shortest path.
    buffer_km = max(args.max_snap_m / 1000.0 * 2, 0.5)

    total_cells = len(by_cell)
    total_hubs = len(hubs)
    print(f"{total_hubs} hubs across {total_cells} cells", flush=True)

    per_hub = []
    t_start = time.time()
    for i, (cid, cell_hubs) in enumerate(by_cell.items(), start=1):
        subgraph = bhe.gather_padded_subgraph(args.base_graph_dir, grid, cid, buffer_km)
        for hub in cell_hubs:
            t0 = time.perf_counter()
            snap = bhe.snap_hub_to_subgraph(subgraph, hub["lon"], hub["lat"], args.max_snap_m)
            elapsed = time.perf_counter() - t0
            if snap is None:
                outcome = "unsnapped"
            elif snap.node_index is not None:
                outcome = "node"
            else:
                outcome = "mid_chain"
            per_hub.append({
                "type": int(hub["type"]), "id": int(hub["id"]),
                "outcome": outcome, "elapsed_s": elapsed,
            })
        elapsed_total = time.time() - t_start
        avg_s = elapsed_total / i
        remaining_s = avg_s * (total_cells - i)
        print(
            f"[{i}/{total_cells}] cell {cid}: {len(cell_hubs)} hubs, {len(per_hub)}/{total_hubs} "
            f"done | elapsed {elapsed_total:.1f}s, ~{remaining_s:.1f}s remaining",
            flush=True,
        )
    total_elapsed_s = time.time() - t_start

    result = report(per_hub, total_elapsed_s, args)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"\nwritten {out_path}")


if __name__ == "__main__":
    main()
