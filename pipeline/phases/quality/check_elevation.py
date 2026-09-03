#!/usr/bin/env python3
"""Read-only checks over phases/elevation/ output (spec docs/superpowers/specs/
2026-09-02-data-quality-monitoring-design.md §4.2): DEM sample plausibility, unresolved
compute_edge_profiles sentinels, implied-speed outliers, and per-edge-set profile-array
integrity. Never mutates its inputs; always exits 0 (spec §3).

Usage: python pipeline/phases/quality/check_elevation.py
"""

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib import binfmt  # noqa: E402
from lib.pipeline import OSM_DIR, QUALITY_DIR, load_config  # noqa: E402
from lib.quality_report import build_check, write_report  # noqa: E402
from lib.timing import phase  # noqa: E402

SCRIPT_NAME = "check_elevation.py"

EDGE_LAYERS = ["hut_edges", "start_edges", "tour_edges"]


def check_elevation_range(node_ele: np.ndarray, interior_ele: np.ndarray, plausible_range: tuple,
                           max_flagged: int) -> dict:
    """§4.2.1: no NaN, no out-of-range sample in either node_ele.npy or interior_ele.npy."""
    lo, hi = plausible_range
    flagged = []
    for layer_name, arr in (("node", node_ele), ("interior", interior_ele)):
        bad = ~np.isfinite(arr) | (arr < lo) | (arr > hi)
        for i in np.nonzero(bad)[0]:
            flagged.append({
                "layer": layer_name, "index": int(i),
                "elevation_m": float(arr[i]) if np.isfinite(arr[i]) else None,
            })
    return build_check(
        "elevation_range", {"plausible_range_m": list(plausible_range)},
        checked=len(node_ele) + len(interior_ele), flagged_rows=flagged, baseline=0,
        max_flagged_rows=max_flagged,
    )


def check_unresolved_sentinels(edges: np.ndarray, max_flagged: int) -> dict:
    """§4.2.2: base_graph/edges.npy rows still holding binfmt.UNSET after compute_edge_profiles."""
    bad = (
        (edges["time_s"] == binfmt.UNSET) | (edges["ascent_m"] == binfmt.UNSET)
        | (edges["descent_m"] == binfmt.UNSET)
    )
    flagged = [
        {"edge_id": int(edges[i]["edge_id"]), "u": int(edges[i]["u"]), "v": int(edges[i]["v"])}
        for i in np.nonzero(bad)[0]
    ]
    return build_check(
        "unresolved_sentinels", {}, checked=len(edges), flagged_rows=flagged, baseline=0,
        max_flagged_rows=max_flagged,
    )


def check_implied_speed(edges: np.ndarray, min_speed_ms: float, max_flagged: int) -> dict:
    """§4.2.3: dist / time_s per base-graph edge, flagged below min_speed_ms. Zero-time_s edges
    are excluded from the flagging test (division by zero, not a speed outlier - a zero-length
    degenerate edge is a different defect class, not this check's job) but still counted in
    `checked`, since every edge was inspected."""
    has_time = edges["time_s"] > 0
    speed = np.divide(edges["dist"], edges["time_s"], out=np.full(len(edges), np.inf),
                       where=has_time)
    bad = has_time & (speed < min_speed_ms)
    flagged = [
        {
            "edge_id": int(edges[i]["edge_id"]), "u": int(edges[i]["u"]), "v": int(edges[i]["v"]),
            "dist_m": float(edges[i]["dist"]), "time_s": float(edges[i]["time_s"]),
            "implied_speed_ms": float(speed[i]),
        }
        for i in np.nonzero(bad)[0]
    ]
    return build_check(
        "implied_speed", {"min_speed_ms": min_speed_ms}, checked=len(edges),
        flagged_rows=flagged, baseline=1011, max_flagged_rows=max_flagged,
        sort_key=lambda r: -r["implied_speed_ms"],
    )


def check_profile_integrity(records: np.ndarray, profiles: np.ndarray, profile_points: int,
                             layer_name: str, max_flagged: int) -> dict:
    """§4.2.4: profile_count==0 while geom_count>0; profile_offset+profile_count past the end of
    profiles.npy; profile_count != config["dem"]["profilePoints"]."""
    flagged = []
    n_profiles = len(profiles)
    for i in range(len(records)):
        r = records[i]
        offset, count, geom_count = int(r["profile_offset"]), int(r["profile_count"]), int(r["geom_count"])
        reasons = []
        if count == 0 and geom_count > 0:
            reasons.append("zero_profile_nonzero_geometry")
        if offset + count > n_profiles:
            reasons.append("offset_past_end")
        if count != profile_points and count != 0:
            reasons.append("wrong_point_count")
        for reason in reasons:
            flagged.append({"layer": layer_name, "row": i, "profile_offset": offset,
                             "profile_count": count, "geom_count": geom_count, "reason": reason})
    return build_check(
        f"profile_integrity_{layer_name}", {"profile_points": profile_points},
        checked=len(records), flagged_rows=flagged, baseline=0, max_flagged_rows=max_flagged,
    )


def main(argv=None):
    config = load_config()
    q = config.get("quality", {})
    max_flagged_default = q.get("maxFlaggedRows", 500)
    elevation_cfg = q.get("elevation", {})

    parser = argparse.ArgumentParser()
    parser.add_argument("--base-graph-dir", default=str(OSM_DIR / "base_graph"))
    parser.add_argument("--edges-root", default=str(OSM_DIR))
    parser.add_argument("--out", default=str(QUALITY_DIR / "elevation.json"))
    parser.add_argument("--max-flagged-rows", type=int, default=max_flagged_default)
    parser.add_argument("--plausible-range-min-m", type=float,
                         default=elevation_cfg.get("plausibleRangeM", [-50, 4300])[0])
    parser.add_argument("--plausible-range-max-m", type=float,
                         default=elevation_cfg.get("plausibleRangeM", [-50, 4300])[1])
    parser.add_argument("--min-speed-ms", type=float, default=elevation_cfg.get("minSpeedMs", 0.05))
    args = parser.parse_args(argv)

    base_graph_dir = Path(args.base_graph_dir)
    edges_root = Path(args.edges_root)
    profile_points = config["dem"]["profilePoints"]

    with phase(SCRIPT_NAME, "check_elevation"):
        checks = []

        node_ele = binfmt.load_array(base_graph_dir / "node_ele.npy", mmap=False)
        interior_ele = binfmt.load_array(base_graph_dir / "interior_ele.npy", mmap=False)
        c = check_elevation_range(node_ele, interior_ele,
                                   (args.plausible_range_min_m, args.plausible_range_max_m),
                                   args.max_flagged_rows)
        print(f"elevation_range: {c['summary']['flagged']:,} / {c['summary']['checked']:,} flagged", flush=True)
        checks.append(c)

        edges = binfmt.load_array(base_graph_dir / "edges.npy", mmap=False)
        c = check_unresolved_sentinels(edges, args.max_flagged_rows)
        print(f"unresolved_sentinels: {c['summary']['flagged']:,} / {c['summary']['checked']:,} flagged", flush=True)
        checks.append(c)

        c = check_implied_speed(edges, args.min_speed_ms, args.max_flagged_rows)
        print(f"implied_speed: {c['summary']['flagged']:,} / {c['summary']['checked']:,} flagged", flush=True)
        checks.append(c)

        for layer_name in EDGE_LAYERS:
            edge_dir = edges_root / layer_name
            records_path, profiles_path = edge_dir / "records.npy", edge_dir / "profiles.npy"
            if not records_path.exists() or not profiles_path.exists():
                continue
            records = binfmt.load_array(records_path, mmap=False)
            profiles = binfmt.load_array(profiles_path, mmap=False)
            c = check_profile_integrity(records, profiles, profile_points, layer_name,
                                         args.max_flagged_rows)
            print(f"profile_integrity[{layer_name}]: {c['summary']['flagged']:,} / "
                  f"{c['summary']['checked']:,} flagged", flush=True)
            checks.append(c)

        write_report(Path(args.out), "elevation", checks)
        print(f"written {args.out}", flush=True)


if __name__ == "__main__":
    main()
