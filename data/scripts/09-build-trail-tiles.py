#!/usr/bin/env python3
"""
Builds a single static PMTiles vector-tile archive from trails.osm.pbf (script 03's output), so
the app can show the full raw OSM trail network as a toggleable layer without a server - PMTiles
is a plain file read via HTTP range requests, same "no backend" shape as every other asset in
this project. See data/README.md's "Displaying the raw OSM trails" section for why this exists
instead of shipping GeoJSON (26.5M nodes is too much for the browser) or standing up a tile
server (this project has none, deliberately).

Pipeline:
    1. `osmium export` streams trails.osm.pbf to line-delimited GeoJSON (one LineString per way)
       piped directly into step 2's stdin - never written to disk itself, unlike script 06's
       intermediate files, since nothing else needs this full-tag version.
    2. A line-by-line Python filter pass (reading that pipe) keeps only the `highway` tag per
       feature (the one tag the frontend styles by); every other OSM tag is dead weight in the
       tiles. Uses `orjson` (Rust-backed) rather than stdlib `json` - this loop is the one part
       of the pipeline that's pure single-threaded Python rather than a C/C++ tool, so it's the
       actual bottleneck; osmium export and tippecanoe are both already multi-core-capable C++
       (tippecanoe parallelizes its own tiling internally, no flag needed).
    3. `tippecanoe` builds zoomed vector tiles from the filtered file into an mbtiles archive.
    4. `pmtiles.convert.mbtiles_to_pmtiles` (the PyPI `pmtiles` package's Python API - it has no
       CLI, despite the package name) repackages the mbtiles into one .pmtiles file.

Requires, on PATH/importable inside the alpen-osm env:
    - osmium-tool (already a pipeline dependency, see 02-filter-trails.py)
    - orjson (conda-forge: `micromamba install -n alpen-osm -c conda-forge orjson`)
    - the `pmtiles` package (PyPI only, not on conda-forge: `pip install pmtiles` inside the
      alpen-osm env) - imported directly, not shelled out to

tippecanoe has no Windows build on conda-forge (linux-64/osx-64 only), so on Windows this script
shells out to it inside WSL instead, via a separate linux-64 micromamba env there - see
data/README.md's "Displaying the raw OSM trails" section for how that env was created. Native
`tippecanoe` on PATH is used automatically if present (e.g. on Linux/macOS running this directly).

Usage:
    python data/scripts/09-build-trail-tiles.py
    python data/scripts/09-build-trail-tiles.py --min-zoom 6 --max-zoom 14
"""

import argparse
import platform
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import orjson
from pmtiles.convert import mbtiles_to_pmtiles

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.pipeline import OSM_DIR, load_config  # noqa: E402

config = load_config()
tiles_config = config.get("trailTiles", {})

WSL_MICROMAMBA_ROOT = "~/micromamba"
WSL_MICROMAMBA_BIN = "~/mm/bin/micromamba"
WSL_ENV_NAME = "tippecanoe"


def _to_wsl_path(arg: str) -> str:
    """Translates a Windows absolute path (e.g. E:\\foo\\bar) to its WSL /mnt/ mount equivalent
    (/mnt/e/foo/bar). Leaves anything that isn't a drive-letter path (flags, numbers) untouched."""
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", arg)
    if not m:
        return arg
    drive, rest = m.groups()
    return f"/mnt/{drive.lower()}/{rest.replace(chr(92), '/')}"


def run_tippecanoe(tippecanoe_args):
    if shutil.which("tippecanoe"):
        subprocess.run(["tippecanoe", *tippecanoe_args], check=True)
        return
    if platform.system() != "Windows":
        raise RuntimeError(
            "tippecanoe not found on PATH. Install it (conda-forge on Linux/macOS) - see "
            "data/README.md."
        )
    inner_cmd = (
        f"{WSL_MICROMAMBA_BIN} run -r {WSL_MICROMAMBA_ROOT} -n {WSL_ENV_NAME} tippecanoe "
        + " ".join(shlex.quote(_to_wsl_path(a)) for a in tippecanoe_args)
    )
    subprocess.run(["wsl", "bash", "-lc", inner_cmd], check=True)

parser = argparse.ArgumentParser()
parser.add_argument("--trails", default=str(OSM_DIR / "trails.osm.pbf"))
parser.add_argument("--out", default=str(OSM_DIR / "trails.pmtiles"))
parser.add_argument("--min-zoom", type=int, default=tiles_config.get("minZoom", 6))
parser.add_argument("--max-zoom", type=int, default=tiles_config.get("maxZoom", 14))
args = parser.parse_args()

trails_pbf = Path(args.trails)
filtered = OSM_DIR / "trails.geojsons"  # tippecanoe recognizes this extension as a JSON sequence
mbtiles = OSM_DIR / "trails.mbtiles"
out_path = Path(args.out)

print(f"streaming {trails_pbf} -> filtering -> {filtered} ...")
# osmium export's stdout is piped straight into the filter loop below - no intermediate
# trails.geojsonseq on disk, since nothing else needs the full-tag version. Streams line-by-line
# throughout, so this never holds the full multi-million-way export in memory.
export = subprocess.Popen(
    [
        "osmium", "export", str(trails_pbf),
        "--geometry-types=linestring",
        "-f", "geojsonseq",
        "-o", "-",
    ],
    stdout=subprocess.PIPE,
)
with open(filtered, "wb") as dst:
    for line in export.stdout:
        line = line.strip(b"\x1e\n")  # RFC 8142 record separator osmium emits per line
        if not line:
            continue
        feat = orjson.loads(line)
        props = feat.get("properties") or {}
        feat["properties"] = {"highway": props.get("highway")}
        dst.write(orjson.dumps(feat))
        dst.write(b"\n")
returncode = export.wait()
if returncode != 0:
    raise subprocess.CalledProcessError(returncode, export.args)

print(f"building vector tiles (z{args.min_zoom}-{args.max_zoom}) -> {mbtiles} ...")
run_tippecanoe(
    [
        "-o", str(mbtiles),
        "-l", "trails",
        "-Z", str(args.min_zoom),
        "-z", str(args.max_zoom),
        "--drop-densest-as-needed",
        "--force",
        str(filtered),
    ]
)

print(f"converting {mbtiles} -> {out_path} ...")
mbtiles_to_pmtiles(str(mbtiles), str(out_path), args.max_zoom)

filtered.unlink(missing_ok=True)
mbtiles.unlink(missing_ok=True)
print(f"written {out_path}")
