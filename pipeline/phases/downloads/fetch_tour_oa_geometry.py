#!/usr/bin/env python3
"""Fetches Outdooractive's published LineString for every AV tour that has a resolved oaId
(fetch_tours.py) - the geometry match_tour_edges.py (Task 4 of docs/superpowers/plans/
2026-08-30-tour-reproducibility.md) uses as its per-tour corridor input when the AV's own
fragmented `paths` fail to reassemble (spec 2026-08-29-official-tours-integration-design.md §2.7's
spike result). Never a fallback for tours already reassembling cleanly - see match_tour_edges.py's
docstring for the precedence.

Usage: python pipeline/phases/downloads/fetch_tour_oa_geometry.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib.oa_geometry import fetch_oa_contents, oa_chain  # noqa: E402
from lib.pipeline import OSM_DIR  # noqa: E402
from lib.timing import phase  # noqa: E402

SCRIPT_NAME = "fetch_tour_oa_geometry.py"

if __name__ == "__main__":
    with open(OSM_DIR / "tours.json", encoding="utf-8") as fh:
        tours = json.load(fh)
    oa_ids = {t["tourId"]: t["oaId"] for t in tours if t.get("oaId")}
    print(f"{len(oa_ids)}/{len(tours)} tours have a resolved oaId", flush=True)

    with phase(SCRIPT_NAME, "fetch_tour_oa_geometry", n_tours=len(oa_ids)):
        contents = fetch_oa_contents(
            list(oa_ids.values()), OSM_DIR / "oa_tours_cache.json", allow_fetch=True,
        )

    id_to_tour = {v: k for k, v in oa_ids.items()}
    traces = []
    for oa_id, content in contents.items():
        tour_id = id_to_tour.get(oa_id)
        if tour_id is None:
            continue
        traces.append({"tourId": tour_id, "points": oa_chain(content)})

    out_path = OSM_DIR / "tour_oa_traces.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(traces, fh)
    print(f"written {out_path} ({len(traces)} tours with geometry)")
