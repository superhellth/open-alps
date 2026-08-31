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
        # Two filter expressions, not one merged railway=...,highway=... string - osmium
        # tags-filter OR's multiple expression arguments together, keeping a node that matches
        # either. Bus stops overwhelmingly still use the older highway=bus_stop tag in AT/Bavaria
        # OSM data (docs/backlog/access-node-coverage.md).
        "tag_filter": ["n/railway=station,halt", "n/highway=bus_stop"],
        # access/motor_vehicle/barrier/disused/abandoned: same usability-filtering shape as
        # parking below, consumed by filter_start_points.py's is_usable(). network/operator
        # dropped - unused downstream and unread by the frontend (TourSearchPage.tsx only reads
        # properties.name).
        "keep_fields": ["name", "access", "motor_vehicle", "barrier", "disused", "abandoned"],
    },
    {
        "name": "parking",
        "tag_filter": ["nwr/amenity=parking"],
        "keep_fields": ["name", "capacity", "fee", "access", "motor_vehicle", "barrier"],
    },
]


def export_layer(layer: dict, timer: StepTimer) -> None:
    out_path = OSM_DIR / f"{layer['name']}.geojson"
    features = []

    for region in config["regions"]:
        src = OSM_DIR / "raw" / f"{region['name']}-latest.osm.pbf"
        filtered = OSM_DIR / f"{region['name']}-{layer['name']}.osm.pbf"
        print(f"filtering {src} -> {filtered}")
        with timer.step(f"{layer['name']}_tag_filter"):
            subprocess.run(
                ["osmium", "tags-filter", str(src), *layer["tag_filter"],
                 "-o", str(filtered), "--overwrite"],
                check=True,
            )

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
