#!/usr/bin/env python3
"""Standalone analysis script - not part of the doit task graph, not imported by any phase
script. Reports the road_m / distance_m distribution over the already-computed hut_edges/ and
start_edges/ records.

Answers open question 1 of docs/superpowers/specs/2026-08-22-tour-suggestion-backend.md: is the
`ROAD_*` variant column worth building? Dropping roadPenaltyFactor (spec A3) leaves nothing
steering routed paths off asphalt, and the size of that regression is currently unknown rather
than small. This is the cheapest available bound on it.

READ THE SIGN OF THE BIAS BEFORE USING THE NUMBER. These records were routed under the *distance*
cost with roadPenaltyFactor 1.3 actively penalising roads. The time-based cost of spec A1 removes
that penalty and additionally rewards roads for being fast, so the post-rebuild road share can
only be higher. This measurement is therefore a floor, not a prediction - a floor that is already
bad settles the question early, and a low floor settles nothing and defers to the post-rebuild
re-run (spec H, "post-rebuild measurements"). Re-run this script unchanged after the rebuild to
get the real figure; the two runs are directly comparable.

Requires data/osm/hut_edges/records.npy and data/osm/start_edges/records.npy
(build_hub_edges.py). Writes data/analysis/road_share.json.

Runtime: seconds. Reads records.npy only - never touches geometry.npy or the DEM.

Usage: python pipeline/analysis/road_share.py [--thresholds 0.1,0.2,0.5]
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import binfmt  # noqa: E402
from lib.pipeline import OSM_DIR, load_config  # noqa: E402

DATA_DIR = OSM_DIR.parent
OUT_PATH = DATA_DIR / "analysis" / "road_share.json"
PERCENTILES = (5, 25, 50, 75, 90, 95, 99)


def describe(share, weights_m, thresholds):
    """`share` is per-edge road fraction; `weights_m` its distance, so the aggregate share is
    length-weighted rather than an average of ratios (which would let a 200 m stub outvote a
    25 km traverse)."""
    n = len(share)
    if n == 0:
        return {"n": 0}
    return {
        "n": int(n),
        "aggregate_road_share": round(float(weights_m @ share / max(weights_m.sum(), 1.0)), 4),
        "mean_edge_share": round(float(share.mean()), 4),
        "percentiles": {f"p{p}": round(float(np.percentile(share, p)), 4) for p in PERCENTILES},
        "edges_road_free": int((share <= 0.0).sum()),
        "edges_road_free_pct": round(100.0 * float((share <= 0.0).mean()), 1),
        "edges_all_road": int((share >= 0.999).sum()),
        "above_threshold": {
            f">{t}": {
                "edges": int((share > t).sum()),
                "pct": round(100.0 * float((share > t).mean()), 1),
            } for t in thresholds
        },
    }


def by_sac_rank(records, share):
    """Cross-tab: if road mass concentrates on the easy edges, a difficulty-capped query is also
    the one most exposed to asphalt - which is the case where `ROAD_*` and the constrained rows
    interact rather than being independent axes."""
    out = {}
    for rank in np.unique(records["sac_rank"]):
        m = records["sac_rank"] == rank
        out[str(int(rank))] = {
            "edges": int(m.sum()),
            "aggregate_road_share": round(
                float(records["road_m"][m].sum() / max(records["distance_m"][m].sum(), 1.0)), 4),
            "median_edge_share": round(float(np.median(share[m])), 4),
        }
    return out


def load(name, thresholds):
    path = OSM_DIR / name / "records.npy"
    if not path.exists():
        print(f"skipping {name}: {path} not found", flush=True)
        return None
    print(f"reading {path} ...", flush=True)
    recs = binfmt.load_array(path, mmap=False)
    dist = recs["distance_m"].astype(np.float64)
    road = recs["road_m"].astype(np.float64)
    share = np.divide(road, dist, out=np.zeros_like(dist), where=dist > 0)
    share = np.clip(share, 0.0, 1.0)
    report = describe(share, dist, thresholds)
    report["by_sac_rank"] = by_sac_rank(recs, share)
    report["total_km"] = round(float(dist.sum() / 1000), 1)
    report["road_km"] = round(float(road.sum() / 1000), 1)
    if name == "start_edges":
        # approaches are short and valley-bottomed, so their road share is expected to be higher
        # and is the number the k-best approach selection (spec E1) has to live with
        for tname, tval in (("station", binfmt.TYPE_STATION), ("parking", binfmt.TYPE_PARKING)):
            m = recs["from_type"] == tval
            if m.any():
                report[f"{tname}_sourced"] = describe(share[m], dist[m], thresholds)
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--thresholds", default="0.1,0.2,0.5",
                    help="road-share cut points to report edge counts above")
    args = ap.parse_args()
    thresholds = [float(t) for t in args.thresholds.split(",") if t.strip()]

    result = {
        "caveat": "routed under the distance cost with roadPenaltyFactor active; the time-based "
                  "cost of spec A1 can only increase these shares. Floor, not prediction.",
        "road_penalty_factor_at_build_time": load_config()["graph"].get("roadPenaltyFactor"),
        "road_highway_tags": load_config()["graph"]["roadHighwayTags"],
    }
    for name in ("hut_edges", "start_edges"):
        report = load(name, thresholds)
        if report is not None:
            result[name] = report

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"\nwrote {OUT_PATH}", flush=True)

    for name in ("hut_edges", "start_edges"):
        if name in result:
            r = result[name]
            print(f"{name}: aggregate road share {r['aggregate_road_share']:.1%}, "
                  f"median edge {r['percentiles']['p50']:.1%}, "
                  f"{r['edges_road_free_pct']}% of edges road-free", flush=True)


if __name__ == "__main__":
    main()
