"""doit task wiring for phases/downloads/ - fetches raw inputs (OSM extracts, hut list, DEM)."""

import json

from lib.doit_support import cli_param, pipeline_task, tracking_param
from lib.pipeline import DEM_DIR, OSM_DIR, load_config

CONFIG = load_config()
REGION_NAMES = [r["name"] for r in CONFIG["regions"]]


def task_download_extracts():
    return pipeline_task(
        "phases/downloads/download_extracts.py",
        # download_extracts.py reads config["regions"] directly (a list of {name, url}, not a
        # sensible CLI flag) - tracked so an edited/added region still triggers a re-download.
        tracking_params=[
            tracking_param("regions_json", str, json.dumps(CONFIG["regions"], sort_keys=True)),
        ],
        targets=[OSM_DIR / "raw" / f"{n}-latest.osm.pbf" for n in REGION_NAMES],
    )


def task_fetch_huts():
    return pipeline_task(
        "phases/downloads/fetch_huts.py",
        # fetch_huts.py reads config["bbox"] directly (a dict, not a sensible CLI flag).
        tracking_params=[
            tracking_param("bbox_json", str, json.dumps(CONFIG["bbox"], sort_keys=True)),
        ],
        targets=[OSM_DIR / "huts.geojson", OSM_DIR / "partner_betriebe.geojson"],
    )


def task_fetch_tours():
    return pipeline_task(
        "phases/downloads/fetch_tours.py",
        # fetch_tours.py resolves Huettenliste GUIDs against huts.geojson's own feature-array
        # position - unlike fetch_huts.py's plain network fetch, a huts refetch that reorders or
        # re-filters huts silently invalidates every hutIndices entry, so this must be a real
        # file_dep, not just a tracked param.
        tracking_params=[
            tracking_param("bbox_json", str, json.dumps(CONFIG["bbox"], sort_keys=True)),
        ],
        file_dep=[OSM_DIR / "huts.geojson"],
        targets=[
            OSM_DIR / "tours.json", OSM_DIR / "tour_traces.json", OSM_DIR / "tour-fetch-gaps.json",
        ],
    )


def task_fetch_tour_oa_geometry():
    # Downstream of fetch_tours.py's oaId resolution - task_dep (not just file_dep on tours.json)
    # because a re-run with the SAME tours.json content but a code change to oa_ids_by_tour's
    # regex should still refetch, and doit's file_dep freshness check alone wouldn't catch that.
    return pipeline_task(
        "phases/downloads/fetch_tour_oa_geometry.py",
        task_dep=["fetch_tours"],
        file_dep=[OSM_DIR / "tours.json"],
        targets=[OSM_DIR / "tour_oa_traces.json"],
    )


def task_fetch_stations_parking():
    return pipeline_task(
        "phases/downloads/fetch_stations_parking.py",
        file_dep=[OSM_DIR / "raw" / f"{n}-latest.osm.pbf" for n in REGION_NAMES],
        targets=[OSM_DIR / "stations.geojson", OSM_DIR / "parking.geojson"],
    )


def task_fetch_dem():
    return pipeline_task(
        "phases/downloads/fetch_dem.py",
        # dem/bbox: config["dem"] (provider name + provider-specific nested config) and
        # config["bbox"] are read directly by fetch_dem.py - neither is a sensible CLI flag.
        # max_edge_km IS a real flag: it sizes bavaria-dgm5's per-hut buffer (composite.py's
        # fetch_regions), so it must invalidate this task too, not just the trail/hub-range tasks.
        params=[cli_param("max_edge_km", "max-edge-km", float, CONFIG["graph"]["maxEdgeKm"])],
        tracking_params=[
            tracking_param("dem_json", str, json.dumps(CONFIG["dem"], sort_keys=True)),
            tracking_param("bbox_json", str, json.dumps(CONFIG["bbox"], sort_keys=True)),
        ],
        targets=[DEM_DIR / "fetch_manifest.json"],
    )
