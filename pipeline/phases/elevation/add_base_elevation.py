#!/usr/bin/env python3
"""Samples data/dem/dem.tif per BASE-GRAPH EDGE (spec B2), not per record.

Why per edge and not per node: nodes.npy holds 6.85M post-contraction junctions and the shape
lives in interior.npy (33.1M points). Node elevation gives only the NET delta across a contracted
edge, so a switchback chain over a col would report its endpoint difference and nothing else.

Why a separate process from build_base_graph.py: that script already peaks at 12.4 GB of 15.95 GB
(data/timings.jsonl). This one reads the DEM PER GRID CELL (cell_index.npy + lib/grid.py), never
as one 74008x39276 window.

Sampling is BILINEAR against a pre-smoothed raster (one cached gdal pass), replacing the old
nearest-neighbour np.floor into a 5 m (Bavaria DGM5) / 10 m (AT BEV) DEM. Ascent/descent are plain
sums of positive/negative deltas along the smoothed profile - eleNoiseThresholdM and its hysteresis
loop are retired, and the kernel width (metres) is the replacement tunable.

Persists node_ele.npy (f4 x 6.85M, 27 MB) and interior_ele.npy (f4 x 33.1M, 132 MB) so
build_profiles.py and every display path can avoid reopening the DEM.

This module is pure functions only (no argv/filesystem access) - the doit wiring, DEM reading and
edges.npy rewrite live in Task 8's main().
"""

import numpy as np


def smooth_profile(elevations, seg_len_m, kernel_m: float) -> np.ndarray:
    """Distance-weighted moving average (triangular kernel, half-width kernel_m/2) over the
    cumulative distance implied by seg_len_m - the kernel is metres, not points, since point
    spacing varies ~7x across base edges (p25 19.7 m, p75 133.7 m)."""
    elevations = np.asarray(elevations, dtype=np.float64)
    if len(elevations) <= 1 or kernel_m <= 0:
        return elevations.copy()
    seg_len_m = np.asarray(seg_len_m, dtype=np.float64)
    x = np.concatenate([[0.0], np.cumsum(seg_len_m)])
    half_width = kernel_m / 2.0
    diff = np.abs(x[:, None] - x[None, :])
    weight = np.clip(1.0 - diff / half_width, 0.0, None)
    return (weight @ elevations) / weight.sum(axis=1)


def edge_ascent_descent(smoothed, edge_starts, edge_counts) -> tuple:
    """Plain signed-delta sums along each edge's smoothed profile - no threshold, no hysteresis.
    `smoothed` is the tight concatenation of every edge's own point sequence in edge order
    (edge_starts[i] == sum(edge_counts[:i])), the same packing convention as
    build_base_graph.py's flat_interior / binfmt.gather_ragged. Vectorised over every edge at
    once via a single np.diff + bincount pass, not a per-edge Python loop."""
    smoothed = np.asarray(smoothed, dtype=np.float64)
    edge_counts = np.asarray(edge_counts, dtype=np.int64)
    n_edges = len(edge_counts)
    if len(smoothed) < 2:
        return np.zeros(n_edges), np.zeros(n_edges)

    diffs = np.diff(smoothed)
    point_group = np.repeat(np.arange(n_edges), edge_counts)
    left_group, right_group = point_group[:-1], point_group[1:]
    same_edge = left_group == right_group

    ascent_vals = np.where(same_edge & (diffs > 0), diffs, 0.0)
    descent_vals = np.where(same_edge & (diffs < 0), -diffs, 0.0)
    diff_group = np.where(same_edge, left_group, 0)  # group value is irrelevant where weight is 0

    ascent = np.bincount(diff_group, weights=ascent_vals, minlength=n_edges)[:n_edges]
    descent = np.bincount(diff_group, weights=descent_vals, minlength=n_edges)[:n_edges]
    return ascent, descent


def sample_bilinear(dem_window: np.ndarray, transform, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Bilinear sampling of a DEM window at pixel CENTRES (standard raster convention: transform
    maps integer (col, row) to a pixel's upper-left CORNER, so the centre of pixel (col, row) is
    at fractional pixel coordinate (col + 0.5, row + 0.5)). Replaces the old nearest-neighbour
    np.floor sampling."""
    lon = np.asarray(lon, dtype=np.float64)
    lat = np.asarray(lat, dtype=np.float64)
    inv = ~transform
    col, row = inv * (lon, lat)
    col_f, row_f = col - 0.5, row - 0.5

    height, width = dem_window.shape
    col0 = np.clip(np.floor(col_f).astype(np.int64), 0, width - 1)
    row0 = np.clip(np.floor(row_f).astype(np.int64), 0, height - 1)
    col1 = np.clip(col0 + 1, 0, width - 1)
    row1 = np.clip(row0 + 1, 0, height - 1)
    fx = np.clip(col_f - col0, 0.0, 1.0)
    fy = np.clip(row_f - row0, 0.0, 1.0)

    v00 = dem_window[row0, col0].astype(np.float64)
    v01 = dem_window[row0, col1].astype(np.float64)
    v10 = dem_window[row1, col0].astype(np.float64)
    v11 = dem_window[row1, col1].astype(np.float64)
    return (1 - fx) * (1 - fy) * v00 + fx * (1 - fy) * v01 + (1 - fx) * fy * v10 + fx * fy * v11
