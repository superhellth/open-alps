#!/usr/bin/env python3
"""
Fetches hut point locations from the Alpenverein ArcGIS layer, filtered to the bbox in
pipeline.config.json (Austria + Bavaria by default), classifies each record, and writes two
GeoJSON FeatureCollections: huts.geojson (real huts, AV-run or not) and partner_betriebe.geojson
(Bergsteigerdörfer partner businesses / ÖAV Vertragshaus - private lodging, not Alpine Club huts;
routed as a separate access-point hub type by filter_start_points.py, see that module's docstring).

classify_hut()'s branch order mirrors, exactly, the Arcade valueExpression on the AV's own ArcGIS
layer's renderer (AVT_GEO_CAA_HUETTEN_View_P/FeatureServer/0's drawingInfo.renderer, recovered
2026-08-28 from a fresh HAR capture of the AV's own map view, docs/caa.alpenverein.at.har) - this
is the AV's own authoritative "Art" classification, not a guess:

    if (kategorie_nr==20 || kategorie_nr==60)
        return "Selbstversorgerhütte";   // Biwak (20) / Jugendherberge-Jugendheim (60)
    else if (verein_nr==8 || verein_nr==5 || verein_nr==3)
        return "AV Hütte";               // ÖAV, DAV, Alpenverein Südtirol
    else if (verein_nr==19 || verein_nr==9 || verein_nr==17 || verein_nr==16)
        return "Partnerbetrieb";         // Bergsteigerdörfer partner / ÖAV Vertragshaus
    else
        return "sonstige Hütte";

Full design rationale, investigation numbers, and the merge-vs-separate-category decision:
docs/superpowers/specs/2026-08-28-hut-classification-design.md.

Usage: python pipeline/phases/downloads/fetch_huts.py
Full field/endpoint reference: docs/alpenverein-api.md
"""

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib.pipeline import OSM_DIR, load_config  # noqa: E402
from lib.timing import phase  # noqa: E402

SCRIPT_NAME = "fetch_huts.py"

_AV_VEREIN_NRS = (8, 5, 3)  # ÖAV, DAV, Alpenverein Südtirol
_PARTNER_VEREIN_NRS = (19, 9, 17, 16)  # Bergsteigerdörfer Partnerbetrieb, ÖAV Vertragshaus
_SELBSTVERSORGER_KATEGORIE_NRS = (20, 60)  # Biwak, Jugendherberge/Jugendheim


def classify_hut(kategorie_nr, verein_nr):
    """Returns (hut_type, serviced). hut_type is "av"/"sonstige" for a real hut, or "partner" for
    a Bergsteigerdörfer partner business (serviced is None in that case - it's routed to
    partner_betriebe.geojson entirely, see split_features). Branch order matches the AV's own
    Arcade classification exactly (module docstring) - do not reorder without checking the source
    again, a future data value could otherwise silently classify differently than the AV's own
    map does."""
    if kategorie_nr in _SELBSTVERSORGER_KATEGORIE_NRS:
        return ("av" if verein_nr in _AV_VEREIN_NRS else "sonstige"), False
    if verein_nr in _AV_VEREIN_NRS:
        return "av", True
    if verein_nr in _PARTNER_VEREIN_NRS:
        return "partner", None
    return "sonstige", True


def split_features(features):
    """Splits ArcGIS features (each {"attributes": {...}, "geometry": {"x", "y"}}) into
    (hut_features, partner_features) - plain GeoJSON Feature dicts, in the input order within
    each list. Hut features carry hutType/serviced/elevation properties; partner features keep
    the same minimal {id, name} shape stations.geojson/parking.geojson already use, with "id" set
    to the ArcGIS layer's OBJECTID (an int) - not the "id" attribute, which is a GUID string huts
    use for their own properties.id and that filter_start_points.py's partner-betrieb loader
    (Task 3) does not expect."""
    huts, partners = [], []
    for f in features:
        a = f["attributes"]
        geometry = {"type": "Point", "coordinates": [f["geometry"]["x"], f["geometry"]["y"]]}
        hut_type, serviced = classify_hut(a.get("kategorie_nr"), a.get("verein_nr"))
        if hut_type == "partner":
            partners.append({
                "type": "Feature",
                "properties": {"id": a["OBJECTID"], "name": a["name"]},
                "geometry": geometry,
            })
        else:
            huts.append({
                "type": "Feature",
                "properties": {
                    "id": a["id"], "name": a["name"], "hutType": hut_type,
                    "serviced": serviced, "elevation": a.get("meereshoehe"),
                },
                "geometry": geometry,
            })
    return huts, partners


def _write_feature_collection(path, features):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": features}, fh)


if __name__ == "__main__":
    config = load_config()
    bbox = config["bbox"]
    huts_out_path = OSM_DIR / "huts.geojson"
    partner_out_path = OSM_DIR / "partner_betriebe.geojson"

    url = (
        "https://services1.arcgis.com/PHS4LHADrqt5glC9/arcgis/rest/services/"
        "AVT_GEO_CAA_HUETTEN_View_P/FeatureServer/0/query"
        "?where=1%3D1&outFields=OBJECTID,id,name,kategorie_nr,verein_nr,meereshoehe"
        "&returnGeometry=true&outSR=4326&resultRecordCount=8000&f=json"
    )

    with phase(SCRIPT_NAME, "fetch_huts"):
        with urllib.request.urlopen(url) as res:
            data = json.load(res)

    features = [
        f
        for f in data["features"]
        if f.get("geometry")
        and bbox["minLng"] <= f["geometry"]["x"] <= bbox["maxLng"]
        and bbox["minLat"] <= f["geometry"]["y"] <= bbox["maxLat"]
    ]
    print(f"records in bbox: {len(features)}")

    hut_features, partner_features = split_features(features)
    print(f"huts: {len(hut_features)}, partner betriebe: {len(partner_features)}")

    _write_feature_collection(huts_out_path, hut_features)
    _write_feature_collection(partner_out_path, partner_features)
    print(f"written {huts_out_path}")
    print(f"written {partner_out_path}")
