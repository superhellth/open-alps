"""Fetches the per-day availability calendar of every hut in scope, one file per hut and season."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date

import common


def calendar_url(ohrs_id: int) -> str:
    return f"{common.OHRS}/api/v1/reservation/availabilityCalendar/{ohrs_id}"


def calendar_body(start: date, end: date) -> dict:
    return {"arrivalDate": common.fmt_date(start), "departureDate": common.fmt_date(end),
            "nextPossibleReservations": False, "numberOfPeople": 1}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--season", type=int, choices=sorted(common.SEASONS))
    args = ap.parse_args(argv)
    ids = common.hut_scope(common.read_json(common.HUTS_GEOJSON)["features"])
    for season in ([args.season] if args.season else sorted(common.SEASONS)):
        s = common.SEASONS[season]
        counts: Counter = Counter()
        for i in ids:
            path = common.OUT / "raw" / f"calendar-{season}" / f"{i}.json"
            fetch = lambda i=i: common.request_json(
                calendar_url(i), calendar_body(s.start, s.fetch_end))
            counts[common.fetch_cached(path, fetch, args.refresh)] += 1
        print(f"calendar {season} for {len(ids)} huts: {dict(counts)}")


if __name__ == "__main__":
    main()
