"""Mid-chain edge splitting: build_base_graph.py contracts purely structurally (lib/
contraction.py), so a hub may need to snap to a point partway along a chain edge's interior
polyline rather than at an existing graph node. This module finds that point and splits the
edge's dist/weight/road_m proportionally by real (haversine) distance along the polyline - not
by vertex count or naive endpoint interpolation, since interior vertices are real, unevenly
spaced trail points."""

import math
from dataclasses import dataclass


def _haversine_m(lon1, lat1, lon2, lat2):
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_point_on_polyline(polyline: list, point: tuple) -> tuple:
    """polyline: [(lon, lat), ...], >=2 points. Returns (segment_index, fraction in [0,1])
    identifying the closest point to `point` using planar projection - fine at the scale of a
    single chain edge (at most a few km), where lon/lat behaves near-linearly."""
    best = (0, 0.0, float("inf"))
    for i in range(len(polyline) - 1):
        ax, ay = polyline[i]
        bx, by = polyline[i + 1]
        dx, dy = bx - ax, by - ay
        seg_len_sq = dx * dx + dy * dy
        if seg_len_sq == 0:
            t = 0.0
        else:
            t = ((point[0] - ax) * dx + (point[1] - ay) * dy) / seg_len_sq
            t = min(max(t, 0.0), 1.0)
        px, py = ax + t * dx, ay + t * dy
        d = (point[0] - px) ** 2 + (point[1] - py) ** 2
        if d < best[2]:
            best = (i, t, d)
    return best[0], best[1]


@dataclass
class SplitResult:
    split_coord: tuple
    dist_to_u: float
    dist_to_v: float
    weight_to_u: float
    weight_to_v: float
    road_m_to_u: float
    road_m_to_v: float
    interior_to_u: list
    interior_to_v: list


def split_edge_at_point(u_coord, v_coord, interior: list, dist_m: float, weight_m: float,
                         road_m: float, segment_index: int, fraction: float) -> SplitResult:
    full_polyline = [u_coord, *interior, v_coord]
    seg_lengths = [
        _haversine_m(*full_polyline[i], *full_polyline[i + 1])
        for i in range(len(full_polyline) - 1)
    ]
    total = sum(seg_lengths) or 1.0

    ax, ay = full_polyline[segment_index]
    bx, by = full_polyline[segment_index + 1]
    split_coord = (ax + fraction * (bx - ax), ay + fraction * (by - ay))

    dist_to_split = sum(seg_lengths[:segment_index]) + fraction * seg_lengths[segment_index]
    ratio_to_u = dist_to_split / total

    return SplitResult(
        split_coord=split_coord,
        dist_to_u=dist_m * ratio_to_u,
        dist_to_v=dist_m * (1 - ratio_to_u),
        weight_to_u=weight_m * ratio_to_u,
        weight_to_v=weight_m * (1 - ratio_to_u),
        road_m_to_u=road_m * ratio_to_u,
        road_m_to_v=road_m * (1 - ratio_to_u),
        interior_to_u=list(interior[:segment_index]),
        interior_to_v=list(interior[segment_index:]),
    )
