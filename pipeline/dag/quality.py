"""doit task wiring for phases/quality/ - read-only checks over already-persisted pipeline output
(spec docs/superpowers/specs/2026-09-02-data-quality-monitoring-design.md). Non-blocking (§3): no
quality task is a file_dep of copy_public_data, and every check script exits 0 unconditionally -
so wiring these into the default DAG never turns a heuristic threshold into a hard gate."""

from lib.doit_support import cli_param, pipeline_task
from lib.pipeline import DEM_DIR, OSM_DIR, QUALITY_DIR, load_config

CONFIG = load_config()


def _max_flagged_param():
    return cli_param(
        "max_flagged_rows", "max-flagged-rows", int,
        CONFIG.get("quality", {}).get("maxFlaggedRows", 500),
    )


def task_check_preprocessing():
    return pipeline_task(
        "phases/quality/check_preprocessing.py",
        args=[
            f"--start-points {OSM_DIR / 'start_points.npy'}",
            f"--id-table {OSM_DIR / 'start_points_id_table.json'}",
            f"--out {QUALITY_DIR / 'preprocessing.json'}",
        ],
        params=[_max_flagged_param()],
        task_dep=["filter_start_points"],
        file_dep=[OSM_DIR / "start_points.npy", OSM_DIR / "start_points_id_table.json"],
        targets=[QUALITY_DIR / "preprocessing.json"],
    )


def task_check_elevation():
    return pipeline_task(
        "phases/quality/check_elevation.py",
        args=[
            f"--base-graph-dir {OSM_DIR / 'base_graph'}",
            f"--edges-root {OSM_DIR}",
            f"--out {QUALITY_DIR / 'elevation.json'}",
        ],
        params=[_max_flagged_param()],
        # compute_edge_profiles rewrites edges.npy in place; build_profiles rewrites each edge
        # set's records.npy profile_offset/profile_count in place - neither is a declared target
        # of those tasks (see dag/graph_building.py / dag/postprocessing.py's own task_dep
        # comments for the same hazard), so file_dep on node_ele.npy/records.npy alone can't
        # guarantee this check runs after them.
        task_dep=["compute_edge_profiles", "build_profiles"],
        file_dep=[
            OSM_DIR / "base_graph" / "node_ele.npy", OSM_DIR / "base_graph" / "interior_ele.npy",
            OSM_DIR / "base_graph" / "manifest.json",
            OSM_DIR / "hut_edges" / "records.npy", OSM_DIR / "start_edges" / "records.npy",
            OSM_DIR / "tour_edges" / "records.npy",
        ],
        targets=[QUALITY_DIR / "elevation.json"],
    )


def task_check_graph_building():
    return pipeline_task(
        "phases/quality/check_graph_building.py",
        args=[f"--osm-dir {OSM_DIR}", f"--dem-dir {DEM_DIR}", f"--out {QUALITY_DIR / 'graph_building.json'}"],
        params=[
            _max_flagged_param(),
            cli_param("max_edge_km", "max-edge-km", float, CONFIG["graph"]["maxEdgeKm"]),
        ],
        task_dep=["build_hub_edges", "build_access_edges", "match_tour_edges"],
        file_dep=[
            OSM_DIR / "unsnapped_huts.json", OSM_DIR / "huts.geojson",
            OSM_DIR / "hut_edges" / "records.npy", OSM_DIR / "hut_edges" / "geometry.npy",
            OSM_DIR / "start_edges" / "records.npy", OSM_DIR / "start_edges" / "geometry.npy",
            OSM_DIR / "tour_edges" / "records.npy", OSM_DIR / "tour_edges" / "geometry.npy",
            OSM_DIR / "base_graph" / "nodes.npy", OSM_DIR / "base_graph" / "edges.npy",
            OSM_DIR / "base_graph" / "interior.npy", OSM_DIR / "base_graph" / "node_ele.npy",
            OSM_DIR / "tour-match-gaps.json",
        ],
        targets=[QUALITY_DIR / "graph_building.json"],
    )
