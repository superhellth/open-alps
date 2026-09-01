"""HMM-style map matching for one tour leg's corridor (docs/superpowers/specs/
2026-09-01-corridor-hmm-map-matching-design.md). Builds a per-leg leuvenmapmatching InMemMap out
of the corridor subgraph's expanded interior polylines, decodes the leg's resampled GPX trace
against it via Viterbi (DistanceMatcher), and hands the winning node path back to
lib/hmm_reconstruct.py for accumulation into the same fields lib/cell_igraph.py's accumulate_path
produces.

Coordinate order: leuvenmapmatching wants (lat, lon); everything else in this pipeline (GPX
points, EDGE_DTYPE/COORD_DTYPE columns, PathResult) is (lon, lat). The swap happens at exactly two
boundaries in this module - _latlon() below - and nowhere else."""

from lib.geo import haversine_m


def _latlon(lon_lat: tuple) -> tuple:
    """(lon, lat) -> (lat, lon) - the one place this module hands a coordinate to
    leuvenmapmatching."""
    lon, lat = lon_lat
    return (lat, lon)


def _lonlat(lat_lon: tuple) -> tuple:
    """(lat, lon) -> (lon, lat) - the one place this module reads a coordinate back out of
    leuvenmapmatching."""
    lat, lon = lat_lon
    return (lon, lat)


def resample_trace(points: list, resample_m: float) -> list:
    """Decimate-only normalization (spec §3): a run of points closer together than resample_m is
    thinned down to it; a sparse stretch is left alone - no point is ever interpolated into
    existence. Endpoints are always kept exactly. points/return value: [(lon, lat), ...]."""
    if len(points) <= 2:
        return list(points)
    out = [points[0]]
    last = points[0]
    for p in points[1:-1]:
        if haversine_m(last[0], last[1], p[0], p[1]) >= resample_m:
            out.append(p)
            last = p
    out.append(points[-1])
    return out
