#!/usr/bin/env python3
"""Downloads an alpenvereinaktiv.com multi-day tour as one GPX per leg into
pipeline/tours/<name>/<N>.gpx, ready for lib/tour_folder.py to ingest.

Usage: python pipeline/tools/fetch_alpenvereinaktiv_tour.py <tour-url> --name "Lechquellenrunde" [--force]
"""

import argparse
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.alpenvereinaktiv import (  # noqa: E402
    extract_tour_id, gpx_download_url, parse_stage_ids,
)
from lib.pipeline import TOURS_DIR  # noqa: E402

_USER_AGENT = "Mozilla/5.0"


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req) as resp:
        return resp.read().decode("utf-8")


def resolve_legs(tour_url: str) -> list:
    """[(leg_number, tour_id), ...]. Falls back to the tour's own id as leg 1 when the page has
    no stage <select> (single-leg tour)."""
    html = _fetch(tour_url)
    legs = parse_stage_ids(html)
    return legs if legs else [(1, extract_tour_id(tour_url))]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tour_url")
    parser.add_argument("--name", required=True, help="tour folder name under pipeline/tours/")
    parser.add_argument("--force", action="store_true", help="overwrite an existing tour folder")
    args = parser.parse_args()

    out_dir = TOURS_DIR / args.name
    if out_dir.exists() and not args.force:
        raise SystemExit(f"{out_dir} already exists - pass --force to overwrite")
    out_dir.mkdir(parents=True, exist_ok=True)

    legs = resolve_legs(args.tour_url)
    print(f"found {len(legs)} leg(s)")
    for leg_number, tour_id in legs:
        out_path = out_dir / f"{leg_number}.gpx"
        url = gpx_download_url(tour_id)
        print(f"downloading leg {leg_number} ({tour_id}) -> {out_path}")
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req) as resp, open(out_path, "wb") as f:
            f.write(resp.read())


if __name__ == "__main__":
    main()
