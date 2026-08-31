#!/usr/bin/env python3
"""Does replacing the ArcGIS tour trace with Outdooractive's own published line fix the
`chain_not_reassembled` wipe-out? (spec 2026-08-29-official-tours-integration-design.md §2.7)

The shipped `match_tour_edges.py` run emitted 18 of 93 legs; 82 of its 84 gaps are
`chain_not_reassembled`, and the four tours that DID match are exactly the four whose ArcGIS
`paths` arrived as a single fragment. So `lib/tour_geometry.py`'s greedy joiner recovers zero
multi-fragment tours, and corridor routing (§2.3) has barely been tested at all - the run measured
reassembly, not matching.

`AVT_CAA_TOUR_View_L` turns out to be a shredded copy of geometry that Outdooractive (which
alpenvereinaktiv.com is a white-label of) serves already ordered: for LQR and Welser Höhenweg the
two sources agree to the point - 6,206 and 2,769 points respectively, same summed length. This
script routes each leg TWICE over the same base graph, changing exactly one input:

  baseline  oriented chain = orient_chain(reassemble_fragments(arcgis_paths))   [production today]
  oa        oriented chain = orient_chain(outdooractive_linestring)             [one clean chain]

and reports emitted-vs-gapped per tour per arm, with reasons. If the OA arm converts the nine
currently-failing tours into emitted legs, reassembly is dead weight and §2.4's leuvenmapmatching
fallback never needs scoping. If it doesn't, the problem was never fragmentation and the corridor
itself needs work.

Scope: the 10 tours whose ArcGIS `homepage` field already carries an alpenvereinaktiv tour id as
its trailing path segment (`/de/tour/<slug>/<id>/`). The other 15 have no OA id and are untouched
here - finding them needs a search endpoint this spike does not use.

NOT a verdict on OA's numbers. Their `metrics.ascent`/`length` disagree with their own stage sums
(HSHR: parent 2,111 m vs stages 2,612 m; RFD4T: parent 56.8 km vs stages 44.3 km), so only OA
GEOMETRY is under test - distance/ascent/descent stay DEM-derived, exactly as in production.

Requires data/osm/base_graph/ with compute_edge_profiles already run (routes on time_s;
lib/cell_igraph.py rejects an UNSET-time_s graph outright), plus hub_snaps.npy,
hub_snap_interior.npy, huts.geojson, tours.json and tour_traces.json.

NETWORK: unlike every other script in this directory, the first run GETs the Outdooractive
contents endpoint (one batched request, no auth, ~1.7 MB) and caches it to
data/osm/oa_tours_cache.json. Later runs read the cache; --no-fetch fails instead of fetching.

Runtime: minutes. One corridor gather + igraph build per leg per arm dominates; the baseline arm
mostly short-circuits before gathering, so the OA arm carries nearly all the cost.

Writes data/analysis/oa_corridor_spike.json.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from lib import binfmt, hub_snap  # noqa: E402
from lib.grid import Grid  # noqa: E402
from lib.pipeline import DATA_DIR, OSM_DIR, load_config  # noqa: E402
from lib.subgraph import clip_subgraph_to_bounds, gather_subgraph_for_bounds  # noqa: E402
from lib.tour_geometry import (  # noqa: E402
    assign_hut_position, leg_chain_slice, orient_chain, reassemble_fragments,
)
from graph_building.match_tour_edges import (  # noqa: E402
    build_tour_legs, corridor_bounds, match_leg,
)
from lib.geo import haversine_m  # noqa: E402
from lib.oa_geometry import fetch_oa_contents, oa_chain, oa_ids_by_tour  # noqa: E402

OUT_PATH = DATA_DIR / "analysis" / "oa_corridor_spike.json"
CACHE_PATH = OSM_DIR / "oa_tours_cache.json"


def run_arm(oriented, legs, tour, hut_coords, persisted_snaps, base_graph_dir, grid, args):
    """One arm's per-leg outcomes. Mirrors match_tour_edges.main()'s inner loop and calls its real
    functions (build_tour_legs / assign_hut_position / leg_chain_slice / haversine_m /
    corridor_bounds / gather_subgraph_for_bounds / clip_subgraph_to_bounds / match_leg) - only the
    ~15 lines of orchestration are restated here, because that loop lives inline in main() and
    analysis/README.md forbids refactoring phases/ to suit a measurement script.

    Deliberately omits build_tour_record: packing a matched leg exercises nothing this spike is
    asking about, and the record shape is already covered by the golden test."""
    if oriented is None:
        return [{"legIndex": i, "reason": "chain_not_reassembled"} for i, _, _ in legs]

    rows = []
    for leg_index, from_hut, to_hut in legs:
        from_coord, to_coord = hut_coords[from_hut], hut_coords[to_hut]

        from_pos = assign_hut_position(oriented, from_coord, args.max_hut_trace_m)
        to_pos = assign_hut_position(oriented, to_coord, args.max_hut_trace_m)
        if from_pos is None or to_pos is None:
            rows.append({"legIndex": leg_index, "reason": "hut_far_from_trace",
                         "detail": {"from_dist_m": from_pos and from_pos[1],
                                    "to_dist_m": to_pos and to_pos[1]}})
            continue

        leg_points = leg_chain_slice(oriented, from_pos[0], to_pos[0])
        trace_length_m = sum(
            haversine_m(leg_points[i][0], leg_points[i][1], leg_points[i + 1][0], leg_points[i + 1][1])
            for i in range(len(leg_points) - 1)
        )
        bounds = corridor_bounds(leg_points or oriented, args.corridor_buffer_m, grid)

        started = time.time()
        subgraph = clip_subgraph_to_bounds(
            gather_subgraph_for_bounds(base_graph_dir, grid, bounds), bounds,
        )
        result = match_leg(subgraph, (binfmt.TYPE_HUT, from_hut), (binfmt.TYPE_HUT, to_hut),
                           persisted_snaps, trace_length_m, args.length_divergence_ratio)
        elapsed = time.time() - started

        row = {"legIndex": leg_index, "traceLengthM": round(trace_length_m, 1),
               "corridorEdges": int(len(subgraph.local_edges)), "seconds": round(elapsed, 1)}
        if result["ok"]:
            path = result["path"]
            routed_m = path.distance_m + result["src_snap"].gap_m + result["tgt_snap"].gap_m
            row.update(reason=None, routedM=round(routed_m, 1),
                       ratio=round(routed_m / trace_length_m, 3) if trace_length_m else None,
                       ascentM=round(path.ascent_m, 1), descentM=round(path.descent_m, 1))
        else:
            row.update(reason=result["reason"], detail=result["detail"])
        rows.append(row)

        state = "ok" if result["ok"] else result["reason"]
        print(f"    leg {leg_index}: {state} ({elapsed:.1f}s, "
              f"{len(subgraph.local_edges):,} corridor edges)", flush=True)
    return rows


def main(argv=None):
    config = load_config()
    tm = config["tourMatch"]
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-graph-dir", default=str(OSM_DIR / "base_graph"),
                        help="directory holding the persisted base graph (build_base_graph.py's output)")
    parser.add_argument("--fragment-break-m", type=float, default=tm["fragmentBreakM"],
                        help="gap distance (m) beyond which a tour trace is split into a new fragment")
    parser.add_argument("--corridor-buffer-m", type=float, default=tm["corridorBufferM"],
                        help="buffer width (m) around a tour trace used to select candidate base-graph edges")
    parser.add_argument("--max-hut-trace-m", type=float, default=tm["maxHutTraceM"],
                        help="max distance (m) a tour's endpoint may sit from a hut to count as matched")
    parser.add_argument("--length-divergence-ratio", type=float,
                        default=tm["lengthDivergenceRatio"],
                        help="max allowed ratio between matched-edge length and the tour trace's own length")
    parser.add_argument("--tours", default="", help="comma-separated shortCodes to limit the run")
    parser.add_argument("--no-fetch", action="store_true",
                        help="fail rather than call the Outdooractive endpoint")
    args = parser.parse_args(argv)

    base_graph_dir = Path(args.base_graph_dir)
    manifest = binfmt.load_manifest(base_graph_dir / "manifest.json")
    grid = Grid(manifest["bbox"], manifest["tile_size_km"])

    with open(OSM_DIR / "tours.json", encoding="utf-8") as fh:
        tours = json.load(fh)
    with open(OSM_DIR / "tour_traces.json", encoding="utf-8") as fh:
        traces_by_tour_id = {t["tourId"]: t["paths"] for t in json.load(fh)}
    with open(OSM_DIR / "huts.geojson", encoding="utf-8") as fh:
        hut_coords = [tuple(f["geometry"]["coordinates"])
                      for f in json.load(fh)["features"]]

    hub_snaps_arr = binfmt.load_array(OSM_DIR / "hub_snaps.npy", mmap=False)
    hub_snap_interior_arr = binfmt.load_array(OSM_DIR / "hub_snap_interior.npy", mmap=False)
    persisted_snaps = hub_snap.load_persisted_snaps(hub_snaps_arr, hub_snap_interior_arr)

    by_tour_id = oa_ids_by_tour(tours)
    wanted = {c.strip() for c in args.tours.split(",") if c.strip()}
    selected = [t for t in tours
                if t["tourId"] in by_tour_id and (not wanted or t["shortCode"] in wanted)]
    if not selected:
        raise SystemExit(f"no tours selected (--tours={args.tours!r})")
    print(f"{len(selected)} tours carry an alpenvereinaktiv id", flush=True)

    contents = fetch_oa_contents([by_tour_id[t["tourId"]] for t in selected], CACHE_PATH,
                                 allow_fetch=not args.no_fetch)

    results = []
    for tour in selected:
        legs = build_tour_legs(tour)
        if not legs:
            print(f"{tour['shortCode']}: no legs (hutIndices={tour['hutIndices']})", flush=True)
            continue
        hut_coords_in_order = [hut_coords[h] for h in tour["hutIndices"] if h != -1]
        is_loop = tour["isLoop"]

        # BASELINE: exactly what match_tour_edges.main() builds today.
        chains = reassemble_fragments(traces_by_tour_id.get(tour["tourId"], []),
                                      args.fragment_break_m)
        baseline_chain = (orient_chain(chains[0], hut_coords_in_order, is_loop)
                          if len(chains) == 1 else None)

        # OA ARM: the published line, oriented by the same function against the same hut order.
        oa_points = oa_chain(contents.get(by_tour_id[tour["tourId"]], {}))
        oa_oriented = orient_chain(oa_points, hut_coords_in_order, is_loop) if oa_points else None

        print(f"\n{tour['shortCode']}: {len(legs)} legs | arcgis {len(chains)} chain(s) "
              f"| oa {len(oa_points):,} pts", flush=True)

        print("  baseline:", flush=True)
        baseline = run_arm(baseline_chain, legs, tour, hut_coords, persisted_snaps,
                           base_graph_dir, grid, args)
        print("  oa:", flush=True)
        oa = run_arm(oa_oriented, legs, tour, hut_coords, persisted_snaps,
                     base_graph_dir, grid, args)

        results.append({
            "tourId": tour["tourId"], "shortCode": tour["shortCode"], "name": tour["name"],
            "oaId": by_tour_id[tour["tourId"]], "isLoop": is_loop, "nLegs": len(legs),
            "arcgisChains": len(chains), "oaPoints": len(oa_points),
            "baseline": baseline, "oa": oa,
        })

    def emitted(rows):
        return sum(1 for r in rows if r.get("reason") is None)

    total_legs = sum(r["nLegs"] for r in results)
    base_ok = sum(emitted(r["baseline"]) for r in results)
    oa_ok = sum(emitted(r["oa"]) for r in results)

    print(f"\n{'code':26} {'legs':>4} {'baseline':>8} {'oa':>4}")
    for r in results:
        print(f"{r['shortCode'][:26]:26} {r['nLegs']:4d} "
              f"{emitted(r['baseline']):8d} {emitted(r['oa']):4d}", flush=True)
    print(f"{'TOTAL':26} {total_legs:4d} {base_ok:8d} {oa_ok:4d}")

    reasons = {}
    for r in results:
        for arm in ("baseline", "oa"):
            for row in r[arm]:
                if row.get("reason"):
                    reasons.setdefault(arm, {}).setdefault(row["reason"], 0)
                    reasons[arm][row["reason"]] += 1
    print(f"\ngap reasons: {json.dumps(reasons)}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump({
            "config": {k: getattr(args, k) for k in
                       ("fragment_break_m", "corridor_buffer_m", "max_hut_trace_m",
                        "length_divergence_ratio")},
            "totals": {"legs": total_legs, "baselineEmitted": base_ok, "oaEmitted": oa_ok},
            "gapReasons": reasons,
            "tours": results,
        }, fh, indent=2)
    print(f"written {OUT_PATH}")


if __name__ == "__main__":
    main()
