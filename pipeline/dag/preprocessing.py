"""doit task wiring for phases/preprocessing/ - filters/merges raw OSM data, computes the hub
range, and verifies the merged trail extract."""

from lib.doit_support import cli_param, pipeline_task
from lib.pipeline import OSM_DIR, load_config

CONFIG = load_config()
REGION_NAMES = [r["name"] for r in CONFIG["regions"]]


def task_filter_trails():
    return pipeline_task(
        "phases/preprocessing/filter_trails.py",
        params=[cli_param("tag_filter", "tag-filter", str, CONFIG["trailTagFilter"])],
        # hub_range.geojson (compute_hub_range, below) needs huts.geojson first, so this
        # early-in-the-pipeline task depends on a task that itself runs later - a DAG diamond, not
        # a mistake: see compute_hub_range.py's docstring for why the bound is provably safe.
        file_dep=[OSM_DIR / "raw" / f"{n}-latest.osm.pbf" for n in REGION_NAMES]
        + [OSM_DIR / "hub_range.geojson"],
        targets=[OSM_DIR / f"{n}-trails.osm.pbf" for n in REGION_NAMES],
    )


def task_merge_trails():
    return pipeline_task(
        "phases/preprocessing/merge_trails.py",
        file_dep=[OSM_DIR / f"{n}-trails.osm.pbf" for n in REGION_NAMES],
        targets=[OSM_DIR / "trails.osm.pbf"],
    )


def task_verify_trails():
    # Targets a stamp file (not uptodate:[False]) so an unchanged trails.osm.pbf (content hash)
    # skips the osmium re-scan - the check result isn't cacheable, but "did the input change" is,
    # and file_dep already tracks that regardless of what the task targets.
    return pipeline_task(
        "phases/preprocessing/verify_trails.py",
        file_dep=[OSM_DIR / "trails.osm.pbf"],
        targets=[OSM_DIR / "verify_trails.stamp"],
    )


def task_compute_hub_range():
    return pipeline_task(
        "phases/preprocessing/compute_hub_range.py",
        params=[cli_param("max_edge_km", "max-edge-km", float, CONFIG["graph"]["maxEdgeKm"])],
        file_dep=[OSM_DIR / "huts.geojson"],
        targets=[OSM_DIR / "hub_range.geojson"],
    )


def task_filter_start_points():
    return pipeline_task(
        "phases/preprocessing/filter_start_points.py",
        params=[cli_param("max_edge_km", "max-edge-km", float, CONFIG["graph"]["maxEdgeKm"])],
        file_dep=[
            OSM_DIR / "huts.geojson", OSM_DIR / "stations.geojson",
            OSM_DIR / "parking.geojson", OSM_DIR / "partner_betriebe.geojson",
        ],
        targets=[OSM_DIR / "start_points.npy", OSM_DIR / "start_points_id_table.json"],
    )
