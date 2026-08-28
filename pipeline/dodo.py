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
every task downstream of it (unlike run_all.py's old global config-mtime check). verify_trails
used to declare `uptodate: [False]` to force a rerun every time it's selected, reasoning that a
gate has no cacheable output - true of the check result, but not of "did trails.osm.pbf change",
which file_dep already tracks. It now targets a verify_trails.stamp (same pattern as
compute_edge_profiles' edge_profiles.stamp below) so an unchanged trails.osm.pbf skips the
osmium re-scan.
build_profiles used to force-rerun on the same "gate has no cacheable output" reasoning, but it doesn't
apply here either: it writes profile_offset/profile_count into hut_edges/records.npy and
start_edges/records.npy in place, which are also its own file_dep (build_hub_edges owns those files as
targets, so build_profiles can't - see task_build_profiles's comment). A standalone doit experiment
confirmed doit hashes file_dep *after* a successful run, so a task that mutates its own file_dep in
place still caches correctly - it isn't perpetually "stale" from its own last write. build_profiles now
uses TaskOptionsChanged() like every other params task, so a --profile-points retune (spec B4: must not
force a re-route or a DEM read) still reruns it, but an unchanged run is skipped. build_base_graph/build_hub_edges/
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
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import binfmt  # noqa: E402
from lib.pipeline import DATA_DIR, DEM_DIR, OSM_DIR, PUBLIC_DATA_DIR, load_config  # noqa: E402
from lib.timing import phase  # noqa: E402


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
        "compute_edge_profiles", "snap_hubs", "gather_route_subgraphs", "build_hub_edges",
        "build_profiles",
        "build_trail_tiles", "build_hut_edge_tiles", "build_start_edge_tiles",
        "build_approach_table", "build_edge_payload",
        "copy_public_data",
    ],
}

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG = load_config()
REGION_NAMES = [r["name"] for r in CONFIG["regions"]]


def rel(path) -> str:
    """file_dep/targets entries below use this instead of a bare str(path): doit's dependency DB
    keys each file's tracked hash by the literal string given here, resolved against doit's own
    cwd (SCRIPT_DIR - pipeline/, where dodo.py lives; both pixi.toml's [tasks] and the README's
    manual conda flow always run doit from there). OSM_DIR/DEM_DIR/PUBLIC_DATA_DIR (lib/pipeline.py)
    are absolute, .resolve()d paths - deliberately, so a worktree's data/ symlink and the main
    checkout's real data/ dir produce identical strings on the SAME machine/OS. But an absolute
    path is still different text on native Windows (C:\\Users\\...) vs WSL (/home/...) for the
    exact same file, so switching between them makes every file_dep look "moved" and forces a full
    rebuild (seen switching this pipeline from native-Windows conda to WSL/pixi - see git history
    around the pixi migration). A path relative to SCRIPT_DIR, normalized to forward slashes, is
    identical text regardless of OS or which machine last ran doit - only the *content* of
    pipeline.config.json/scripts should invalidate a task, not which OS wrote the cache.
    Actions (subprocess/script CLI args) are untouched by this - they still use OSM_DIR/DEM_DIR
    absolute paths directly, since those are just runtime arguments to a fresh process each run,
    not something doit hashes and compares across runs."""
    return os.path.relpath(Path(path).resolve(), SCRIPT_DIR).replace(os.sep, "/")

PUBLIC_FILES = [
    "huts.geojson",
    "hut-edges.pmtiles",
    "hut-edge-stats.json",
    "hut-edge-geometry.bin",
    "hut-edge-geometry.json",
    "start-edges.pmtiles",
    "start-edge-geometry.bin",
    "start-edge-geometry.json",
    "trails.pmtiles",
    "stations.geojson",
    "parking.geojson",
    "unsnapped_huts.json",
    "approaches.bin",
    "approaches.json",
    "hut-edge-payload.bin",
    "hut-edge-payload.json",
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
        "targets": [rel(OSM_DIR / "raw" / f"{n}-latest.osm.pbf") for n in REGION_NAMES],
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
        "file_dep": [rel(OSM_DIR / "raw" / f"{n}-latest.osm.pbf") for n in REGION_NAMES]
        + [rel(OSM_DIR / "hub_range.geojson")],
        "targets": [rel(OSM_DIR / f"{n}-trails.osm.pbf") for n in REGION_NAMES],
        "uptodate": [TaskOptionsChanged()],
    }


# ---- 03: merge trails -------------------------------------------------------

def task_merge_trails():
    return {
        "actions": [py("phases/preprocessing/merge_trails.py")],
        "file_dep": [rel(OSM_DIR / f"{n}-trails.osm.pbf") for n in REGION_NAMES],
        "targets": [rel(OSM_DIR / "trails.osm.pbf")],
    }


# ---- 04: verify (gate) ------------------------------------------------------
# Targets verify_trails.stamp so this is freshness-checked like any other task - trails.osm.pbf
# unchanged (content hash) means the file already passed osmium fileinfo -e last time, so
# re-scanning it buys nothing. Used to force-rerun via uptodate:[False] on the reasoning that a
# gate has no cacheable output; that's true of the *check result* but not of "did the input
# change", which file_dep already tracks regardless of targets.

def task_verify_trails():
    return {
        "actions": [py("phases/preprocessing/verify_trails.py")],
        "file_dep": [rel(OSM_DIR / "trails.osm.pbf")],
        "targets": [rel(OSM_DIR / "verify_trails.stamp")],
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
        "targets": [rel(OSM_DIR / "huts.geojson"), rel(OSM_DIR / "partner_betriebe.geojson")],
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
        "file_dep": [rel(OSM_DIR / "huts.geojson")],
        "targets": [rel(OSM_DIR / "hub_range.geojson")],
        "uptodate": [TaskOptionsChanged()],
    }


# ---- 05b: fetch stations + parking (reads raw extracts, not filtered) -----

def task_fetch_stations_parking():
    return {
        "actions": [py("phases/downloads/fetch_stations_parking.py")],
        "file_dep": [rel(OSM_DIR / "raw" / f"{n}-latest.osm.pbf") for n in REGION_NAMES],
        "targets": [rel(OSM_DIR / "stations.geojson"), rel(OSM_DIR / "parking.geojson")],
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
            rel(OSM_DIR / "huts.geojson"), rel(OSM_DIR / "stations.geojson"),
            rel(OSM_DIR / "parking.geojson"), rel(OSM_DIR / "partner_betriebe.geojson"),
        ],
        "targets": [rel(OSM_DIR / "start_points.npy"), rel(OSM_DIR / "start_points_id_table.json")],
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
            # tracking-only, no CLI flag: build_base_graph.py reads config["graph"]
            # ["roadHighwayTags"] directly (WayGraphHandler's is_road classification) and
            # config["bbox"] directly (pack_and_write's Grid, which decides every node's cell_id) -
            # without these, editing either in pipeline.config.json would silently leave the
            # multi-hour rebuild un-triggered.
            {"name": "road_highway_tags_json", "long": "road-highway-tags-json", "type": str,
             "default": json.dumps(CONFIG["graph"]["roadHighwayTags"])},
            {"name": "bbox_json", "long": "bbox-json", "type": str,
             "default": json.dumps(CONFIG["bbox"], sort_keys=True)},
            # tracking-only, no CLI flag (see binfmt.SCHEMA_VERSION's docstring): a code-only
            # EDGE_DTYPE change must still force this task's multi-hour rebuild.
            {"name": "schema_version", "long": "schema-version", "type": int,
             "default": binfmt.SCHEMA_VERSION},
        ],
        "file_dep": [rel(OSM_DIR / "trails.osm.pbf")],
        "targets": [rel(OSM_DIR / "base_graph" / "manifest.json")],
        "uptodate": [TaskOptionsChanged()],
    }


# ---- 06b1: snap every hub onto the base graph (independent of max_edge_km/variants) -------
# Split out of build_hub_edges.py (docs/superpowers/plans/2026-08-23-split-build-hub-edges.md):
# snapping only needs trail data within max_snap_m, not max_edge_km, and doesn't depend on
# graph.variants at all - see snap_hubs.py's module docstring for why this used to force a full
# re-snap on every --max-edge-km/variants retune.

def task_snap_hubs():
    return {
        "actions": [
            f'"{sys.executable}" "{SCRIPT_DIR / "phases" / "graph_building" / "snap_hubs.py"}"'
            " --max-snap-m %(max_snap_m)s --max-snap-ascent-m %(max_snap_ascent_m)s"
        ],
        "params": [
            {"name": "max_snap_m", "long": "max-snap-m", "type": float,
             "default": CONFIG["graph"]["maxSnapM"]},
            {"name": "max_snap_ascent_m", "long": "max-snap-ascent-m", "type": float,
             "default": CONFIG["graph"]["maxSnapAscentM"]},
            # tracking-only, no CLI flag: see task_build_base_graph's schema_version param.
            {"name": "schema_version", "long": "schema-version", "type": int,
             "default": binfmt.SCHEMA_VERSION},
        ],
        # task_dep (not just file_dep) on compute_edge_profiles: edges.npy's time_s/ascent_m/
        # descent_m are rewritten in place by that task but aren't one of its declared targets
        # (build_base_graph already owns edges.npy as a target, and doit forbids two tasks
        # sharing one target) - node_ele.npy is the completion signal instead.
        "task_dep": ["compute_edge_profiles"],
        "file_dep": [
            rel(OSM_DIR / "base_graph" / "manifest.json"), rel(OSM_DIR / "base_graph" / "node_ele.npy"),
            rel(OSM_DIR / "huts.geojson"), rel(OSM_DIR / "start_points.npy"),
            # spec E3: hub elevation is sampled directly from the DEM (same raster as
            # node_ele.npy/interior_ele.npy).
            rel(DEM_DIR / "dem.tif"),
        ],
        "targets": [
            rel(OSM_DIR / "hub_snaps.npy"), rel(OSM_DIR / "hub_snap_interior.npy"),
            rel(OSM_DIR / "unsnapped_huts.json"),
        ],
        "uptodate": [TaskOptionsChanged()],
    }


# ---- 06b2: gather + cache per-cell max-edge-km-padded subgraphs -----------
# Split out of build_hub_edges.py: this is the expensive part of gather_padded_subgraph (cell
# union + one-hop closure + array copy - see lib/subgraph.py's module docstring), cached so a
# graph.variants-only retune of build_hub_edges doesn't repeat it - see
# gather_route_subgraphs.py's module docstring. Depends on max_edge_km (unlike snap_hubs above),
# so an edge-km retune still invalidates this task, same as before the split.

def task_gather_route_subgraphs():
    return {
        "actions": [
            f'"{sys.executable}" '
            f'"{SCRIPT_DIR / "phases" / "graph_building" / "gather_route_subgraphs.py"}"'
            " --max-edge-km %(max_edge_km)s"
        ],
        "params": [
            {"name": "max_edge_km", "long": "max-edge-km", "type": float,
             "default": CONFIG["graph"]["maxEdgeKm"]},
            {"name": "schema_version", "long": "schema-version", "type": int,
             "default": binfmt.SCHEMA_VERSION},
        ],
        "task_dep": ["compute_edge_profiles"],  # same in-place-edit reasoning as task_snap_hubs
        "file_dep": [
            rel(OSM_DIR / "base_graph" / "manifest.json"), rel(OSM_DIR / "base_graph" / "node_ele.npy"),
            rel(OSM_DIR / "huts.geojson"), rel(OSM_DIR / "start_points.npy"),
        ],
        "targets": [rel(OSM_DIR / "route_subgraphs" / "manifest.json")],
        "uptodate": [TaskOptionsChanged()],
    }


# ---- 06c: build hut-hut / start-hut edges (tiled, multiprocess) -----------

def task_build_hub_edges():
    return {
        "actions": [
            f'"{sys.executable}" "{SCRIPT_DIR / "phases" / "graph_building" / "build_hub_edges.py"}"'
            " --max-edge-km %(max_edge_km)s"
        ],
        "params": [
            {"name": "max_edge_km", "long": "max-edge-km", "type": float,
             "default": CONFIG["graph"]["maxEdgeKm"]},
            # tracking-only, no CLI flag: build_hub_edges.py reads config["graph"]["variants"]
            # directly (variants_lib.enabled_variants), so without this a three-row -> four-row
            # grid edit would report "up to date" and silently skip the rebuild.
            {"name": "variants_json", "long": "variants-json", "type": str,
             "default": json.dumps(CONFIG["graph"]["variants"], sort_keys=True)},
            # tracking-only, no CLI flag: see task_build_base_graph's schema_version param.
            {"name": "schema_version", "long": "schema-version", "type": int,
             "default": binfmt.SCHEMA_VERSION},
        ],
        "task_dep": ["snap_hubs", "gather_route_subgraphs"],
        "file_dep": [
            rel(OSM_DIR / "base_graph" / "manifest.json"),
            rel(OSM_DIR / "huts.geojson"), rel(OSM_DIR / "start_points.npy"),
            rel(OSM_DIR / "hub_snaps.npy"), rel(OSM_DIR / "hub_snap_interior.npy"),
            rel(OSM_DIR / "route_subgraphs" / "manifest.json"),
        ],
        "targets": [
            rel(OSM_DIR / "hut_edges" / "records.npy"), rel(OSM_DIR / "start_edges" / "records.npy"),
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
        "targets": [rel(DEM_DIR / "fetch_manifest.json")],
        "uptodate": [TaskOptionsChanged()],
    }


def task_build_dem_vrt():
    return {
        "actions": [py("phases/elevation/build_dem_vrt.py")],
        "file_dep": [rel(DEM_DIR / "fetch_manifest.json")],
        "targets": [rel(DEM_DIR / "dem.vrt"), rel(DEM_DIR / "dem.tif")],
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
        "file_dep": [rel(OSM_DIR / "base_graph" / "manifest.json"), rel(DEM_DIR / "dem.tif")],
        "targets": [
            rel(OSM_DIR / "base_graph" / "node_ele.npy"), rel(OSM_DIR / "base_graph" / "interior_ele.npy"),
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
            rel(OSM_DIR / "base_graph" / "node_ele.npy"), rel(OSM_DIR / "base_graph" / "interior_ele.npy"),
        ],
        # edges.npy is rewritten in place but can't be this task's target - build_base_graph
        # already owns it as a target, and doit forbids two tasks sharing one target (same
        # reason build_hub_edges below signals off node_ele.npy instead of edges.npy). This
        # stamp file is the completion signal instead.
        "targets": [rel(OSM_DIR / "base_graph" / "edge_profiles.stamp")],
        "uptodate": [TaskOptionsChanged()],
    }


# ---- 09b: display-only elevation profiles (never reads the DEM) -----------
# Meant to be cheap, and usually run precisely to retune --profile-points (spec B4: that retune
# must not force a re-route or a DEM read). It genuinely was seconds until start_edges grew to
# ~235k records / ~200M geometry points (2026-08-27), at which point build_profiles.py's
# _fill_unmatched - a point-at-a-time Python loop - dominated with 800+s of the ~830s run
# (data/timings.jsonl). Fixed by vectorizing _fill_unmatched; if this task gets slow again, check
# timings.jsonl's hut_edges_s/start_edges_s split before assuming it's still cheap.
#
# Used to declare uptodate: [False] to force a rerun on every `doit` invocation, reasoning that a
# task depending on (file_dep) a file it also mutates in place - hut_edges/records.npy and
# start_edges/records.npy, where it fills profile_offset/profile_count, while build_hub_edges owns
# them as targets - would otherwise look permanently stale from its own last write. A standalone
# doit experiment (dodo.py history/PR description) showed that's wrong: doit hashes file_dep
# *after* a successful run, so it correctly detects "unchanged since I last touched it" and skips.
# Now uses TaskOptionsChanged() like every other params task instead.

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
            rel(OSM_DIR / "base_graph" / "interior_ele.npy"),
            rel(OSM_DIR / "hut_edges" / "records.npy"), rel(OSM_DIR / "start_edges" / "records.npy"),
        ],
        # records.npy is rewritten in place (profile_offset/profile_count filled) but NOT listed
        # as a target here: build_hub_edges already owns it as a target, and doit forbids two
        # tasks sharing one target. profiles.npy is the only file this task alone produces.
        # Downstream tasks that need to wait for the in-place rewrite (the tile builders) declare
        # an explicit task_dep on build_profiles instead of relying on a shared target/file_dep link.
        "targets": [
            rel(OSM_DIR / "hut_edges" / "profiles.npy"), rel(OSM_DIR / "start_edges" / "profiles.npy"),
        ],
        "uptodate": [TaskOptionsChanged()],
    }


# ---- 09: build trail vector tiles ------------------------------------------

def task_build_trail_tiles():
    tiles_cfg = CONFIG.get("trailTiles", {})
    return {
        "actions": [
            py(
                "phases/postprocessing/build_trail_tiles.py",
                "--min-zoom %(min_zoom)s",
                "--max-zoom %(max_zoom)s",
            )
        ],
        # was baked straight into the action string with no params/uptodate - same doit gap as
        # build_approach_table's --k (see its comment): retuning trailTiles zoom never reran this.
        "params": [
            {"name": "min_zoom", "long": "min-zoom", "type": int,
             "default": tiles_cfg.get("minZoom", 6)},
            {"name": "max_zoom", "long": "max-zoom", "type": int,
             "default": tiles_cfg.get("maxZoom", 14)},
        ],
        "file_dep": [rel(OSM_DIR / "trails.osm.pbf")],
        "targets": [rel(OSM_DIR / "trails.pmtiles")],
        "uptodate": [TaskOptionsChanged()],
    }


# ---- 11: build hut-edge / start-edge vector tiles + stats -----------------

# tracking-only param builder shared by both edge-tile tasks below - config["hutEdgeTiles"] used
# to be baked straight into each action's f-string with no params/uptodate at all, so retuning
# zoom/hover-tolerance never reran either task (same doit gap as build_approach_table's --k, see
# its comment).
def _hut_edge_tiles_params():
    tiles_cfg = CONFIG.get("hutEdgeTiles", {})
    return [
        {"name": "min_zoom", "long": "min-zoom", "type": int, "default": tiles_cfg.get("minZoom", 6)},
        {"name": "max_zoom", "long": "max-zoom", "type": int, "default": tiles_cfg.get("maxZoom", 14)},
        {"name": "simplify_tolerance_deg", "long": "simplify-tolerance-deg",
         "type": float, "default": tiles_cfg.get("simplifyToleranceDeg", 0.0003)},
    ]


def task_build_hut_edge_tiles():
    return {
        "actions": [
            py(
                "phases/postprocessing/build_edge_tiles.py",
                f"--edges-dir {OSM_DIR / 'hut_edges'}",
                f"--id-table {OSM_DIR / 'start_points_id_table.json'}",
                "--layer-name hut_edges",
                f"--out-tiles {OSM_DIR / 'hut-edges.pmtiles'}",
                f"--out-stats {OSM_DIR / 'hut-edge-stats.json'}",
                f"--out-geometry-bin {OSM_DIR / 'hut-edge-geometry.bin'}",
                f"--out-geometry-json {OSM_DIR / 'hut-edge-geometry.json'}",
                "--min-zoom %(min_zoom)s",
                "--max-zoom %(max_zoom)s",
                "--simplify-tolerance-deg %(simplify_tolerance_deg)s",
            )
        ],
        "params": _hut_edge_tiles_params(),
        # task_dep (not just file_dep) on build_profiles: records.npy's profile_offset/
        # profile_count are rewritten in place by that task but aren't one of its declared
        # targets (see task_build_profiles's comment), so doit's file-hash freshness check alone
        # wouldn't guarantee this task runs after it.
        "task_dep": ["build_profiles"],
        "file_dep": [rel(OSM_DIR / "hut_edges" / "records.npy")],
        "targets": [
            rel(OSM_DIR / "hut-edges.pmtiles"), rel(OSM_DIR / "hut-edge-stats.json"),
            rel(OSM_DIR / "hut-edge-geometry.bin"), rel(OSM_DIR / "hut-edge-geometry.json"),
        ],
        "uptodate": [TaskOptionsChanged()],
    }


def task_build_start_edge_tiles():
    return {
        "actions": [
            py(
                "phases/postprocessing/build_edge_tiles.py",
                f"--edges-dir {OSM_DIR / 'start_edges'}",
                f"--id-table {OSM_DIR / 'start_points_id_table.json'}",
                "--layer-name start_edges",
                f"--out-tiles {OSM_DIR / 'start-edges.pmtiles'}",
                f"--out-stats {OSM_DIR / 'start-edge-stats.json'}",
                f"--out-geometry-bin {OSM_DIR / 'start-edge-geometry.bin'}",
                f"--out-geometry-json {OSM_DIR / 'start-edge-geometry.json'}",
                "--min-zoom %(min_zoom)s",
                "--max-zoom %(max_zoom)s",
                "--simplify-tolerance-deg %(simplify_tolerance_deg)s",
            )
        ],
        "params": _hut_edge_tiles_params(),
        "task_dep": ["build_profiles"],  # see task_build_hut_edge_tiles's comment
        "file_dep": [rel(OSM_DIR / "start_edges" / "records.npy")],
        "targets": [
            rel(OSM_DIR / "start-edges.pmtiles"), rel(OSM_DIR / "start-edge-stats.json"),
            rel(OSM_DIR / "start-edge-geometry.bin"), rel(OSM_DIR / "start-edge-geometry.json"),
        ],
        "uptodate": [TaskOptionsChanged()],
    }


# ---- 11a: approach/exit table + loop-closure reverse index ----------------

def task_build_approach_table():
    return {
        "actions": [
            py(
                "phases/postprocessing/build_approach_table.py",
                f"--edges-dir {OSM_DIR / 'start_edges'}",
                f"--id-table {OSM_DIR / 'start_points_id_table.json'}",
                "--k %(k)s",
                f"--out-bin {OSM_DIR / 'approaches.bin'}",
                f"--out-manifest {OSM_DIR / 'approaches.json'}",
            )
        ],
        # was hardcoded straight into the action string with no params/uptodate at all - doit's
        # up-to-date check never diffs the action string itself, only file_dep hashes and declared
        # uptodate checks (see doit/dependency.py's get_status), so a config["approach"]["k"]
        # retune silently never reran this task.
        "params": [
            {"name": "k", "long": "k", "type": int, "default": CONFIG["approach"]["k"]},
        ],
        "file_dep": [
            rel(OSM_DIR / "start_edges" / "records.npy"),
            rel(OSM_DIR / "start_points_id_table.json"),
        ],
        "targets": [rel(OSM_DIR / "approaches.bin"), rel(OSM_DIR / "approaches.json")],
        "uptodate": [TaskOptionsChanged()],
    }


# ---- 11b: pack + ship the hut-edge payload ---------------------------------

def task_build_edge_payload():
    return {
        "actions": [
            py(
                "phases/postprocessing/build_edge_payload.py",
                f"--edges-dir {OSM_DIR / 'hut_edges'}",
                f"--huts {OSM_DIR / 'huts.geojson'}",
                f"--out-bin {OSM_DIR / 'hut-edge-payload.bin'}",
                f"--out-manifest {OSM_DIR / 'hut-edge-payload.json'}",
            )
        ],
        "task_dep": ["build_profiles"],  # see task_build_hut_edge_tiles's comment
        "file_dep": [rel(OSM_DIR / "hut_edges" / "records.npy"), rel(OSM_DIR / "huts.geojson")],
        "targets": [rel(OSM_DIR / "hut-edge-payload.bin"), rel(OSM_DIR / "hut-edge-payload.json")],
    }


# ---- 12: copy outputs into huts/public/data --------------------------------

def task_copy_public_data():
    def copy_all():
        import shutil

        with phase("dodo.py", "copy_public_data"):
            PUBLIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
            for name in PUBLIC_FILES:
                src = OSM_DIR / name
                if not src.exists():
                    print(f"  skip {name} (not built yet)")
                    continue
                shutil.copy2(src, PUBLIC_DATA_DIR / name)
                print(f"  {src} -> {PUBLIC_DATA_DIR / name}")

    deps = [rel(OSM_DIR / name) for name in PUBLIC_FILES if (OSM_DIR / name).exists()] or [
        rel(OSM_DIR / name) for name in PUBLIC_FILES
    ]
    return {
        "actions": [copy_all],
        "file_dep": deps,
        "targets": [rel(PUBLIC_DATA_DIR / name) for name in PUBLIC_FILES],
    }
