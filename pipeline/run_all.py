#!/usr/bin/env python3
"""
Runs the OSM hut-graph pipeline end to end, driven by pipeline.config.json.

By default runs all steps 01-08, skipping any step whose output already exists and is newer
than the config file (delete an output, or edit pipeline.config.json, to force it to rerun).

Use --only to run just a subset of steps, e.g. while re-tuning one step at a time. Steps passed
via --only always run (freshness check is skipped for them, since picking a step explicitly
means you want it to run now).

Usage:
    python pipeline/run_all.py                    # full pipeline, idempotent
    python pipeline/run_all.py --only 6            # just rebuild the graph
    python pipeline/run_all.py --only 5,6           # re-fetch huts + rebuild graph
    python pipeline/run_all.py --only 3-6           # merge onward
    python pipeline/run_all.py --only 6 -- --max-edge-km 15   # step 6 with its own flags
    python pipeline/run_all.py --only 12            # just re-copy outputs into huts/public/data/

Any args after a literal `--` are passed through to 06-build-hut-graph.py. Step 8's own flag
(--ele-noise-threshold-m) isn't forwarded here to keep that unambiguous when both are selected
at once - run `python pipeline/08-add-elevation.py --ele-noise-threshold-m 3` directly for
that.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.pipeline import CONFIG_PATH, DEM_DIR, OSM_DIR, PUBLIC_DATA_DIR, load_config  # noqa: E402
from lib.timing import phase  # noqa: E402

# What the app (huts/src/App.jsx, GraphPage.jsx) actually fetches - see root CLAUDE.md "App
# structure". hut-edges.geojson (raw, ~190MB) and the *-test-out/*.mbtiles intermediates are
# deliberately not copied - nothing in huts/ reads them.
PUBLIC_FILES = [
    "huts.geojson",
    "hut-edges.pmtiles",
    "hut-edge-stats.json",
    "trails.pmtiles",
    "stations.geojson",
    "parking.geojson",
]

SCRIPT_DIR = Path(__file__).resolve().parent
STEP_NAMES = {
    1: "download extracts",
    2: "filter trails",
    3: "merge trails",
    4: "verify merged trails",
    5: "fetch huts",
    6: "build hut graph",
    7: "fetch DEM",
    8: "add elevation",
    9: "build trail vector tiles",
    10: "fetch stations & parking",
    11: "build hut-edge vector tiles",
    12: "copy outputs into huts/public/data",
}


def parse_steps(spec: str) -> set[int]:
    try:
        steps = set()
        for part in spec.split(","):
            part = part.strip()
            if "-" in part:
                lo, hi = part.split("-", 1)
                steps.update(range(int(lo), int(hi) + 1))
            else:
                steps.add(int(part))
    except ValueError:
        raise SystemExit(f"--only: can't parse {spec!r} (expected e.g. '6', '1,2', '3-6')")
    unknown = steps - STEP_NAMES.keys()
    if unknown:
        raise SystemExit(f"unknown step(s): {sorted(unknown)} (valid: 1-12)")
    return steps


parser = argparse.ArgumentParser()
parser.add_argument(
    "--only",
    metavar="STEPS",
    help="comma/range list of steps to run, e.g. '6' or '1,2' or '3-6' (default: all, 1-12)",
)
args, passthrough = parser.parse_known_args()
if passthrough and passthrough[0] == "--":
    passthrough = passthrough[1:]

selected = parse_steps(args.only) if args.only else set(STEP_NAMES)
forced = selected if args.only else set()

config = load_config()
config_mtime = CONFIG_PATH.stat().st_mtime


def fresh(path: Path) -> bool:
    return path.exists() and path.stat().st_mtime > config_mtime


def run(script, *script_args):
    subprocess.run([sys.executable, str(SCRIPT_DIR / script), *script_args], check=True)


def step(n, already_fresh, do_run):
    if n not in selected:
        return
    label = f"== {n:02d}: {STEP_NAMES[n]} =="
    if n not in forced and already_fresh():
        print(f"{label} skip (up to date) ==", flush=True)
        return
    print(label, flush=True)
    with phase("run_all", f"{n:02d}-{STEP_NAMES[n]}"):
        do_run()


region_names = [r["name"] for r in config["regions"]]

step(1, lambda: all(fresh(OSM_DIR / "raw" / f"{n}-latest.osm.pbf") for n in region_names),
     lambda: run("01-download-extracts.py"))

step(2, lambda: all(fresh(OSM_DIR / f"{n}-trails.osm.pbf") for n in region_names),
     lambda: run("02-filter-trails.py"))

step(3, lambda: fresh(OSM_DIR / "trails.osm.pbf"),
     lambda: run("03-merge-trails.py"))

step(4, lambda: False,  # verify is a gate, not a cacheable output - always run when selected
     lambda: run("04-verify-trails.py"))

step(5, lambda: fresh(OSM_DIR / "huts.geojson"),
     lambda: run("05-fetch-huts.py"))

step(6, lambda: False,  # cheap enough, and usually run precisely to pick up new hyperparameters
     lambda: run("06-build-hut-graph.py", *passthrough))

def fetch_and_build_dem():
    run("07-fetch-dem.py")
    run("07b-build-dem-vrt.py")


step(7, lambda: fresh(DEM_DIR / "dem.tif"), fetch_and_build_dem)

step(8, lambda: False,  # cheap; usually run precisely to pick up a new elevation threshold
     lambda: run("08-add-elevation.py"))

step(9, lambda: fresh(OSM_DIR / "trails.pmtiles"),
     lambda: run("09-build-trail-tiles.py"))

step(10, lambda: fresh(OSM_DIR / "stations.geojson") and fresh(OSM_DIR / "parking.geojson"),
     lambda: run("05b-fetch-stations-parking.py"))

step(11, lambda: fresh(OSM_DIR / "hut-edges.pmtiles") and fresh(OSM_DIR / "hut-edge-stats.json"),
     lambda: run("11-build-hut-edge-tiles.py"))


def public_copy_fresh() -> bool:
    return all(
        (PUBLIC_DATA_DIR / name).exists()
        and (PUBLIC_DATA_DIR / name).stat().st_mtime >= (OSM_DIR / name).stat().st_mtime
        for name in PUBLIC_FILES
        if (OSM_DIR / name).exists()
    )


def copy_public_data():
    PUBLIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    for name in PUBLIC_FILES:
        src = OSM_DIR / name
        if not src.exists():
            print(f"  skip {name} (not built yet)", flush=True)
            continue
        shutil.copy2(src, PUBLIC_DATA_DIR / name)
        print(f"  {src} -> {PUBLIC_DATA_DIR / name}", flush=True)


step(12, public_copy_fresh, copy_public_data)

if 8 in selected:
    print(f"done -> {OSM_DIR / 'hut-edges.geojson'}", flush=True)
elif 6 in selected:
    print(f"done -> {OSM_DIR / 'hut-edges.geojson'} (no elevation - steps 7/8 not selected)", flush=True)
if 9 in selected:
    print(f"done -> {OSM_DIR / 'trails.pmtiles'}", flush=True)
if 11 in selected:
    print(f"done -> {OSM_DIR / 'hut-edges.pmtiles'}, {OSM_DIR / 'hut-edge-stats.json'}", flush=True)
if 12 in selected:
    print(f"done -> copied into {PUBLIC_DATA_DIR}", flush=True)
