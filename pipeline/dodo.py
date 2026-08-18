"""
doit DAG for the OSM hut-graph pipeline (replaces run_all.py).

Setup (inside the alpen-osm conda env):
    pip install doit

Usage:
    doit list                              # show all tasks + up-to-date status
    doit                                   # run everything, idempotently (like old run_all.py)
    doit build_hut_graph                   # run one task + its deps (like --only 6)
    doit fetch_huts build_hut_graph        # several tasks (like --only 5,6)
    doit build_hut_graph --max-edge-km 15  # task with its own flag (like --only 6 -- --max-edge-km 15)
    doit info build_hut_graph              # show why a task would (not) run, without running it

A task always reruns if any file in its file_dep changed (content hash, not mtime - doit hashes
by default) or if pipeline.config.json changed (every task depends on it, so editing the config
invalidates everything downstream of the values it actually touches, same as run_all.py's
config-mtime check but per-task instead of global). Tasks with no target (verify) or whose output
is regenerated every run regardless of inputs (build_hut_graph, add_elevation - see their
docstrings) declare `uptodate: [False]` to force a rerun every time they're selected, matching
run_all.py's original behavior for steps 4/6/8.

CLAUDE.md's "never run a pipeline step without asking" rule applies here exactly as it did to
run_all.py - `doit <task>` / bare `doit` are pipeline-step invocations.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.pipeline import CONFIG_PATH, DATA_DIR, DEM_DIR, OSM_DIR, PUBLIC_DATA_DIR, load_config  # noqa: E402

DOIT_CONFIG = {
    # keeps doit's runtime state out of the tracked half of pipeline/, alongside every other
    # generated/gitignored pipeline artifact (see root CLAUDE.md's data/ vs pipeline/ split)
    "dep_file": str(DATA_DIR / ".doit.db"),
    "default_tasks": [
        "download_extracts", "filter_trails", "merge_trails", "verify_trails",
        "fetch_huts", "fetch_stations_parking", "build_hut_graph",
        "fetch_dem", "build_dem_vrt", "add_elevation",
        "build_trail_tiles", "build_hut_edge_tiles", "copy_public_data",
    ],
}

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG = load_config()
REGION_NAMES = [r["name"] for r in CONFIG["regions"]]

PUBLIC_FILES = [
    "huts.geojson",
    "hut-edges.pmtiles",
    "hut-edge-stats.json",
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


# ---- 06: build hut graph ----------------------------------------------------
# Always reruns when selected (cheap; usually run precisely to pick up a new hyperparameter),
# same as run_all.py. Exposed as doit --params so `doit build_hut_graph --max-edge-km 15` works
# without run_all.py's `--only 6 -- ...` passthrough hack.

def task_build_hut_graph():
    return {
        "actions": [
            f'"{sys.executable}" "{SCRIPT_DIR / "build_hut_graph.py"}"'
            " --max-edge-km %(max_edge_km)s --max-snap-m %(max_snap_m)s"
            " --road-penalty-factor %(road_penalty_factor)s"
        ],
        "params": [
            {"name": "max_edge_km", "long": "max-edge-km", "type": float,
             "default": CONFIG["graph"]["maxEdgeKm"]},
            {"name": "max_snap_m", "long": "max-snap-m", "type": float,
             "default": CONFIG["graph"]["maxSnapM"]},
            {"name": "road_penalty_factor", "long": "road-penalty-factor", "type": float,
             "default": CONFIG["graph"]["roadPenaltyFactor"]},
        ],
        "file_dep": [str(OSM_DIR / "trails.osm.pbf"), str(OSM_DIR / "huts.geojson")],
        "targets": [str(OSM_DIR / "hut-edges.geojson")],
        "uptodate": [False],
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


# ---- 08: add elevation (in-place edit of hut-edges.geojson) ---------------
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
        "task_dep": ["build_hut_graph"],  # same file, not just same mtime - see docstring above
        "file_dep": [str(DEM_DIR / "dem.tif")],
        "targets": [str(OSM_DIR / "hut-edges.geojson")],
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


# ---- 11: build hut-edge vector tiles + stats -------------------------------

def task_build_hut_edge_tiles():
    tiles_cfg = CONFIG.get("hutEdgeTiles", {})
    return {
        "actions": [
            py(
                "build_hut_edge_tiles.py",
                f"--min-zoom {tiles_cfg.get('minZoom', 6)}",
                f"--max-zoom {tiles_cfg.get('maxZoom', 14)}",
                f"--hover-simplify-tolerance-deg {tiles_cfg.get('hoverSimplifyToleranceDeg', 0.0003)}",
            )
        ],
        "file_dep": [str(OSM_DIR / "hut-edges.geojson")],
        "targets": [str(OSM_DIR / "hut-edges.pmtiles"), str(OSM_DIR / "hut-edge-stats.json")],
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
