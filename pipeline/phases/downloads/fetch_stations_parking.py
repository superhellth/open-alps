#!/usr/bin/env python3
"""
Fetches train station and trailhead-parking point locations from OSM, filtered from the raw
region extracts already downloaded by download_extracts.py (no new download), and writes them
as two GeoJSON FeatureCollections - same flat {id?, name, ...} properties shape as 05's
huts.geojson.

osmium export dumps every OSM tag verbatim, which is noisy (source, fixme, survey:date, etc.) -
KEEP_FIELDS below prunes each layer's raw properties down to a fixed field set, mirroring 05's
outFields=id,name approach for the Alpenverein API.

Parking is mapped as ways/polygons (the lot's outline), not points - `--geometry-types point`
makes osmium export emit each polygon's centroid instead of its shape, keeping this layer a plain
Point FeatureCollection like every other layer here.

Usage: python pipeline/phases/downloads/fetch_stations_parking.py
Requires osmium-tool on PATH (same as filter_trails.py).
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib.pipeline import OSM_DIR, load_config  # noqa: E402
from lib.timing import StepTimer, phase  # noqa: E402

SCRIPT_NAME = "fetch_stations_parking.py"

config = load_config()

LAYERS = [
    {
        "name": "stations",
        # Two pipelines, unioned via `osmium sort` rather than OR'd in one tags-filter call - an
        # AND needs sequential filter passes since `osmium tags-filter` only ORs across the tags
        # named in one call. Both require a name (measured: only ~0.3% of rail station/halt nodes
        # in AT+Bayern lack one, so this is a free no-op there, but it matters for bus stops - see
        # below). The bus branch additionally requires public_transport=platform - NOT applied to
        # rail, since that tag is essentially never present on railway=station/halt nodes in this
        # data (measured 1694->1 AT, 1331->0 Bayern; it marks the platform way/node, not the
        # station node) and would wipe out real stations rather than filter noise. Without the
        # bus branch's public_transport=platform + name narrowing, plain highway=bus_stop pulled
        # in ~5x the prior access-point count (~15.6k -> ~84.5k, see data/timings.jsonl's
        # hub_edge_query meta), most of it unnamed poles/duplicates that inflate
        # build_hub_edges.py's per-cell routing cost roughly linearly in access-point count
        # without adding real trailhead value.
        "tag_filter_pipelines": [
            ["n/railway=station,halt", "n/name"],
            ["n/highway=bus_stop", "n/public_transport=platform", "n/name"],
        ],
        # access/motor_vehicle/barrier/disused/abandoned: same usability-filtering shape as
        # parking below, consumed by filter_start_points.py's is_usable(). network/operator
        # dropped - unused downstream and unread by the frontend (TourSearchPage.tsx only reads
        # properties.name).
        "keep_fields": ["name", "access", "motor_vehicle", "barrier", "disused", "abandoned"],
    },
    {
        "name": "parking",
        "tag_filter_pipelines": [["nwr/amenity=parking"]],
        "keep_fields": ["name", "capacity", "fee", "access", "motor_vehicle", "barrier"],
    },
]


def run_filter_pipeline(src: Path, pipeline: list, tmp_prefix: Path, tmp_files: list) -> Path:
    """Runs `pipeline`'s tag-filter expressions as sequential AND stages - each stage's output
    feeds the next as input, so only objects matching every stage survive - and returns the last
    stage's output path. Every stage's output (named tmp_prefix-s{i}.osm.pbf) is appended to
    `tmp_files` for the caller to clean up once it's done with the pipeline's final output."""
    current = src
    out = current
    for i, expr in enumerate(pipeline):
        out = tmp_prefix.with_name(f"{tmp_prefix.name}-s{i}.osm.pbf")
        subprocess.run(
            ["osmium", "tags-filter", str(current), expr, "-o", str(out), "--overwrite"],
            check=True,
        )
        tmp_files.append(out)
        current = out
    return out


def export_layer(layer: dict, timer: StepTimer) -> None:
    out_path = OSM_DIR / f"{layer['name']}.geojson"
    features = []

    for region in config["regions"]:
        src = OSM_DIR / "raw" / f"{region['name']}-latest.osm.pbf"
        filtered = OSM_DIR / f"{region['name']}-{layer['name']}.osm.pbf"
        print(f"filtering {src} -> {filtered}")
        with timer.step(f"{layer['name']}_tag_filter"):
            pipeline_outputs = []
            tmp_files = []
            for p, pipeline in enumerate(layer["tag_filter_pipelines"]):
                tmp_prefix = OSM_DIR / f"{region['name']}-{layer['name']}-p{p}"
                stage_out = run_filter_pipeline(src, pipeline, tmp_prefix, tmp_files)
                pipeline_outputs.append(stage_out)
            if len(pipeline_outputs) > 1:
                # `osmium sort` merges multiple inputs (like `cat`) AND restores the by-ID
                # ordering `osmium export` requires - a plain `cat` concatenation leaves node IDs
                # out of order (each pipeline's output is independently ID-sorted, but the union
                # of two sorted sequences isn't itself sorted) and `export` refuses to run on that.
                subprocess.run(
                    ["osmium", "sort", *[str(p) for p in pipeline_outputs],
                     "-o", str(filtered), "--overwrite"],
                    check=True,
                )
            else:
                pipeline_outputs[0].replace(filtered)
                tmp_files.remove(pipeline_outputs[0])
            for tmp in tmp_files:
                tmp.unlink(missing_ok=True)

        with timer.step(f"{layer['name']}_export"):
            result = subprocess.run(
                # --add-unique-id=type_id: osmium export emits no id at all by default. With this
                # flag it lands on each Feature's top-level "id" (e.g. "n8091317", type prefix +
                # numeric id) - not inside "properties" - which filter_start_points.py's osm_id
                # depends on to identify every station/parking point.
                ["osmium", "export", str(filtered), "-f", "geojson",
                 "--geometry-types", "point", "--add-unique-id=type_id"],
                check=True, capture_output=True, text=True, encoding="utf-8",
            )
        fc = json.loads(result.stdout)
        for feat in fc["features"]:
            raw_props = feat["properties"]
            feat["properties"] = {k: raw_props[k] for k in layer["keep_fields"] if k in raw_props}
        features.extend(fc["features"])

    print(f"{layer['name']}: {len(features)} features")
    geojson = {"type": "FeatureCollection", "features": features}
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(geojson, fh)
    print(f"written {out_path}")


timer = StepTimer()
with phase(SCRIPT_NAME, "fetch_stations_parking") as meta:
    for layer in LAYERS:
        export_layer(layer, timer)
    meta.update(timer.as_meta())
print(f"step totals: {timer.summary()}", flush=True)
