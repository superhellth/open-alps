"""doit task wiring for phases/quality/ - read-only checks over already-persisted pipeline output
(spec docs/superpowers/specs/2026-09-02-data-quality-monitoring-design.md). Non-blocking (§3): no
quality task is a file_dep of copy_public_data, and every check script exits 0 unconditionally -
so wiring these into the default DAG never turns a heuristic threshold into a hard gate."""

from lib.doit_support import cli_param, pipeline_task
from lib.pipeline import (
    BASE_GRAPH_DIR, BUILD_DIR, HUT_EDGES_DIR, QUALITY_DIR, RAW_DEM_DIR, RAW_DIR, RAW_OSM_DIR, SNAPPING_DIR,
    START_EDGES_DIR, START_POINTS_DIR, load_config,
)

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
            f"--start-points {START_POINTS_DIR / 'start-points.npy'}",
            f"--id-table {START_POINTS_DIR / 'start-points-id-table.json'}",
            f"--out {QUALITY_DIR / 'preprocessing.json'}",
        ],
        params=[_max_flagged_param()],
        task_dep=["filter_start_points"],
        file_dep=[START_POINTS_DIR / "start-points.npy", START_POINTS_DIR / "start-points-id-table.json"]
        + [RAW_DIR / f"{layer}.geojson" for layer in ("huts", "stations", "parking", "partner_betriebe")]
        + [RAW_OSM_DIR / f"{r['name']}.poly" for r in CONFIG["regions"]],
        targets=[QUALITY_DIR / "preprocessing.json"],
    )


def task_check_elevation():
    return pipeline_task(
        "phases/quality/check_elevation.py",
        args=[
            f"--base-graph-dir {BASE_GRAPH_DIR}",
            f"--build-dir {BUILD_DIR}",
            f"--out {QUALITY_DIR / 'elevation.json'}",
        ],
        params=[_max_flagged_param()],
        # compute_edge_profiles rewrites edges.npy in place; build_profiles rewrites each edge
        # set's records.npy profile_offset/profile_count in place - neither is a declared target
        # of those tasks (see dag/graph_building.py / dag/postprocessing.py's own task_dep
        # comments for the same hazard), so file_dep on node-ele.npy/records.npy alone can't
        # guarantee this check runs after them.
        task_dep=["compute_edge_profiles", "build_profiles"],
        file_dep=[
            BASE_GRAPH_DIR / "node-ele.npy", BASE_GRAPH_DIR / "interior-ele.npy",
            BASE_GRAPH_DIR / "manifest.json",
            HUT_EDGES_DIR / "records.npy", START_EDGES_DIR / "records.npy",
        ],
        targets=[QUALITY_DIR / "elevation.json"],
    )


def task_check_graph_building():
    return pipeline_task(
        "phases/quality/check_graph_building.py",
        args=[f"--raw-dir {RAW_DIR}", f"--build-dir {BUILD_DIR}", f"--dem-dir {RAW_DEM_DIR}",
              f"--out {QUALITY_DIR / 'graph_building.json'}"],
        params=[
            _max_flagged_param(),
            cli_param("max_edge_km", "max-edge-km", float, CONFIG["graph"]["maxEdgeKm"]),
        ],
        # build_profiles rewrites each edge set's records.npy profile_offset/profile_count in
        # place, which isn't a declared target of that task (see task_check_elevation's identical
        # comment) - file_dep on records.npy alone can't guarantee this check runs after it.
        task_dep=["build_hub_edges", "build_access_edges", "build_profiles"],
        file_dep=[
            SNAPPING_DIR / "unsnapped-huts.json", RAW_DIR / "huts.geojson",
            HUT_EDGES_DIR / "records.npy", HUT_EDGES_DIR / "geometry.npy",
            START_EDGES_DIR / "records.npy", START_EDGES_DIR / "geometry.npy",
            BASE_GRAPH_DIR / "nodes.npy", BASE_GRAPH_DIR / "edges.npy",
            BASE_GRAPH_DIR / "interior.npy", BASE_GRAPH_DIR / "node-ele.npy",
        ],
        targets=[QUALITY_DIR / "graph_building.json"],
    )


def task_check_postprocessing():
    return pipeline_task(
        "phases/quality/check_postprocessing.py",
        args=[f"--raw-dir {RAW_DIR}", f"--build-dir {BUILD_DIR}",
              f"--out {QUALITY_DIR / 'postprocessing.json'}"],
        params=[_max_flagged_param()],
        # check_postprocessing.py reads huts/public/data/ for the freshness check (§4.4.4), so it
        # must run AFTER copy_public_data even though it's never a file_dep OF it (spec §3's
        # non-blocking rule is about the reverse direction only - copy_public_data must not wait
        # on quality output, but quality output reading the copy is fine and in fact the point).
        task_dep=[
            "build_approach_table", "build_edge_payload",
            "build_hut_edge_tiles", "build_start_edge_tiles",
            "copy_public_data",
        ],
        file_dep=[
            RAW_DIR / "huts.geojson", START_EDGES_DIR / "records.npy",
            START_POINTS_DIR / "start-points-id-table.json",
            START_EDGES_DIR / "approaches.bin", START_EDGES_DIR / "approaches.json",
            HUT_EDGES_DIR / "payload.json", HUT_EDGES_DIR / "geometry.json",
            HUT_EDGES_DIR / "geometry.bin",
            START_EDGES_DIR / "geometry.json", START_EDGES_DIR / "geometry.bin",
            HUT_EDGES_DIR / "payload.bin", HUT_EDGES_DIR / "records.npy",
            HUT_EDGES_DIR / "geometry.npy", START_EDGES_DIR / "geometry.npy",
        ],
        targets=[QUALITY_DIR / "postprocessing.json"],
    )


def task_quality_summary():
    return pipeline_task(
        "phases/quality/summarize.py",
        args=[f"--quality-dir {QUALITY_DIR}", f"--out {QUALITY_DIR / 'summary.json'}"],
        task_dep=[
            "check_preprocessing", "check_elevation", "check_graph_building",
            "check_postprocessing",
        ],
        file_dep=[
            QUALITY_DIR / "preprocessing.json", QUALITY_DIR / "elevation.json",
            QUALITY_DIR / "graph_building.json",
            QUALITY_DIR / "postprocessing.json",
        ],
        targets=[QUALITY_DIR / "summary.json"],
    )
