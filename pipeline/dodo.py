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
by default) or if pipeline.config.json changed (every task depends on it, so editing the config
invalidates everything downstream of the values it actually touches, same as run_all.py's
config-mtime check but per-task instead of global). verify_trails has no target (it's a gate, not
a cacheable output) and declares `uptodate: [False]` to force a rerun every time it's selected.
add_elevation does too - genuinely cheap (~90-100s, data/timings.jsonl) and usually run precisely
to retune --ele-noise-threshold-m. build_base_graph/build_hub_edges are NOT force-rerun despite
looking similar - their predecessor build_hut_graph.py was measured at ~4.1 hours
(data/timings.jsonl, 2026-08-15) - so they're freshness-checked normally, each with a
config_changed uptodate check on its own params so passing a different --max-edge-km still
reruns it without needing `doit forget` first (see the docstrings above those tasks).

CLAUDE.md's "never run a pipeline step without asking" rule applies here exactly as it did to
run_all.py - `doit <task>` / bare `doit` are pipeline-step invocations.
"""

import json
import sys
from pathlib import Path

from doit.tools import config_changed

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.pipeline import CONFIG_PATH, DATA_DIR, DEM_DIR, OSM_DIR, PUBLIC_DATA_DIR, load_config  # noqa: E402

DOIT_CONFIG = {
    # keeps doit's runtime state out of the tracked half of pipeline/, alongside every other
    # generated/gitignored pipeline artifact (see root CLAUDE.md's data/ vs pipeline/ split)
    "dep_file": str(DATA_DIR / ".doit.db"),
    "default_tasks": [
        "download_extracts", "filter_trails", "merge_trails", "verify_trails",
        "fetch_huts", "fetch_stations_parking", "filter_start_points",
        "build_base_graph", "build_hub_edges",
        "fetch_dem", "build_dem_vrt", "add_elevation",
        "build_trail_tiles", "build_hut_edge_tiles", "build_start_edge_tiles",
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
]


def py(script, *args):
    parts = [f'"{sys.executable}"', f'"{SCRIPT_DIR / script}"', *[str(a) for a in args]]
    return " ".join(parts)


# ---- 01: download extracts -------------------------------------------------

def task_download_extracts():
    return {
        "actions": [py("download_extracts.py")],
        "file_dep": [str(CONFIG_PATH)],
        "targets": [str(OSM_DIR / "raw" / f"{n}-latest.osm.pbf") for n in REGION_NAMES],
    }


# ---- 02: filter trails per region ------------------------------------------

def task_filter_trails():
    return {
        "actions": [py("filter_trails.py")],
        "file_dep": [str(OSM_DIR / "raw" / f"{n}-latest.osm.pbf") for n in REGION_NAMES]
        + [str(CONFIG_PATH)],
        "targets": [str(OSM_DIR / f"{n}-trails.osm.pbf") for n in REGION_NAMES],
    }


# ---- 03: merge trails -------------------------------------------------------

def task_merge_trails():
    return {
        "actions": [py("merge_trails.py")],
        "file_dep": [str(OSM_DIR / f"{n}-trails.osm.pbf") for n in REGION_NAMES],
        "targets": [str(OSM_DIR / "trails.osm.pbf")],
    }


# ---- 04: verify (gate, no target - always runs when selected) -------------

def task_verify_trails():
    return {
        "actions": [py("verify_trails.py")],
        "file_dep": [str(OSM_DIR / "trails.osm.pbf")],
        "uptodate": [False],
    }


# ---- 05: fetch huts ---------------------------------------------------------

def task_fetch_huts():
    return {
        "actions": [py("fetch_huts.py")],
        "file_dep": [str(CONFIG_PATH)],
        "targets": [str(OSM_DIR / "huts.geojson")],
    }


# ---- 05b: fetch stations + parking (reads raw extracts, not filtered) -----

def task_fetch_stations_parking():
    return {
        "actions": [py("fetch_stations_parking.py")],
        "file_dep": [str(OSM_DIR / "raw" / f"{n}-latest.osm.pbf") for n in REGION_NAMES],
        "targets": [str(OSM_DIR / "stations.geojson"), str(OSM_DIR / "parking.geojson")],
    }


# ---- 05c: filter stations/parking down to hub-range candidates ------------

def task_filter_start_points():
    return {
        "actions": [py("filter_start_points.py")],
        "file_dep": [
            str(OSM_DIR / "huts.geojson"), str(OSM_DIR / "stations.geojson"),
            str(OSM_DIR / "parking.geojson"), str(CONFIG_PATH),
        ],
        "targets": [str(OSM_DIR / "start_points.npy"), str(OSM_DIR / "start_points_id_table.json")],
    }


# ---- 06a: build base graph (hub-agnostic, cached trail graph) -------------
# NOT cheap - build_hut_graph.py's old stream+contract half recorded ~4.1 hour runs
# (data/timings.jsonl), so this is freshness-checked like every other step, not force-rerun.
# Still reruns automatically when --tile-size-km is passed a different value than last time, via
# the config_changed uptodate check below - not just on file_dep changes.

def task_build_base_graph():
    return {
        "actions": [
            f'"{sys.executable}" "{SCRIPT_DIR / "build_base_graph.py"}"'
            " --tile-size-km %(tile_size_km)s"
        ],
        "params": [
            {"name": "tile_size_km", "long": "tile-size-km", "type": float,
             "default": CONFIG["graph"]["tileSizeKm"]},
        ],
        "file_dep": [str(OSM_DIR / "trails.osm.pbf")],
        "targets": [str(OSM_DIR / "base_graph" / "manifest.json")],
        "uptodate": [lambda task, values: config_changed(json.dumps(task.options, sort_keys=True))(task, values)],
    }


# ---- 06b: build hut-hut / start-hut edges (tiled, multiprocess) -----------

def task_build_hub_edges():
    return {
        "actions": [
            f'"{sys.executable}" "{SCRIPT_DIR / "build_hub_edges.py"}"'
            " --max-edge-km %(max_edge_km)s --max-snap-m %(max_snap_m)s"
        ],
        "params": [
            {"name": "max_edge_km", "long": "max-edge-km", "type": float,
             "default": CONFIG["graph"]["maxEdgeKm"]},
            {"name": "max_snap_m", "long": "max-snap-m", "type": float,
             "default": CONFIG["graph"]["maxSnapM"]},
        ],
        "file_dep": [
            str(OSM_DIR / "base_graph" / "manifest.json"), str(OSM_DIR / "huts.geojson"),
            str(OSM_DIR / "start_points.npy"),
        ],
        "targets": [
            str(OSM_DIR / "hut_edges" / "records.npy"), str(OSM_DIR / "start_edges" / "records.npy"),
        ],
        "uptodate": [lambda task, values: config_changed(json.dumps(task.options, sort_keys=True))(task, values)],
    }


# ---- 07 / 07b: fetch DEM + materialize -------------------------------------

def task_fetch_dem():
    return {
        "actions": [py("fetch_dem.py")],
        "file_dep": [str(CONFIG_PATH)],
        "targets": [str(DEM_DIR / "fetch_manifest.json")],
    }


def task_build_dem_vrt():
    return {
        "actions": [py("build_dem_vrt.py")],
        "file_dep": [str(DEM_DIR / "fetch_manifest.json")],
        "targets": [str(DEM_DIR / "dem.vrt"), str(DEM_DIR / "dem.tif")],
    }


# ---- 08: add elevation (in-place edit of hut_edges/ + start_edges/ records) --
# Always reruns when selected (cheap; usually run precisely to retune --ele-noise-threshold-m).

def task_add_elevation():
    return {
        "actions": [
            f'"{sys.executable}" "{SCRIPT_DIR / "add_elevation.py"}"'
            " --ele-noise-threshold-m %(ele_noise_threshold_m)s"
            " --profile-points %(profile_points)s"
        ],
        "params": [
            {"name": "ele_noise_threshold_m", "long": "ele-noise-threshold-m", "type": float,
             "default": CONFIG["dem"]["eleNoiseThresholdM"]},
            {"name": "profile_points", "long": "profile-points", "type": int,
             "default": CONFIG["dem"].get("profilePoints", 30)},
        ],
        "task_dep": ["build_hub_edges"],  # same file, not just same mtime - see docstring above
        "file_dep": [str(DEM_DIR / "dem.tif")],
        # records.npy is rewritten in place (ascent_m/descent_m/profile_offset/profile_count
        # filled) but NOT listed as a target here: build_hub_edges already owns it as a target,
        # and doit forbids two tasks sharing one target. profiles.npy is the only file this task
        # alone produces. Downstream tasks that need to wait for the in-place rewrite (the tile
        # builders) declare an explicit task_dep on add_elevation instead of relying on a shared
        # target/file_dep link.
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
                "build_trail_tiles.py",
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
                "build_edge_tiles.py",
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
        # task_dep (not just file_dep) on add_elevation: records.npy is rewritten in place by
        # that task but isn't one of its declared targets (see task_add_elevation's comment), so
        # doit's file-hash freshness check alone wouldn't guarantee this task runs after it.
        "task_dep": ["add_elevation"],
        "file_dep": [str(OSM_DIR / "hut_edges" / "records.npy")],
        "targets": [str(OSM_DIR / "hut-edges.pmtiles"), str(OSM_DIR / "hut-edge-stats.json")],
    }


def task_build_start_edge_tiles():
    tiles_cfg = CONFIG.get("hutEdgeTiles", {})
    return {
        "actions": [
            py(
                "build_edge_tiles.py",
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
        "task_dep": ["add_elevation"],  # see task_build_hut_edge_tiles's comment
        "file_dep": [str(OSM_DIR / "start_edges" / "records.npy")],
        "targets": [str(OSM_DIR / "start-edges.pmtiles"), str(OSM_DIR / "start-edge-stats.json")],
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
