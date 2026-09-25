"""Anchor points on an edge's real path, shipped so the client can stand a tour's signpost on its
route without loading geometry. An anchor sits at a fixed fraction of the edge's arc length,
measured on the full-resolution polyline. Each anchor ships as an i2 offset, in 1e-4 degree units,
from a reference coordinate (the hut coordinate as shipped in huts.geojson), one column per axis
and fraction (docs/tour-suggestion-payload.md §1)."""

import numpy as np

from lib.geo import haversine_m_vec_pairs

ANCHOR_FRACTIONS = (0.25, 0.5, 0.75)
ANCHOR_UNIT_DEG = 1e-4
_I2_MAX = 32767
_M_PER_DEG = 111_320.0


def anchor_column_names(fractions=ANCHOR_FRACTIONS) -> list:
    return [f"a{int(round(f * 100))}_{axis}" for f in fractions for axis in ("dlat", "dlng")]


def points_at_fractions(lons, lats, fractions=ANCHOR_FRACTIONS) -> np.ndarray:
    """Points at the given fractions of the polyline's haversine arc length, linearly interpolated
    inside the segment that crosses each target. Returns (k, 2) of lon, lat."""
    lons = np.asarray(lons, dtype=np.float64)
    lats = np.asarray(lats, dtype=np.float64)
    if len(lons) == 0:
        raise ValueError("cannot place anchors on an empty polyline")
    k = len(fractions)
    if len(lons) == 1:
        return np.tile([lons[0], lats[0]], (k, 1))
    seg = haversine_m_vec_pairs(lons[:-1], lats[:-1], lons[1:], lats[1:])
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = cum[-1]
    if total == 0:
        return np.tile([lons[0], lats[0]], (k, 1))
    targets = np.asarray(fractions, dtype=np.float64) * total
    idx = np.clip(np.searchsorted(cum, targets, side="right") - 1, 0, len(seg) - 1)
    seg_len = seg[idx]
    t = np.divide(targets - cum[idx], seg_len, out=np.zeros_like(targets), where=seg_len > 0)
    lon = lons[idx] + t * (lons[idx + 1] - lons[idx])
    lat = lats[idx] + t * (lats[idx + 1] - lats[idx])
    return np.column_stack([lon, lat])


def quantise_offsets(points_lonlat, ref_lonlat) -> tuple:
    """(dlat, dlng) i2 arrays of each point's offset from ref, in ANCHOR_UNIT_DEG units."""
    d = np.rint((np.asarray(points_lonlat) - np.asarray(ref_lonlat)) / ANCHOR_UNIT_DEG)
    if np.abs(d).max() > _I2_MAX:
        raise ValueError(f"anchor offset {np.abs(d).max():.0f} units overflows i2 (max {_I2_MAX})")
    return d[:, 1].astype("i2"), d[:, 0].astype("i2")


def decode_offsets(ref_lonlat, dlat, dlng) -> np.ndarray:
    ref = np.asarray(ref_lonlat, dtype=np.float64)
    return np.column_stack([
        ref[0] + np.asarray(dlng, dtype=np.float64) * ANCHOR_UNIT_DEG,
        ref[1] + np.asarray(dlat, dtype=np.float64) * ANCHOR_UNIT_DEG,
    ])


def edge_anchor_columns(records, geometry, row_ids, ref_lonlat, fractions=ANCHOR_FRACTIONS) -> dict:
    """Anchor columns (i2, one entry per row in `row_ids`) for the edges `records[row_ids]`, cut from
    their slices of `geometry`. `ref_lonlat` is (n, 2), aligned with `row_ids`."""
    n = len(row_ids)
    columns = {name: np.zeros(n, dtype="i2") for name in anchor_column_names(fractions)}
    for i, row in enumerate(row_ids):
        offset, count = int(records[row]["geom_offset"]), int(records[row]["geom_count"])
        piece = geometry[offset:offset + count]
        points = points_at_fractions(piece["lon"], piece["lat"], fractions)
        dlat, dlng = quantise_offsets(points, ref_lonlat[i])
        for k, f in enumerate(fractions):
            key = int(round(f * 100))
            columns[f"a{key}_dlat"][i] = dlat[k]
            columns[f"a{key}_dlng"][i] = dlng[k]
    return columns


def decode_row(columns, i, ref_lonlat, fractions=ANCHOR_FRACTIONS) -> np.ndarray:
    """(k, 2) lon, lat of row i's anchors from unpacked columns."""
    dlat = [columns[f"a{int(round(f * 100))}_dlat"][i] for f in fractions]
    dlng = [columns[f"a{int(round(f * 100))}_dlng"][i] for f in fractions]
    return decode_offsets(ref_lonlat, dlat, dlng)


def distance_to_polyline_m(lon, lat, poly_lonlat) -> float:
    """Minimum distance in metres from a point to a lon/lat polyline (local equirectangular)."""
    poly = np.asarray(poly_lonlat, dtype=np.float64)
    kx = _M_PER_DEG * np.cos(np.radians(lat))
    xy = np.column_stack([(poly[:, 0] - lon) * kx, (poly[:, 1] - lat) * _M_PER_DEG])
    if len(xy) == 1:
        return float(np.hypot(*xy[0]))
    a, ab = xy[:-1], xy[1:] - xy[:-1]
    len2 = (ab ** 2).sum(axis=1)
    t = np.divide(-(a * ab).sum(axis=1), len2, out=np.zeros_like(len2), where=len2 > 0)
    closest = a + np.clip(t, 0.0, 1.0)[:, None] * ab
    return float(np.hypot(closest[:, 0], closest[:, 1]).min())
