#!/usr/bin/env python3
"""Standalone analysis script - not part of the doit task graph, not imported by any phase
script. Measures the three client payload sizes that
docs/superpowers/specs/2026-08-22-tour-suggestion-backend.md leaves as estimates:

  1. the packed hut-edge column set (spec F) - the "~32 B/row, ~580 KB raw" figure, which the
     spec itself flags as assuming a packing that does not exist and a gzip figure it calls
     optimistic;
  2. the k-best-per-hut approach table (spec E1) - "< 100 KB", and, more usefully, how many huts
     actually get k approaches once the access rule deletes the private and gated trailheads;
  3. the loop-closure reverse index (spec E2) - "bounded by start_edges/, ~1.9 MB raw", open
     question 3.

It builds each artifact for real - narrowing ids to u2, laying the columns out contiguously,
gzipping with and without a byte-shuffle filter - rather than multiplying a row count by an
assumed row width. Nothing here writes into the pipeline's output tree; the packed arrays exist
only to be measured.

APPROXIMATIONS, both consequences of measuring before the Part 1 rebuild:

  - `ascent_m` is UNSET on 100% of the current records, so the k-best approach ranking uses
    distance as a proxy for time, exactly as the spec's own degree measurement does. Selection
    *sizes* are unaffected (k rows per hut either way); which k edges get picked is not final.
  - The four new columns (max_ele_m, ungraded_m, inferred_m, snap_m) do not exist yet. They are
    materialised as zeros so the packed width and row count are right. Zeros compress better than
    real data will, so every gzip figure below is a floor - stated per artifact in the output.

`motor_vehicle` is NOT measurable here: fetch_stations_parking.py's keep_fields lets through only
name/capacity/fee/access, and filter_start_points.py then drops even those. The access rule of
spec E1 is therefore evaluated on `access` alone, and the script reports how many start points
carry no access tag at all - the `access_unknown` bucket the spec says to keep and mark. Widening
keep_fields is a prerequisite for building E1, not for measuring it.

Requires data/osm/hut_edges/records.npy, data/osm/start_edges/records.npy (build_hub_edges.py),
data/osm/parking.geojson + stations.geojson (fetch_stations_parking.py).
Writes data/analysis/payload_sizing.json.

Runtime: seconds. Reads records.npy and the two GeoJSON layers; never touches geometry.npy.

Usage: python pipeline/analysis/payload_sizing.py [--k 3] [--variants 3]
"""

import argparse
import gzip
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import binfmt  # noqa: E402
from lib.pipeline import OSM_DIR  # noqa: E402

DATA_DIR = OSM_DIR.parent
OUT_PATH = DATA_DIR / "analysis" / "payload_sizing.json"

# Spec E1: hard-drop restricted access. `customers` and `permit` are reported separately rather
# than folded in - they are legally ambiguous for a trailhead park-and-hike and the decision is
# the spec's to make, not this script's.
HARD_DROP_ACCESS = {"private", "no", "employees", "agricultural", "forestry", "delivery"}
AMBIGUOUS_ACCESS = {"customers", "permit", "destination", "disabled"}

# Spec F, hut graph edges. Widths are the narrowed client-side ones, not RECORD_DTYPE's.
PAYLOAD_DTYPE = np.dtype([
    ("from_id", "u2"), ("to_id", "u2"), ("variant", "u1"),
    ("sac_rank", "i1"), ("via_ferrata", "u1"),
    ("distance_m", "f4"), ("ascent_m", "f4"), ("descent_m", "f4"),
    ("max_ele_m", "f4"), ("road_m", "f4"), ("ungraded_m", "f4"),
    ("inferred_m", "f4"), ("snap_m", "f4"),
])


def gzip_size(raw: bytes) -> int:
    return len(gzip.compress(raw, compresslevel=9))


def byte_shuffle(arr: np.ndarray) -> bytes:
    """Groups the Nth byte of every element together before compressing - the same idea as
    HDF5/Blosc's shuffle filter. f4 columns of similar magnitudes share exponent bytes, so this
    is what decides whether the spec's 'raw f4 compresses poorly' caveat bites or not."""
    raw = np.ascontiguousarray(arr).view(np.uint8)
    if arr.dtype.itemsize <= 1:
        return raw.tobytes()
    return raw.reshape(-1, arr.dtype.itemsize).T.copy().tobytes()


def size_report(label, arrays, note=None):
    """`arrays` is a list of (name, ndarray) laid out columnar - one contiguous buffer per column,
    which is how the client will actually consume them (typed-array views, no per-row parsing)."""
    raw_total = sum(a.nbytes for _, a in arrays)
    gz_plain = sum(gzip_size(np.ascontiguousarray(a).tobytes()) for _, a in arrays)
    gz_shuf = sum(gzip_size(byte_shuffle(a)) for _, a in arrays)
    report = {
        "rows": int(len(arrays[0][1])) if arrays else 0,
        "columns": len(arrays),
        "bytes_per_row": round(raw_total / max(len(arrays[0][1]), 1), 1) if arrays else 0,
        "raw_bytes": int(raw_total),
        "raw_kb": round(raw_total / 1024, 1),
        "gzip_kb": round(gz_plain / 1024, 1),
        "gzip_shuffled_kb": round(gz_shuf / 1024, 1),
        "per_column_raw_kb": {n: round(a.nbytes / 1024, 1) for n, a in arrays},
    }
    if note:
        report["note"] = note
    print(f"{label}: {report['rows']:,} rows, {report['bytes_per_row']} B/row, "
          f"{report['raw_kb']} KB raw -> {report['gzip_kb']} KB gz "
          f"({report['gzip_shuffled_kb']} KB shuffled)", flush=True)
    return report


def pack_hut_edges(recs, variants):
    """Spec F's column set at the client's widths, replicated `variants` times to price the
    phase-1 three-row grid against the single stored variant."""
    hut_ids = np.unique(np.concatenate([recs["from_id"], recs["to_id"]]))
    if hut_ids.max() > np.iinfo(np.uint16).max:
        raise SystemExit(f"hut id {hut_ids.max()} exceeds u2 - spec F's narrowing does not hold")
    packed = np.zeros(len(recs), dtype=PAYLOAD_DTYPE)
    packed["from_id"] = recs["from_id"].astype(np.uint16)
    packed["to_id"] = recs["to_id"].astype(np.uint16)
    packed["variant"] = recs["variant"]
    packed["sac_rank"] = recs["sac_rank"]
    packed["via_ferrata"] = recs["via_ferrata"].astype(np.uint8)
    for f in ("distance_m", "ascent_m", "descent_m", "road_m"):
        packed[f] = recs[f]
    # not yet computed: zeros, so width and row count are right and gzip is a floor
    for f in ("max_ele_m", "ungraded_m", "inferred_m", "snap_m"):
        packed[f] = 0.0

    tiled = np.tile(packed, variants) if variants > 1 else packed
    arrays = [(name, np.ascontiguousarray(tiled[name])) for name in PAYLOAD_DTYPE.names]
    note = (f"{variants} variant(s) x {len(recs)} stored edges; max_ele_m/ungraded_m/inferred_m/"
            "snap_m are zeros (not computed yet), and the variant copies are identical, so both "
            "gzip figures are floors - real variants differ and compress worse")
    return size_report(f"hut edge payload (x{variants})", arrays, note), int(len(hut_ids))


def load_access():
    """osm_id -> access tag, from the two shipped GeoJSON layers. fetch_stations_parking.py puts
    the OSM id on the Feature (e.g. 'n21261052'), not in properties - same convention
    filter_start_points.py relies on."""
    access = {}
    counts = Counter()
    for layer in ("parking.geojson", "stations.geojson"):
        path = OSM_DIR / layer
        if not path.exists():
            print(f"  missing {path}, skipping", flush=True)
            continue
        with open(path, encoding="utf-8") as f:
            fc = json.load(f)
        for feat in fc["features"]:
            raw_id = feat.get("id")
            if raw_id is None:
                continue
            tag = feat["properties"].get("access")
            access[int(raw_id[1:])] = tag
            counts[tag if tag is not None else "<unknown>"] += 1
    return access, counts


def select_k_best(recs, access, k):
    """Spec E1's selection rule, as far as the current data supports it: hard-drop restricted
    access, keep the k best by time (distance proxy - ascent is UNSET), and never fill all k from
    one source type where both are available."""
    dropped_access = 0
    dropped_ambiguous = 0
    by_hut = {}
    order = np.argsort(recs["distance_m"], kind="stable")
    for idx in order:
        osm_id = int(recs["from_id"][idx])
        tag = access.get(osm_id)
        if tag in HARD_DROP_ACCESS:
            dropped_access += 1
            continue
        if tag in AMBIGUOUS_ACCESS:
            dropped_ambiguous += 1
        hut = int(recs["to_id"][idx])
        src = int(recs["from_type"][idx])
        slot = by_hut.setdefault(hut, {"rows": [], "types": Counter()})
        if len(slot["rows"]) < k:
            slot["rows"].append((idx, src, tag))
            slot["types"][src] += 1
            continue
        # k already filled: swap the worst row of an over-represented source type out, so a hut
        # with both parking and station edges never ships k rows from one of them
        if slot["types"][src] == 0 and len(slot["types"]) == 1:
            for pos in range(len(slot["rows"]) - 1, -1, -1):
                other = slot["rows"][pos][1]
                if slot["types"][other] > 1:
                    slot["types"][other] -= 1
                    slot["rows"][pos] = (idx, src, tag)
                    slot["types"][src] += 1
                    break
    return by_hut, dropped_access, dropped_ambiguous


def pack_approach_table(recs, by_hut, access):
    rows = [(hut, idx, src, tag) for hut, slot in by_hut.items()
            for idx, src, tag in slot["rows"]]
    rows.sort()
    idxs = np.array([r[1] for r in rows], dtype=np.int64)
    access_codes = np.array(
        [0 if r[3] is None else (1 if r[3] in AMBIGUOUS_ACCESS else 2) for r in rows],
        dtype=np.uint8)
    arrays = [
        ("hut_id", np.array([r[0] for r in rows], dtype=np.uint16)),
        ("start_id", recs["from_id"][idxs].astype(np.uint32)),
        ("source_type", np.array([r[2] for r in rows], dtype=np.uint8)),
        ("access_code", access_codes),
        ("distance_m", recs["distance_m"][idxs].astype(np.float32)),
        ("ascent_m", recs["ascent_m"][idxs].astype(np.float32)),
        ("descent_m", recs["descent_m"][idxs].astype(np.float32)),
        ("road_m", recs["road_m"][idxs].astype(np.float32)),
        ("sac_rank", recs["sac_rank"][idxs].astype(np.int8)),
    ]
    note = ("start_id kept at u4 because it is a raw OSM id (max "
            f"{int(recs['from_id'].max())}) - narrowing it needs a dense remap the spec does not "
            "define; access_code 0=unknown 1=ambiguous 2=open")
    return size_report(f"approach table (k-best)", arrays, note), rows


def pack_reverse_index(recs, start_ids):
    """Spec E2: every start_edges record whose start_id is in S, keyed both ways. Both keyings
    are the same rows under two CSR offset arrays, so the payload is the rows plus two small
    offset tables - measured, not assumed."""
    mask = np.isin(recs["from_id"], np.array(sorted(start_ids), dtype=recs["from_id"].dtype))
    kept = recs[mask]
    uniq_starts = np.unique(kept["from_id"])
    start_remap = {int(s): i for i, s in enumerate(uniq_starts)}
    arrays = [
        ("start_idx", np.array([start_remap[int(s)] for s in kept["from_id"]], dtype=np.uint16)
         if len(uniq_starts) <= np.iinfo(np.uint16).max
         else np.array([start_remap[int(s)] for s in kept["from_id"]], dtype=np.uint32)),
        ("hut_id", kept["to_id"].astype(np.uint16)),
        ("source_type", kept["from_type"].astype(np.uint8)),
        ("distance_m", kept["distance_m"].astype(np.float32)),
        ("ascent_m", kept["ascent_m"].astype(np.float32)),
        ("descent_m", kept["descent_m"].astype(np.float32)),
        ("road_m", kept["road_m"].astype(np.float32)),
        ("sac_rank", kept["sac_rank"].astype(np.int8)),
        # the two CSR keyings (hut -> starts, start -> huts)
        ("csr_by_hut_offset", np.zeros(int(kept["to_id"].max()) + 2, dtype=np.uint32)),
        ("csr_by_start_offset", np.zeros(len(uniq_starts) + 1, dtype=np.uint32)),
        ("start_osm_id", uniq_starts.astype(np.uint64)),
    ]
    note = (f"S = {len(start_ids):,} start points; {int(mask.sum()):,} of "
            f"{len(recs):,} start_edges records retained. Bounded above by the full table, as "
            "the spec says - this is where in that bound it actually lands")
    return size_report("loop-closure reverse index", arrays, note), int(mask.sum()), len(uniq_starts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=3, help="approaches retained per hut (spec E1)")
    ap.add_argument("--variants", type=int, default=3,
                    help="variant rows to price the hut-edge payload for (phase 1 is 3)")
    args = ap.parse_args()

    hut_recs = binfmt.load_array(OSM_DIR / "hut_edges" / "records.npy", mmap=False)
    st_recs = binfmt.load_array(OSM_DIR / "start_edges" / "records.npy", mmap=False)
    print(f"loaded {len(hut_recs):,} hut edges, {len(st_recs):,} start edges\n", flush=True)

    result = {"params": {"k": args.k, "variants": args.variants}}

    result["hut_edge_payload_1_variant"], n_huts = pack_hut_edges(hut_recs, 1)
    result[f"hut_edge_payload_{args.variants}_variants"], _ = pack_hut_edges(
        hut_recs, args.variants)
    result["hut_ids_in_graph"] = n_huts

    print("\nloading access tags ...", flush=True)
    access, access_counts = load_access()
    result["access_tag_distribution"] = dict(access_counts.most_common())
    result["access_note"] = (
        "motor_vehicle is not measurable: fetch_stations_parking.py keep_fields is "
        "[name, capacity, fee, access], and filter_start_points.py drops even those. Widening "
        "both is a prerequisite for building spec E1.")

    by_hut, dropped_access, dropped_ambiguous = select_k_best(st_recs, access, args.k)
    approach_report, rows = pack_approach_table(st_recs, by_hut, access)
    filled = Counter(len(slot["rows"]) for slot in by_hut.values())
    mix = Counter(tuple(sorted(slot["types"])) for slot in by_hut.values())
    approach_report.update({
        "huts_with_any_approach": len(by_hut),
        "huts_by_approach_count": {str(c): n for c, n in sorted(filled.items())},
        "huts_short_of_k": int(sum(n for c, n in filled.items() if c < args.k)),
        "source_type_mix": {"+".join(str(t) for t in k): v for k, v in mix.most_common()},
        "edges_dropped_hard_access": dropped_access,
        "edges_kept_but_ambiguous_access": dropped_ambiguous,
    })
    result["approach_table"] = approach_report

    start_ids = {int(st_recs["from_id"][idx]) for _, idx, _, _ in rows}
    result["S_size"] = len(start_ids)
    rev_report, kept_rows, n_starts = pack_reverse_index(st_recs, start_ids)
    rev_report.update({"records_retained": kept_rows, "unique_start_points": n_starts,
                       "share_of_start_edges": round(kept_rows / max(len(st_recs), 1), 3)})
    result["reverse_index"] = rev_report

    total_gz = (result[f"hut_edge_payload_{args.variants}_variants"]["gzip_shuffled_kb"]
                + approach_report["gzip_shuffled_kb"] + rev_report["gzip_shuffled_kb"])
    result["total_gzip_shuffled_kb"] = round(total_gz, 1)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"\nwrote {OUT_PATH}", flush=True)
    print(f"total client payload (shuffled gzip, floor): {total_gz:.1f} KB", flush=True)
    print(f"huts with fewer than k={args.k} approaches: "
          f"{approach_report['huts_short_of_k']} of {len(by_hut)}", flush=True)


if __name__ == "__main__":
    main()
