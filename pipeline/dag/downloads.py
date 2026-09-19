"""doit task wiring for phases/downloads/ - fetches raw inputs (OSM extracts, hut list, DEM)."""

import json

from lib.doit_support import pipeline_task, tracking_param
from lib.pipeline import HUB_RANGE_DIR, RAW_DEM_DIR, RAW_DIR, RAW_OSM_DIR, load_config

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
            [RAW_OSM_DIR / f"{n}-latest.osm.pbf" for n in REGION_NAMES]
            + [RAW_OSM_DIR / f"{n}.poly" for n in REGION_NAMES]
        ),
    )


def task_fetch_huts():
    return pipeline_task(
        "phases/downloads/fetch_huts.py",
        # Depends on download_extracts.py's .poly outputs (same downloads/ phase, not the usual
        # downloads->preprocessing direction) because the AT+Bavaria coverage filter needs the
        # real admin-boundary polygon Geofabrik ships alongside each extract - see lib/poly.py.
        file_dep=[RAW_OSM_DIR / f"{n}.poly" for n in REGION_NAMES],
        targets=[RAW_DIR / "huts.geojson", RAW_DIR / "partner_betriebe.geojson"],
    )


def task_fetch_stations_parking():
    return pipeline_task(
        "phases/downloads/fetch_stations_parking.py",
        file_dep=[RAW_OSM_DIR / f"{n}-latest.osm.pbf" for n in REGION_NAMES],
        targets=[RAW_DIR / "stations.geojson", RAW_DIR / "parking.geojson"],
    )


def task_fetch_dem():
    return pipeline_task(
        "phases/downloads/fetch_dem.py",
        # config["dem"] (provider name + provider-specific nested config) is read directly by
        # fetch_dem.py - not a sensible CLI flag. The hub range (hub-range.geojson) defines the
        # area to cover; the .poly files clip regions that carry a "boundary".
        file_dep=[HUB_RANGE_DIR / "hub-range.geojson"] + [RAW_OSM_DIR / f"{n}.poly" for n in REGION_NAMES],
        tracking_params=[
            tracking_param("dem_json", str, json.dumps(CONFIG["dem"], sort_keys=True)),
        ],
        targets=[RAW_DEM_DIR / "fetch_manifest.json"],
    )
