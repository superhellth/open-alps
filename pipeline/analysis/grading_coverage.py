#!/usr/bin/env python3
"""Standalone analysis script - not part of the doit task graph, not imported by any phase
script. Measures how much of the trail network, and of the already-computed hut edges, would be
"ungraded" under the passability tier rules proposed in
docs/superpowers/specs/2026-08-22-tour-suggestion-backend.md (section C4).

Answers the T0 question the sizing probe cannot answer cheaply: the spec's 7.9%-ungraded figure
is network-wide and per-segment, but what decides whether the strict constrained rows
(`ungraded_m == 0`) destroy connectivity is whether ungraded terrain sits on the only link
between two huts. This script computes both - the network-wide tier mass *by length*, and the
per-hut-edge tier split attributed onto the real stored paths - then reports how many huts lose
their last connection when the fully-graded rule is added on top of a plain sac_rank cap. That
difference is the cheap preview of the probe's "ungraded blocker rate" (spec H.3), and a small
value retires the fourth-passability-row risk before any routing code is written.

NOTE ON THE ANALYSIS CONTRACT: this script does not have a production function to call, because
the grading classifier it measures does not exist yet - it is the rule being *proposed*. The
classifier below is therefore the specification's tier table written out, deliberately in one
place, and it is the thing under measurement rather than a copy of something under phases/. What
it does reuse from production is real: lib/grading.py's SAC_SCALE_RANK and build_base_graph.py's
haversine_m_vec, and the persisted binfmt arrays. If the rule is adopted, the classifier moves
into build_base_graph.py's way handler and this script should then import it from there.

APPROXIMATION - segment attribution is by coordinate identity. A stored hut-edge polyline is
built from base-graph edges whose points are original OSM node coordinates, so each consecutive
vertex pair is matched back to its OSM way segment by an exact (quantized) endpoint-pair key.
Segments that fail to match - chiefly the two synthetic halves either side of a mid-chain snap
split (lib/edge_split.py), which have a snap point as one endpoint - are counted and reported
separately as `unmatched_m` rather than silently folded into any tier. Read the match rate before
reading anything else; a low rate invalidates the per-edge numbers.

Requires data/osm/trails.osm.pbf (merge_trails.py) and data/osm/hut_edges/ (build_hub_edges.py);
--start-edges additionally requires data/osm/start_edges/.

Runtime: ~20-25 min, dominated by the single osmium pass over trails.osm.pbf (~16 min, the same
stream build_base_graph.py pays). Peak RSS ~3-4 GB (the segment lookup table is ~440 MB of
array.array plus a ~600 MB sorted numpy copy). --no-attribution skips the lookup table and the
hut-edge pass, leaving only the network-wide tier mass, at ~1 GB and ~17 min.

Usage: python pipeline/analysis/grading_coverage.py [--start-edges] [--no-attribution]
                                                    [--leg-budget-km 12]
"""

import argparse
import json
import sys
from array import array
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import osmium

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases" / "graph_building"))
import build_base_graph as bbg  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import binfmt, grading  # noqa: E402
from lib.pipeline import OSM_DIR, load_config  # noqa: E402

DATA_DIR = OSM_DIR.parent
OUT_PATH = DATA_DIR / "analysis" / "grading_coverage.json"

# --- The proposed tier table (spec C4). Ranks are SAC ranks, matching grading.SAC_SCALE_RANK. ---

TIER_EXPLICIT, TIER_IMPLIED, TIER_UNGRADED = 0, 1, 2
TIER_NAMES = {TIER_EXPLICIT: "explicit", TIER_IMPLIED: "inferred", TIER_UNGRADED: "ungraded"}

# "Physically implied" - the tag makes alpine terrain impossible by construction, not by a
# mapper's judgement. T1 == "hiking" == rank 1; T2 == "mountain_hiking" == rank 2.
IMPLIED_BY_HIGHWAY = {
    "residential": 1, "service": 1, "unclassified": 1, "tertiary": 1,  # car-drivable
    "track": 1,                                                        # tractor-drivable
    "footway": 1,
    "steps": 2,
}
PAVED_SURFACES = {"asphalt", "paving_stones", "concrete"}

# Downgrades are always honoured and hard-exclude a way from every constrained row, whatever
# else it carries. Asymmetric on purpose: a downgrade can only strengthen the guarantee.
BAD_VISIBILITY = {"bad", "horrible", "no"}
BLOCKING_ACCESS = {"private", "no"}


def classify_way(tags):
    """Returns (tier, rank, excluded, reason). `rank` is -1 for ungraded. `excluded` means the
    way may not appear in any constrained row regardless of its rank."""
    excluded_reasons = []
    if tags.get("trail_visibility", "") in BAD_VISIBILITY:
        excluded_reasons.append("trail_visibility")
    if tags.get("informal", "") == "yes":
        excluded_reasons.append("informal")
    if tags.get("ladder", "") == "yes":
        excluded_reasons.append("ladder")
    if tags.get("access", "") in BLOCKING_ACCESS or tags.get("foot", "") in BLOCKING_ACCESS:
        excluded_reasons.append("access")
    highway = tags.get("highway", "")
    if highway == "via_ferrata" or "via_ferrata_scale" in tags:
        excluded_reasons.append("via_ferrata")

    explicit = grading.SAC_SCALE_RANK.get(tags.get("sac_scale", ""), -1)
    if explicit >= 0:
        tier, rank = TIER_EXPLICIT, explicit
    elif highway in IMPLIED_BY_HIGHWAY:
        tier, rank = TIER_IMPLIED, IMPLIED_BY_HIGHWAY[highway]
    elif highway == "path" and tags.get("surface", "") in PAVED_SURFACES:
        tier, rank = TIER_IMPLIED, 1
    else:
        tier, rank = TIER_UNGRADED, -1
    return tier, rank, bool(excluded_reasons), excluded_reasons


# --- Coordinate-identity keys, for attributing a stored polyline back onto OSM segments ---

LON_OFFSET = np.uint64(1_800_000_000)
LAT_OFFSET = np.uint64(1_800_000_000)
LAT_SPAN = np.uint64(3_600_000_001)
PAIR_DTYPE = np.dtype([("a", "u8"), ("b", "u8")])


def point_codes(lon, lat):
    """One uint64 per point, from coordinates quantized to 1e-7 deg (OSM's own precision). Exact
    equality, no tolerance - a matched segment is the same two OSM nodes, or it is unmatched."""
    lonq = (np.rint(np.asarray(lon, dtype=np.float64) * 1e7).astype(np.int64)).astype(np.uint64)
    latq = (np.rint(np.asarray(lat, dtype=np.float64) * 1e7).astype(np.int64)).astype(np.uint64)
    return (lonq + LON_OFFSET) * LAT_SPAN + (latq + LAT_OFFSET)


def pair_keys(code_a, code_b):
    """Undirected segment key: the two endpoint codes, smaller first, as a structured record.
    Sorting/searchsorted on a two-field structured dtype is lexicographic and exact, so this is a
    real lookup rather than a hash with collisions to argue about."""
    a = np.asarray(code_a, dtype=np.uint64)
    b = np.asarray(code_b, dtype=np.uint64)
    lo, hi = np.minimum(a, b), np.maximum(a, b)
    keys = np.empty(len(a), dtype=PAIR_DTYPE)
    keys["a"], keys["b"] = lo, hi
    return keys


class GradingHandler(osmium.SimpleHandler):
    """Streams every way once. Network-wide tier mass is accumulated into O(1) counters; the
    per-segment lookup table (only built when attribution is on) is held in array.array, not
    Python lists, because 23M segments of boxed ints is the difference between 440 MB and
    several GB."""

    def __init__(self, collect_lookup=True, progress_every=200_000):
        super().__init__()
        self.collect_lookup = collect_lookup
        self.progress_every = progress_every
        self.n_ways = 0
        self.n_segments = 0
        # network-wide, by length
        self.len_by_tier = defaultdict(float)
        self.len_by_highway_tier = defaultdict(float)
        self.len_by_rank = defaultdict(float)
        self.len_excluded_by_reason = defaultdict(float)
        self.len_excluded_total = 0.0
        self.len_ungraded_by_highway = defaultdict(float)
        self.ways_by_tier = Counter()
        self.total_len = 0.0
        # lookup table
        self.key_a, self.key_b = array("Q"), array("Q")
        self.seg_tier, self.seg_rank, self.seg_excluded = array("b"), array("b"), array("b")

    def way(self, w):
        nodes = [n for n in w.nodes if n.location.valid()]
        if len(nodes) < 2:
            return
        lons = np.fromiter((n.location.lon for n in nodes), dtype=np.float64, count=len(nodes))
        lats = np.fromiter((n.location.lat for n in nodes), dtype=np.float64, count=len(nodes))
        dists = bbg.haversine_m_vec(lons[:-1], lats[:-1], lons[1:], lats[1:])
        total = float(dists.sum())
        n_edges = len(nodes) - 1

        tags = {t.k: t.v for t in w.tags}
        tier, rank, excluded, reasons = classify_way(tags)
        highway = tags.get("highway", "")

        self.n_ways += 1
        self.n_segments += n_edges
        self.total_len += total
        self.ways_by_tier[tier] += 1
        self.len_by_tier[tier] += total
        self.len_by_highway_tier[(highway, tier)] += total
        self.len_by_rank[rank] += total
        if excluded:
            self.len_excluded_total += total
            for r in reasons:
                self.len_excluded_by_reason[r] += total
        if tier == TIER_UNGRADED:
            self.len_ungraded_by_highway[highway] += total

        if self.collect_lookup:
            codes = point_codes(lons, lats)
            a, b = codes[:-1], codes[1:]
            lo, hi = np.minimum(a, b), np.maximum(a, b)
            self.key_a.extend(lo.tolist())
            self.key_b.extend(hi.tolist())
            self.seg_tier.extend([tier] * n_edges)
            self.seg_rank.extend([rank] * n_edges)
            self.seg_excluded.extend([int(excluded)] * n_edges)

        if self.progress_every and self.n_ways % self.progress_every == 0:
            print(f"  stream: {self.n_ways:,} ways, {self.n_segments:,} segments, "
                  f"{self.total_len / 1000:,.0f} km", flush=True)


def build_lookup(handler):
    """Sorts the streamed segment table into a searchsorted-able index. Duplicate keys (the same
    node pair mapped twice, e.g. overlapping ways) keep the *strictest* row - highest tier value,
    then excluded - so attribution never reports a pair as better-graded than some way carrying
    it claims."""
    print("building segment lookup ...", flush=True)
    keys = np.empty(len(handler.key_a), dtype=PAIR_DTYPE)
    keys["a"] = np.frombuffer(handler.key_a, dtype=np.uint64)
    keys["b"] = np.frombuffer(handler.key_b, dtype=np.uint64)
    tier = np.frombuffer(handler.seg_tier, dtype=np.int8).copy()
    rank = np.frombuffer(handler.seg_rank, dtype=np.int8).copy()
    excl = np.frombuffer(handler.seg_excluded, dtype=np.int8).copy()

    # strictest-first within a duplicate run: tier desc, excluded desc, rank desc
    order = np.lexsort((-rank.astype(np.int16), -excl.astype(np.int16),
                        -tier.astype(np.int16), keys["b"], keys["a"]))
    keys, tier, rank, excl = keys[order], tier[order], rank[order], excl[order]
    first = np.ones(len(keys), dtype=bool)
    if len(keys) > 1:
        first[1:] = (keys["a"][1:] != keys["a"][:-1]) | (keys["b"][1:] != keys["b"][:-1])
    dupes = int(len(keys) - first.sum())
    keys, tier, rank, excl = keys[first], tier[first], rank[first], excl[first]
    print(f"  {len(keys):,} unique segment keys ({dupes:,} duplicate node pairs collapsed)",
          flush=True)
    return keys, tier, rank, excl


def attribute_edges(records, geometry, lookup, label, chunk=200):
    """Per stored edge: metres by tier, metres excluded by a downgrade tag, metres unmatched, and
    the max rank over its matched graded segments."""
    keys, tier, rank, excl = lookup
    n = len(records)
    out = {
        "explicit_m": np.zeros(n), "inferred_m": np.zeros(n), "ungraded_m": np.zeros(n),
        "excluded_m": np.zeros(n), "unmatched_m": np.zeros(n), "matched_m": np.zeros(n),
        "total_m": np.zeros(n), "max_rank": np.full(n, -1, dtype=np.int8),
    }
    print(f"attributing {n:,} {label} records ...", flush=True)
    for i in range(n):
        off, cnt = int(records["geom_offset"][i]), int(records["geom_count"][i])
        if cnt < 2:
            continue
        pts = geometry[off:off + cnt]
        lon, lat = pts["lon"].astype(np.float64), pts["lat"].astype(np.float64)
        seg_len = bbg.haversine_m_vec(lon[:-1], lat[:-1], lon[1:], lat[1:])
        codes = point_codes(lon, lat)
        q = pair_keys(codes[:-1], codes[1:])

        pos = np.searchsorted(keys, q)
        pos_clipped = np.minimum(pos, len(keys) - 1)
        hit = (keys["a"][pos_clipped] == q["a"]) & (keys["b"][pos_clipped] == q["b"])

        out["total_m"][i] = seg_len.sum()
        out["unmatched_m"][i] = seg_len[~hit].sum()
        out["matched_m"][i] = seg_len[hit].sum()
        if not hit.any():
            continue
        hp, hl = pos_clipped[hit], seg_len[hit]
        ht, hr, he = tier[hp], rank[hp], excl[hp]
        out["explicit_m"][i] = hl[ht == TIER_EXPLICIT].sum()
        out["inferred_m"][i] = hl[ht == TIER_IMPLIED].sum()
        out["ungraded_m"][i] = hl[ht == TIER_UNGRADED].sum()
        out["excluded_m"][i] = hl[he == 1].sum()
        graded = hr[ht != TIER_UNGRADED]
        out["max_rank"][i] = int(graded.max()) if len(graded) else -1
        if (i + 1) % (chunk * 5) == 0 or i + 1 == n:
            print(f"  [{i + 1}/{n}] {label}", flush=True)
    return out


def connectivity_gate(records, attr, budget_km):
    """The money number. Compares, on the *existing* stored paths, how many huts keep at least
    one connection under a plain sac_rank cap versus under the same cap plus the strict
    fully-graded rule the constrained rows enforce. The delta is the extra deletion the
    ungraded rule causes - i.e. how much substitution a constrained row has to buy back, and
    therefore whether the fourth passability row (spec H fallback) is likely needed.

    Measured on stored paths only, so it is a lower bound on the strict rows' real connectivity:
    a constrained re-route may find a graded path where the unconstrained one was ungraded. That
    is exactly what makes a *small* delta conclusive and a large one merely suggestive."""
    in_budget = records["distance_m"] <= budget_km * 1000.0
    huts = np.unique(np.concatenate([records["from_id"], records["to_id"]]))
    ungraded_free = (attr["ungraded_m"] <= 0.0) & (attr["excluded_m"] <= 0.0)
    no_ferrata = ~records["via_ferrata"]

    def degree_report(mask):
        kept = records[mask]
        connected = np.unique(np.concatenate([kept["from_id"], kept["to_id"]])) if len(kept) else \
            np.zeros(0, dtype=records["from_id"].dtype)
        isolated = len(huts) - len(connected)
        return {
            "edges": int(mask.sum()),
            "huts_connected": int(len(connected)),
            "huts_isolated": int(isolated),
            "huts_isolated_pct": round(100.0 * isolated / max(len(huts), 1), 1),
            "mean_degree": round(2.0 * int(mask.sum()) / max(len(connected), 1), 2),
        }

    rows = {"budget_only": degree_report(in_budget)}
    for cap in (2, 3):
        cap_mask = in_budget & no_ferrata & (records["sac_rank"] <= cap)
        strict = cap_mask & ungraded_free & (attr["max_rank"] <= cap)
        rows[f"sac_rank_le_{cap}"] = degree_report(cap_mask)
        rows[f"sac_rank_le_{cap}_fully_graded"] = degree_report(strict)
        lost = int(cap_mask.sum()) - int(strict.sum())
        rows[f"sac_rank_le_{cap}_delta"] = {
            "edges_lost_to_ungraded_rule": lost,
            "edges_lost_pct": round(100.0 * lost / max(int(cap_mask.sum()), 1), 1),
            "extra_huts_isolated": rows[f"sac_rank_le_{cap}_fully_graded"]["huts_isolated"]
            - rows[f"sac_rank_le_{cap}"]["huts_isolated"],
        }
    return rows


def summarize_attr(attr, records):
    total = attr["total_m"].sum()
    matched = attr["matched_m"].sum()
    frac = attr["ungraded_m"] / np.maximum(attr["total_m"], 1.0)
    return {
        "n_edges": int(len(records)),
        "match_rate_by_length": round(float(matched / max(total, 1.0)), 4),
        "total_km": round(float(total / 1000), 1),
        "explicit_km": round(float(attr["explicit_m"].sum() / 1000), 1),
        "inferred_km": round(float(attr["inferred_m"].sum() / 1000), 1),
        "ungraded_km": round(float(attr["ungraded_m"].sum() / 1000), 1),
        "excluded_km": round(float(attr["excluded_m"].sum() / 1000), 1),
        "unmatched_km": round(float(attr["unmatched_m"].sum() / 1000), 1),
        "edges_fully_graded": int((attr["ungraded_m"] <= 0).sum()),
        "edges_fully_graded_pct": round(100.0 * float((attr["ungraded_m"] <= 0).mean()), 1),
        "ungraded_share_percentiles": {
            f"p{p}": round(float(np.percentile(frac, p)), 4) for p in (50, 75, 90, 95, 99)
        },
    }


def network_report(h):
    by_tier = {TIER_NAMES[t]: round(v / 1000, 1) for t, v in sorted(h.len_by_tier.items())}
    total_km = h.total_len / 1000
    return {
        "ways": h.n_ways,
        "segments": h.n_segments,
        "total_km": round(total_km, 1),
        "km_by_tier": by_tier,
        "pct_by_tier": {k: round(100.0 * v / max(total_km, 1e-9), 2) for k, v in by_tier.items()},
        "ways_by_tier": {TIER_NAMES[t]: c for t, c in sorted(h.ways_by_tier.items())},
        "km_by_rank": {str(r): round(v / 1000, 1) for r, v in sorted(h.len_by_rank.items())},
        "excluded_km_total": round(h.len_excluded_total / 1000, 1),
        "excluded_km_by_reason": {
            r: round(v / 1000, 1) for r, v in sorted(h.len_excluded_by_reason.items(),
                                                    key=lambda kv: -kv[1])
        },
        "ungraded_km_by_highway": {
            hw: round(v / 1000, 1) for hw, v in sorted(h.len_ungraded_by_highway.items(),
                                                       key=lambda kv: -kv[1])
        },
        "km_by_highway_tier": {
            f"{hw}/{TIER_NAMES[t]}": round(v / 1000, 1)
            for (hw, t), v in sorted(h.len_by_highway_tier.items(), key=lambda kv: -kv[1])
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-edges", action="store_true",
                    help="also attribute start_edges/ (109M geometry points, adds ~5 min)")
    ap.add_argument("--no-attribution", action="store_true",
                    help="network-wide tier mass only; skips the segment lookup table")
    ap.add_argument("--leg-budget-km", type=float, default=12.0,
                    help="edge-length budget for the connectivity gate, matching the spec's "
                         "12 km ~ 5 h leg proxy")
    args = ap.parse_args()

    trails = OSM_DIR / "trails.osm.pbf"
    if not trails.exists():
        raise SystemExit(f"missing {trails} - run merge_trails.py first")

    print(f"streaming {trails} (this is the ~16 min part) ...", flush=True)
    handler = GradingHandler(collect_lookup=not args.no_attribution)
    handler.apply_file(str(trails), locations=True)
    print(f"streamed {handler.n_ways:,} ways / {handler.n_segments:,} segments, "
          f"{handler.total_len / 1000:,.0f} km", flush=True)

    result = {
        "config": {
            "trail_tag_filter": load_config()["trailTagFilter"],
            "leg_budget_km": args.leg_budget_km,
            "implied_by_highway": IMPLIED_BY_HIGHWAY,
            "paved_surfaces": sorted(PAVED_SURFACES),
        },
        "network": network_report(handler),
    }

    if not args.no_attribution:
        lookup = build_lookup(handler)
        handler.key_a = handler.key_b = None  # free the array.array copies before the pass
        handler.seg_tier = handler.seg_rank = handler.seg_excluded = None

        hut_recs = binfmt.load_array(OSM_DIR / "hut_edges" / "records.npy", mmap=False)
        hut_geom = binfmt.load_array(OSM_DIR / "hut_edges" / "geometry.npy", mmap=True)
        hut_attr = attribute_edges(hut_recs, hut_geom, lookup, "hut_edges")
        result["hut_edges"] = summarize_attr(hut_attr, hut_recs)
        result["connectivity_gate"] = connectivity_gate(hut_recs, hut_attr, args.leg_budget_km)

        if args.start_edges:
            st_recs = binfmt.load_array(OSM_DIR / "start_edges" / "records.npy", mmap=False)
            st_geom = binfmt.load_array(OSM_DIR / "start_edges" / "geometry.npy", mmap=True)
            st_attr = attribute_edges(st_recs, st_geom, lookup, "start_edges")
            result["start_edges"] = summarize_attr(st_attr, st_recs)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"\nwrote {OUT_PATH}", flush=True)

    net = result["network"]
    print(f"\nnetwork by length: {net['pct_by_tier']}", flush=True)
    if "hut_edges" in result:
        he = result["hut_edges"]
        print(f"hut edges: match rate {he['match_rate_by_length']:.1%}, "
              f"{he['edges_fully_graded']}/{he['n_edges']} fully graded "
              f"({he['edges_fully_graded_pct']}%)", flush=True)
        for cap in (2, 3):
            d = result["connectivity_gate"][f"sac_rank_le_{cap}_delta"]
            print(f"  T{cap}: fully-graded rule drops {d['edges_lost_to_ungraded_rule']} more "
                  f"edges ({d['edges_lost_pct']}%), isolating "
                  f"{d['extra_huts_isolated']} more huts", flush=True)


if __name__ == "__main__":
    main()
