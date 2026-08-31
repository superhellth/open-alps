"""Mid-chain edge splitting: build_base_graph.py contracts purely structurally (lib/
contraction.py), so a hub may need to snap to a point partway along a chain edge's interior
polyline rather than at an existing graph node. This module finds that point and splits the
edge's dist/road_m/ungraded_m/inferred_m proportionally by real (haversine) distance along the
polyline - not by vertex count or naive endpoint interpolation, since interior vertices are real,
unevenly spaced trail points."""

from dataclasses import dataclass

from lib.geo import haversine_m as _haversine_m


def nearest_point_on_polyline(polyline: list, point: tuple, lng_scale: float = 1.0) -> tuple:
    """polyline: [(lon, lat), ...], >=2 points. Returns (segment_index, fraction in [0,1])
    identifying the closest point to `point`, using a locally-flat projection where longitude
    distances are scaled by `lng_scale` (pass cos(radians(reference_latitude)) so degrees of
    longitude and latitude compare in real-world proportion - see hub_snap.py's _project_m for
    the same correction applied elsewhere in the snapping path). Defaults to 1.0 (no correction)
    for callers that intentionally want raw degree-space comparison."""
    best = (0, 0.0, float("inf"))
    for i in range(len(polyline) - 1):
        ax, ay = polyline[i]
        bx, by = polyline[i + 1]
        dx, dy = (bx - ax) * lng_scale, by - ay
        seg_len_sq = dx * dx + dy * dy
        if seg_len_sq == 0:
            t = 0.0
        else:
            t = ((point[0] - ax) * lng_scale * dx + (point[1] - ay) * dy) / seg_len_sq
            t = min(max(t, 0.0), 1.0)
        px, py = ax + t * (bx - ax), ay + t * dy
        d = ((point[0] - px) * lng_scale) ** 2 + (point[1] - py) ** 2
        if d < best[2]:
            best = (i, t, d)
    return best[0], best[1]


@dataclass
class SplitResult:
    split_coord: tuple
    dist_to_u: float
    dist_to_v: float
    road_m_to_u: float
    road_m_to_v: float
    ungraded_m_to_u: float
    ungraded_m_to_v: float
    inferred_m_to_u: float
    inferred_m_to_v: float
    interior_to_u: list
    interior_to_v: list


def split_edge_at_point(u_coord, v_coord, interior: list, dist_m: float, road_m: float,
                         ungraded_m: float, inferred_m: float, segment_index: int,
                         frac: float) -> SplitResult:
    full_polyline = [u_coord, *interior, v_coord]
    seg_lengths = [
        _haversine_m(*full_polyline[i], *full_polyline[i + 1])
        for i in range(len(full_polyline) - 1)
    ]
    total = sum(seg_lengths) or 1.0

    ax, ay = full_polyline[segment_index]
    bx, by = full_polyline[segment_index + 1]
    split_coord = (ax + frac * (bx - ax), ay + frac * (by - ay))

    dist_to_split = sum(seg_lengths[:segment_index]) + frac * seg_lengths[segment_index]
    ratio_to_u = dist_to_split / total

    return SplitResult(
        split_coord=split_coord,
        dist_to_u=dist_m * ratio_to_u,
        dist_to_v=dist_m * (1 - ratio_to_u),
        road_m_to_u=road_m * ratio_to_u,
        road_m_to_v=road_m * (1 - ratio_to_u),
        ungraded_m_to_u=ungraded_m * ratio_to_u,
        ungraded_m_to_v=ungraded_m * (1 - ratio_to_u),
        inferred_m_to_u=inferred_m * ratio_to_u,
        inferred_m_to_v=inferred_m * (1 - ratio_to_u),
        interior_to_u=list(interior[:segment_index]),
        interior_to_v=list(interior[segment_index:]),
    )
