#!/usr/bin/env python3
"""
Fetches train station and trailhead-parking point locations from OSM, filtered from the raw
region extracts already downloaded by 01-download-extracts.py (no new download), and writes them
as two GeoJSON FeatureCollections - same flat {id?, name, ...} properties shape as 05's
huts.geojson.

osmium export dumps every OSM tag verbatim, which is noisy (source, fixme, survey:date, etc.) -
KEEP_FIELDS below prunes each layer's raw properties down to a fixed field set, mirroring 05's
outFields=id,name approach for the Alpenverein API.

Parking is mapped as ways/polygons (the lot's outline), not points - `--geometry-types point`
makes osmium export emit each polygon's centroid instead of its shape, keeping this layer a plain
Point FeatureCollection like every other layer here.

Usage: python pipeline/05b-fetch-stations-parking.py
Requires osmium-tool on PATH (same as 02-filter-trails.py).
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.pipeline import OSM_DIR, load_config  # noqa: E402

config = load_config()

LAYERS = [
    {
        "name": "stations",
        "tag_filter": "n/railway=station,halt",
        "keep_fields": ["name", "network", "operator"],
    },
    {
        "name": "parking",
        "tag_filter": "nwr/amenity=parking",
        "keep_fields": ["name", "capacity", "fee", "access"],
    },
]


def export_layer(layer: dict) -> None:
    out_path = OSM_DIR / f"{layer['name']}.geojson"
    features = []

    for region in config["regions"]:
        src = OSM_DIR / "raw" / f"{region['name']}-latest.osm.pbf"
        filtered = OSM_DIR / f"{region['name']}-{layer['name']}.osm.pbf"
        print(f"filtering {src} -> {filtered}")
        subprocess.run(
            ["osmium", "tags-filter", str(src), layer["tag_filter"],
             "-o", str(filtered), "--overwrite"],
            check=True,
        )

        result = subprocess.run(
            ["osmium", "export", str(filtered), "-f", "geojson",
             "--geometry-types", "point"],
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


for layer in LAYERS:
    export_layer(layer)
