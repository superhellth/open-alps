#!/usr/bin/env python3
"""
Builds a single static PMTiles vector-tile archive from trails.osm.pbf (script 03's output), so
the app can show the full raw OSM trail network as a toggleable layer without a server - PMTiles
is a plain file read via HTTP range requests, same "no backend" shape as every other asset in
this project. See pipeline/README.md's "Displaying the raw OSM trails" section for why this exists
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
    3. `lib.tippecanoe.build_pmtiles()` tiles the filtered file into an mbtiles archive, repacks
       it into a single .pmtiles file, and deletes both intermediates.

Requires, on PATH/importable inside the alpen-osm env:
    - osmium-tool (already a pipeline dependency, see filter_trails.py)
    - orjson (conda-forge: `micromamba install -n alpen-osm -c conda-forge orjson`)
    - the `pmtiles` package (PyPI only, not on conda-forge: `pip install pmtiles` inside the
      alpen-osm env) - imported directly, not shelled out to

tippecanoe has no Windows build on conda-forge (linux-64/osx-64 only), so on Windows this script
shells out to it inside WSL instead, via a separate linux-64 micromamba env there - see
pipeline/README.md's "Displaying the raw OSM trails" section for how that env was created. Native
`tippecanoe` on PATH is used automatically if present (e.g. on Linux/macOS running this directly).

Usage:
    python pipeline/phases/postprocessing/build_trail_tiles.py
    python pipeline/phases/postprocessing/build_trail_tiles.py --min-zoom 6 --max-zoom 14
"""

import argparse
import subprocess
import sys
from pathlib import Path

import orjson

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib.pipeline import OSM_DIR, load_config  # noqa: E402
from lib.tippecanoe import build_pmtiles  # noqa: E402
from lib.timing import StepTimer, phase  # noqa: E402

SCRIPT_NAME = "build_trail_tiles.py"


def filter_trail_feature(feat: dict) -> dict:
    """Strips a GeoJSON feature's properties down to just `highway` - the one tag the frontend
    styles by - in place, returning it for chaining. Every other OSM tag is dead weight in the
    tiles."""
    props = feat.get("properties") or {}
    feat["properties"] = {"highway": props.get("highway")}
    return feat


def export_and_filter(trails_pbf: Path, out_path: Path, timer: StepTimer) -> int:
    """Streams trails_pbf through `osmium export` (piped straight in, never written to disk
    itself, since nothing else needs the full-tag version) and writes each filtered feature as
    one line of GeoJSON-seq to out_path. Returns the feature count."""
    export = subprocess.Popen(
        [
            "osmium", "export", str(trails_pbf),
            "--geometry-types=linestring",
            "-f", "geojsonseq",
            "-o", "-",
        ],
        stdout=subprocess.PIPE,
    )
    n_features = 0
    with timer.step("osmium_export_filter"), open(out_path, "wb") as dst:
        for line in export.stdout:
            line = line.strip(b"\x1e\n")  # RFC 8142 record separator osmium emits per line
            if not line:
                continue
            feat = filter_trail_feature(orjson.loads(line))
            dst.write(orjson.dumps(feat))
            dst.write(b"\n")
            n_features += 1
        returncode = export.wait()
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, export.args)
    return n_features


if __name__ == "__main__":
    config = load_config()
    tiles_config = config.get("trailTiles", {})

    parser = argparse.ArgumentParser()
    parser.add_argument("--trails", default=str(OSM_DIR / "trails.osm.pbf"),
                        help="merged trails.osm.pbf to render as the raw-trail vector-tile layer")
    parser.add_argument("--out", default=str(OSM_DIR / "trails.pmtiles"),
                        help="path to write the output PMTiles archive")
    parser.add_argument("--min-zoom", type=int, default=tiles_config.get("minZoom", 6),
                        help="lowest zoom level tippecanoe builds tiles for (see pipeline.config.json's trailTiles.minZoom)")
    parser.add_argument("--max-zoom", type=int, default=tiles_config.get("maxZoom", 14),
                        help="highest zoom level tippecanoe builds tiles for (see pipeline.config.json's trailTiles.maxZoom)")
    args = parser.parse_args()

    trails_pbf = Path(args.trails)
    filtered = OSM_DIR / "trails.geojsons"  # tippecanoe recognizes this extension as a JSON sequence
    mbtiles = OSM_DIR / "trails.mbtiles"
    out_path = Path(args.out)

    # Splits the three costs: the osmium export + per-feature tag rewrite (ours, Python), tippecanoe
    # (external), and the pmtiles conversion. Without the split a slower run is unattributable.
    timer = StepTimer()

    print(f"streaming {trails_pbf} -> filtering -> {filtered} ...", flush=True)
    n_features = export_and_filter(trails_pbf, filtered, timer)

    print(f"building vector tiles (z{args.min_zoom}-{args.max_zoom}) -> {mbtiles} "
          f"-> {out_path} ...", flush=True)
    build_pmtiles(timer, filtered, mbtiles, out_path, "trails", args.min_zoom, args.max_zoom)

    with phase(SCRIPT_NAME, "build_trail_tiles", n_features=n_features,
               min_zoom=args.min_zoom, max_zoom=args.max_zoom, **timer.as_meta()):
        pass
    print(f"step totals: {timer.summary()}", flush=True)
    print(f"written {out_path}")
