#!/usr/bin/env python3
"""Fetches the AV's 26 official multi-day tour routes from the AVT_CAA_TOUR_View_L ArcGIS layer
(docs/alpenverein-api.md §3, docs/superpowers/specs/2026-08-29-official-tours-integration-
design.md §0/§1) and resolves each tour's Huettenliste (a comma-separated, IN-ORDER list of hut
GUIDs) against huts.geojson's own `id` property into RECORD_DTYPE's positional hut index
convention (the same index build_hub_edges.py's load_all_hubs uses for TYPE_HUT).

Two output files, not one: tours.json (shipped - client-shaped tour metadata) and
tour_traces.json (internal - the ~3.5MB raw per-tour polyline fragments, consumed only by
match_tour_edges.py, never shipped to the client - that geometry ships matched, via
tour-edges.pmtiles, once match_tour_edges.py has run).

Usage: python pipeline/phases/downloads/fetch_tours.py
"""

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib.oa_geometry import OA_URL_RE  # noqa: E402
from lib.pipeline import OSM_DIR  # noqa: E402
from lib.timing import phase  # noqa: E402

SCRIPT_NAME = "fetch_tours.py"

# Manual overrides for tours whose OA id was found via their own homepage's embedded widget
# (Task 2 of docs/superpowers/plans/2026-08-30-tour-reproducibility.md) or via a direct search of
# alpenvereinaktiv.com for a matching tour name, verified by checking every one of the tour's own
# hutIndices lands within maxHutTraceM of the candidate's geometry (assign_hut_position) before
# trusting it - alpenvereinaktiv.com often has several similarly-named entries (individual stages,
# personal trip logs, alternate variants) for one real-world route, so name matching alone is not
# enough; a rejected candidate (e.g. PHR's "Zillertaler Runde" and "Auf Spurensuche vom Zillertal
# ins Wipptal" each only cover 2 of PHR's 6 huts, SHR's first candidate found was a shorter
# variant missing one hut, and MontafonerHüttenrunde's FIRST candidate found covered only 5 of
# its 9 huts - a second, correct candidate was found afterwards) is left unresolved rather than
# force-matched. PHR's own OA tour (outdooractive.com id
# 7523011, cross-project but the SAME underlying content id resolves via project/alpenverein too)
# was found and IS the right tour by name/region, but its geoJson comes back None because it's a
# paid Outdooractive "proplus" listing (meta.premium.userAccess: False in the raw content) - not
# fixable without a premium API key, so it stays unresolved too.
HOMEPAGE_EMBED_OA_IDS = {
    "KHW": "9027602",
    "BHW": "21729786",
    "IHW": "7749907",
    "STHW": "107992237",
    "SHR": "17872005",
    "Karwendel Höhenweg": "256769252",
    "VT4T": "60696720",
    "KT01": "23684449",
    "TT4T": "17676990",
    "MontafonerHüttenrunde": "12949948",
}


def parse_huettenliste(raw) -> list:
    if not raw:
        return []
    return [g.strip() for g in raw.split(",") if g.strip()]


def resolve_hut_indices(guids: list, hut_id_to_index: dict, tour_short_code: str, gaps: list) -> list:
    """Resolves each GUID to huts.geojson's positional index, in the SAME order as `guids` -
    tour order is meaningful (leg sequence), so this must never reorder or drop entries. An
    unresolvable GUID (hut outside config["bbox"], reclassified to partner_betriebe.geojson, or
    genuinely absent - verified empty against the live layer as of 2026-08-29, so this path is
    defensive) becomes -1 and is recorded in `gaps` - match_tour_edges.py splits the chain at a
    -1 entry rather than silently fusing the two real stages on either side of it into one leg."""
    out = []
    for guid in guids:
        idx = hut_id_to_index.get(guid)
        if idx is None:
            gaps.append({
                "tourShortCode": tour_short_code, "globalId": guid, "reason": "unresolved_hut_guid",
            })
            out.append(-1)
        else:
            out.append(idx)
    return out


def build_tour_records(features: list, hut_id_to_index: dict) -> tuple:
    """Returns (tours, traces, gaps). tours/traces are index-aligned by position - tourId is the
    array index into BOTH lists (same convention as huts.geojson's own feature-array-position
    hut ids), stable for the life of one pipeline run. `#DUMMY` (garbage record, geometry in
    Bolivia, spec §0) is filtered by Kurzbezeichnung, not by a null-name/empty-hut-list heuristic -
    both of those also occur on real tours."""
    tours, traces, gaps = [], [], []
    for f in features:
        a = f["attributes"]
        if a.get("Kurzbezeichnung") == "#DUMMY":
            continue
        guids = parse_huettenliste(a.get("Huettenliste"))
        short_code = a.get("Kurzbezeichnung") or ""
        hut_indices = resolve_hut_indices(guids, hut_id_to_index, short_code, gaps)
        tour_id = len(tours)
        oa_match = OA_URL_RE.search(a.get("Homepage") or "")
        oa_id = oa_match.group(1) if oa_match else HOMEPAGE_EMBED_OA_IDS.get(short_code)
        tours.append({
            "tourId": tour_id,
            "globalId": a.get("GlobalID"),
            "name": a.get("Bezeichnung"),
            "shortCode": a.get("Kurzbezeichnung"),
            "isLoop": bool(a.get("Rundtour")),
            "homepage": a.get("Homepage"),
            "oaId": oa_id,
            "hutIndices": hut_indices,
        })
        traces.append({"tourId": tour_id, "paths": f.get("geometry", {}).get("paths", [])})
    return tours, traces, gaps


if __name__ == "__main__":
    huts_path = OSM_DIR / "huts.geojson"
    with open(huts_path, encoding="utf-8") as fh:
        hut_id_to_index = {
            feat["properties"]["id"]: i
            for i, feat in enumerate(json.load(fh)["features"])
        }

    url = (
        "https://services1.arcgis.com/PHS4LHADrqt5glC9/arcgis/rest/services/"
        "AVT_CAA_TOUR_View_L/FeatureServer/0/query"
        "?where=1%3D1&outFields=*&returnGeometry=true&outSR=4326&resultRecordCount=200&f=json"
    )

    with phase(SCRIPT_NAME, "fetch_tours"):
        with urllib.request.urlopen(url) as res:
            data = json.load(res)

    tours, traces, gaps = build_tour_records(data["features"], hut_id_to_index)
    print(f"tours: {len(tours)}, hut-guid gaps: {len(gaps)}")

    tours_path = OSM_DIR / "tours.json"
    traces_path = OSM_DIR / "tour_traces.json"
    gaps_path = OSM_DIR / "tour-fetch-gaps.json"
    with open(tours_path, "w", encoding="utf-8") as fh:
        json.dump(tours, fh)
    with open(traces_path, "w", encoding="utf-8") as fh:
        json.dump(traces, fh)
    with open(gaps_path, "w", encoding="utf-8") as fh:
        json.dump(gaps, fh)
    print(f"written {tours_path}, {traces_path} and {gaps_path}")
