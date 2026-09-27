"""doit task wiring for phases/preprocessing/ - filters/merges raw OSM data, computes the hub
range, and verifies the merged trail extract."""

from lib.doit_support import cli_param, pipeline_task
from lib.pipeline import HUB_RANGE_DIR, RAW_DIR, RAW_OSM_DIR, START_POINTS_DIR, TRAILS_DIR, load_config

CONFIG = load_config()
REGION_NAMES = [r["name"] for r in CONFIG["regions"]]


def task_filter_trails():
    return pipeline_task(
        "phases/preprocessing/filter_trails.py",
        params=[cli_param("tag_filter", "tag-filter", str, CONFIG["trailTagFilter"])],
        # hub-range.geojson (compute_hub_range, below) needs huts.geojson first, so this
        # early-in-the-pipeline task depends on a task that itself runs later - a DAG diamond, not
        # a mistake: see compute_hub_range.py's docstring for why the bound is provably safe.
        file_dep=[RAW_OSM_DIR / f"{n}-latest.osm.pbf" for n in REGION_NAMES]
        + [HUB_RANGE_DIR / "hub-range.geojson"],
        targets=[TRAILS_DIR / f"{n}-trails.osm.pbf" for n in REGION_NAMES],
    )


def task_merge_trails():
    return pipeline_task(
        "phases/preprocessing/merge_trails.py",
        file_dep=[TRAILS_DIR / f"{n}-trails.osm.pbf" for n in REGION_NAMES],
        targets=[TRAILS_DIR / "trails.osm.pbf"],
    )


def task_verify_trails():
    # Targets a stamp file (not uptodate:[False]) so an unchanged trails.osm.pbf (content hash)
    # skips the osmium re-scan - the check result isn't cacheable, but "did the input change" is,
    # and file_dep already tracks that regardless of what the task targets.
    return pipeline_task(
        "phases/preprocessing/verify_trails.py",
        file_dep=[TRAILS_DIR / "trails.osm.pbf"],
        targets=[TRAILS_DIR / "verify-trails.stamp"],
    )


def task_compute_hub_range():
    return pipeline_task(
        "phases/preprocessing/compute_hub_range.py",
        params=[cli_param("max_edge_km", "max-edge-km", float, CONFIG["graph"]["maxEdgeKm"])],
        file_dep=[RAW_DIR / "huts.geojson"],
        targets=[HUB_RANGE_DIR / "hub-range.geojson"],
    )


def task_filter_start_points():
    return pipeline_task(
        "phases/preprocessing/filter_start_points.py",
        params=[cli_param("max_edge_km", "max-edge-km", float, CONFIG["graph"]["maxEdgeKm"])],
        file_dep=[
            RAW_DIR / "huts.geojson", RAW_DIR / "stations.geojson",
            RAW_DIR / "parking.geojson", RAW_DIR / "partner_betriebe.geojson",
        ],
        targets=[START_POINTS_DIR / "start-points.npy", START_POINTS_DIR / "start-points-id-table.json"],
    )
