"""doit DAG for the OSM hut-graph pipeline.

Setup (inside the alpen-osm conda/pixi env):
    pip install doit

Usage:
    doit list                              # show all tasks + up-to-date status
    doit                                   # run everything, idempotently
    doit build_base_graph                  # run one task + its deps
    doit fetch_huts build_hub_edges        # several tasks
    doit build_hub_edges --max-edge-km 15  # task with its own flag
    doit info build_hub_edges              # show why a task would (not) run, without running it

Task wiring (params, file_dep, targets, uptodate) lives in dag/, one module per phases/
subdirectory (downloads, preprocessing, graph_building, elevation, postprocessing) - this file
just assembles them plus the pipeline-wide finalize step (copy_public_data) and DOIT_CONFIG. The
"how do I track a config value doit can't see, or build an action command line" plumbing lives in
lib/doit_support.py (pipeline_task/cli_param/tracking_param/TaskOptionsChanged) - see that
module's docstring for why TaskOptionsChanged exists at all (two doit bugs, not a style choice).

CLAUDE.md's "never run a pipeline step without asking" rule applies here exactly as it did to the
old run_all.py - `doit <task>` / bare `doit` are pipeline-step invocations.

Rationale that only makes sense at the whole-DAG level (why a task sits where it does, why
something isn't force-rerun) lives as a short comment on that task in its dag/ module, not here -
see pipeline/CLAUDE.md "Keep task-wiring rationale short-lived" for the writing rule this follows.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dag.downloads import (  # noqa: E402,F401
    task_download_extracts, task_fetch_dem, task_fetch_huts, task_fetch_stations_parking,
)
from dag.elevation import (  # noqa: E402,F401
    task_build_dem_vrt, task_build_profiles, task_compute_edge_profiles, task_sample_base_elevation,
)
from dag.graph_building import (  # noqa: E402,F401
    task_build_access_edges, task_build_base_graph, task_build_hub_edges,
    task_gather_route_subgraphs, task_match_tour_edges, task_snap_hubs,
)
from dag.postprocessing import (  # noqa: E402,F401
    task_build_approach_table, task_build_edge_ids, task_build_edge_payload,
    task_build_hut_edge_tiles, task_build_start_edge_ids, task_build_start_edge_tiles,
    task_build_tour_edge_tiles, task_build_trail_tiles,
    task_select_approach_pairs,
)
from dag.preprocessing import (  # noqa: E402,F401
    task_compute_hub_range, task_filter_start_points, task_filter_trails, task_merge_trails,
    task_verify_trails,
)
from dag.quality import (  # noqa: E402,F401
    task_check_elevation, task_check_graph_building, task_check_postprocessing,
    task_check_preprocessing, task_check_tour_matching, task_quality_summary,
)
from lib.doit_support import FlushingReporter, rel  # noqa: E402
from lib.pipeline import (  # noqa: E402
    DATA_DIR, HUT_EDGES_DIR, PUBLIC_DATA_DIR, RAW_DIR, SNAPPING_DIR, START_EDGES_DIR,
    TOUR_EDGES_DIR, TRAILS_DIR,
)
from lib.timing import phase  # noqa: E402

DOIT_CONFIG = {
    # keeps doit's runtime state out of the tracked half of pipeline/, alongside every other
    # generated/gitignored pipeline artifact (see root CLAUDE.md's data/ vs pipeline/ split)
    # .doit.json.db, not the old .doit.db: that file is in dbm format, which the json backend
    # below can't read (doit errors "seems to use an old format"). Starting a fresh cache file is
    # harmless here - see DOIT_CONFIG["backend"]'s comment; none of .doit.db's entries reliably
    # matched the current post-refactor task shapes anyway (fetch_dem/build_dem_vrt had none at
    # all - the mid-run-kill bug this same commit fixes).
    "dep_file": str(DATA_DIR / ".doit.json.db"),
    # 2 = stream both stdout and stderr from the task's action, live. doit's default (1) captures
    # stdout and only replays it if the task fails, which hides the per-unit progress lines this
    # pipeline is required to print (see CLAUDE.md "Progress logging") and makes a multi-hour task
    # look hung. A single task can still opt out with "verbosity" in its own task dict.
    "verbosity": 2,
    # json (not the dbm default) + FlushingReporter: persist each task's success to disk as it
    # happens instead of only once at the end of the whole run - see FlushingReporter's docstring
    # (lib/doit_support.py) for why a mid-run kill was silently discarding already-completed
    # tasks' state, forcing e.g. fetch_dem to rerun even right after it finished.
    "backend": "json",
    "reporter": FlushingReporter,
    "default_tasks": [
        "download_extracts", "fetch_huts",
        "compute_hub_range", "filter_trails",
        "merge_trails", "verify_trails",
        "fetch_stations_parking", "filter_start_points",
        "check_preprocessing",
        "build_base_graph", "fetch_dem", "build_dem_vrt", "sample_base_elevation",
        "compute_edge_profiles", "snap_hubs", "gather_route_subgraphs", "build_hub_edges",
        "select_approach_pairs", "build_access_edges",
        "match_tour_edges", "check_tour_matching",
        "build_profiles",
        "check_graph_building",
        "check_elevation",
        "build_trail_tiles", "build_hut_edge_tiles", "build_start_edge_tiles",
        "build_tour_edge_tiles",
        "build_approach_table", "build_edge_payload", "build_edge_ids", "build_start_edge_ids",
        "copy_public_data",
        "check_postprocessing",
        "quality_summary",
    ],
}

# (source under data/, file name under huts/public/data/) - the public names are the app's
# contract (docs/tour-suggestion-payload.md) and do not follow data/build/'s naming convention.
PUBLIC_FILES = [
    (RAW_DIR / "huts.geojson", "huts.geojson"),
    (HUT_EDGES_DIR / "edges.pmtiles", "hut-edges.pmtiles"),
    (HUT_EDGES_DIR / "stats.json", "hut-edge-stats.json"),
    (HUT_EDGES_DIR / "geometry.bin", "hut-edge-geometry.bin"),
    (HUT_EDGES_DIR / "geometry.json", "hut-edge-geometry.json"),
    (HUT_EDGES_DIR / "elevation.bin", "hut-edge-elevation.bin"),
    (HUT_EDGES_DIR / "elevation.json", "hut-edge-elevation.json"),
    (START_EDGES_DIR / "edges.pmtiles", "start-edges.pmtiles"),
    (START_EDGES_DIR / "geometry.bin", "start-edge-geometry.bin"),
    (START_EDGES_DIR / "geometry.json", "start-edge-geometry.json"),
    (START_EDGES_DIR / "elevation.bin", "start-edge-elevation.bin"),
    (START_EDGES_DIR / "elevation.json", "start-edge-elevation.json"),
    (TRAILS_DIR / "trails.pmtiles", "trails.pmtiles"),
    (RAW_DIR / "stations.geojson", "stations.geojson"),
    (RAW_DIR / "parking.geojson", "parking.geojson"),
    (SNAPPING_DIR / "unsnapped-huts.json", "unsnapped_huts.json"),
    (START_EDGES_DIR / "approaches.bin", "approaches.bin"),
    (START_EDGES_DIR / "approaches.json", "approaches.json"),
    (HUT_EDGES_DIR / "payload.bin", "hut-edge-payload.bin"),
    (HUT_EDGES_DIR / "payload.json", "hut-edge-payload.json"),
    (HUT_EDGES_DIR / "ids.bin", "hut-edge-ids.bin"),
    (HUT_EDGES_DIR / "ids.json", "hut-edge-ids.json"),
    (START_EDGES_DIR / "ids.bin", "start-edge-ids.bin"),
    (START_EDGES_DIR / "ids.json", "start-edge-ids.json"),
    (RAW_DIR / "partner_betriebe.geojson", "partner_betriebe.geojson"),
    (TOUR_EDGES_DIR / "tours.json", "tours.json"),
    (TOUR_EDGES_DIR / "edges.pmtiles", "tour-edges.pmtiles"),
    (TOUR_EDGES_DIR / "stats.json", "tour-edge-stats.json"),
    (TOUR_EDGES_DIR / "geometry.bin", "tour-edge-geometry.bin"),
    (TOUR_EDGES_DIR / "geometry.json", "tour-edge-geometry.json"),
    (TOUR_EDGES_DIR / "elevation.bin", "tour-edge-elevation.bin"),
    (TOUR_EDGES_DIR / "elevation.json", "tour-edge-elevation.json"),
]


# ---- copy outputs into huts/public/data ------------------------------------
# Whole-pipeline finalize step, not one phase's output - stays here rather than in dag/
# postprocessing.py.

def task_copy_public_data():
    def copy_all():
        import shutil

        with phase("dodo.py", "copy_public_data"):
            PUBLIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
            for src, name in PUBLIC_FILES:
                if not src.exists():
                    print(f"  skip {name} (not built yet)")
                    continue
                shutil.copy2(src, PUBLIC_DATA_DIR / name)
                print(f"  {src} -> {PUBLIC_DATA_DIR / name}")

    deps = [rel(src) for src, _ in PUBLIC_FILES if src.exists()] or [
        rel(src) for src, _ in PUBLIC_FILES
    ]
    return {
        "actions": [copy_all],
        "file_dep": deps,
        "targets": [rel(PUBLIC_DATA_DIR / name) for _, name in PUBLIC_FILES],
    }
