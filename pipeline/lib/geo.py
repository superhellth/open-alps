"""Hub-range geometry: extracting the lng/lat points a DEM-tile buffer or trail clip is built
from (hut_points), and the real-world-radius circle/union math
(circle_polygon, hub_range_polygon) that turns those points into a coverage shape - shared by
compute_hub_range.py (filter_trails.py's clip) and dem_providers/composite.py (bavaria-dgm5's
per-hut tile buffer), which must derive the same radius from the same HUB_RANGE_SAFETY_MARGIN or
the two shapes silently drift apart (docs/superpowers/specs/2026-08-22-hub-range-dem-coverage.md)."""

import json
import math

from shapely.geometry import Polygon
from shapely.ops import unary_union


def hut_points(huts_path, filter_bbox=None):
    """Returns every [lng, lat] in huts_path (script 05's output), narrowed to filter_bbox if
    given. huts.geojson holds every hut in the pipeline's whole scope (both Austria and Bavaria),
    so filter_bbox picks out the huts that actually belong to one region (e.g. Bavaria's rough
    state boundary)."""
    with open(huts_path, encoding="utf-8") as f:
        huts_fc = json.load(f)

    points = []
    for feat in huts_fc["features"]:
        lng, lat = feat["geometry"]["coordinates"]
        if filter_bbox is not None and not (
            filter_bbox["minLng"] <= lng <= filter_bbox["maxLng"]
            and filter_bbox["minLat"] <= lat <= filter_bbox["maxLat"]
        ):
            continue
        points.append([lng, lat])

    if not points:
        raise ValueError(f"no huts found inside filter_bbox {filter_bbox} in {huts_path}")
    return points


# Safety margin applied by callers ON TOP OF graph.maxEdgeKm before passing radius_km to
# circle_polygon()/hub_range_polygon() (compute_hub_range.py) and into bavaria-dgm5's per-hut
# tile buffer (dem_providers/composite.py) - the ONE place both sides' radius is derived from, so
# they cannot independently drift the way the old bufferKm/bufferDeg mismatch did
# (docs/superpowers/specs/2026-08-22-hub-range-dem-coverage.md). Covers circle_polygon's
# n_points=32 polygon-approximation shortfall at the flat spots between vertices
# (cos(pi/32) ~= 0.9952, ~0.5% under the true radius there) plus a little headroom - tile-grid
# quantization (bavaria_dgm.tiles_for_utm_bounds) already rounds outward and needs no
# compensation.
HUB_RANGE_SAFETY_MARGIN = 1.01


def circle_polygon(lng: float, lat: float, radius_km: float, n_points: int = 32) -> Polygon:
    """Approximates a real-world radius_km circle around (lng, lat) as an n_points-vertex
    polygon, using per-point local flat-earth trig rather than shapely's Point.buffer() (which
    operates in raw degree space). One degree of longitude is only cos(lat) as many real km as
    one degree of latitude away from the equator, so a naive degree-radius buffer becomes an
    ellipse that UNDER-covers east-west at any latitude away from the equator - exactly the wrong
    direction for a bound meant to be a safe over-approximation. Flat-earth error at
    graph.maxEdgeKm's ~30km scale is negligible, and this is computed per-hut-locally (using that
    hut's own latitude), not from one global scale factor, so it stays accurate everywhere in the
    pipeline's scope."""
    deg_per_km_lat = 1 / 111.320
    deg_per_km_lng = 1 / (111.320 * math.cos(math.radians(lat)))
    ring = [
        (
            lng + radius_km * math.sin(theta) * deg_per_km_lng,
            lat + radius_km * math.cos(theta) * deg_per_km_lat,
        )
        for theta in (2 * math.pi * i / n_points for i in range(n_points))
    ]
    ring.append(ring[0])
    return Polygon(ring)


def hub_range_polygon(huts_path, radius_km: float, n_points: int = 32):
    """Unions a circle_polygon() (real-world radius_km) around every hut in huts_path into one
    (Multi)Polygon - the shape filter_trails.py clips trail extraction to, and (via the same
    radius_km) what bavaria-dgm5's per-hut DEM tile buffer must at least match. Returns a Polygon
    when hut circles overlap enough to merge, a MultiPolygon otherwise - callers must handle
    both (shapely.geometry.mapping() does, transparently)."""
    points = hut_points(huts_path)
    circles = [circle_polygon(lng, lat, radius_km, n_points) for lng, lat in points]
    return unary_union(circles)
