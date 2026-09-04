#!/usr/bin/env python3
"""Measures how closely match_tour_edges.py's routed geometry (data/osm/tour_edges/) follows each
tour leg's own GPX trace (pipeline/tours/), beyond the length-ratio check match_leg already applies
(spec 2026-08-30-tour-folder-ingestion-design.md §3's lengthDivergenceRatio compares total length
only - two parallel valley trails of the same length would pass it while diverging badly in shape).
For each successfully-routed leg, samples every GPX trace point's nearest-point distance to the
routed polyline (lib/edge_split.py's nearest_point_on_polyline, reused rather than reimplemented)
and reports mean/max deviation in meters alongside the existing length ratio.

Read-only: never modifies phases/ or dodo.py (pipeline/analysis/README.md's rule). Requires
data/osm/tour_edges/ and data/osm/tours.json already built (pipeline/CLAUDE.md's "ask before
running any pipeline task" rule covers producing them, not reading them here).

Writes data/analysis/corridor_match_quality.json.

Usage: python pipeline/analysis/corridor_match_quality.py
"""

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import binfmt  # noqa: E402
from lib.edge_split import nearest_point_on_polyline  # noqa: E402
from lib.geo import haversine_m  # noqa: E402
from lib.hubs import HUB_TYPE_JSON_NAMES  # noqa: E402
from lib.pipeline import DATA_DIR, OSM_DIR, TOURS_DIR  # noqa: E402
from lib.tour_folder import load_all_tour_folders, load_tour_folder  # noqa: E402
from lib.timing import phase  # noqa: E402

SCRIPT_NAME = "corridor_match_quality.py"
OUT_PATH = DATA_DIR / "analysis" / "corridor_match_quality.json"


def _deviation_m(trace_points: list, routed_points: list) -> tuple:
    """(mean_m, max_m): every trace point's nearest-point distance to the routed polyline."""
    if len(routed_points) < 2:
        return 0.0, 0.0
    ref_lat = routed_points[len(routed_points) // 2][1]
    lng_scale = math.cos(math.radians(ref_lat))
    dists = []
    for p in trace_points:
        seg_i, t = nearest_point_on_polyline(routed_points, p, lng_scale=lng_scale)
        ax, ay = routed_points[seg_i]
        bx, by = routed_points[seg_i + 1]
        px, py = ax + t * (bx - ax), ay + t * (by - ay)
        dists.append(haversine_m(p[0], p[1], px, py))
    return sum(dists) / len(dists), max(dists)


def main():
    records = binfmt.load_array(OSM_DIR / "tour_edges" / "records.npy", mmap=False)
    geometry = binfmt.load_array(OSM_DIR / "tour_edges" / "geometry.npy", mmap=False)
    tour_meta = binfmt.load_array(OSM_DIR / "tour_edges" / "tour_meta.npy", mmap=False)
    tour_folders = load_all_tour_folders(TOURS_DIR)

    rows = []
    with phase(SCRIPT_NAME, "corridor_match_quality", n_records=len(records)):
        for i, rec in enumerate(records):
            tour_id, leg_index = int(tour_meta[i]["tour_id"]), int(tour_meta[i]["leg_index"])
            tour_name, folder = tour_folders[tour_id]
            legs = {n - 1: pts for n, pts in load_tour_folder(folder)}
            trace_points = legs[leg_index]

            off, cnt = int(rec["geom_offset"]), int(rec["geom_count"])
            routed_points = [(float(g["lon"]), float(g["lat"])) for g in geometry[off:off + cnt]]

            mean_m, max_m = _deviation_m(trace_points, routed_points)
            trace_length_m = sum(
                haversine_m(*trace_points[j], *trace_points[j + 1])
                for j in range(len(trace_points) - 1)
            )
            length_ratio = float(rec["distance_m"]) / trace_length_m if trace_length_m > 0 else None

            rows.append({
                "tourName": tour_name, "legIndex": leg_index,
                "lengthRatio": length_ratio, "meanDeviationM": mean_m, "maxDeviationM": max_m,
            })
            print(f"[{i + 1}/{len(records)}] {tour_name} leg {leg_index}: "
                  f"mean={mean_m:.1f}m max={max_m:.1f}m ratio={length_ratio}", flush=True)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=2)

    if rows:
        mean_of_means = sum(r["meanDeviationM"] for r in rows) / len(rows)
        worst_max = max(r["maxDeviationM"] for r in rows)
        print(f"\n{len(rows)} legs measured. mean-of-means deviation: {mean_of_means:.1f}m, "
              f"worst single-leg max deviation: {worst_max:.1f}m")
    print(f"written {OUT_PATH}")


if __name__ == "__main__":
    main()
