#!/usr/bin/env python3
"""
Fetches hut point locations from the Alpenverein ArcGIS layer, filtered to the bbox in
pipeline.config.json (Austria + Bavaria by default), and writes them as a GeoJSON
FeatureCollection.
Usage: python pipeline/fetch_huts.py
Full field/endpoint reference: docs/alpenverein-api.md
"""

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.pipeline import OSM_DIR, load_config  # noqa: E402

bbox = load_config()["bbox"]
out_path = OSM_DIR / "huts.geojson"

url = (
    "https://services1.arcgis.com/PHS4LHADrqt5glC9/arcgis/rest/services/"
    "AVT_GEO_CAA_HUETTEN_View_P/FeatureServer/0/query"
    "?where=1%3D1&outFields=id,name&returnGeometry=true&outSR=4326"
    "&resultRecordCount=8000&f=json"
)

with urllib.request.urlopen(url) as res:
    data = json.load(res)

features = [
    f
    for f in data["features"]
    if f.get("geometry")
    and bbox["minLng"] <= f["geometry"]["x"] <= bbox["maxLng"]
    and bbox["minLat"] <= f["geometry"]["y"] <= bbox["maxLat"]
]
print(f"huts in bbox: {len(features)}")

geojson = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"id": f["attributes"]["id"], "name": f["attributes"]["name"]},
            "geometry": {"type": "Point", "coordinates": [f["geometry"]["x"], f["geometry"]["y"]]},
        }
        for f in features
    ],
}

with open(out_path, "w", encoding="utf-8") as fh:
    json.dump(geojson, fh)
print(f"written {out_path}")
