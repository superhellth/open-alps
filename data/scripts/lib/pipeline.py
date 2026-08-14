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


def bbox_from_huts(huts_path, filter_bbox=None, buffer_deg=0.05):
    """Computes a tight {minLng,maxLng,minLat,maxLat} covering every hut in huts_path (script 05's
    output), instead of a hand-picked political-boundary box. huts.geojson holds every hut in the
    pipeline's whole scope (both Austria and Bavaria), so filter_bbox first narrows to the huts
    that actually belong to one region (e.g. Bavaria's rough state boundary) before the tight bbox
    is measured from just those points - without it, every region would get the same
    all-huts bbox. buffer_deg pads the result so DEM coverage doesn't clip right at a hut's
    coordinate; a hut's trail edges (see hut-edges.geojson) extend somewhat past the hut point
    itself, and elevation sampling needs the trail's terrain, not just the endpoint's."""
    with open(huts_path, encoding="utf-8") as f:
        huts_fc = json.load(f)

    lngs, lats = [], []
    for feat in huts_fc["features"]:
        lng, lat = feat["geometry"]["coordinates"]
        if filter_bbox is not None and not (
            filter_bbox["minLng"] <= lng <= filter_bbox["maxLng"]
            and filter_bbox["minLat"] <= lat <= filter_bbox["maxLat"]
        ):
            continue
        lngs.append(lng)
        lats.append(lat)

    if not lngs:
        raise ValueError(f"no huts found inside filter_bbox {filter_bbox} in {huts_path}")

    return {
        "minLng": min(lngs) - buffer_deg,
        "maxLng": max(lngs) + buffer_deg,
        "minLat": min(lats) - buffer_deg,
        "maxLat": max(lats) + buffer_deg,
    }
