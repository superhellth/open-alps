#!/usr/bin/env python3
"""Builds display-only elevation profiles for hut_edges/ and start_edges/ records, interpolated
onto config["dem"]["profilePoints"] evenly-spaced distances per record (spec B4). Never opens the
DEM: every point's elevation comes from sample_base_elevation.py's already-persisted
base_graph/{node_ele.npy, interior_ele.npy} (spec B2/B3 - routing and display read the same
numbers), looked up by exact (quantized) coordinate identity - the same coordinate-identity
attribution technique analysis/grading_coverage.py already uses to attribute a stored polyline
back onto OSM segments.

Two kinds of geometry points never match that lookup: a record's own hub/access-point endpoints
(never base-graph points at all) and a mid-chain hub-snap point (lib/edge_split.py's interpolated
split_coord). Both are filled by carrying the nearest matched neighbour's elevation along the
polyline - a reasonable approximation for a DISPLAY profile, not the routing cost.

Retuning --profile-points is meant to be cheap (no re-route, no DEM read) - this script alone
owns that retune path; sample_base_elevation.py/compute_edge_profiles.py stay untouched by it.

Usage: python pipeline/phases/elevation/build_profiles.py [--profile-points 30]
Requires data/osm/base_graph/{node_ele.npy,interior_ele.npy} (sample_base_elevation.py) and
data/osm/{hut_edges,start_edges}/{records.npy,geometry.npy} (build_hub_edges.py).
"""

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib import binfmt  # noqa: E402
from lib.geo import haversine_m_vec_pairs as _haversine_m_vec_pairs  # noqa: E402
from lib.pipeline import OSM_DIR, load_config  # noqa: E402
from lib.timing import StepTimer, phase  # noqa: E402

SCRIPT_NAME = "build_profiles.py"

_QUANT = 1e7  # OSM's own coordinate precision (~1.1 cm at the equator)


def _point_codes(lon, lat):
    lonq = np.rint(np.asarray(lon, dtype=np.float64) * _QUANT).astype(np.int64)
    latq = np.rint(np.asarray(lat, dtype=np.float64) * _QUANT).astype(np.int64)
    # pack into one sortable int64-safe key (lon/lat both fit well within 2^31 after quantizing
    # a +/-180deg range to 1e-7deg)
    return (lonq + 2_000_000_000) * np.int64(4_000_000_001) + (latq + 2_000_000_000)


def build_elevation_lookup(nodes, interior, node_ele, interior_ele):
    """Sorted (key, elevation) table over every base-graph node + interior point, for
    searchsorted-based exact-coordinate lookup. Node keys are appended after interior keys so
    that, on a rare exact coordinate collision, np.unique's `return_index` keeps the FIRST
    occurrence - doesn't matter here since a real collision means the two points share a
    location and therefore, in practice, an elevation."""
    keys = np.concatenate([_point_codes(interior["lon"], interior["lat"]),
                            _point_codes(nodes["lon"], nodes["lat"])])
    values = np.concatenate([interior_ele, node_ele])
    order = np.argsort(keys, kind="stable")
    keys, values = keys[order], values[order]
    uniq_keys, first_idx = np.unique(keys, return_index=True)
    return uniq_keys, values[first_idx]


def lookup_elevations(lon, lat, lookup_keys, lookup_values):
    """Vectorized exact-match lookup; unmatched points come back as NaN for the caller to fill."""
    codes = _point_codes(lon, lat)
    pos = np.searchsorted(lookup_keys, codes)
    pos_clipped = np.minimum(pos, len(lookup_keys) - 1)
    hit = lookup_keys[pos_clipped] == codes
    out = np.full(len(codes), np.nan)
    out[hit] = lookup_values[pos_clipped[hit]]
    return out


def _ffill(arr: np.ndarray) -> np.ndarray:
    """Vectorized forward-fill: each NaN becomes the nearest preceding non-NaN value, or stays
    NaN if none precedes it. `np.maximum.accumulate` over "index if valid else -1" gives, at
    every position, the index of the most recent valid value seen so far."""
    valid = ~np.isnan(arr)
    idx = np.where(valid, np.arange(len(arr)), -1)
    idx = np.maximum.accumulate(idx)
    return np.where(idx >= 0, arr[np.clip(idx, 0, None)], np.nan)


def _fill_unmatched(elevations: np.ndarray) -> np.ndarray:
    """Nearest-neighbour carry along the polyline for NaN (unmatched) points - forward-fill then
    backward-fill so both leading and trailing gaps (a record's own hub/access-point endpoints
    are NEVER base-graph points) are covered.

    Vectorized (see _ffill) rather than a pair of pure-Python loops: at production scale
    (start_edges, ~235k records / ~200M geometry points as of 2026-08-27) the old
    point-at-a-time Python loops were the entire cost of build_profiles.py - 807s of its 827s
    total (data/timings.jsonl), even though this task is meant to be a cheap, always-rerun
    retune path for --profile-points (see this module's docstring and dodo.py's
    task_build_profiles comment)."""
    n = len(elevations)
    if n == 0 or np.all(np.isnan(elevations)):
        return np.nan_to_num(elevations)
    fwd = _ffill(elevations)
    return _ffill(fwd[::-1])[::-1]


def elevation_profile(lon: np.ndarray, lat: np.ndarray, samples: np.ndarray, n_points: int) -> list:
    if len(lon) < 2:
        return []
    seg_lens = _haversine_m_vec_pairs(lon[:-1], lat[:-1], lon[1:], lat[1:])
    xs = np.concatenate([[0.0], np.cumsum(seg_lens)])
    targets = np.linspace(xs[0], xs[-1], n_points)
    return [round(v, 1) for v in np.interp(targets, xs, samples).tolist()]


def build_profiles_for_edge_set(records, geometry, lookup_keys, lookup_values, profile_points):
    records = records.copy()
    lon_all, lat_all = geometry["lon"], geometry["lat"]
    ele_all = lookup_elevations(lon_all, lat_all, lookup_keys, lookup_values)

    profile_chunks = []
    cursor = 0
    for i in range(len(records)):
        offset, count = int(records[i]["geom_offset"]), int(records[i]["geom_count"])
        lon = lon_all[offset:offset + count]
        lat = lat_all[offset:offset + count]
        elevations = _fill_unmatched(ele_all[offset:offset + count])

        profile = elevation_profile(lon, lat, elevations, profile_points)
        records[i]["profile_offset"] = cursor
        records[i]["profile_count"] = len(profile)
        profile_chunks.extend(profile)
        cursor += len(profile)

    profiles = np.array(profile_chunks, dtype=binfmt.PROFILE_DTYPE)
    return records, profiles


def _process_edge_set(edge_dir: Path, lookup_keys, lookup_values, profile_points: int):
    records = binfmt.load_array(edge_dir / "records.npy", mmap=False)
    geometry = binfmt.load_array(edge_dir / "geometry.npy", mmap=False)
    if len(records) == 0:
        binfmt.save_array(edge_dir / "records.npy", records)
        binfmt.save_array(edge_dir / "profiles.npy", np.zeros(0, dtype=binfmt.PROFILE_DTYPE))
        return
    updated_records, profiles = build_profiles_for_edge_set(
        records, geometry, lookup_keys, lookup_values, profile_points
    )
    binfmt.save_array(edge_dir / "records.npy", updated_records)
    binfmt.save_array(edge_dir / "profiles.npy", profiles)


def main(argv=None):
    config = load_config()
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-graph-dir", default=str(OSM_DIR / "base_graph"),
                        help="directory holding the persisted base graph (build_base_graph.py's output)")
    parser.add_argument("--profile-points", type=int, default=config["dem"].get("profilePoints", 30),
                        help="number of evenly-spaced points to interpolate each edge's display elevation profile onto (see pipeline.config.json's dem.profilePoints)")
    args = parser.parse_args(argv)

    base_graph_dir = Path(args.base_graph_dir)
    timer = StepTimer()
    with phase(SCRIPT_NAME, "build_profiles", profile_points=args.profile_points) as meta:
        with timer.step("load_lookup"):
            nodes = binfmt.load_array(base_graph_dir / "nodes.npy", mmap=False)
            interior = binfmt.load_array(base_graph_dir / "interior.npy", mmap=False)
            node_ele = binfmt.load_array(base_graph_dir / "node_ele.npy", mmap=False)
            interior_ele = binfmt.load_array(base_graph_dir / "interior_ele.npy", mmap=False)
            lookup_keys, lookup_values = build_elevation_lookup(nodes, interior, node_ele, interior_ele)

        for name in ("hut_edges", "start_edges", "tour_edges"):
            edge_dir = OSM_DIR / name
            if not (edge_dir / "records.npy").exists():
                print(f"skipping {edge_dir} (not built yet)", flush=True)
                continue
            print(f"processing {edge_dir} ...", flush=True)
            with timer.step(name):
                _process_edge_set(edge_dir, lookup_keys, lookup_values, args.profile_points)
            print(f"written {edge_dir}/records.npy, {edge_dir}/profiles.npy", flush=True)
        meta.update(timer.as_meta())
    print(f"step totals: {timer.summary()}", flush=True)


if __name__ == "__main__":
    main()
