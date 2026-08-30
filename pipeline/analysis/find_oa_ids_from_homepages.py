#!/usr/bin/env python3
"""One-shot check: do any of the AV tours WITHOUT an alpenvereinaktiv.com id in their own
`homepage` field (see Task 2 of docs/superpowers/plans/2026-08-30-tour-reproducibility.md) embed
an Outdooractive widget anyway? Fetches each such tour's homepage HTML once and searches for
lib.oa_geometry.OA_URL_RE, plus a looser fallback pattern (`/tour/[^"'<>]+/(\d+)` under any host
containing "outdooractive" or "alpenvereinaktiv" or ending in the same TLD segment as the known
white-label touren.montafon.at, to catch other same-vendor deployments) so a same-vendor,
different-domain deployment doesn't get missed the way the strict OA_URL_RE deliberately excludes
touren.montafon.at.

NETWORK: fetches up to 12 third-party homepages, one GET each, read-only. Requires explicit user
confirmation before running - a new class of external host this session hasn't touched before.

Writes data/analysis/oa_id_homepage_scan.json. Never modifies tours.json or any phases/ script.
"""

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.oa_geometry import OA_UA, OA_URL_RE, oa_ids_by_tour  # noqa: E402
from lib.pipeline import DATA_DIR, OSM_DIR  # noqa: E402

OUT_PATH = DATA_DIR / "analysis" / "oa_id_homepage_scan.json"
FALLBACK_RE = re.compile(r'outdooractive[^"\'<>]*?/tour/[^"\'<>]+/(\d+)|'
                          r'/tour/[^"\'<>]+/(\d+)[^"\'<>]*?outdooractive', re.IGNORECASE)


def scan_homepage(url: str) -> tuple:
    """Returns (found_oa_id, matched_pattern) or (None, None)."""
    request = urllib.request.Request(url, headers={"user-agent": OA_UA})
    with urllib.request.urlopen(request, timeout=20) as response:
        html = response.read().decode("utf-8", errors="replace")
    strict = OA_URL_RE.search(html)
    if strict:
        return strict.group(1), "alpenvereinaktiv_embed"
    loose = FALLBACK_RE.search(html)
    if loose:
        return (loose.group(1) or loose.group(2)), "outdooractive_generic_embed"
    return None, None


if __name__ == "__main__":
    with open(OSM_DIR / "tours.json", encoding="utf-8") as fh:
        tours = json.load(fh)
    already_have = oa_ids_by_tour(tours)
    candidates = [t for t in tours if t["tourId"] not in already_have and t.get("homepage")]
    print(f"scanning {len(candidates)} homepages ...", flush=True)

    results = []
    for i, tour in enumerate(candidates):
        homepage = tour["homepage"]
        try:
            found_id, pattern = scan_homepage(homepage)
        except Exception as exc:  # noqa: BLE001 - a dead/blocked third-party site is expected data, not a bug
            found_id, pattern = None, f"error: {exc}"
        print(f"[{i + 1}/{len(candidates)}] {tour['shortCode']}: {found_id or 'none'}"
              f" ({pattern})", flush=True)
        results.append({"tourId": tour["tourId"], "shortCode": tour["shortCode"],
                         "homepage": homepage, "found_oa_id": found_id, "matched_pattern": pattern})
        time.sleep(1.0)  # one GET per distinct third-party host, no need to hammer any of them

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2)
    found = sum(1 for r in results if r["found_oa_id"])
    print(f"{found}/{len(results)} homepages carried a discoverable OA id -> {OUT_PATH}")
