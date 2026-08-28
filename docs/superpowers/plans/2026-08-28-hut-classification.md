# Hut Classification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **This repo forbids subagent-driven-development and git worktrees entirely** (see root
> `CLAUDE.md`, "No git worktrees, no subagent-driven development") — execute every task directly,
> in-session, on the current checkout. Do not use `superpowers:subagent-driven-development`
> regardless of what this plan's own template says elsewhere.

**Goal:** Classify Alpenverein huts as `av`/`sonstige` (with a `serviced` flag) vs. reclassifying
`Partnerbetrieb` entries as a new `TYPE_PARTNER` access-point hub, using the AV's own official
classification logic recovered from their ArcGIS layer's renderer.

**Architecture:** `fetch_huts.py` fetches more fields, classifies each record with a pure
`classify_hut()` function, and splits its output into `huts.geojson` (av/sonstige, now carrying
`hutType`/`serviced`/`elevation`) and a new `partner_betriebe.geojson`. The new file slots into the
pipeline's *already-generalized* access-point flow (`filter_start_points.py` →
`snap_hubs.py`/`build_hub_edges.py`, which iterate hub types generically) via one new `binfmt`
constant and small additions to two dicts (`build_approach_table.py`, `build_edge_tiles.py`) that
enumerate hub types by name — no change needed in the actual routing code, which was verified to
never hardcode `TYPE_STATION`/`TYPE_PARKING` specifically.

**Tech Stack:** Python (pixi env `alpen-osm`, run via `pixi run -e default <cmd>` from `pipeline/`),
pytest, doit, numpy.

**Spec:** `docs/superpowers/specs/2026-08-28-hut-classification-design.md`

## Global Constraints

- Do not merge `AV Hütte` and `sonstige Hütte` — they stay distinct `hutType` values (AV membership
  terms apply only to `av`).
- `Partnerbetrieb` is not a hut — reclassified as `TYPE_PARTNER`, routed one-directionally to huts
  like stations/parking, never hut↔hut.
- Accept the noise in `sonstige`'s unlabeled tail — no name-pattern filtering.
- `classify_hut()`'s branch order must exactly mirror the AV's own Arcade `valueExpression` (spec,
  §"Investigation summary"): `kategorie_nr in (20,60)` first, then `verein_nr in (8,5,3)`, then
  `verein_nr in (19,9,17,16)`, else `sonstige`.
- **Never run any `pipeline/` task** (via `doit`, or any script under `phases/`) without first
  asking the user and getting explicit confirmation — even scripts that look cheap (root
  `CLAUDE.md`). This plan's tasks only edit code and add/run unit tests (which use `tmp_path`
  fixtures, not real `data/` files or network calls) — no task here runs `fetch_huts.py`,
  `filter_start_points.py`, or `doit` for real. Actually regenerating `data/osm/huts.geojson` /
  `partner_betriebe.geojson` / `start_points.npy` from live data is a separate, explicitly
  confirmed step after this plan is done (see the end of this document).

---

### Task 1: `binfmt.TYPE_PARTNER`

**Files:**
- Modify: `pipeline/lib/binfmt.py:62-64`
- Test: `pipeline/tests/test_binfmt.py`

**Interfaces:**
- Produces: `binfmt.TYPE_PARTNER = 3` (int), for every later task to import.

- [ ] **Step 1: Write the failing test**

Add to `pipeline/tests/test_binfmt.py`:

```python
def test_type_partner_is_distinct_from_existing_hub_types():
    assert binfmt.TYPE_PARTNER == 3
    assert binfmt.TYPE_PARTNER not in (binfmt.TYPE_HUT, binfmt.TYPE_STATION, binfmt.TYPE_PARKING)
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `pipeline/`): `pixi run -e default pytest tests/test_binfmt.py -k type_partner -v`
Expected: FAIL with `AttributeError: module 'lib.binfmt' has no attribute 'TYPE_PARTNER'`

- [ ] **Step 3: Implement**

In `pipeline/lib/binfmt.py`, change:

```python
TYPE_HUT = 0
TYPE_STATION = 1
TYPE_PARKING = 2
```

to:

```python
TYPE_HUT = 0
TYPE_STATION = 1
TYPE_PARKING = 2
# Bergsteigerdörfer partner businesses / ÖAV Vertragshaus (docs/superpowers/specs/
# 2026-08-28-hut-classification-design.md) - private guesthouses/pensions, not Alpine Club huts.
# Routed one-directionally to huts exactly like TYPE_STATION/TYPE_PARKING (fetch_huts.py splits
# them out of huts.geojson into partner_betriebe.geojson; filter_start_points.py loads that file
# as a third access-point layer). start_points.npy's "osm_id" field holds the ArcGIS layer's
# OBJECTID for this type, not a real OSM id - see filter_start_points.py's _load_layer docstring.
TYPE_PARTNER = 3
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pixi run -e default pytest tests/test_binfmt.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/lib/binfmt.py pipeline/tests/test_binfmt.py
git commit -m "feat(pipeline): Add TYPE_PARTNER hub type for Bergsteigerdörfer partner businesses"
```

---

### Task 2: `fetch_huts.py` — `classify_hut()` and `split_features()`

**Files:**
- Modify: `pipeline/phases/downloads/fetch_huts.py`
- Create: `pipeline/tests/test_fetch_huts.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (pure functions, no `binfmt` dependency — hub type mapping
  happens later in `filter_start_points.py`, Task 3).
- Produces: `classify_hut(kategorie_nr: int | None, verein_nr: int | None) -> tuple[str, bool | None]`
  returning `(hut_type, serviced)` where `hut_type` is `"av"`/`"sonstige"`/`"partner"`, and
  `serviced` is `True`/`False` for huts, `None` for `"partner"`.
  `split_features(features: list[dict]) -> tuple[list[dict], list[dict]]` returning
  `(hut_geojson_features, partner_geojson_features)` — both plain GeoJSON `Feature` dicts.
  Later tasks (Task 3) read `partner_betriebe.geojson`'s `properties.id` as the ArcGIS `OBJECTID`.

- [ ] **Step 1: Write the failing tests**

Create `pipeline/tests/test_fetch_huts.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from downloads.fetch_huts import classify_hut, split_features  # noqa: E402


def test_biwak_under_oeav_is_av_and_unserviced():
    # kategorie_nr 20 = Biwak, verein_nr 8 = ÖAV
    assert classify_hut(kategorie_nr=20, verein_nr=8) == ("av", False)


def test_biwak_under_slovenia_is_sonstige_and_unserviced():
    # kategorie_nr 20 = Biwak, verein_nr 20 = Alpine Association of Slovenia (not AV/DAV/AVS)
    assert classify_hut(kategorie_nr=20, verein_nr=20) == ("sonstige", False)


def test_jugendherberge_is_unserviced_too():
    # kategorie_nr 60 = Jugendherberge/Jugendheim, same Selbstversorger bucket as Biwak
    assert classify_hut(kategorie_nr=60, verein_nr=5) == ("av", False)


def test_dav_hut_is_av_and_serviced():
    assert classify_hut(kategorie_nr=40, verein_nr=5) == ("av", True)


def test_oeav_and_avs_are_also_av():
    assert classify_hut(kategorie_nr=30, verein_nr=8)[0] == "av"
    assert classify_hut(kategorie_nr=30, verein_nr=3)[0] == "av"


def test_bergsteigerdoerfer_partner_is_partner_with_no_serviced_flag():
    assert classify_hut(kategorie_nr=100, verein_nr=19) == ("partner", None)


def test_oeav_vertragshaus_is_also_partner():
    assert classify_hut(kategorie_nr=1, verein_nr=9) == ("partner", None)


def test_unrecognized_club_is_sonstige_and_serviced():
    # e.g. Privat (verein_nr 14), Club Alpino Italiano (4), Schweizer Alpenclub (10)
    assert classify_hut(kategorie_nr=30, verein_nr=14) == ("sonstige", True)


def test_split_features_routes_partner_to_second_list_with_minimal_properties():
    features = [
        {"attributes": {"id": "{GUID-1}", "OBJECTID": 501, "name": "Bielefelder Hütte",
                         "kategorie_nr": 40, "verein_nr": 5, "meereshoehe": 2112},
         "geometry": {"x": 10.9, "y": 47.2}},
        {"attributes": {"id": "{GUID-2}", "OBJECTID": 502, "name": "Gasthof Alpenrose",
                         "kategorie_nr": 100, "verein_nr": 19, "meereshoehe": 1150},
         "geometry": {"x": 11.5, "y": 47.3}},
    ]

    huts, partners = split_features(features)

    assert len(huts) == 1 and len(partners) == 1
    assert huts[0]["properties"] == {
        "id": "{GUID-1}", "name": "Bielefelder Hütte", "hutType": "av",
        "serviced": True, "elevation": 2112,
    }
    assert partners[0]["properties"] == {"id": 502, "name": "Gasthof Alpenrose"}
    assert partners[0]["geometry"] == {"type": "Point", "coordinates": [11.5, 47.3]}


def test_split_features_preserves_input_order_within_each_list():
    features = [
        {"attributes": {"id": "a", "OBJECTID": 1, "name": "Hut A", "kategorie_nr": 30,
                         "verein_nr": 5, "meereshoehe": 2000},
         "geometry": {"x": 10.0, "y": 47.0}},
        {"attributes": {"id": "b", "OBJECTID": 2, "name": "Partner B", "kategorie_nr": 100,
                         "verein_nr": 19, "meereshoehe": 1000},
         "geometry": {"x": 10.1, "y": 47.1}},
        {"attributes": {"id": "c", "OBJECTID": 3, "name": "Hut C", "kategorie_nr": 30,
                         "verein_nr": 8, "meereshoehe": 2200},
         "geometry": {"x": 10.2, "y": 47.2}},
    ]

    huts, partners = split_features(features)

    assert [h["properties"]["name"] for h in huts] == ["Hut A", "Hut C"]
    assert [p["properties"]["name"] for p in partners] == ["Partner B"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `pipeline/`): `pixi run -e default pytest tests/test_fetch_huts.py -v`
Expected: FAIL with `ImportError: cannot import name 'classify_hut'` (module doesn't export it yet)

- [ ] **Step 3: Implement**

Replace the whole body of `pipeline/phases/downloads/fetch_huts.py` with:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pixi run -e default pytest tests/test_fetch_huts.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/phases/downloads/fetch_huts.py pipeline/tests/test_fetch_huts.py
git commit -m "feat(pipeline): Classify huts as av/sonstige/partner, split Partnerbetrieb into a separate file"
```

---

### Task 3: `filter_start_points.py` — load `partner_betriebe.geojson` as a third layer

**Files:**
- Modify: `pipeline/phases/preprocessing/filter_start_points.py`
- Modify: `pipeline/tests/test_filter_start_points.py`

**Interfaces:**
- Consumes: `binfmt.TYPE_PARTNER` (Task 1); `partner_betriebe.geojson`'s shape from Task 2
  (`properties: {"id": <int OBJECTID>, "name": <str>}`).
- Produces: `_load_layer(path, point_type, id_from_properties=False)` — new keyword param, default
  preserves existing OSM-export behavior; `start_points.npy` (Task 1's `TYPE_PARTNER`) and
  `start_points_id_table.json` now include `partner_betrieb` entries when run for real.

- [ ] **Step 1: Write the failing test**

Add to `pipeline/tests/test_filter_start_points.py`:

```python
def test_load_layer_reads_id_from_properties_for_non_osm_sources(tmp_path):
    # partner_betriebe.geojson (fetch_huts.py, Task 2) is not OSM data - id is a plain int
    # already sitting in properties["id"] (the ArcGIS layer's OBJECTID), not a "n12345"-shaped
    # top-level Feature id the way stations/parking (osmium export) have.
    fc = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature",
             "geometry": {"type": "Point", "coordinates": [11.5, 47.3]},
             "properties": {"id": 502, "name": "Gasthof Alpenrose"}},
        ],
    }
    path = tmp_path / "partner_betriebe.geojson"
    path.write_text(json.dumps(fc), encoding="utf-8")

    points = _load_layer(path, "partner_betrieb", id_from_properties=True)

    assert len(points) == 1
    assert points[0]["osm_id"] == 502
    assert points[0]["type"] == "partner_betrieb"
    assert points[0]["lon"] == 11.5 and points[0]["lat"] == 47.3


def test_default_id_from_properties_is_false_existing_osm_behavior_unchanged(tmp_path):
    # regression: Task 3 must not change the default path used by stations.geojson/parking.geojson
    fc = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "id": "n8091317",
             "geometry": {"type": "Point", "coordinates": [16.31, 48.21]},
             "properties": {"name": "Wien Ottakring"}},
        ],
    }
    path = tmp_path / "stations.geojson"
    path.write_text(json.dumps(fc), encoding="utf-8")

    points = _load_layer(path, "station")

    assert points[0]["osm_id"] == 8091317
```

(`test_filter_start_points.py` already imports `json` at the top of the file for its own
`test_load_layer_reads_top_level_feature_id(tmp_path)` test, so no new import is needed.)

- [ ] **Step 2: Run tests to verify they fail**

Run (from `pipeline/`): `pixi run -e default pytest tests/test_filter_start_points.py -k "id_from_properties" -v`
Expected: FAIL with `TypeError: _load_layer() got an unexpected keyword argument 'id_from_properties'`

- [ ] **Step 3: Implement**

In `pipeline/phases/preprocessing/filter_start_points.py`, replace `_load_layer`:

```python
def _load_layer(path: Path, point_type: str, id_from_properties: bool = False) -> list:
    """id_from_properties=False (default - stations/parking, fetch_stations_parking.py's osmium
    export --add-unique-id=type_id): the id is on the Feature itself, OSM-export shaped
    ("n8091317" - type-prefix char + numeric id), not inside "properties" - properties only ever
    holds the tag fields KEEP_FIELDS lets through.

    id_from_properties=True (partner_betriebe.geojson, from fetch_huts.py/the Alpenverein ArcGIS
    layer - not OSM data at all): the id is a plain int already sitting in properties["id"] (the
    ArcGIS layer's OBJECTID, see fetch_huts.py's split_features), no prefix character to strip."""
    with open(path, encoding="utf-8") as f:
        fc = json.load(f)
    points = []
    for feat in fc["features"]:
        if id_from_properties:
            raw_id = feat.get("properties", {}).get("id")
            osm_id = None if raw_id is None else int(raw_id)
        else:
            raw_id = feat.get("id")
            osm_id = None if raw_id is None else int(raw_id[1:])
        if osm_id is None:
            continue
        lon, lat = feat["geometry"]["coordinates"]
        points.append({
            "lon": lon, "lat": lat, "osm_id": osm_id, "type": point_type,
            "properties": feat.get("properties", {}),
        })
    return points
```

Then in the `if __name__ == "__main__":` block, change:

```python
        all_points = (
            _load_layer(OSM_DIR / "stations.geojson", "station")
            + _load_layer(OSM_DIR / "parking.geojson", "parking")
        )
```

to:

```python
        all_points = (
            _load_layer(OSM_DIR / "stations.geojson", "station")
            + _load_layer(OSM_DIR / "parking.geojson", "parking")
            + _load_layer(OSM_DIR / "partner_betriebe.geojson", "partner_betrieb",
                          id_from_properties=True)
        )
```

and:

```python
        type_code = {"station": binfmt.TYPE_STATION, "parking": binfmt.TYPE_PARKING}
```

to:

```python
        type_code = {
            "station": binfmt.TYPE_STATION, "parking": binfmt.TYPE_PARKING,
            "partner_betrieb": binfmt.TYPE_PARTNER,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pixi run -e default pytest tests/test_filter_start_points.py -v`
Expected: all PASS (including the pre-existing tests — confirms the default-arg change is
backward compatible)

- [ ] **Step 5: Commit**

```bash
git add pipeline/phases/preprocessing/filter_start_points.py pipeline/tests/test_filter_start_points.py
git commit -m "feat(pipeline): Load partner_betriebe.geojson as a third start-point layer"
```

---

### Task 4: `build_approach_table.py` — recognize `TYPE_PARTNER`

**Files:**
- Modify: `pipeline/phases/postprocessing/build_approach_table.py:45`
- Modify: `pipeline/tests/test_build_approach_table.py`

**Interfaces:**
- Consumes: `binfmt.TYPE_PARTNER` (Task 1).
- Produces: `_SOURCE_TYPE_NAME` now maps `TYPE_PARTNER -> "partner_betrieb"`, so
  `select_approaches` no longer silently drops `TYPE_PARTNER` records (today it drops any
  `from_type` not in the dict — see `type_name is None: continue` right after the lookup).

- [ ] **Step 1: Write the failing test**

Add to `pipeline/tests/test_build_approach_table.py`, using the file's existing `_record`/
`_records` helpers (defined near the top of that file — `_record(from_id, from_type, to_id,
distance_m, ascent_m, descent_m, variant=binfmt.VARIANT_FAST_ANY)`, `_records(rows)`):

```python
def test_partner_betrieb_source_type_is_not_dropped():
    records = _records([_record(1, binfmt.TYPE_PARTNER, 7, 1000.0, 50.0, 20.0)])

    rows = select_approaches(records, id_table={"partner_betrieb": {"1": {"access": None}}}, k=3)

    assert any(r["start_id"] == 1 for r in rows)
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `pipeline/`): `pixi run -e default pytest tests/test_build_approach_table.py -k partner_betrieb -v`
Expected: FAIL — `rows` is empty (currently dropped: `_SOURCE_TYPE_NAME.get(int(r["from_type"]))`
returns `None` for `TYPE_PARTNER`, hitting the `if type_name is None: continue` in
`select_approaches`)

- [ ] **Step 3: Implement**

In `pipeline/phases/postprocessing/build_approach_table.py`, change:

```python
_SOURCE_TYPE_NAME = {binfmt.TYPE_PARKING: "parking", binfmt.TYPE_STATION: "station"}
```

to:

```python
_SOURCE_TYPE_NAME = {
    binfmt.TYPE_PARKING: "parking", binfmt.TYPE_STATION: "station",
    binfmt.TYPE_PARTNER: "partner_betrieb",
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pixi run -e default pytest tests/test_build_approach_table.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/phases/postprocessing/build_approach_table.py pipeline/tests/test_build_approach_table.py
git commit -m "feat(pipeline): Include partner_betrieb approaches in the approach table"
```

---

### Task 5: `build_edge_tiles.py` — recognize `TYPE_PARTNER`

**Files:**
- Modify: `pipeline/phases/postprocessing/build_edge_tiles.py:30`
- Modify: `pipeline/tests/test_build_edge_tiles.py`

**Interfaces:**
- Consumes: `binfmt.TYPE_PARTNER` (Task 1).
- Produces: `TYPE_PREFIX` now maps `TYPE_PARTNER -> "partner_betrieb"`.

- [ ] **Step 1: Write the failing test**

`pipeline/tests/test_build_edge_tiles.py` doesn't reference `TYPE_PREFIX` today — it only tests
`rdp_keep_indices` and `build_stats` (the latter builds its own `binfmt.RECORD_DTYPE` row directly,
see `test_build_stats_resolves_ids_via_id_table` in that file). Add a standalone dict-membership
test — `TYPE_PREFIX` is module-level, no fixture needed:

```python
def test_type_prefix_includes_partner_betrieb():
    from postprocessing.build_edge_tiles import TYPE_PREFIX

    assert TYPE_PREFIX[binfmt.TYPE_PARTNER] == "partner_betrieb"
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `pipeline/`): `pixi run -e default pytest tests/test_build_edge_tiles.py -k type_prefix -v`
Expected: FAIL with `KeyError: 3`

- [ ] **Step 3: Implement**

In `pipeline/phases/postprocessing/build_edge_tiles.py`, change:

```python
TYPE_PREFIX = {binfmt.TYPE_HUT: "hut", binfmt.TYPE_STATION: "station", binfmt.TYPE_PARKING: "parking"}
```

to:

```python
TYPE_PREFIX = {
    binfmt.TYPE_HUT: "hut", binfmt.TYPE_STATION: "station", binfmt.TYPE_PARKING: "parking",
    binfmt.TYPE_PARTNER: "partner_betrieb",
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pixi run -e default pytest tests/test_build_edge_tiles.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/phases/postprocessing/build_edge_tiles.py pipeline/tests/test_build_edge_tiles.py
git commit -m "feat(pipeline): Include partner_betrieb in edge-tile type prefixes"
```

---

### Task 6: `dodo.py` wiring

**Files:**
- Modify: `pipeline/dodo.py` (`task_fetch_huts`, `task_filter_start_points`)
- Modify: `pipeline/tests/test_dodo_wiring.py`

**Interfaces:**
- Consumes: nothing new — just wires existing task functions to the new file.
- Produces: `task_fetch_huts()["targets"]` includes `partner_betriebe.geojson`;
  `task_filter_start_points()["file_dep"]` includes it too, so a doit run correctly reruns
  `filter_start_points` whenever `fetch_huts` produces a new `partner_betriebe.geojson`.

- [ ] **Step 1: Write the failing tests**

Add to `pipeline/tests/test_dodo_wiring.py`:

```python
def test_fetch_huts_targets_include_partner_betriebe():
    targets = dodo.task_fetch_huts()["targets"]
    assert any(t.endswith("partner_betriebe.geojson") for t in targets)


def test_filter_start_points_depends_on_partner_betriebe():
    deps = dodo.task_filter_start_points()["file_dep"]
    assert any(d.endswith("partner_betriebe.geojson") for d in deps)
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `pipeline/`): `pixi run -e default pytest tests/test_dodo_wiring.py -k partner_betriebe -v`
Expected: both FAIL (`assert any(...)` is `False`)

- [ ] **Step 3: Implement**

In `pipeline/dodo.py`, in `task_fetch_huts()`, change:

```python
        "targets": [rel(OSM_DIR / "huts.geojson")],
```

to:

```python
        "targets": [rel(OSM_DIR / "huts.geojson"), rel(OSM_DIR / "partner_betriebe.geojson")],
```

In `task_filter_start_points()`, change:

```python
        "file_dep": [
            rel(OSM_DIR / "huts.geojson"), rel(OSM_DIR / "stations.geojson"),
            rel(OSM_DIR / "parking.geojson"),
        ],
```

to:

```python
        "file_dep": [
            rel(OSM_DIR / "huts.geojson"), rel(OSM_DIR / "stations.geojson"),
            rel(OSM_DIR / "parking.geojson"), rel(OSM_DIR / "partner_betriebe.geojson"),
        ],
```

Leave `PUBLIC_FILES` (near the top of `dodo.py`) unmodified — `partner_betriebe.geojson` is not
added to it, per the spec's Non-goals (no frontend consumer yet, same "built but not shipped"
status other pipeline outputs already have).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pixi run -e default pytest tests/test_dodo_wiring.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/dodo.py pipeline/tests/test_dodo_wiring.py
git commit -m "feat(pipeline): Wire partner_betriebe.geojson into the fetch_huts/filter_start_points DAG edge"
```

---

### Task 7: Documentation

**Files:**
- Modify: `docs/alpenverein-api.md` (Fields table, §1)
- Modify: `pipeline/phases/preprocessing/README.md:55`
- Modify: `pipeline/phases/graph_building/README.md:148`
- Modify: `docs/tour-suggestion-payload.md` (§6, §8)

No tests — documentation only. Verify by rereading each changed section for accuracy against the
code from Tasks 1-6.

- [ ] **Step 1: `docs/alpenverein-api.md`**

In the `### Fields` table (§1), the row `| kategorie_nr` / kategorie | int / string | | |` already
lists the field but doesn't say it's fetched — add a note. Change:

```
| `kategorie_nr` / `kategorie` | int / string | |
```

to:

```
| `kategorie_nr` / `kategorie` | int / string | `kategorie_nr` is fetched by `fetch_huts.py` and drives its hut/Selbstversorger/Partnerbetrieb classification (`docs/superpowers/specs/2026-08-28-hut-classification-design.md`); `kategorie` (the string label) is not fetched. |
```

and the `verein_nr` row:

```
| `verein_nr` | int | club number — **this is the OHRS `tenantCode`** (8 = ÖAV, 5 = DAV) |
```

to:

```
| `verein_nr` | int | club number — **this is the OHRS `tenantCode`** (8 = ÖAV, 5 = DAV, 3 = Alpenverein Südtirol). Fetched by `fetch_huts.py` and drives its classification alongside `kategorie_nr` — see `docs/superpowers/specs/2026-08-28-hut-classification-design.md` for the full `verein_nr`/`kategorie_nr` → `hutType` table. |
```

and `meereshoehe`:

```
| `meereshoehe` | int | elevation, m |
```

to:

```
| `meereshoehe` | int | elevation, m. Fetched by `fetch_huts.py` since 2026-08-28 and shipped as `huts.geojson`'s `elevation` property; `0` means missing (not sea level) — a handful of records have no value entered. |
```

Add a new subsection after the Fields table, before `Related layer referenced by the app`:

```markdown
### Hut classification

`fetch_huts.py` fetches `kategorie_nr`/`verein_nr` (alongside `id`/`name`/`meereshoehe`) and
classifies every record using logic recovered from the AV's own ArcGIS layer renderer (an Arcade
`valueExpression`, decoded from a HAR capture of the raw map view — see
`docs/superpowers/specs/2026-08-28-hut-classification-design.md` for the full recovery and the
investigation numbers behind it). Records classified `"partner"` (Bergsteigerdörfer partner
businesses, private lodging — not Alpine Club huts) are written to `partner_betriebe.geojson`
instead of `huts.geojson`, and routed through the pipeline as an access-point hub type
(`binfmt.TYPE_PARTNER`) alongside stations/parking, not as a hut.
```

- [ ] **Step 2: `pipeline/phases/preprocessing/README.md`**

Change:

```
  - `data/osm/start_points.npy` — structured array `(lon: f8, lat: f8, osm_id: i8, type: u1)`,
    `type` is `binfmt.TYPE_STATION` (1) / `binfmt.TYPE_PARKING` (2).
```

to:

```
  - `data/osm/start_points.npy` — structured array `(lon: f8, lat: f8, osm_id: i8, type: u1)`,
    `type` is `binfmt.TYPE_STATION` (1) / `binfmt.TYPE_PARKING` (2) / `binfmt.TYPE_PARTNER` (3,
    Bergsteigerdörfer partner businesses from `partner_betriebe.geojson` — `docs/superpowers/specs/
    2026-08-28-hut-classification-design.md`). For `TYPE_PARTNER`, `osm_id` holds the ArcGIS
    layer's `OBJECTID`, not a real OSM id.
```

- [ ] **Step 3: `pipeline/phases/graph_building/README.md`**

Change:

```
i4)` — `from_type`/`to_type` are `binfmt.TYPE_HUT` (0) / `TYPE_STATION` (1) / `TYPE_PARKING` (2);
```

to:

```
i4)` — `from_type`/`to_type` are `binfmt.TYPE_HUT` (0) / `TYPE_STATION` (1) / `TYPE_PARKING` (2) /
`TYPE_PARTNER` (3, added `docs/superpowers/specs/2026-08-28-hut-classification-design.md` —
Bergsteigerdörfer partner businesses, routed one-directionally to huts exactly like
stations/parking, never hut↔hut);
```

- [ ] **Step 4: `docs/tour-suggestion-payload.md`**

In §6, change:

```
**Approach table** (`approaches.bin`, columns per `approaches.json`'s `columns` manifest):
`hut_id` (u2), `start_id` (u8 — raw OSM node id, exceeds u4 range), `source_type` (u1, `binfmt.TYPE_PARKING`/`TYPE_STATION`),
```

to:

```
**Approach table** (`approaches.bin`, columns per `approaches.json`'s `columns` manifest):
`hut_id` (u2), `start_id` (u8 — a raw OSM node id for `TYPE_PARKING`/`TYPE_STATION` rows, or the
Alpenverein ArcGIS layer's `OBJECTID` for `TYPE_PARTNER` rows — same field, two different id
spaces depending on `source_type`, exceeds u4 range either way), `source_type` (u1,
`binfmt.TYPE_PARKING`/`TYPE_STATION`/`TYPE_PARTNER` — the last added
`docs/superpowers/specs/2026-08-28-hut-classification-design.md`),
```

In §8 ("Hut metadata"), change:

```
Already shipped as `huts.geojson` (unchanged by this backend) — this payload's `hut_ids` /
`from_id`/`to_id` indices join back onto it by array position, not by any new id scheme.
```

to:

```
Already shipped as `huts.geojson` — this payload's `hut_ids` / `from_id`/`to_id` indices join back
onto it by array position, not by any new id scheme. `huts.geojson` itself gained `hutType`
(`"av"`/`"sonstige"`), `serviced` (bool), and `elevation` properties on 2026-08-28
(`docs/superpowers/specs/2026-08-28-hut-classification-design.md`) — a separate, unrelated change
from this backend, noted here only because a client reading this payload will likely also read
those fields off the huts it joins onto.
```

- [ ] **Step 5: Commit**

```bash
git add docs/alpenverein-api.md pipeline/phases/preprocessing/README.md \
  pipeline/phases/graph_building/README.md docs/tour-suggestion-payload.md
git commit -m "docs: Document hutType/serviced/elevation fields and TYPE_PARTNER"
```

---

## Self-review notes (already applied above)

- **Spec coverage:** §1 (fields/classify) → Task 2. §2 (TYPE_PARTNER + wiring) → Tasks 1, 3, 4, 5,
  6. §3 (docs) → Task 7. Non-goals (no pipeline run, no frontend, no noise filter, no
  Selbstversorger-as-separate-hutType) are respected — no task touches `GraphPage.jsx`/`App.jsx`,
  adds a name filter, or runs any `phases/` script for real.
- **id scheme snag caught during planning, not left as a placeholder:** the spec's §2 didn't
  address that `partner_betriebe.geojson` can't reuse `_load_layer`'s OSM-id-parsing convention
  (huts use a GUID `id`, not an OSM-shaped one) — resolved in Task 2/3 by using the ArcGIS
  `OBJECTID` as the numeric id and adding `_load_layer`'s `id_from_properties` parameter, with a
  regression test (Task 3) proving the existing stations/parking path is unaffected.
- **Type consistency:** `classify_hut`'s return shape (`tuple[str, bool | None]`) and
  `split_features`'s output (`tuple[list[dict], list[dict]]`) are used identically in Task 2's
  implementation and tests. `binfmt.TYPE_PARTNER` (Task 1) is the same symbol imported in Tasks 3,
  4, 5, unchanged.

## After this plan: regenerating real data (separate, explicit step)

This plan only changes code and adds unit tests — none of its steps fetch real data or run a
pipeline task. Once all 7 tasks are done and committed, actually regenerating
`data/osm/huts.geojson` / `partner_betriebe.geojson` / `start_points.npy` (by running
`fetch_huts.py`, `filter_start_points.py`, or `doit fetch_huts filter_start_points`) requires
asking the user first, per root `CLAUDE.md`'s standing rule — do not run any of these as part of
"finishing" this plan.
