"""
doit DAG for the OSM hut-graph pipeline (replaces run_all.py).

Setup (inside the alpen-osm conda env):
    pip install doit

Usage:
    doit list                              # show all tasks + up-to-date status
    doit                                   # run everything, idempotently (like old run_all.py)
    doit build_base_graph                  # run one task + its deps
    doit fetch_huts build_hub_edges        # several tasks
    doit build_hub_edges --max-edge-km 15  # task with its own flag
    doit info build_hub_edges              # show why a task would (not) run, without running it

A task always reruns if any file in its file_dep changed (content hash, not mtime - doit hashes
by default) or if the specific pipeline.config.json values it reads changed - each task pulls
those into "params" (CLI flags defaulted from CONFIG) and tracks them with TaskOptionsChanged,
never depends on the whole config file's bytes, so an edit to an unrelated key doesn't invalidate
every task downstream of it (unlike run_all.py's old global config-mtime check). verify_trails has
no target (it's a gate, not a cacheable output) and declares `uptodate: [False]` to force a rerun
every time it's selected.
build_profiles does too - it never reads the DEM (spec B4) and is usually run precisely to retune
--profile-points, so a fresh run is always cheap (seconds). build_base_graph/build_hub_edges/
sample_base_elevation/compute_edge_profiles are NOT force-rerun despite compute_edge_profiles
looking similarly cheap-to-retune - their predecessor build_hut_graph.py was measured at ~4.1
hours (data/timings.jsonl, 2026-08-15), and sample_base_elevation genuinely reads the whole DEM
and compute_edge_profiles re-routes every base edge - so they're freshness-checked normally, each
with a TaskOptionsChanged uptodate check on its own params so passing a different flag still
reruns it without needing `doit forget` first (see the docstrings above those tasks and
TaskOptionsChanged's own docstring below).

CLAUDE.md's "never run a pipeline step without asking" rule applies here exactly as it did to
run_all.py - `doit <task>` / bare `doit` are pipeline-step invocations.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.pipeline import DATA_DIR, DEM_DIR, OSM_DIR, PUBLIC_DATA_DIR, load_config  # noqa: E402


class TaskOptionsChanged:
    """uptodate check: rerun a task if its own resolved param values (task.options - the CLI
    flags/defaults doit already parsed for it, e.g. --tile-size-km) changed since its last
    successful run. This is what `config_changed(json.dumps(task.options, sort_keys=True))`
    is meant to do, but doit only registers the "persist this digest after success" hook
    (Task._init_uptodate, doit/task.py) for uptodate items that expose a `configure_task`
    method - a bare `config_changed(...)` instance has one, but wrapping it in
    `lambda task, values: config_changed(...)(task, values)` hides it behind a plain lambda,
    so the digest never gets saved and the task shows "not up to date" on every single future
    run, forever, even immediately after a clean success. That silently defeated caching for
    build_base_graph/build_hub_edges/compute_edge_profiles (add_base_elevation at the time this
    was fixed, later split into sample_base_elevation + compute_edge_profiles) - among the tasks
    this pipeline most needs NOT to rerun by accident (see this module's docstring).

    Second, unrelated bug this class works around: doit only calls Task.init_options() (which
    populates task.options from parsed CLI flags/defaults - see doit/task.py) for tasks named
    directly in the command-line selection (TaskControl._process_filter, doit/control.py). A
    task reached only transitively, as someone else's file_dep/task_dep - e.g. download_extracts
    when you run `doit build_base_graph` - never gets init_options() called, so task.options
    stays None. json.dumps(None) ('null') then never matches the saved digest, so __call__ below
    would return False unconditionally, forcing a full rerun of every upstream task not named on
    the command line, every time - defeating the cache exactly for the deep, expensive tasks
    (downloads, merges) that most need it. init_options() is idempotent (task.py: only acts
    `if self.options is None`), so calling it here is a safe way to guarantee options are
    populated before comparing, regardless of whether doit already did it.

    Note this only applies to tasks with real params (compute_edge_profiles, build_base_graph,
    build_hub_edges) - sample_base_elevation has none, so it doesn't need this at all."""

    def configure_task(self, task):
        task.value_savers.append(
            lambda: {"_task_options": json.dumps(task.options, sort_keys=True)}
        )

    def __call__(self, task, values):
        task.init_options()
        return values.get("_task_options") == json.dumps(task.options, sort_keys=True)

DOIT_CONFIG = {
    # keeps doit's runtime state out of the tracked half of pipeline/, alongside every other
    # generated/gitignored pipeline artifact (see root CLAUDE.md's data/ vs pipeline/ split)
    "dep_file": str(DATA_DIR / ".doit.db"),
    # 2 = stream both stdout and stderr from the task's action, live. doit's default (1) captures
    # stdout and only replays it if the task fails, which hides the per-unit progress lines this
    # pipeline is required to print (see CLAUDE.md "Progress logging") and makes a multi-hour task
    # look hung. A single task can still opt out with "verbosity" in its own task dict.
    "verbosity": 2,
    "default_tasks": [
        "download_extracts", "fetch_huts", "compute_hub_range", "filter_trails",
        "merge_trails", "verify_trails",
        "fetch_stations_parking", "filter_start_points",
        "build_base_graph", "fetch_dem", "build_dem_vrt", "sample_base_elevation",
        "compute_edge_profiles", "build_hub_edges", "build_profiles",
        "build_trail_tiles", "build_hut_edge_tiles", "build_start_edge_tiles",
        "build_approach_table",
        "copy_public_data",
    ],
}

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG = load_config()
REGION_NAMES = [r["name"] for r in CONFIG["regions"]]

PUBLIC_FILES = [
    "huts.geojson",
    "hut-edges.pmtiles",
    "hut-edge-stats.json",
    "start-edges.pmtiles",
    "start-edge-stats.json",
    "trails.pmtiles",
    "stations.geojson",
    "parking.geojson",
    "unsnapped_huts.json",
    "approaches.bin",
    "approaches.json",
]


def py(script, *args):
    parts = [f'"{sys.executable}"', f'"{SCRIPT_DIR / script}"', *[str(a) for a in args]]
    return " ".join(parts)


# ---- 01: download extracts -------------------------------------------------

def task_download_extracts():
    return {
        "actions": [py("phases/downloads/download_extracts.py")],
        # download_extracts.py reads config["regions"] directly (a list of {name, url} - not a
        # sensible CLI flag), so this param exists only to track it via TaskOptionsChanged
        # instead of the whole pipeline.config.json file - keep the key path here in sync with
        # what the script actually reads.
        "params": [
            {"name": "regions_json", "long": "regions-json", "type": str,
             "default": json.dumps(CONFIG["regions"], sort_keys=True)},
        ],
        "targets": [str(OSM_DIR / "raw" / f"{n}-latest.osm.pbf") for n in REGION_NAMES],
        "uptodate": [TaskOptionsChanged()],
    }


# ---- 02: filter trails per region ------------------------------------------

def task_filter_trails():
    return {
        "actions": [
            f'"{sys.executable}" "{SCRIPT_DIR / "phases" / "preprocessing" / "filter_trails.py"}"'
            " --tag-filter %(tag_filter)s"
        ],
        "params": [
            {"name": "tag_filter", "long": "tag-filter", "type": str,
             "default": CONFIG["trailTagFilter"]},
        ],
        # hub_range.json (compute_hub_range.py, task 05a below) needs huts.geojson first, so this
        # early-numbered task now depends on a later-numbered one - see 05a's comment.
        "file_dep": [str(OSM_DIR / "raw" / f"{n}-latest.osm.pbf") for n in REGION_NAMES]
        + [str(OSM_DIR / "hub_range.geojson")],
        "targets": [str(OSM_DIR / f"{n}-trails.osm.pbf") for n in REGION_NAMES],
        "uptodate": [TaskOptionsChanged()],
    }


# ---- 03: merge trails -------------------------------------------------------

def task_merge_trails():
    return {
        "actions": [py("phases/preprocessing/merge_trails.py")],
        "file_dep": [str(OSM_DIR / f"{n}-trails.osm.pbf") for n in REGION_NAMES],
        "targets": [str(OSM_DIR / "trails.osm.pbf")],
    }


# ---- 04: verify (gate, no target - always runs when selected) -------------

def task_verify_trails():
    return {
        "actions": [py("phases/preprocessing/verify_trails.py")],
        "file_dep": [str(OSM_DIR / "trails.osm.pbf")],
        "uptodate": [False],
    }


# ---- 05: fetch huts ---------------------------------------------------------

def task_fetch_huts():
    return {
        "actions": [py("phases/downloads/fetch_huts.py")],
        # fetch_huts.py reads config["bbox"] directly (a {minLng, minLat, maxLng, maxLat} dict -
        # not a sensible CLI flag), so this param exists only to track it via TaskOptionsChanged
        # instead of the whole pipeline.config.json file - keep the key path here in sync with
        # what the script actually reads.
        "params": [
            {"name": "bbox_json", "long": "bbox-json", "type": str,
             "default": json.dumps(CONFIG["bbox"], sort_keys=True)},
        ],
        "targets": [str(OSM_DIR / "huts.geojson")],
        "uptodate": [TaskOptionsChanged()],
    }


# ---- 05a: hub range (every hut's bbox + graph.maxEdgeKm buffer) -----------
# Numbered after fetch_huts (needs huts.geojson) but consumed by filter_trails (02) - a DAG
# diamond, not a numbering mistake: huts.geojson must exist before this can compute the range
# filter_trails clips to, even though filter_trails otherwise runs early in the pipeline. See
# compute_hub_range.py's docstring for why this bound is provably safe, not a heuristic.

def task_compute_hub_range():
    return {
        "actions": [
            f'"{sys.executable}" "{SCRIPT_DIR / "phases" / "preprocessing" / "compute_hub_range.py"}"'
            " --max-edge-km %(max_edge_km)s"
        ],
        "params": [
            {"name": "max_edge_km", "long": "max-edge-km", "type": float,
             "default": CONFIG["graph"]["maxEdgeKm"]},
        ],
        "file_dep": [str(OSM_DIR / "huts.geojson")],
        "targets": [str(OSM_DIR / "hub_range.geojson")],
        "uptodate": [TaskOptionsChanged()],
    }


# ---- 05b: fetch stations + parking (reads raw extracts, not filtered) -----

def task_fetch_stations_parking():
    return {
        "actions": [py("phases/downloads/fetch_stations_parking.py")],
        "file_dep": [str(OSM_DIR / "raw" / f"{n}-latest.osm.pbf") for n in REGION_NAMES],
        "targets": [str(OSM_DIR / "stations.geojson"), str(OSM_DIR / "parking.geojson")],
    }


# ---- 05c: filter stations/parking down to hub-range candidates ------------

def task_filter_start_points():
    return {
        "actions": [
            f'"{sys.executable}" '
            f'"{SCRIPT_DIR / "phases" / "preprocessing" / "filter_start_points.py"}"'
            " --max-edge-km %(max_edge_km)s"
        ],
        "params": [
            {"name": "max_edge_km", "long": "max-edge-km", "type": float,
             "default": CONFIG["graph"]["maxEdgeKm"]},
        ],
        "file_dep": [
            str(OSM_DIR / "huts.geojson"), str(OSM_DIR / "stations.geojson"),
            str(OSM_DIR / "parking.geojson"),
        ],
        "targets": [str(OSM_DIR / "start_points.npy"), str(OSM_DIR / "start_points_id_table.json")],
        "uptodate": [TaskOptionsChanged()],
    }


# ---- 06a: build base graph (hub-agnostic, cached trail graph) -------------
# NOT cheap - build_hut_graph.py's old stream+contract half recorded ~4.1 hour runs
# (data/timings.jsonl), so this is freshness-checked like every other step, not force-rerun.
# Still reruns automatically when --tile-size-km is passed a different value than last time, via
# the TaskOptionsChanged uptodate check below - not just on file_dep changes.

def task_build_base_graph():
    return {
        "actions": [
            f'"{sys.executable}" "{SCRIPT_DIR / "phases" / "graph_building" / "build_base_graph.py"}"'
            " --tile-size-km %(tile_size_km)s"
        ],
        "params": [
            {"name": "tile_size_km", "long": "tile-size-km", "type": float,
             "default": CONFIG["graph"]["tileSizeKm"]},
        ],
        "file_dep": [str(OSM_DIR / "trails.osm.pbf")],
        "targets": [str(OSM_DIR / "base_graph" / "manifest.json")],
        "uptodate": [TaskOptionsChanged()],
    }


# ---- 06b: build hut-hut / start-hut edges (tiled, multiprocess) -----------

def task_build_hub_edges():
    return {
        "actions": [
            f'"{sys.executable}" "{SCRIPT_DIR / "phases" / "graph_building" / "build_hub_edges.py"}"'
            " --max-edge-km %(max_edge_km)s --max-snap-m %(max_snap_m)s"
            " --max-snap-ascent-m %(max_snap_ascent_m)s"
        ],
        "params": [
            {"name": "max_edge_km", "long": "max-edge-km", "type": float,
             "default": CONFIG["graph"]["maxEdgeKm"]},
            {"name": "max_snap_m", "long": "max-snap-m", "type": float,
             "default": CONFIG["graph"]["maxSnapM"]},
            {"name": "max_snap_ascent_m", "long": "max-snap-ascent-m", "type": float,
             "default": CONFIG["graph"]["maxSnapAscentM"]},
        ],
        # task_dep (not just file_dep) on compute_edge_profiles: edges.npy's time_s/ascent_m/
        # descent_m are rewritten in place by that task but aren't one of its declared targets
        # (build_base_graph already owns edges.npy as a target, and doit forbids two tasks
        # sharing one target) - node_ele.npy is the completion signal instead.
        "task_dep": ["compute_edge_profiles"],
        "file_dep": [
            str(OSM_DIR / "base_graph" / "manifest.json"), str(OSM_DIR / "base_graph" / "node_ele.npy"),
            str(OSM_DIR / "huts.geojson"), str(OSM_DIR / "start_points.npy"),
            # spec E3: hub elevation is now sampled directly from the DEM (same raster as
            # node_ele.npy/interior_ele.npy), a real new dependency this task didn't have before.
            str(DEM_DIR / "dem.tif"),
        ],
        "targets": [
            str(OSM_DIR / "hut_edges" / "records.npy"), str(OSM_DIR / "start_edges" / "records.npy"),
            str(OSM_DIR / "unsnapped_huts.json"),
        ],
        "uptodate": [TaskOptionsChanged()],
    }


# ---- 07 / 07b: fetch DEM + materialize -------------------------------------

def task_fetch_dem():
    return {
        "actions": [
            f'"{sys.executable}" "{SCRIPT_DIR / "phases" / "downloads" / "fetch_dem.py"}"'
            " --max-edge-km %(max_edge_km)s"
        ],
        # fetch_dem.py reads config["dem"] (provider name + provider-specific nested config) and
        # config["bbox"] directly - neither is a sensible CLI flag, so these params exist only to
        # track them via TaskOptionsChanged instead of the whole pipeline.config.json file - keep
        # the key paths here in sync with what the script actually reads. max_edge_km IS a real
        # flag (unlike the two above) - it sizes bavaria-dgm5's per-hut buffer (see
        # dem_providers/composite.py's fetch_regions), so a maxEdgeKm change must invalidate this
        # task too, not just compute_hub_range/filter_trails.
        "params": [
            {"name": "dem_json", "long": "dem-json", "type": str,
             "default": json.dumps(CONFIG["dem"], sort_keys=True)},
            {"name": "bbox_json", "long": "bbox-json", "type": str,
             "default": json.dumps(CONFIG["bbox"], sort_keys=True)},
            {"name": "max_edge_km", "long": "max-edge-km", "type": float,
             "default": CONFIG["graph"]["maxEdgeKm"]},
        ],
        "targets": [str(DEM_DIR / "fetch_manifest.json")],
        "uptodate": [TaskOptionsChanged()],
    }


def task_build_dem_vrt():
    return {
        "actions": [py("phases/elevation/build_dem_vrt.py")],
        "file_dep": [str(DEM_DIR / "fetch_manifest.json")],
        "targets": [str(DEM_DIR / "dem.vrt"), str(DEM_DIR / "dem.tif")],
    }


# ---- 06c: elevation per base edge (in-place edit of base_graph/edges.npy) --
# NOT force-rerun - reads the whole DEM and re-derives time_s/ascent_m/descent_m for every base
# edge, the thing that makes the next `build_hub_edges` run the multi-hour job (see dodo.py's
# module docstring and Task 22's schema_version fingerprint). Split into two tasks because only
# sample_base_elevation reads the DEM - compute_edge_profiles only reacts to
# --smoothing-kernel-m, and used to force a full DEM resample on every retune when this was one
# task (add_base_elevation).

def task_sample_base_elevation():
    return {
        "actions": [
            py("phases/elevation/sample_base_elevation.py"),
        ],
        # spec B5: the elevation pass genuinely needs the DEM, so declare it - the previous
        # numbering-convention ordering let a stale dem.tif through silently.
        "file_dep": [str(OSM_DIR / "base_graph" / "manifest.json"), str(DEM_DIR / "dem.tif")],
        "targets": [
            str(OSM_DIR / "base_graph" / "node_ele.npy"), str(OSM_DIR / "base_graph" / "interior_ele.npy"),
        ],
    }


def task_compute_edge_profiles():
    return {
        "actions": [
            f'"{sys.executable}" "{SCRIPT_DIR / "phases" / "elevation" / "compute_edge_profiles.py"}"'
            " --smoothing-kernel-m %(smoothing_kernel_m)s --speed-v0 %(speed_v0)s"
            " --speed-k %(speed_k)s --speed-s0 %(speed_s0)s"
        ],
        "params": [
            {"name": "smoothing_kernel_m", "long": "smoothing-kernel-m", "type": float,
             "default": CONFIG["dem"]["smoothingKernelM"]},
            # speedModel is read directly by compute_edge_profiles.py's time_s computation - every
            # value it uses from there must be its own tracked param, or TaskOptionsChanged()
            # can't see a speedModel-only config edit (e.g. a routing_probe.py recalibration) and
            # reports "up to date" while edges.npy's time_s stays stale under the old constants.
            {"name": "speed_v0", "long": "speed-v0", "type": float,
             "default": CONFIG["graph"]["speedModel"]["v0"]},
            {"name": "speed_k", "long": "speed-k", "type": float,
             "default": CONFIG["graph"]["speedModel"]["k"]},
            {"name": "speed_s0", "long": "speed-s0", "type": float,
             "default": CONFIG["graph"]["speedModel"]["s0"]},
        ],
        "task_dep": ["sample_base_elevation"],
        "file_dep": [
            str(OSM_DIR / "base_graph" / "node_ele.npy"), str(OSM_DIR / "base_graph" / "interior_ele.npy"),
        ],
        # edges.npy is rewritten in place but can't be this task's target - build_base_graph
        # already owns it as a target, and doit forbids two tasks sharing one target (same
        # reason build_hub_edges below signals off node_ele.npy instead of edges.npy). This
        # stamp file is the completion signal instead.
        "targets": [str(OSM_DIR / "base_graph" / "edge_profiles.stamp")],
        "uptodate": [TaskOptionsChanged()],
    }


# ---- 09b: display-only elevation profiles (never reads the DEM) -----------
# Always reruns when selected - genuinely cheap (seconds), and usually run precisely to retune
# --profile-points (spec B4: that retune must not force a re-route or a DEM read).

def task_build_profiles():
    return {
        "actions": [
            f'"{sys.executable}" "{SCRIPT_DIR / "phases" / "elevation" / "build_profiles.py"}"'
            " --profile-points %(profile_points)s"
        ],
        "params": [
            {"name": "profile_points", "long": "profile-points", "type": int,
             "default": CONFIG["dem"].get("profilePoints", 30)},
        ],
        "task_dep": ["build_hub_edges"],  # same file, not just same mtime - see docstring above
        "file_dep": [
            str(OSM_DIR / "base_graph" / "interior_ele.npy"),
            str(OSM_DIR / "hut_edges" / "records.npy"), str(OSM_DIR / "start_edges" / "records.npy"),
        ],
        # records.npy is rewritten in place (profile_offset/profile_count filled) but NOT listed
        # as a target here: build_hub_edges already owns it as a target, and doit forbids two
        # tasks sharing one target. profiles.npy is the only file this task alone produces.
        # Downstream tasks that need to wait for the in-place rewrite (the tile builders) declare
        # an explicit task_dep on build_profiles instead of relying on a shared target/file_dep link.
        "targets": [
            str(OSM_DIR / "hut_edges" / "profiles.npy"), str(OSM_DIR / "start_edges" / "profiles.npy"),
        ],
        "uptodate": [False],
    }


# ---- 09: build trail vector tiles ------------------------------------------

def task_build_trail_tiles():
    tiles_cfg = CONFIG.get("trailTiles", {})
    return {
        "actions": [
            py(
                "phases/postprocessing/build_trail_tiles.py",
                f"--min-zoom {tiles_cfg.get('minZoom', 6)}",
                f"--max-zoom {tiles_cfg.get('maxZoom', 14)}",
            )
        ],
        "file_dep": [str(OSM_DIR / "trails.osm.pbf")],
        "targets": [str(OSM_DIR / "trails.pmtiles")],
    }


# ---- 11: build hut-edge / start-edge vector tiles + stats -----------------

def task_build_hut_edge_tiles():
    tiles_cfg = CONFIG.get("hutEdgeTiles", {})
    return {
        "actions": [
            py(
                "phases/postprocessing/build_edge_tiles.py",
                f"--edges-dir {OSM_DIR / 'hut_edges'}",
                f"--id-table {OSM_DIR / 'start_points_id_table.json'}",
                "--layer-name hut_edges",
                f"--out-tiles {OSM_DIR / 'hut-edges.pmtiles'}",
                f"--out-stats {OSM_DIR / 'hut-edge-stats.json'}",
                f"--min-zoom {tiles_cfg.get('minZoom', 6)}",
                f"--max-zoom {tiles_cfg.get('maxZoom', 14)}",
                f"--hover-simplify-tolerance-deg {tiles_cfg.get('hoverSimplifyToleranceDeg', 0.0003)}",
            )
        ],
        # task_dep (not just file_dep) on build_profiles: records.npy's profile_offset/
        # profile_count are rewritten in place by that task but aren't one of its declared
        # targets (see task_build_profiles's comment), so doit's file-hash freshness check alone
        # wouldn't guarantee this task runs after it.
        "task_dep": ["build_profiles"],
        "file_dep": [str(OSM_DIR / "hut_edges" / "records.npy")],
        "targets": [str(OSM_DIR / "hut-edges.pmtiles"), str(OSM_DIR / "hut-edge-stats.json")],
    }


def task_build_start_edge_tiles():
    tiles_cfg = CONFIG.get("hutEdgeTiles", {})
    return {
        "actions": [
            py(
                "phases/postprocessing/build_edge_tiles.py",
                f"--edges-dir {OSM_DIR / 'start_edges'}",
                f"--id-table {OSM_DIR / 'start_points_id_table.json'}",
                "--layer-name start_edges",
                f"--out-tiles {OSM_DIR / 'start-edges.pmtiles'}",
                f"--out-stats {OSM_DIR / 'start-edge-stats.json'}",
                f"--min-zoom {tiles_cfg.get('minZoom', 6)}",
                f"--max-zoom {tiles_cfg.get('maxZoom', 14)}",
                f"--hover-simplify-tolerance-deg {tiles_cfg.get('hoverSimplifyToleranceDeg', 0.0003)}",
            )
        ],
        "task_dep": ["build_profiles"],  # see task_build_hut_edge_tiles's comment
        "file_dep": [str(OSM_DIR / "start_edges" / "records.npy")],
        "targets": [str(OSM_DIR / "start-edges.pmtiles"), str(OSM_DIR / "start-edge-stats.json")],
    }


# ---- 11a: approach/exit table + loop-closure reverse index ----------------

def task_build_approach_table():
    return {
        "actions": [
            py(
                "phases/postprocessing/build_approach_table.py",
                f"--edges-dir {OSM_DIR / 'start_edges'}",
                f"--id-table {OSM_DIR / 'start_points_id_table.json'}",
                f"--k {CONFIG['approach']['k']}",
                f"--out-bin {OSM_DIR / 'approaches.bin'}",
                f"--out-manifest {OSM_DIR / 'approaches.json'}",
            )
        ],
        "file_dep": [
            str(OSM_DIR / "start_edges" / "records.npy"),
            str(OSM_DIR / "start_points_id_table.json"),
        ],
        "targets": [str(OSM_DIR / "approaches.bin"), str(OSM_DIR / "approaches.json")],
    }


# ---- 12: copy outputs into huts/public/data --------------------------------

def task_copy_public_data():
    def copy_all():
        import shutil

        PUBLIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
        for name in PUBLIC_FILES:
            src = OSM_DIR / name
            if not src.exists():
                print(f"  skip {name} (not built yet)")
                continue
            shutil.copy2(src, PUBLIC_DATA_DIR / name)
            print(f"  {src} -> {PUBLIC_DATA_DIR / name}")

    deps = [str(OSM_DIR / name) for name in PUBLIC_FILES if (OSM_DIR / name).exists()] or [
        str(OSM_DIR / name) for name in PUBLIC_FILES
    ]
    return {
        "actions": [copy_all],
        "file_dep": deps,
        "targets": [str(PUBLIC_DATA_DIR / name) for name in PUBLIC_FILES],
    }
