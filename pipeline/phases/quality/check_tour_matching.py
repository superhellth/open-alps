#!/usr/bin/env python3
"""Read-only checks over phases/graph_building/match_tour_edges.py's output (spec
docs/superpowers/specs/2026-09-14-gpx-hut-snap-design.md "Quality checks"): every leg endpoint
resolves to a hub of the type its position in the tour requires, every matched leg's scalar fields
are finite and non-negative, every tour-match-gaps.json entry is reported with its reason,
tour_edges' profiles are well-formed, and tours.json's edgeIds agree with tour_edges/records.npy.
Never mutates its inputs; always exits 0.

Usage: python pipeline/phases/quality/check_tour_matching.py
"""

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import binfmt  # noqa: E402
from lib.pipeline import QUALITY_DIR, TOUR_EDGES_DIR, load_config  # noqa: E402
from lib.quality_report import build_check, write_report  # noqa: E402
from lib.timing import phase  # noqa: E402
from quality.check_elevation import check_profile_integrity  # noqa: E402

SCRIPT_NAME = "check_tour_matching.py"


def check_endpoint_types(tours: list, max_flagged: int) -> dict:
    """Every leg's "from" must be a hut unless legIndex == 0 (the tour's very first leg may start
    at any hub type); every leg's "to" must be a hut unless legIndex == numDays - 1 (the tour's
    very last leg may end at any hub type) - checked against legIndex rather than the leg's
    position in tours.json's legs list. A gap leg's unresolved endpoint (None) is not flagged - it
    is reported by check_gap_reasons."""
    flagged = []
    checked = 0
    for tour in tours:
        num_days = tour["numDays"]
        for leg in tour["legs"]:
            checked += 1
            leg_index = leg["legIndex"]
            for endpoint, required in (("from", leg_index != 0), ("to", leg_index != num_days - 1)):
                hub = leg[endpoint]
                if required and hub is not None and hub["type"] != "hut":
                    flagged.append({
                        "tourId": tour["tourId"], "tourName": tour["name"], "legIndex": leg_index,
                        "endpoint": endpoint, "hubType": hub["type"], "reason": "wrong_endpoint_type",
                    })
    return build_check(
        "tour_endpoint_types", {}, checked=checked, flagged_rows=flagged, baseline=0,
        max_flagged_rows=max_flagged,
    )


def check_leg_scalars(tours: list, max_flagged: int) -> dict:
    """distanceM/ascentM/descentM/durationS/maxEleM of every matched leg (edgeId != null) must be
    finite; all but maxEleM must also be non-negative. Gap legs carry no scalars and are skipped."""
    flagged = []
    checked = 0
    fields = ("distanceM", "ascentM", "descentM", "durationS", "maxEleM")
    for tour in tours:
        for leg in tour["legs"]:
            if leg.get("edgeId") is None:
                continue
            checked += 1
            for field in fields:
                value = leg[field]
                if not math.isfinite(value) or (value < 0 and field != "maxEleM"):
                    flagged.append({
                        "tourId": tour["tourId"], "tourName": tour["name"],
                        "legIndex": leg["legIndex"], "field": field, "value": value,
                        "reason": "non_finite_or_negative",
                    })
    return build_check(
        "tour_leg_scalars", {}, checked=checked, flagged_rows=flagged, baseline=0,
        max_flagged_rows=max_flagged,
    )


def check_gap_reasons(gaps: list, max_flagged: int) -> dict:
    """Every entry in tour-match-gaps.json is a leg endpoint that did not resolve, so every one is
    flagged (with its reason and detail) to keep unmatched legs visible."""
    flagged = [
        {"tourId": g["tourId"], "tourName": g["tourName"], "legIndex": g["legIndex"],
         "reason": g["reason"], "detail": g.get("detail")}
        for g in gaps
    ]
    return build_check(
        "tour_gap_reasons", {}, checked=len(gaps), flagged_rows=flagged, baseline=0,
        max_flagged_rows=max_flagged,
    )


def check_tours_json_agreement(tours: list, n_records: int, max_flagged: int) -> dict:
    """Every non-null edgeId indexes a row of tour_edges/records.npy, and the number of matched
    legs equals that row count."""
    flagged = []
    matched = 0
    for tour in tours:
        for leg in tour["legs"]:
            edge_id = leg.get("edgeId")
            if edge_id is None:
                continue
            matched += 1
            if not 0 <= edge_id < n_records:
                flagged.append({"tourId": tour["tourId"], "tourName": tour["name"],
                                "legIndex": leg["legIndex"], "edgeId": edge_id,
                                "reason": "edge_id_out_of_range"})
    if matched != n_records:
        flagged.append({"reason": "matched_leg_count_mismatch", "matched_legs": matched,
                        "records_rows": n_records})
    return build_check("tours_json_agreement", {}, checked=matched, flagged_rows=flagged,
                       baseline=0, max_flagged_rows=max_flagged)


def main(argv=None):
    config = load_config()
    max_flagged_default = config.get("quality", {}).get("maxFlaggedRows", 500)

    parser = argparse.ArgumentParser()
    parser.add_argument("--tour-edges-dir", default=str(TOUR_EDGES_DIR))
    parser.add_argument("--out", default=str(QUALITY_DIR / "tour_matching.json"))
    parser.add_argument("--max-flagged-rows", type=int, default=max_flagged_default)
    args = parser.parse_args(argv)

    tour_dir = Path(args.tour_edges_dir)

    with phase(SCRIPT_NAME, "check_tour_matching"):
        with open(tour_dir / "tours.json", encoding="utf-8") as f:
            tours = json.load(f)
        with open(tour_dir / "tour-match-gaps.json", encoding="utf-8") as f:
            gaps = json.load(f)

        checks = []
        c = check_endpoint_types(tours, args.max_flagged_rows)
        print(f"tour_endpoint_types: {c['summary']['flagged']:,} / {c['summary']['checked']:,} flagged", flush=True)
        checks.append(c)

        c = check_leg_scalars(tours, args.max_flagged_rows)
        print(f"tour_leg_scalars: {c['summary']['flagged']:,} / {c['summary']['checked']:,} flagged", flush=True)
        checks.append(c)

        c = check_gap_reasons(gaps, args.max_flagged_rows)
        print(f"tour_gap_reasons: {c['summary']['flagged']:,} / {c['summary']['checked']:,} flagged", flush=True)
        checks.append(c)

        records_path = tour_dir / "records.npy"
        profiles_path = tour_dir / "profiles.npy"
        if records_path.exists() and profiles_path.exists():
            records = binfmt.load_array(records_path, mmap=False)
            profiles = binfmt.load_array(profiles_path, mmap=False)
            c = check_profile_integrity(records, profiles, config["dem"]["profilePoints"],
                                        "tour_edges", args.max_flagged_rows)
            print(f"profile_integrity[tour_edges]: {c['summary']['flagged']:,} / "
                  f"{c['summary']['checked']:,} flagged", flush=True)
            checks.append(c)

            c = check_tours_json_agreement(tours, len(records), args.max_flagged_rows)
            print(f"tours_json_agreement: {c['summary']['flagged']:,} / {c['summary']['checked']:,} flagged",
                  flush=True)
            checks.append(c)

        write_report(Path(args.out), "tour_matching", checks)
        print(f"written {args.out}", flush=True)


if __name__ == "__main__":
    main()
