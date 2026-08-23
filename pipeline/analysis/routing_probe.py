#!/usr/bin/env python3
"""Sizing probe (spec 2026-08-22-tour-suggestion-backend.md §H). "Probe costs minutes; guessing
wrong costs hours of compute" - this is the gate `build_hub_edges.py`'s multi-hour variant rebuild
does not start without.

Samples ~200 hut pairs, stratified across the grid cells' terrain range (each cell's node
elevation spread as the strat key - a uniform sample over-weights the flat north and would
understate every constrained row's cost), and routes each pair over all nine grid combinations:
three CONSTRAINT ROWS (FAST_ANY / FAST_T2 / FAST_T3, via lib/variants.py's real edge_mask()) times
three OBJECTIVE COLUMNS. Only the FAST column (route on time_s) has a production counterpart today
- SHORT (route on dist) and ROAD_AVOID (route on time_s times a multiplicative road penalty, per
spec's "not lexicographic, not additive - a scale-free multiplier") are simulated here, in-probe,
because their only purpose is to measure whether they would ever be worth building. If adopted,
ROAD_AVOID's multiplier moves into lib/variants.py as a real column; until then this script is the
one place it exists, per analysis/README.md's rule for a classifier proposal with no production
counterpart yet.

Calls the real production functions: lib.subgraph.gather_padded_subgraph,
graph_building.build_hub_edges.snap_hub_to_subgraph / _build_igraph_with_snaps / _path_for,
lib.variants.edge_mask, lib.speed.edge_time_s / din_duration_h. Never reimplements routing itself.

Requires data/osm/base_graph/ WITH add_base_elevation.py already run (time_s/ascent_m/descent_m/
node_ele.npy/interior_ele.npy populated - a probe run before that measures a graph that no longer
represents what will be built) and data/osm/huts.geojson.

Runtime: minutes at the default 200-pair sample (--pairs), linear in it.

Writes data/analysis/routing_probe.json.
"""

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from lib import binfmt, speed, variants  # noqa: E402
from lib.grid import Grid  # noqa: E402
from lib.pipeline import DATA_DIR, OSM_DIR, hut_points, load_config  # noqa: E402
from lib.subgraph import gather_padded_subgraph  # noqa: E402
from graph_building.build_hub_edges import (  # noqa: E402
    _build_igraph_with_snaps, _path_for, snap_hub_to_subgraph,
)

OUT_PATH = DATA_DIR / "analysis" / "routing_probe.json"

ROWS = [binfmt.VARIANT_FAST_ANY, binfmt.VARIANT_FAST_T2, binfmt.VARIANT_FAST_T3]
COLUMNS = ("FAST", "SHORT", "ROAD_AVOID")
ROAD_MULTIPLIER = 4.0  # spec H: "factor ~3-5" - midpoint, probe-only until ROAD_* is adopted
N_STRATA = 5


def is_substitution(baseline_coords, candidate_coords) -> bool:
    """True when candidate_coords traces a different polyline than baseline_coords - a column or
    row earns its build cost by producing a DIFFERENT ROUTE, not merely a different number (spec
    C2). Equal-cost-different-geometry is still a substitution; only exact coordinate-sequence
    identity counts as "same"."""
    return [tuple(p) for p in baseline_coords] != [tuple(p) for p in candidate_coords]


def classify_blocker(reachable_ignoring_ungraded: bool, reachable_ignoring_difficulty: bool) -> str:
    """spec H.3: for a pair a constrained row cannot connect, tells apart "the only path crosses
    ungraded terrain" (relaxing the ungraded rule alone opens a path) from "the only path is
    graded but too hard" (relaxing the difficulty ceiling alone opens a path) from "there is no
    path under either relaxation" (a genuine disconnection, nothing to do with passability)."""
    if reachable_ignoring_ungraded and not reachable_ignoring_difficulty:
        return "ungraded"
    if reachable_ignoring_difficulty and not reachable_ignoring_ungraded:
        return "difficulty"
    if reachable_ignoring_ungraded and reachable_ignoring_difficulty:
        return "combined"
    return "disconnected"


def _road_avoid_weights(graph) -> list:
    dist = np.asarray(graph.es["dist"], dtype=np.float64)
    road_m = np.asarray(graph.es["road_m"], dtype=np.float64)
    time_s = np.asarray(graph.es["time_s"], dtype=np.float64)
    road_frac = np.divide(road_m, dist, out=np.zeros_like(dist), where=dist > 0)
    road_frac = np.clip(road_frac, 0.0, 1.0)
    return (time_s * (1.0 + (ROAD_MULTIPLIER - 1.0) * road_frac)).tolist()


def _row_graph(full_graph, row: int):
    """Derives a row-filtered graph from full_graph (built once per pair with edge_mask=None) via
    igraph's own subgraph_edges, instead of re-running _build_igraph_with_snaps's Python-level
    edge construction per row - that construction (per-edge interior-point gathers over a mmap
    array) is the expensive part per docs/superpowers/specs's build-cost analysis, and paying it
    three times per pair instead of once was what made a 3-pair smoke test miss a 120s budget.
    delete_vertices=False keeps every vertex id (and therefore hub_vertex) valid across rows -
    only edges are ever removed by a constraint row (spec C2: rows delete, never move, a vertex)."""
    if row == binfmt.VARIANT_FAST_ANY:
        return full_graph
    variant = variants.VARIANTS[row]
    sac_rank = np.asarray(full_graph.es["sac_rank"])
    constrained_ok = np.asarray(full_graph.es["constrained_ok"], dtype=bool)
    kept = constrained_ok & (sac_rank >= 0) & (sac_rank <= variant.max_sac_rank)
    kept_eids = np.nonzero(kept)[0].tolist()
    return full_graph.subgraph_edges(kept_eids, delete_vertices=False)


def _column_weights(graph, column: str) -> list:
    if column == "FAST":
        return graph.es["time_s"]
    if column == "SHORT":
        return graph.es["dist"]
    if column == "ROAD_AVOID":
        return _road_avoid_weights(graph)
    raise ValueError(column)


def _measure_path(graph, vertex_coords, src_v, tgt_v, weights):
    """Like build_hub_edges._path_for, but routes on an arbitrary weight list instead of the
    graph's own "weight" attribute (which is always time_s), so the probe can try SHORT/
    ROAD_AVOID columns without mutating production state. Returns None when no path exists."""
    if src_v == tgt_v:
        return {
            "coords": [], "distance_m": 0.0, "time_s": 0.0, "road_m": 0.0,
            "ascent_m": 0.0, "descent_m": 0.0, "sac_rank": -1, "via_ferrata": False,
        }
    epath = graph.get_shortest_paths(src_v, to=tgt_v, weights=weights, output="epath")[0]
    if not epath:
        # get_shortest_paths returns [] both for "unreachable" and for src==tgt (handled above);
        # confirm genuine unreachability by checking finite igraph distance.
        d = graph.distances(source=[src_v], target=[tgt_v], weights=weights)[0][0]
        if not math.isfinite(d):
            return None
    coords = []
    distance_m = time_s_total = road_m = ascent_m = descent_m = 0.0
    max_sac_rank = -1
    has_via_ferrata = False
    cur = src_v
    for eid in epath:
        e = graph.es[eid]
        forward = e.source == cur
        nxt = e.target if forward else e.source
        interior = e["interior"] if forward else list(reversed(e["interior"]))
        coords.append(vertex_coords[cur])
        coords.extend(interior)
        distance_m += e["dist"]
        time_s_total += e["time_s"]
        road_m += e["road_m"]
        ascent_m += e["ascent_m"] if forward else e["descent_m"]
        descent_m += e["descent_m"] if forward else e["ascent_m"]
        if e["sac_rank"] > max_sac_rank:
            max_sac_rank = e["sac_rank"]
        if e["via_ferrata"]:
            has_via_ferrata = True
        cur = nxt
    coords.append(vertex_coords[cur])
    return {
        "coords": coords, "distance_m": distance_m, "time_s": time_s_total, "road_m": road_m,
        "ascent_m": ascent_m, "descent_m": descent_m, "sac_rank": max_sac_rank,
        "via_ferrata": has_via_ferrata,
    }


def _cell_elevation_spread(base_graph_dir: Path) -> dict:
    """Per-cell (max - min) node elevation, used only to stratify pair sampling toward varied
    terrain - not a routing input. nodes.npy is grouped by cell (cell_index.npy gives each cell's
    contiguous slice), and node_ele.npy (add_base_elevation.py) is aligned 1:1 with nodes.npy."""
    cell_index = binfmt.load_array(base_graph_dir / "cell_index.npy")
    node_ele = binfmt.load_array(base_graph_dir / "node_ele.npy")
    spreads = {}
    for cid in range(len(cell_index)):
        start, count = int(cell_index["start_offset"][cid]), int(cell_index["count"][cid])
        if count == 0:
            continue
        ele = np.asarray(node_ele[start:start + count])
        spreads[cid] = float(ele.max() - ele.min())
    return spreads


def _sample_pairs(huts_by_cell: dict, cell_strata: dict, n_pairs: int, max_edge_km: float,
                   rng: random.Random) -> list:
    """Stratified sample: buckets cells into N_STRATA elevation-spread quantile bins, then draws
    pairs with the source hub's cell chosen uniformly across bins (not proportional to hub count),
    so the flat, hub-dense north cannot dominate the sample. The target hut is the nearest-by
    straight-line-distance hut within max_edge_km of the source that is not the source itself -
    trail distance is always >= straight-line, so this is a safe proxy for "plausibly connectable"
    (a pair with no straight-line-feasible partner would waste a probe slot on guaranteed
    disconnection, which is not what H.3's blocker classification is measuring)."""
    cells_with_huts = [c for c in huts_by_cell if c in cell_strata]
    if not cells_with_huts:
        raise ValueError("no grid cells with both huts and elevation data")
    spreads = sorted(cell_strata[c] for c in cells_with_huts)
    edges = [spreads[int(q * (len(spreads) - 1))] for q in np.linspace(0, 1, N_STRATA + 1)]
    bins = [[] for _ in range(N_STRATA)]
    for c in cells_with_huts:
        s = cell_strata[c]
        b = min(N_STRATA - 1, sum(1 for e in edges[1:-1] if s >= e))
        bins[b].append(c)
    bins = [b for b in bins if b]

    all_huts = [h for hubs in huts_by_cell.values() for h in hubs]
    pairs = []
    attempts = 0
    while len(pairs) < n_pairs and attempts < n_pairs * 50:
        attempts += 1
        b = bins[rng.randrange(len(bins))]
        cid = b[rng.randrange(len(b))]
        src = rng.choice(huts_by_cell[cid])
        candidates = [
            h for h in all_huts if h["id"] != src["id"]
            and _haversine_km(src["lon"], src["lat"], h["lon"], h["lat"]) <= max_edge_km
        ]
        if not candidates:
            continue
        tgt = rng.choice(candidates)
        pairs.append((src, tgt))
    return pairs


def _haversine_km(lon1, lat1, lon2, lat2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def run_probe(n_pairs: int, seed: int, direction_sample: int) -> dict:
    config = load_config()
    base_graph_dir = OSM_DIR / "base_graph"
    manifest = binfmt.load_manifest(base_graph_dir / "manifest.json")
    grid = Grid(manifest["bbox"], manifest["tile_size_km"])
    max_edge_km = config["graph"]["maxEdgeKm"]
    max_snap_m = config["graph"]["maxSnapM"]

    hut_coords = hut_points(OSM_DIR / "huts.geojson")
    huts = [{"id": i, "lon": lon, "lat": lat} for i, (lon, lat) in enumerate(hut_coords)]
    huts_by_cell = {}
    for h in huts:
        cid = grid.cell_id_for_point(h["lon"], h["lat"])
        huts_by_cell.setdefault(cid, []).append(h)

    print(f"{len(huts)} huts across {len(huts_by_cell)} grid cells; computing terrain strata...",
          flush=True)
    cell_strata = _cell_elevation_spread(base_graph_dir)

    rng = random.Random(seed)
    pairs = _sample_pairs(huts_by_cell, cell_strata, n_pairs, max_edge_km, rng)
    print(f"sampled {len(pairs)} pairs (target {n_pairs})", flush=True)

    wall_time_s = {col: [] for col in COLUMNS}
    substitution_hits = {(row, col): 0 for row in ROWS for col in COLUMNS}
    substitution_total = {(row, col): 0 for row in ROWS for col in COLUMNS}
    baseline_violates = {row: 0 for row in ROWS if row != binfmt.VARIANT_FAST_ANY}
    baseline_violates_total = {row: 0 for row in ROWS if row != binfmt.VARIANT_FAST_ANY}
    blocker_counts = {"ungraded": 0, "difficulty": 0, "combined": 0, "disconnected": 0}
    duration_pairs = []  # (routed_time_h, din_duration_h)
    direction_spread = []  # (same_geometry: bool, cost_ratio)

    def _process_pair(src, tgt, full_graph, row_graphs, hub_vertex, vertex_coords):
        src_key, tgt_key = ("hut", src["id"]), ("hut", tgt["id"])
        if src_key not in hub_vertex or tgt_key not in hub_vertex:
            return

        results = {}
        for col in COLUMNS:
            for row in ROWS:
                graph, hv, vc = row_graphs[row]
                if src_key not in hv or tgt_key not in hv:
                    results[(row, col)] = None
                    continue
                weights = _column_weights(graph, col)
                t0 = time.time()
                result = _measure_path(graph, vc, hv[src_key], hv[tgt_key], weights)
                elapsed = time.time() - t0
                if row == binfmt.VARIANT_FAST_ANY:
                    wall_time_s[col].append(elapsed)
                results[(row, col)] = result

        # Every one of the nine cells is compared against the SAME single reference - the one path
        # that actually ships today (FAST_ANY row, FAST column) - never against another cell's own
        # column. Comparing (FAST_ANY, SHORT) to (FAST_ANY, FAST) is what answers "does SHORT ever
        # produce a different route at all"; comparing it to itself (col-matched baseline) would be
        # trivially 0 by construction and silently hide the real answer to that question.
        reference = results.get((binfmt.VARIANT_FAST_ANY, "FAST"))
        if reference is not None:
            for row in ROWS:
                for col in COLUMNS:
                    r = results.get((row, col))
                    substitution_total[(row, col)] += 1
                    if r is not None and is_substitution(reference["coords"], r["coords"]):
                        substitution_hits[(row, col)] += 1

        for row in (binfmt.VARIANT_FAST_T2, binfmt.VARIANT_FAST_T3):
            baseline_violates_total[row] += 1
            epath = full_graph.get_shortest_paths(
                hub_vertex[src_key], to=hub_vertex[tgt_key], weights="time_s", output="epath"
            )[0]
            variant = variants.VARIANTS[row]
            violates = any(
                not (bool(full_graph.es[eid]["constrained_ok"])
                     and 0 <= full_graph.es[eid]["sac_rank"] <= variant.max_sac_rank)
                for eid in epath
            )
            if violates:
                baseline_violates[row] += 1

            if results.get((row, "FAST")) is None:
                # Reuses full_graph's own edge attributes (sac_rank/constrained_ok already carry
                # through split edges - Task 13) rather than rebuilding from the LocalSubgraph:
                # ignore_ungraded relaxes constrained_ok alone (ceiling still applies), ignore_
                # difficulty relaxes the ceiling alone (constrained_ok still applies).
                sac_rank = np.asarray(full_graph.es["sac_rank"])
                constrained_ok = np.asarray(full_graph.es["constrained_ok"], dtype=bool)
                kept_iu = (sac_rank >= 0) & (sac_rank <= variant.max_sac_rank)
                kept_id = constrained_ok
                g_iu = full_graph.subgraph_edges(np.nonzero(kept_iu)[0].tolist(), delete_vertices=False)
                g_id = full_graph.subgraph_edges(np.nonzero(kept_id)[0].tolist(), delete_vertices=False)
                reach_iu = _measure_path(
                    g_iu, vertex_coords, hub_vertex[src_key], hub_vertex[tgt_key], g_iu.es["time_s"]
                ) is not None
                reach_id = _measure_path(
                    g_id, vertex_coords, hub_vertex[src_key], hub_vertex[tgt_key], g_id.es["time_s"]
                ) is not None
                blocker_counts[classify_blocker(reach_iu, reach_id)] += 1

        fast_any = results.get((binfmt.VARIANT_FAST_ANY, "FAST"))
        if fast_any is not None and fast_any["distance_m"] > 0:
            routed_h = fast_any["time_s"] / 3600.0
            din_h = speed.din_duration_h(fast_any["distance_m"], fast_any["ascent_m"], fast_any["descent_m"])
            duration_pairs.append((routed_h, din_h))

        if len(direction_spread) < direction_sample and fast_any is not None:
            reverse = _path_for(full_graph, vertex_coords, hub_vertex[tgt_key], hub_vertex[src_key])
            rev_coords, rev_distance = reverse[0], reverse[1]
            # fast_any["coords"] and reverse's trail_coords are both _path_for-style traces (start
            # and end AT the snap vertex, no separate hub-coordinate prepend) - directly comparable
            # once reversed, no trimming needed.
            fwd_coords_rev = list(reversed(fast_any["coords"]))
            same = [tuple(p) for p in rev_coords] == [tuple(p) for p in fwd_coords_rev]
            cost_ratio = (rev_distance / fast_any["distance_m"]) if fast_any["distance_m"] > 0 else 1.0
            direction_spread.append((same, cost_ratio))

    # Grouped by the SOURCE hub's cell: gather_padded_subgraph + _build_igraph_with_snaps are the
    # genuinely expensive per-cell steps (spec's own cost analysis - a 60km padded cell holds
    # ~670k edges, and _build_igraph_with_snaps's per-edge Python interior-point gather dominates,
    # same as production build_hub_edges.py's "build_igraph" StepTimer step). Production pays that
    # cost once per cell and answers every pair sharing it; paying it once per SAMPLED PAIR instead
    # (46 cells but up to 200 pairs) is what made an early smoke test take ~15s/pair. Snapping only
    # the huts this cell's own sampled pairs actually need (not the whole hub set) keeps the snap
    # loop itself cheap.
    pairs_by_cell = {}
    for src, tgt in pairs:
        cid = grid.cell_id_for_point(src["lon"], src["lat"])
        pairs_by_cell.setdefault(cid, []).append((src, tgt))

    n_done = 0
    t_start = time.time()
    for cell_id, cell_pairs in pairs_by_cell.items():
        subgraph = gather_padded_subgraph(base_graph_dir, grid, cell_id, max_edge_km)
        needed_huts = {}
        for src, tgt in cell_pairs:
            needed_huts[src["id"]] = src
            needed_huts[tgt["id"]] = tgt
        snaps = {}
        for hub in needed_huts.values():
            snap = snap_hub_to_subgraph(subgraph, hub["lon"], hub["lat"], max_snap_m)
            if snap is not None:
                snaps[("hut", hub["id"])] = snap

        full_graph, hub_vertex, vertex_coords = _build_igraph_with_snaps(subgraph, snaps)
        row_graphs = {binfmt.VARIANT_FAST_ANY: (full_graph, hub_vertex, vertex_coords)}
        for row in (binfmt.VARIANT_FAST_T2, binfmt.VARIANT_FAST_T3):
            row_graphs[row] = (_row_graph(full_graph, row), hub_vertex, vertex_coords)

        for src, tgt in cell_pairs:
            _process_pair(src, tgt, full_graph, row_graphs, hub_vertex, vertex_coords)
            n_done += 1
            if n_done % 10 == 0 or n_done == len(pairs):
                elapsed = time.time() - t_start
                print(f"[{n_done}/{len(pairs)}] elapsed {elapsed:.1f}s, "
                      f"~{elapsed / n_done * (len(pairs) - n_done):.1f}s remaining", flush=True)

    def _sub_rate(row, col):
        total = substitution_total[(row, col)]
        return substitution_hits[(row, col)] / total if total else None

    fitted = _fit_speed_constants(duration_pairs)

    result = {
        "n_pairs_requested": n_pairs, "n_pairs_sampled": len(pairs), "seed": seed,
        "wall_time_s": {
            col: {"mean": float(np.mean(v)) if v else None, "n": len(v)}
            for col, v in wall_time_s.items()
        },
        "wall_time_ratio_to_fast": {
            col: (float(np.mean(wall_time_s[col])) / float(np.mean(wall_time_s["FAST"])))
            if wall_time_s[col] and wall_time_s["FAST"] else None
            for col in COLUMNS
        },
        "substitution_rate": {
            f"{binfmt.VARIANT_NAMES[row]}_{col}": _sub_rate(row, col)
            for row in ROWS for col in COLUMNS
        },
        "baseline_violates_row": {
            binfmt.VARIANT_NAMES[row]: (
                baseline_violates[row] / baseline_violates_total[row]
                if baseline_violates_total[row] else None
            )
            for row in baseline_violates
        },
        "ungraded_blocker_rate": blocker_counts,
        "duration_calibration": {
            "n_pairs": len(duration_pairs),
            "fitted_v0_k_s0": fitted,
        },
        "direction_spread": {
            "n_pairs": len(direction_spread),
            "same_geometry_fraction": (
                float(np.mean([1.0 if s else 0.0 for s, _ in direction_spread]))
                if direction_spread else None
            ),
            "cost_ratio_mean": (
                float(np.mean([r for _, r in direction_spread])) if direction_spread else None
            ),
        },
    }
    return result


def _fit_speed_constants(duration_pairs: list) -> dict:
    """Least-squares fit of the routed FAST_ANY time (hours) against DIN 33466 duration on the
    same pair, expressed as a single scale factor on the existing (v0, k, s0) - a full nonlinear
    refit of the Tobler-shaped curve is out of scope for a probe; this reports the multiplicative
    residual so Task 11 can decide whether v0 alone needs recalibrating or the shape itself does."""
    if not duration_pairs:
        return {"scale_routed_to_din": None, "residual_std": None}
    routed = np.array([r for r, _ in duration_pairs])
    din = np.array([d for _, d in duration_pairs])
    scale = float(np.sum(routed * din) / np.sum(din * din)) if np.sum(din * din) > 0 else None
    residual_std = float(np.std(routed - din)) if scale is not None else None
    return {"scale_routed_to_din": scale, "residual_std_h": residual_std}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--direction-sample", type=int, default=30,
                         help="route this many of the sampled pairs both directions too")
    args = parser.parse_args()

    result = run_probe(args.pairs, args.seed, args.direction_sample)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"written {OUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
