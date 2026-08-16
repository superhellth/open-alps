#!/usr/bin/env python3
"""
Adds ascent_m/descent_m and a downsampled elevation_profile to every edge in hut-edges.geojson
(script 06's output), by sampling the DEM mosaic (script 07's materialized dem.tif - a real
GeoTIFF, not the lazily-reprojecting dem.vrt it's built from, so this stays cheap to rerun; see
lib/pipeline.py's materialize_geotiff()) along each edge's real trail polyline.

Raw DEM samples are noisy - summing every up/down step between adjacent samples overcounts
ascent on flat-looking terrain (a well-known issue for any elevation-gain calculation, not
specific to this DEM). Filtered with a threshold-hysteresis pass: only count a direction change
once cumulative elevation drift since the last counted point exceeds --ele-noise-threshold-m
(default from pipeline.config.json's dem.eleNoiseThresholdM). Small threshold = more sensitive to
real short climbs but noisier; large threshold = smoother but can flatten genuinely short steep
sections.

elevation_profile is a fixed-length array of `dem.profilePoints` elevations (meters), evenly
spaced by cumulative trail distance from the from-hut to the to-hut - not the raw DEM samples,
which sit at the polyline's original (irregular) vertex spacing and may have nodata gaps. The
frontend can render it as a sparkline without knowing anything about sample spacing; x-position
i/n_points maps to that fraction of the edge's distance_m.

All edges' polyline vertices are sampled in a single `dem.sample()` call rather than one call per
edge - at this edge count (low hundreds), the per-call GDAL/VRT open-and-seek overhead dominated
over the actual read cost, so batching is a bigger win here than parallelizing the per-edge loop
would be.

Usage:
    python pipeline/08-add-elevation.py
    python pipeline/08-add-elevation.py --ele-noise-threshold-m 3
Requires data/dem/dem.tif (step 07) and data/osm/hut-edges.geojson (step 06).
"""

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import rasterio
import rasterio.transform
import rasterio.windows

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.pipeline import DEM_DIR, OSM_DIR, load_config  # noqa: E402
from lib.timing import phase  # noqa: E402

SCRIPT_NAME = "08-add-elevation.py"

config = load_config()
dem_config = config["dem"]

parser = argparse.ArgumentParser()
parser.add_argument("--edges", default=str(OSM_DIR / "hut-edges.geojson"))
parser.add_argument("--dem", default=str(DEM_DIR / "dem.tif"))
parser.add_argument("--out", default=str(OSM_DIR / "hut-edges.geojson"))
parser.add_argument("--ele-noise-threshold-m", type=float, default=dem_config["eleNoiseThresholdM"])
parser.add_argument("--profile-points", type=int, default=dem_config.get("profilePoints", 30))
args = parser.parse_args()


def ascent_descent(elevations, threshold_m):
    """Threshold-hysteresis ascent/descent: only counts a run once cumulative drift from the
    last counted point exceeds threshold_m, so DEM sample noise doesn't inflate the total."""
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


def elevation_profile(coords, samples, nodata, n_points):
    """Downsamples DEM elevation samples along a trail polyline to n_points evenly spaced by
    cumulative distance - so the frontend gets a fixed-size, evenly-spaced series regardless of
    the polyline's original vertex spacing or DEM nodata gaps."""
    dist = 0.0
    xs, ys = [], []
    prev = None
    for (lon, lat), s in zip(coords, samples):
        if prev is not None:
            dist += haversine_m(prev[0], prev[1], lon, lat)
        prev = (lon, lat)
        if nodata is not None and s == nodata:
            continue
        xs.append(dist)
        ys.append(float(s))
    if len(xs) < 2:
        return []
    targets = np.linspace(xs[0], xs[-1], n_points)
    return [round(v, 1) for v in np.interp(targets, xs, ys).tolist()]


with open(args.edges, encoding="utf-8") as f:
    fc = json.load(f)

vertex_counts = [len(feat["geometry"]["coordinates"]) for feat in fc["features"]]
all_coords = [c for feat in fc["features"] for c in feat["geometry"]["coordinates"]]

print(f"sampling {args.dem} for {len(all_coords):,} points across {len(fc['features'])} edges ...")
with rasterio.open(args.dem) as dem:
    nodata = dem.nodata
    lons = np.array([c[0] for c in all_coords])
    lats = np.array([c[1] for c in all_coords])
    # rasterio.transform.rowcol() crashes on this GDAL/rasterio build for any array input
    # longer than 1 (native-level bug, reproduces even on 2 plain floats) - compute the
    # row/col indices directly from the affine transform coefficients instead.
    t = dem.transform
    cols = np.floor((lons - t.c) / t.a).astype(np.int64)
    rows = np.floor((lats - t.f) / t.e).astype(np.int64)

    # dem.sample() opens+seeks a tiny window per point - fine for a handful of edges, but with
    # thousands of vertices the per-point call overhead dominates. The DEM mosaic itself is too
    # big to read wholesale into RAM (tens of GB), but the edges only span a small bbox within
    # it, so read just that window once and fancy-index it - single I/O call, all points at once.
    row_off = max(0, int(rows.min()))
    col_off = max(0, int(cols.min()))
    row_max = min(dem.height - 1, int(rows.max()))
    col_max = min(dem.width - 1, int(cols.max()))
    window = rasterio.windows.Window(
        col_off, row_off, col_max - col_off + 1, row_max - row_off + 1
    )
    with phase(SCRIPT_NAME, "read_dem_window", width=window.width, height=window.height):
        band = dem.read(1, window=window)
    rows_clip = np.clip(rows, row_off, row_max) - row_off
    cols_clip = np.clip(cols, col_off, col_max) - col_off
    all_samples = band[rows_clip, cols_clip]

nodata_count = 0
offset = 0
with phase(SCRIPT_NAME, "per_edge_ascent_profile", edges=len(fc["features"])):
    for i, feat in enumerate(fc["features"]):
        coords = feat["geometry"]["coordinates"]
        n = vertex_counts[i]
        samples = all_samples[offset:offset + n]
        offset += n

        elevations = []
        for s in samples:
            if nodata is not None and s == nodata:
                nodata_count += 1
                continue
            elevations.append(float(s))

        ascent, descent = ascent_descent(elevations, args.ele_noise_threshold_m)
        feat["properties"]["ascent_m"] = round(ascent, 1)
        feat["properties"]["descent_m"] = round(descent, 1)
        feat["properties"]["elevation_profile"] = elevation_profile(
            coords, samples, nodata, args.profile_points
        )

        if i % 200 == 0:
            print(f"  {i}/{len(fc['features'])} edges processed")

if nodata_count:
    print(f"warning: {nodata_count} sample points had no DEM coverage (outside downloaded tiles)")

with open(args.out, "w", encoding="utf-8") as f:
    json.dump(fc, f)
print(f"written {args.out}")
