"""doit task wiring for phases/downloads/ - fetches raw inputs (OSM extracts, hut list, DEM)."""

import json

from lib.doit_support import cli_param, pipeline_task, tracking_param
from lib.pipeline import DEM_DIR, OSM_DIR, load_config

CONFIG = load_config()
REGION_NAMES = [r["name"] for r in CONFIG["regions"]]


def task_download_extracts():
    return pipeline_task(
        "phases/downloads/download_extracts.py",
        # download_extracts.py reads config["regions"] directly (a list of {name, url, polyUrl},
        # not a sensible CLI flag) - tracked so an edited/added region still triggers a re-download.
        tracking_params=[
            tracking_param("regions_json", str, json.dumps(CONFIG["regions"], sort_keys=True)),
        ],
        targets=(
            [OSM_DIR / "raw" / f"{n}-latest.osm.pbf" for n in REGION_NAMES]
            + [OSM_DIR / "raw" / f"{n}.poly" for n in REGION_NAMES]
        ),
    )


def task_fetch_huts():
    return pipeline_task(
        "phases/downloads/fetch_huts.py",
        # Depends on download_extracts.py's .poly outputs (same downloads/ phase, not the usual
        # downloads->preprocessing direction) because the AT+Bavaria coverage filter needs the
        # real admin-boundary polygon Geofabrik ships alongside each extract - see lib/poly.py.
        file_dep=[OSM_DIR / "raw" / f"{n}.poly" for n in REGION_NAMES],
        targets=[OSM_DIR / "huts.geojson", OSM_DIR / "partner_betriebe.geojson"],
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
