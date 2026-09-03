#!/usr/bin/env python3
"""Read-only checks over phases/preprocessing/ output (spec docs/superpowers/specs/
2026-09-02-data-quality-monitoring-design.md §4.1): start_points.npy integrity and its coverage
in start_points_id_table.json. Never mutates its inputs; always exits 0 (spec §3).

Usage: python pipeline/phases/quality/check_preprocessing.py
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib import binfmt  # noqa: E402
from lib.pipeline import OSM_DIR, QUALITY_DIR, load_config  # noqa: E402
from lib.quality_report import build_check, write_report  # noqa: E402
from lib.timing import phase  # noqa: E402

SCRIPT_NAME = "check_preprocessing.py"

_TYPE_NAMES = {
    binfmt.TYPE_STATION: "station", binfmt.TYPE_PARKING: "parking",
    binfmt.TYPE_PARTNER: "partner_betrieb",
}


def check_start_point_integrity(start_points: np.ndarray, bbox: dict, max_flagged: int) -> dict:
    """§4.1.1: coordinates finite, inside bbox, and no (type, osm_id) duplicate rows."""
    lon, lat = start_points["lon"], start_points["lat"]
    finite = np.isfinite(lon) & np.isfinite(lat)
    in_bbox = (
        (lon >= bbox["minLng"]) & (lon <= bbox["maxLng"])
        & (lat >= bbox["minLat"]) & (lat <= bbox["maxLat"])
    )

    flagged = []
    for i in np.nonzero(~finite)[0]:
        flagged.append({
            "row": int(i), "type": _TYPE_NAMES.get(int(start_points[i]["type"]), "?"),
            "osm_id": int(start_points[i]["osm_id"]), "reason": "non_finite",
        })
    for i in np.nonzero(finite & ~in_bbox)[0]:
        flagged.append({
            "row": int(i), "type": _TYPE_NAMES.get(int(start_points[i]["type"]), "?"),
            "osm_id": int(start_points[i]["osm_id"]), "lon": float(lon[i]), "lat": float(lat[i]),
            "reason": "outside_bbox",
        })

    seen = {}
    for i in range(len(start_points)):
        key = (int(start_points[i]["type"]), int(start_points[i]["osm_id"]))
        if key in seen:
            flagged.append({
                "row": int(i), "type": _TYPE_NAMES.get(key[0], "?"), "osm_id": key[1],
                "first_row": seen[key], "reason": "duplicate",
            })
        else:
            seen[key] = i

    return build_check(
        "start_point_integrity", {}, checked=len(start_points), flagged_rows=flagged,
        baseline=0, max_flagged_rows=max_flagged,
    )


def check_id_table_coverage(start_points: np.ndarray, id_table: dict, max_flagged: int) -> dict:
    """§4.1.2: every start_points.npy row's osm_id must resolve in its layer of the id table."""
    flagged = []
    for i in range(len(start_points)):
        type_name = _TYPE_NAMES.get(int(start_points[i]["type"]))
        if type_name is None:
            continue
        osm_id = int(start_points[i]["osm_id"])
        if str(osm_id) not in id_table.get(type_name, {}):
            flagged.append({"row": i, "type": type_name, "osm_id": osm_id})

    return build_check(
        "id_table_coverage", {}, checked=len(start_points), flagged_rows=flagged,
        baseline=0, max_flagged_rows=max_flagged,
    )


def main(argv=None):
    config = load_config()
    max_flagged_default = config.get("quality", {}).get("maxFlaggedRows", 500)

    parser = argparse.ArgumentParser()
    parser.add_argument("--start-points", default=str(OSM_DIR / "start_points.npy"))
    parser.add_argument("--id-table", default=str(OSM_DIR / "start_points_id_table.json"))
    parser.add_argument("--out", default=str(QUALITY_DIR / "preprocessing.json"))
    parser.add_argument("--max-flagged-rows", type=int, default=max_flagged_default)
    args = parser.parse_args(argv)

    with phase(SCRIPT_NAME, "check_preprocessing"):
        start_points = binfmt.load_array(Path(args.start_points), mmap=False)
        with open(args.id_table, encoding="utf-8") as f:
            id_table = json.load(f)

        checks = []
        c = check_start_point_integrity(start_points, config["bbox"], args.max_flagged_rows)
        print(f"start_point_integrity: {c['summary']['flagged']:,} / {c['summary']['checked']:,} flagged",
              flush=True)
        checks.append(c)

        c = check_id_table_coverage(start_points, id_table, args.max_flagged_rows)
        print(f"id_table_coverage: {c['summary']['flagged']:,} / {c['summary']['checked']:,} flagged",
              flush=True)
        checks.append(c)

        write_report(Path(args.out), "preprocessing", checks)
        print(f"written {args.out}", flush=True)


if __name__ == "__main__":
    main()
