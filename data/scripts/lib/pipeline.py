"""Single config reader shared by every pipeline script, so pipeline.config.json is the
one source of truth for hyperparameters (bbox, regions, tag filter, graph thresholds)."""

import json
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = SCRIPTS_DIR.parent
OSM_DIR = DATA_DIR / "osm"
DEM_DIR = DATA_DIR / "dem"
CONFIG_PATH = DATA_DIR / "pipeline.config.json"


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


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


def edge_points(edges_path, filter_bbox=None):
    """Returns every trail-polyline vertex [lng, lat] in edges_path (script 06's hut-edges.geojson
    output), narrowed to filter_bbox if given. Vertices trace the actual trail geometry between
    huts, not just the hut endpoints - this is exactly what 08-add-elevation.py samples, so a
    DEM-tile selection built from these points needs no separate assumption about how far a trail
    can wander from its endpoints (see bufferKm in bavaria_dgm.py's tiles_for_points - no longer
    needs to be sized off graph.maxEdgeKm)."""
    with open(edges_path, encoding="utf-8") as f:
        edges_fc = json.load(f)

    points = []
    for feat in edges_fc["features"]:
        for lng, lat in feat["geometry"]["coordinates"]:
            if filter_bbox is not None and not (
                filter_bbox["minLng"] <= lng <= filter_bbox["maxLng"]
                and filter_bbox["minLat"] <= lat <= filter_bbox["maxLat"]
            ):
                continue
            points.append([lng, lat])

    if not points:
        raise ValueError(f"no edge vertices found inside filter_bbox {filter_bbox} in {edges_path}")
    return points


def bbox_from_huts(huts_path, filter_bbox=None, buffer_deg=0.05):
    """Computes a tight {minLng,maxLng,minLat,maxLat} covering every hut in huts_path, instead of
    a hand-picked political-boundary box. buffer_deg pads the result so DEM coverage doesn't clip
    right at a hut's coordinate; a hut's trail edges (see hut-edges.geojson) extend somewhat past
    the hut point itself, and elevation sampling needs the trail's terrain, not just the
    endpoint's.

    Huts scattered across a wide area (e.g. Bavaria's alpine-fringe cluster plus a few outlying
    non-alpine AV huts up near the Bavarian Forest) make this a poor shape for a per-tile DEM
    fetch: the enclosing rectangle balloons to cover empty terrain between clusters. Callers doing
    a tile-per-request fetch (bavaria_dgm.py) should use hut_points() + a per-point buffer instead
    - this bbox is for providers that only need a coarse fetch extent (e.g. a single bulk
    download)."""
    points = hut_points(huts_path, filter_bbox)
    lngs = [p[0] for p in points]
    lats = [p[1] for p in points]

    return {
        "minLng": min(lngs) - buffer_deg,
        "maxLng": max(lngs) + buffer_deg,
        "minLat": min(lats) - buffer_deg,
        "maxLat": max(lats) + buffer_deg,
    }
