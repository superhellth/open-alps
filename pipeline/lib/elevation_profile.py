"""Portable elevation-profile math shared by phases/graph_building/match_tour_edges.py - smoothing,
slope-segment merging, ascent/descent summation, and display-profile resampling, all pure functions
over an elevation array + geometry, no base-graph dependency. resample_to_points takes an
elevation array directly. See docs/superpowers/specs/2026-09-14-gpx-hut-snap-design.md."""

import numpy as np

from lib.geo import haversine_m_vec_pairs


def smooth_profile(elevations, seg_len_m, kernel_m: float) -> np.ndarray:
    """Distance-weighted moving average (triangular kernel, half-width kernel_m/2) over the
    cumulative distance implied by seg_len_m - the kernel is metres, not points, since a GPX
    trace's point spacing is whatever the recording device chose, not a fixed sample rate."""
    elevations = np.asarray(elevations, dtype=np.float64)
    if len(elevations) <= 1 or kernel_m <= 0:
        return elevations.copy()
    seg_len_m = np.asarray(seg_len_m, dtype=np.float64)
    x = np.concatenate([[0.0], np.cumsum(seg_len_m)])
    half_width = kernel_m / 2.0
    diff = np.abs(x[:, None] - x[None, :])
    weight = np.clip(1.0 - diff / half_width, 0.0, None)
    return (weight @ elevations) / weight.sum(axis=1)


def merge_segments(seg_len, dz, min_segment_m: float) -> tuple:
    """Merges consecutive (seg_len, dz) pairs from the smoothed profile until each merged segment's
    horizontal run is at least min_segment_m, so slope is computed over a wider run than the raw
    per-point digitization. A trailing remainder shorter than min_segment_m is kept as its own final
    segment, never dropped or force-merged - dropping it would silently discard real distance/
    elevation."""
    seg_len = np.asarray(seg_len, dtype=np.float64)
    dz = np.asarray(dz, dtype=np.float64)
    merged_len, merged_dz = [], []
    run_len, run_dz = 0.0, 0.0
    for length, delta in zip(seg_len, dz):
        run_len += length
        run_dz += delta
        if run_len >= min_segment_m:
            merged_len.append(run_len)
            merged_dz.append(run_dz)
            run_len, run_dz = 0.0, 0.0
    if run_len > 0:
        merged_len.append(run_len)
        merged_dz.append(run_dz)
    return np.array(merged_len, dtype=np.float64), np.array(merged_dz, dtype=np.float64)


def ascent_descent(elevations) -> tuple:
    """Plain signed-delta sums over `elevations` - positive deltas summed into ascent_m, negative
    into descent_m. Deliberately run on the SMOOTHED, UNMERGED profile, not merge_segments' output:
    merge_segments widens the run for its slope calculation, which would understate real elevation
    gain/loss on a genuine staircase of short climbs."""
    elevations = np.asarray(elevations, dtype=np.float64)
    if len(elevations) < 2:
        return 0.0, 0.0
    diffs = np.diff(elevations)
    return float(diffs[diffs > 0].sum()), float(-diffs[diffs < 0].sum())


def resample_to_points(lon, lat, elevations, n_points: int) -> list:
    """Interpolates `elevations` (already sampled/smoothed along (lon, lat)) onto n_points evenly-
    spaced distances along the polyline - the leg's display elevation profile."""
    lon = np.asarray(lon, dtype=np.float64)
    lat = np.asarray(lat, dtype=np.float64)
    if len(lon) < 2:
        return []
    seg_lens = haversine_m_vec_pairs(lon[:-1], lat[:-1], lon[1:], lat[1:])
    xs = np.concatenate([[0.0], np.cumsum(seg_lens)])
    targets = np.linspace(xs[0], xs[-1], n_points)
    return [round(v, 1) for v in np.interp(targets, xs, elevations).tolist()]
