"""Shortest approach duration per hut from the app's approaches.bin/.json outputs."""
from __future__ import annotations

import numpy as np


def din_minutes(distance_m: float, ascent_m: float, descent_m: float) -> float:
    """DIN 33466 duration in minutes (same formula as pipeline/lib/speed.py din_duration_h)."""
    t_h = distance_m / 4000.0
    t_v = ascent_m / 300.0 + descent_m / 500.0
    return (max(t_h, t_v) + min(t_h, t_v) / 2.0) * 60.0


def _col(manifest: dict, blob: bytes, name: str) -> np.ndarray:
    c = manifest["columns"][name]
    return np.frombuffer(blob, dtype="<" + c["dtype"], count=manifest["rows"], offset=c["offset"])


def approach_minutes(manifest: dict, blob: bytes, hut_ids: list[str]) -> dict[str, float]:
    """Upper-case hut GUID -> minimum approach minutes over all its approach rows."""
    hut = _col(manifest, blob, "hut_id")
    dist = _col(manifest, blob, "distance_m").astype(float)
    asc = _col(manifest, blob, "ascent_m").astype(float)
    desc = _col(manifest, blob, "descent_m").astype(float)
    t_h = dist / 4000.0
    t_v = asc / 300.0 + desc / 500.0
    minutes = (np.maximum(t_h, t_v) + np.minimum(t_h, t_v) / 2.0) * 60.0
    out: dict[str, float] = {}
    for idx, m in zip(hut.tolist(), minutes.tolist()):
        g = hut_ids[idx].upper()
        out[g] = min(m, out.get(g, m))
    return out
