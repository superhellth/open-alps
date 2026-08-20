#!/usr/bin/env python3
"""Adds ascent_m/descent_m/elevation_profile to hut-edges.npy AND start-edges.npy records
(build_hub_edges.py's output), sampling data/dem/dem.tif along each record's geometry.npy
polyline. Same threshold-hysteresis algorithm as before V2 (ascent_descent/elevation_profile,
unchanged); only the I/O layer changed from GeoJSON to lib/binfmt.py's binary arrays, and both
edge sets are now processed together in one combined batched DEM window read.

Usage:
    python pipeline/phases/elevation/add_elevation.py
    python pipeline/phases/elevation/add_elevation.py --ele-noise-threshold-m 3
Requires data/dem/dem.tif (build_dem_vrt.py) and data/osm/{hut_edges,start_edges}/records.npy
(build_hub_edges.py).
"""

import argparse
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib import binfmt  # noqa: E402
from lib.pipeline import DEM_DIR, OSM_DIR, load_config  # noqa: E402
from lib.timing import phase  # noqa: E402

SCRIPT_NAME = "add_elevation.py"


def ascent_descent(elevations, threshold_m):
    if len(elevations) < 2:
        return 0.0, 0.0
    ascent = descent = 0.0
    baseline = elevations[0]
    for e in elevations[1:]:
        delta = e - baseline
        if abs(delta) < threshold_m:
            continue
        if delta > 0:
            ascent += delta
        else:
            descent += -delta
        baseline = e
    return ascent, descent


def haversine_m(lon1, lat1, lon2, lat2):
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def haversine_m_vec_pairs(lon1: np.ndarray, lat1: np.ndarray,
                           lon2: np.ndarray, lat2: np.ndarray) -> np.ndarray:
    """Fully-vectorized haversine over paired arrays (both endpoints vary per element) - computes
    every polyline segment length for one edge's elevation profile in a single call instead of a
    per-point Python loop calling the scalar haversine_m above."""
    r = 6_371_000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlambda / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def elevation_profile(lon: np.ndarray, lat: np.ndarray, samples: np.ndarray, n_points: int) -> list:
    if len(lon) < 2:
        return []
    seg_lens = haversine_m_vec_pairs(lon[:-1], lat[:-1], lon[1:], lat[1:])
    xs = np.concatenate([[0.0], np.cumsum(seg_lens)])
    targets = np.linspace(xs[0], xs[-1], n_points)
    return [round(v, 1) for v in np.interp(targets, xs, samples).tolist()]


def fill_elevation_records(records: np.ndarray, geometry: np.ndarray, all_elevations: np.ndarray,
                            profile_points: int, noise_threshold_m: float):
    records = records.copy()
    profile_chunks = []
    cursor = 0
    lons, lats = geometry["lon"], geometry["lat"]
    for i in range(len(records)):
        offset, count = int(records[i]["geom_offset"]), int(records[i]["geom_count"])
        lon = lons[offset:offset + count]
        lat = lats[offset:offset + count]
        elevations = all_elevations[offset:offset + count].astype(np.float64)

        # ascent_descent's threshold-hysteresis is inherently sequential (each step's baseline
        # reset depends on the cumulative decision so far), so it stays a Python loop - but over a
        # plain list (elevations.tolist()) rather than iterating a numpy array element-by-element,
        # which boxes each element as a numpy scalar and is slower than plain Python floats here.
        ascent, descent = ascent_descent(elevations.tolist(), noise_threshold_m)
        profile = elevation_profile(lon, lat, elevations, profile_points)

        records[i]["ascent_m"] = round(ascent, 1)
        records[i]["descent_m"] = round(descent, 1)
        records[i]["profile_offset"] = cursor
        records[i]["profile_count"] = len(profile)
        profile_chunks.extend(profile)
        cursor += len(profile)

    profiles = np.array(profile_chunks, dtype=binfmt.PROFILE_DTYPE)
    return records, profiles


def _process_edge_set(edge_dir: Path, dem_path: Path, profile_points: int, noise_threshold_m: float):
    import rasterio
    import rasterio.windows

    records = binfmt.load_array(edge_dir / "records.npy", mmap=False)
    geometry = binfmt.load_array(edge_dir / "geometry.npy", mmap=False)

    with rasterio.open(dem_path) as dem:
        t = dem.transform
        lons = geometry["lon"]
        lats = geometry["lat"]
        cols = np.floor((lons - t.c) / t.a).astype(np.int64)
        rows = np.floor((lats - t.f) / t.e).astype(np.int64)
        row_off, col_off = max(0, int(rows.min())), max(0, int(cols.min()))
        row_max = min(dem.height - 1, int(rows.max()))
        col_max = min(dem.width - 1, int(cols.max()))
        window = rasterio.windows.Window(col_off, row_off, col_max - col_off + 1, row_max - row_off + 1)
        with phase(SCRIPT_NAME, "read_dem_window", width=window.width, height=window.height):
            band = dem.read(1, window=window)
        rows_clip = np.clip(rows, row_off, row_max) - row_off
        cols_clip = np.clip(cols, col_off, col_max) - col_off
        elevations = band[rows_clip, cols_clip]

    with phase(SCRIPT_NAME, "per_edge_ascent_profile", edges=len(records)):
        updated_records, profiles = fill_elevation_records(
            records, geometry, elevations, profile_points, noise_threshold_m
        )

    binfmt.save_array(edge_dir / "records.npy", updated_records)
    binfmt.save_array(edge_dir / "profiles.npy", profiles)


if __name__ == "__main__":
    config = load_config()
    dem_config = config["dem"]

    parser = argparse.ArgumentParser()
    parser.add_argument("--dem", default=str(DEM_DIR / "dem.tif"))
    parser.add_argument("--ele-noise-threshold-m", type=float, default=dem_config["eleNoiseThresholdM"])
    parser.add_argument("--profile-points", type=int, default=dem_config.get("profilePoints", 30))
    args = parser.parse_args()

    for name in ("hut_edges", "start_edges"):
        edge_dir = OSM_DIR / name
        print(f"processing {edge_dir} ...")
        _process_edge_set(edge_dir, Path(args.dem), args.profile_points, args.ele_noise_threshold_m)
        print(f"written {edge_dir}/records.npy, {edge_dir}/profiles.npy")
