#!/usr/bin/env python3
"""Matches each tour folder's legs (pipeline/tours/<Name>/<N>.gpx) directly onto their own GPX
trace + the DEM - no OSM base graph, no routing, no map matching (spec docs/superpowers/specs/
2026-09-14-gpx-hut-snap-design.md). Each leg's
distance/ascent/descent/duration/geometry come straight from its raw trace; only its two endpoints
are resolved onto a hub, by pure nearest-point distance (lib/hubs.py's nearest_hub_to_point).

Produces data/build/tour-edges/{records.npy, geometry.npy, profiles.npy} (binfmt.TOUR_LEG_DTYPE),
data/build/tour-edges/tours.json (per shipped tour, `numDays` legs; each leg carries `edgeId` = its row in
tour-edges/records.npy plus its scalars and both endpoints). A tour with any unresolved leg endpoint is
dropped from every output, so tours.json and records/geometry/profiles.npy never contain a gap leg;
data/build/tour-edges/tour-match-gaps.json (one reason: "leg_endpoint_unsnapped" entry per unresolved leg
endpoint, including those of dropped tours; build-only, reported by check_tour_matching.py) and
data/build/tour-edges/hubs.json (the hub set snapped against).

Usage: python pipeline/phases/graph_building/match_tour_edges.py
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import binfmt, speed  # noqa: E402
from lib.dem_sample import sample_points  # noqa: E402
from lib.elevation_profile import ascent_descent, merge_segments, resample_to_points, smooth_profile  # noqa: E402
from lib.geo import haversine_m_vec_pairs  # noqa: E402
from lib.hubs import HUB_TYPE_JSON_NAMES, load_all_hubs, nearest_hub_to_point  # noqa: E402
from lib.pipeline import (  # noqa: E402
    RAW_DEM_DIR, RAW_DIR, START_POINTS_DIR, TOUR_EDGES_DIR, TOURS_DIR, load_config,
)  # noqa: E402
from lib.timing import phase  # noqa: E402
from lib.tour_folder import load_all_tour_folders, load_tour_folder  # noqa: E402

SCRIPT_NAME = "match_tour_edges.py"


def match_leg(points, dem_path, kernel_m, min_slope_segment_m, speed_model, min_speed_ms,
              profile_points, elevations=None) -> dict:
    """Computes one leg's distance/ascent/descent/duration/max_ele/display-profile straight from
    its own GPX trace `points` (ordered (lon, lat) tuples) + a DEM sample. `elevations` is exposed
    as an optional override purely so tests can exercise the profile math without a real DEM
    (dem_path is unused when elevations is given)."""
    lons = np.array([p[0] for p in points], dtype=np.float64)
    lats = np.array([p[1] for p in points], dtype=np.float64)
    seg_len_m = (
        haversine_m_vec_pairs(lons[:-1], lats[:-1], lons[1:], lats[1:]) if len(points) > 1
        else np.zeros(0)
    )
    distance_m = float(seg_len_m.sum())

    if elevations is None:
        elevations = sample_points(dem_path, points)
    smoothed = smooth_profile(elevations, seg_len_m, kernel_m)
    ascent_m, descent_m = ascent_descent(smoothed)
    max_ele_m = float(np.max(smoothed)) if len(smoothed) else 0.0

    merged_len, merged_dz = merge_segments(seg_len_m, np.diff(smoothed), min_slope_segment_m)
    duration_s = float(speed.edge_time_s(merged_len, merged_dz, **speed_model).sum())
    if distance_m > 0:
        duration_s = min(duration_s, distance_m / min_speed_ms)

    profile = resample_to_points(lons, lats, smoothed, profile_points)
    return {
        "distance_m": distance_m, "ascent_m": ascent_m, "descent_m": descent_m,
        "duration_s": duration_s, "max_ele_m": max_ele_m, "profile": profile,
    }


def _resolve_endpoint(hubs, huts_only, point, max_snap_m, require_hut):
    """Resolves one leg endpoint via lib.hubs.nearest_hub_to_point against the huts-only subset
    when `require_hut` (every overnight/interior endpoint), or the full hub set when not (the
    tour's very first leg's "from" and very last leg's "to" only)."""
    pool = huts_only if require_hut else hubs
    return nearest_hub_to_point(pool, point, max_snap_m)


def _hub_json(hub):
    return {"type": HUB_TYPE_JSON_NAMES[hub["type"]], "id": hub["id"]} if hub else None


def _pack_tour_legs(legs: list) -> tuple:
    """Packs matched leg dicts into binfmt.TOUR_LEG_DTYPE + flat geometry.npy/profiles.npy,
    (one growing array per file, each record's offset/count slicing into it). No geometry dedup: a
    tour leg's own raw GPX trace is never repeated across legs."""
    records_arr = np.zeros(len(legs), dtype=binfmt.TOUR_LEG_DTYPE)
    flat_geometry: list = []
    flat_profiles: list = []
    geom_cursor = 0
    profile_cursor = 0
    for i, leg in enumerate(legs):
        geom = leg["geometry"]
        profile = leg["profile"]
        records_arr[i] = (
            leg["from_id"], leg["to_id"], leg["from_type"], leg["to_type"],
            leg["distance_m"], leg["ascent_m"], leg["descent_m"], leg["duration_s"],
            leg["max_ele_m"], geom_cursor, len(geom), profile_cursor, len(profile),
        )
        flat_geometry.extend(geom)
        geom_cursor += len(geom)
        flat_profiles.extend(profile)
        profile_cursor += len(profile)

    geometry_arr = np.zeros(len(flat_geometry), dtype=binfmt.COORD_DTYPE)
    if flat_geometry:
        geometry_arr["lon"] = [p[0] for p in flat_geometry]
        geometry_arr["lat"] = [p[1] for p in flat_geometry]
    profiles_arr = np.array(flat_profiles, dtype=binfmt.PROFILE_DTYPE)
    return records_arr, geometry_arr, profiles_arr


def write_hubs_json(hubs: list, out_dir: Path) -> Path:
    """Writes the hub set this script snaps against as [{id, type, lon, lat, name}] so the dev-only
    GPX editor (huts/src/gpxEditor) snaps against exactly the same hubs and ids as
    tour-match-gaps.json reports (spec 2026-09-18-gpx-editor-design.md)."""
    path = Path(out_dir) / "hubs.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {"id": h["id"], "type": HUB_TYPE_JSON_NAMES[h["type"]], "lon": h["lon"], "lat": h["lat"],
         "name": h["name"]}
        for h in hubs
    ]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
    return path


def main(argv=None):
    config = load_config()
    speed_cfg = config["graph"]["speedModel"]
    parser = argparse.ArgumentParser()
    parser.add_argument("--dem", default=str(RAW_DEM_DIR / "dem.tif"),
                        help="path to the materialized DEM GeoTIFF (build_dem_vrt.py's output)")
    parser.add_argument("--out-dir", default=str(TOUR_EDGES_DIR),
                        help="directory to write the tour-edge set, tours.json, tour-match-gaps.json and hubs.json into")
    parser.add_argument("--huts", default=str(RAW_DIR / "huts.geojson"), help="hut list (fetch_huts.py's output)")
    parser.add_argument("--start-points", default=str(START_POINTS_DIR / "start-points.npy"),
                        help="start-point array (filter_start_points.py's output)")
    parser.add_argument("--max-snap-m", type=float, default=config["graph"]["maxSnapM"],
                        help="max distance (m) a leg endpoint may be from the nearest hub to snap to it (see pipeline.config.json's graph.maxSnapM)")
    parser.add_argument("--smoothing-kernel-m", type=float, default=config["dem"]["smoothingKernelM"],
                        help="width (m) of the distance-weighted triangular smoothing kernel applied to each leg's raw DEM profile (see pipeline.config.json's dem.smoothingKernelM)")
    parser.add_argument("--min-slope-segment-m", type=float, default=config["dem"]["minSlopeSegmentM"],
                        help="minimum horizontal run (m) a merged segment must reach before slope is computed for duration_s (see pipeline.config.json's dem.minSlopeSegmentM)")
    parser.add_argument("--profile-points", type=int, default=config["dem"].get("profilePoints", 30),
                        help="number of evenly-spaced points each leg's display elevation profile is interpolated onto (see pipeline.config.json's dem.profilePoints)")
    parser.add_argument("--speed-v0", type=float, default=speed_cfg["v0"])
    parser.add_argument("--speed-k", type=float, default=speed_cfg["k"])
    parser.add_argument("--speed-s0", type=float, default=speed_cfg["s0"])
    parser.add_argument("--min-speed-ms", type=float, default=speed_cfg["minSpeedMs"],
                        help="floor on implied walking speed (m/s); a leg's duration_s is clamped so it never implies a slower speed (see pipeline.config.json's graph.speedModel.minSpeedMs)")
    args = parser.parse_args(argv)

    speed_model = {"v0": args.speed_v0, "k": args.speed_k, "s0": args.speed_s0}

    hubs = load_all_hubs(Path(args.huts), Path(args.start_points))
    huts_only = [h for h in hubs if h["type"] == binfmt.TYPE_HUT]

    tour_folders = load_all_tour_folders(Path(TOURS_DIR))
    matched_legs, gaps, tours_index = [], [], []

    with phase(SCRIPT_NAME, "match_tour_edges", n_tours=len(tour_folders)):
        for tour_id, (tour_name, folder) in enumerate(tour_folders):
            legs = load_tour_folder(folder)
            n_legs = len(legs)

            resolved, tour_gaps = [], []
            for position, (leg_number, points) in enumerate(legs):
                leg_index = leg_number - 1
                from_requires_hut = position != 0
                to_requires_hut = position != n_legs - 1

                from_chosen, from_nearest, from_dist = _resolve_endpoint(
                    hubs, huts_only, points[0], args.max_snap_m, from_requires_hut)
                to_chosen, to_nearest, to_dist = _resolve_endpoint(
                    hubs, huts_only, points[-1], args.max_snap_m, to_requires_hut)

                if from_chosen is None or to_chosen is None:
                    endpoint = "from" if from_chosen is None else "to"
                    nearest, dist = (from_nearest, from_dist) if from_chosen is None else (to_nearest, to_dist)
                    tour_gaps.append({
                        "tourId": tour_id, "tourName": tour_name, "legIndex": leg_index,
                        "reason": "leg_endpoint_unsnapped",
                        "detail": {
                            "endpoint": endpoint,
                            "nearestType": HUB_TYPE_JSON_NAMES[nearest["type"]] if nearest else None,
                            "nearestId": nearest["id"] if nearest else None,
                            "nearestDistM": dist,
                        },
                    })
                resolved.append((leg_index, points, from_chosen, to_chosen))

            if tour_gaps:
                gaps.extend(tour_gaps)
                continue

            tour_legs_json = []
            for leg_index, points, from_chosen, to_chosen in resolved:
                result = match_leg(
                    points, args.dem, args.smoothing_kernel_m, args.min_slope_segment_m,
                    speed_model, args.min_speed_ms, args.profile_points,
                )

                tour_legs_json.append({
                    "legIndex": leg_index, "edgeId": len(matched_legs),
                    "distanceM": result["distance_m"], "ascentM": result["ascent_m"],
                    "descentM": result["descent_m"], "durationS": result["duration_s"],
                    "maxEleM": result["max_ele_m"],
                    "from": _hub_json(from_chosen), "to": _hub_json(to_chosen),
                })

                matched_legs.append({
                    "from_id": from_chosen["id"], "to_id": to_chosen["id"],
                    "from_type": from_chosen["type"], "to_type": to_chosen["type"],
                    "distance_m": result["distance_m"], "ascent_m": result["ascent_m"],
                    "descent_m": result["descent_m"], "duration_s": result["duration_s"],
                    "max_ele_m": result["max_ele_m"], "geometry": points,
                    "profile": result["profile"],
                })

            tours_index.append({
                "tourId": tour_id, "name": tour_name, "numDays": n_legs, "legs": tour_legs_json,
            })

    print(f"tours shipped: {len(tours_index)} / {len(tour_folders)}, legs matched: {len(matched_legs)}, "
          f"unresolved endpoints: {len(gaps)}")

    out_dir = Path(args.out_dir)
    records_arr, geometry_arr, profiles_arr = _pack_tour_legs(matched_legs)
    binfmt.save_array(out_dir / "records.npy", records_arr)
    binfmt.save_array(out_dir / "geometry.npy", geometry_arr)
    binfmt.save_array(out_dir / "profiles.npy", profiles_arr)

    tours_path = out_dir / "tours.json"
    with open(tours_path, "w", encoding="utf-8") as fh:
        json.dump(tours_index, fh)

    gaps_path = out_dir / "tour-match-gaps.json"
    with open(gaps_path, "w", encoding="utf-8") as fh:
        json.dump(gaps, fh)
    hubs_path = write_hubs_json(hubs, out_dir)
    print(f"written {out_dir}/records.npy, geometry.npy, profiles.npy, {tours_path}, {gaps_path} and {hubs_path}")


if __name__ == "__main__":
    main()
