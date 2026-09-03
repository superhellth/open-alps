"""Two quantities that must never be conflated (spec A1/A2).

ROUTING WEIGHT (edge_time_s): additive per base-graph edge, pointwise, Tobler-shaped:
    v(s) = v0 * exp(-k * |s + s0|)   km/h,  s = dz/dx
Base edges have median length 49.5 m (p25 19.7, p75 133.7, n=8.34M). At that granularity DIN's
max+min/2 blend never engages, and a per-edge DIN sum degenerates to t_h + t_v - +33% over the
route-level figure at t_h == t_v. The pointwise integral is additive at ANY granularity, and its
direction asymmetry falls out of the curve rather than a bolted-on rule.

REPORTED DURATION (din_duration_h): DIN 33466 over a whole leg's aggregates. Computed client-side
and NOT stored (spec D3); this implementation exists so the probe can compare the two, and as the
authoritative definition.

The constants are CALIBRATED against DIN on real legs by analysis/routing_probe.py (spec H.4), not
inherited from Tobler. Live values: pipeline.config.json's graph.speedModel.
"""

import numpy as np


def speed_kmh(slope, *, v0: float, k: float, s0: float):
    return v0 * np.exp(-k * np.abs(np.asarray(slope, dtype=np.float64) + s0))


def edge_time_s(dist_m, dz_m, *, v0: float, k: float, s0: float):
    """Seconds per segment. dist_m is horizontal length, dz_m the signed elevation delta."""
    dist_m = np.asarray(dist_m, dtype=np.float64)
    dz_m = np.asarray(dz_m, dtype=np.float64)
    safe = np.where(dist_m > 0, dist_m, 1.0)
    slope = np.where(dist_m > 0, dz_m / safe, 0.0)
    v_ms = speed_kmh(slope, v0=v0, k=k, s0=s0) * (1000.0 / 3600.0)
    return np.where(dist_m > 0, dist_m / v_ms, 0.0)


def technical_time_s(dist_m, dz_m, *, pace_ms: float):
    """Constant pace over 3D distance - via ferrata / T5-T6 terrain isn't walking, and its pace
    isn't primarily a function of horizontal slope the way Tobler assumes."""
    dist_m = np.asarray(dist_m, dtype=np.float64)
    dz_m = np.asarray(dz_m, dtype=np.float64)
    return np.hypot(dist_m, dz_m) / pace_ms


def din_duration_h(distance_m: float, ascent_m: float, descent_m: float) -> float:
    """DIN 33466. NEVER call this with a routing-penalised distance - a road does not take longer
    to walk (spec A3)."""
    t_h = distance_m / 4000.0
    t_v = ascent_m / 300.0 + descent_m / 500.0
    return max(t_h, t_v) + min(t_h, t_v) / 2.0
