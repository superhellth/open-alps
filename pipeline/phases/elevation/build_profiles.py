#!/usr/bin/env python3
"""Builds display-only elevation profiles for hut_edges/ and start_edges/ records, interpolated
onto config["dem"]["profilePoints"] evenly-spaced distances per record (spec B4). Never opens the
DEM: every point's elevation comes from add_base_elevation.py's already-persisted
base_graph/{node_ele.npy, interior_ele.npy} (spec B2/B3 - routing and display read the same
numbers), looked up by exact (quantized) coordinate identity - the same coordinate-identity
attribution technique analysis/grading_coverage.py already uses to attribute a stored polyline
back onto OSM segments.

Two kinds of geometry points never match that lookup: a record's own hub/access-point endpoints
(never base-graph points at all) and a mid-chain hub-snap point (lib/edge_split.py's interpolated
split_coord). Both are filled by carrying the nearest matched neighbour's elevation along the
polyline - a reasonable approximation for a DISPLAY profile, not the routing cost.

Retuning --profile-points is meant to be cheap (no re-route, no DEM read) - this script alone
owns that retune path; add_base_elevation.py stays untouched by it.

Usage: python pipeline/phases/elevation/build_profiles.py [--profile-points 30]
Requires data/osm/base_graph/{node_ele.npy,interior_ele.npy} (add_base_elevation.py) and
data/osm/{hut_edges,start_edges}/{records.npy,geometry.npy} (build_hub_edges.py).
"""

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib import binfmt  # noqa: E402
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


def _fill_unmatched(elevations: np.ndarray) -> np.ndarray:
    """Nearest-neighbour carry along the polyline for NaN (unmatched) points - forward-fill then
    backward-fill so both leading and trailing gaps (a record's own hub/access-point endpoints
    are NEVER base-graph points) are covered."""
    out = elevations.copy()
    n = len(out)
    if n == 0 or np.all(np.isnan(out)):
        return np.nan_to_num(out)
    last = None
    for i in range(n):
        if np.isnan(out[i]):
            if last is not None:
                out[i] = last
        else:
            last = out[i]
    nxt = None
    for i in range(n - 1, -1, -1):
        if np.isnan(out[i]):
            out[i] = nxt
        else:
            nxt = out[i]
    return out


def _haversine_m_vec_pairs(lon1, lat1, lon2, lat2):
    r = 6_371_000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlambda / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


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
    parser.add_argument("--base-graph-dir", default=str(OSM_DIR / "base_graph"))
    parser.add_argument("--profile-points", type=int, default=config["dem"].get("profilePoints", 30))
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

        for name in ("hut_edges", "start_edges"):
            edge_dir = OSM_DIR / name
            print(f"processing {edge_dir} ...", flush=True)
            with timer.step(name):
                _process_edge_set(edge_dir, lookup_keys, lookup_values, args.profile_points)
            print(f"written {edge_dir}/records.npy, {edge_dir}/profiles.npy", flush=True)
        meta.update(timer.as_meta())
    print(f"step totals: {timer.summary()}", flush=True)


if __name__ == "__main__":
    main()
