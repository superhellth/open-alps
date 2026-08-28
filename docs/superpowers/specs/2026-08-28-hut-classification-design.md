# Hut classification (AV / sonstige / Selbstversorger / Partnerbetrieb) design

Date: 2026-08-28
Status: draft, for planning

## Problem

`fetch_huts.py` requests only `id,name` from the Alpenverein ArcGIS hut layer, discarding every
other field. Two problems fall out of that for a usable app:

1. **No serviced/unserviced distinction.** Users planning multi-day hut tours need to know whether
   a hut is staffed (warden, meals, bookable beds) or self-service (Biwak/Jugendherberge — no
   warden, first-come-first-served).
2. **No filtering by AV membership terms.** ~13% of the layer's 1173 records (158) are
   `Partnerbetrieb` — private guesthouses/pensions/apartments enrolled in the Bergsteigerdörfer
   partner program, not Alpine Club huts. They sit at village elevation (median 1191m vs. 1747m for
   genuine non-AV huts), have zero `ohrs_hut_id`/`huettenwirt_name`, and no AV member discount
   applies to them — conflating them with `AV Hütte` misrepresents both to a user planning a route.

## Investigation summary (already done, see conversation)

Live-queried the ArcGIS layer (`outFields=*`) and decoded a freshly re-captured HAR
(`docs/caa.alpenverein.at.har`) of the Alpenverein's own raw map view. That HAR's
`AVT_GEO_CAA_HUETTEN_View_P/FeatureServer/0?f=json` response contains the layer's renderer, whose
`valueExpression` (Arcade) is the AV's own authoritative classification logic:

```js
if (kategorie_nr==20 || kategorie_nr==60)
    return "Selbstversorgerhütte";   // Biwak (20) / Jugendherberge-Jugendheim (60)
else if (verein_nr==8 || verein_nr==5 || verein_nr==3)
    return "AV Hütte";               // ÖAV, DAV, Alpenverein Südtirol
else if (verein_nr==19 || verein_nr==9 || verein_nr==17 || verein_nr==16)
    return "Partnerbetrieb";         // Bergsteigerdörfer partner / ÖAV Vertragshaus
else
    return "sonstige Hütte";
```

Confirmed no filtering exists anywhere in the chain (`definitionExpression` is `null` on the
FeatureServer, the query is `where=1=1`, the web-map item in the HAR only defines basemap layers) —
the AV's own map shows all 1173 records, styled into these 4 buckets, nothing excluded.

Counts: `AV Hütte` 527, `sonstige Hütte` 399, `Partnerbetrieb` 158, `Selbstversorgerhütte` 89.

`sonstige Hütte` was checked by `verein_name` and is predominantly genuine alpine huts run by
clubs the formula doesn't name explicitly (Alpine Association of Slovenia 130, Privat 77, Privat
Südtirol 43, Land Südtirol 27, Club Alpino Italiano 18, Schweizer Alpenclub 10, Naturfreunde
Österreich 10, Liechtensteiner Alpenverein 2) plus a `-`/unlabeled bucket (78) that is mostly real
huts with a small tail of guesthouse-looking entries mixed in. Elevation confirms it's a genuine
hut population (median 1747m, mean 1682m) — not the village-lodging profile `Partnerbetrieb` has.
This noise is accepted as-is (see Decisions).

## Decisions (confirmed with user)

- `AV Hütte` and `sonstige Hütte` stay **separate** categories, not merged — AV membership terms
  (e.g. discounts) apply only to `AV Hütte`, so the distinction is user-facing, not cosmetic.
- `Partnerbetrieb` is **not a hut** — it's reclassified as a new access-point hub type, routed the
  same way `stations.geojson`/`parking.geojson` already are (one-directional access→hut edges),
  reflecting its real role: lodging before/after a route, not a waypoint between huts.
- The small amount of noise in `sonstige Hütte`'s unlabeled tail is accepted, not filtered — matches
  what the AV's own map does, and is small relative to 399 records.

## Design

### 1. `fetch_huts.py`: request more fields, classify, split output

Change `outFields=id,name` to `outFields=id,name,kategorie_nr,verein_nr,meereshoehe`. Add:

```python
def classify_hut(kategorie_nr, verein_nr):
    """Mirrors the AV's own ArcGIS renderer valueExpression's branch order (see this file's
    module docstring for where that came from) - returns (hut_type, serviced) for a hut record,
    or ("partner", None) for a Partnerbetrieb, which is routed to a separate output entirely.
    Branch order matches the Arcade source exactly; empirically Partnerbetrieb records never have
    kategorie_nr 20/60 so the two orderings agree on current data, but keep this order so a
    future data change can't silently diverge from the AV's own classification."""
    if kategorie_nr in (20, 60):
        return ("av" if verein_nr in (8, 5, 3) else "sonstige"), False
    if verein_nr in (8, 5, 3):
        return "av", True
    if verein_nr in (19, 9, 17, 16):
        return "partner", None
    return "sonstige", True
```

Records classifying as `"partner"` are written to a new `partner_betriebe.geojson` (same shape as
`stations.geojson`/`parking.geojson`: `Point` features, minimal properties) instead of
`huts.geojson`. Remaining `huts.geojson` features gain three new properties: `hutType: "av" |
"sonstige"`, `serviced: bool`, `elevation` (from `meereshoehe` — not currently carried at all,
picked up incidentally since the field is now fetched).

### 2. `partner_betriebe.geojson` as a new hub type

New `TYPE_PARTNER = 3` in `pipeline/lib/binfmt.py`, alongside the existing `TYPE_HUT`/
`TYPE_STATION`/`TYPE_PARKING`. This slots into the already-generalized access-point pipeline with
no new special-casing, following the exact pattern `station`/`parking` already use:

- `filter_start_points.py`: add `_load_layer(OSM_DIR / "partner_betriebe.geojson",
  "partner_betrieb")` to the existing station/parking list; extend the `type_code` dict with
  `"partner_betrieb": binfmt.TYPE_PARTNER`.
- `snap_hubs.py`: no change needed — it already iterates `start_points.npy` generically by type.
- `build_hub_edges.py`: routes Partnerbetrieb→hut edges the same one-directional way it already
  does for stations/parking (`start_edges/`). Partnerbetriebe never get hut↔hut edges —
  `hut_edges/records.npy` stays hut-only.
- `build_approach_table.py`'s `_SOURCE_TYPE_NAME` dict and `build_edge_tiles.py`'s `TYPE_PREFIX`
  dict each get a `binfmt.TYPE_PARTNER: "partner_betrieb"` entry, same pattern as the existing two.
- `copy_public_data` (dodo.py): `partner_betriebe.geojson` is a new pipeline output but is **not**
  added to the copied-to-`huts/public/data/` set by this task — it has no consumer yet (see
  Non-goals), same "built but not yet fetched" status the payload docs already describe for other
  fields.

### 3. Docs

Update wherever `TYPE_STATION`/`TYPE_PARKING` are enumerated to also list `TYPE_PARTNER`:
`pipeline/phases/graph_building/README.md`, `pipeline/phases/preprocessing/README.md`,
`pipeline/phases/postprocessing/README.md` (if it enumerates hub types),
`docs/tour-suggestion-payload.md`. Document `huts.geojson`'s new `hutType`/`serviced`/`elevation`
properties wherever its schema is currently described (`docs/alpenverein-api.md`'s Fields table,
noting these are now fetched vs. the ones still dropped).

## Non-goals

- Not re-running any `pipeline/` task — per the project's standing rule, that needs separate
  explicit confirmation after this code change lands.
- Not touching frontend consumption (`GraphPage.jsx`/`App.jsx` filtering or styling by
  `hutType`/`serviced`, or rendering `partner_betriebe.geojson` at all) — ships in the data, not yet
  consumed by any client code, same pattern as `start-edges.pmtiles`/`approaches.*` today.
- Not building a name-pattern noise filter for `sonstige Hütte`'s unlabeled tail (explicit user
  decision — accept the noise).
- Not deciding here how/whether `Selbstversorgerhütte` gets its own `hutType` value vs. staying
  `av`/`sonstige` + `serviced: false` — the design above keeps it as the latter (2 `hutType` values,
  1 orthogonal `serviced` flag) since Selbstversorgerhütte can be either AV- or non-AV-run.

## Follow-up (separate task, not this one)

Once `meereshoehe` is fetched into `huts.geojson`, compare it against the pipeline's own
DEM-sampled hub elevation (`snap_hubs.py`'s `hub_snap.sample_hub_elevations`, persisted per-hub) —
a real second elevation source for the same points is a natural cross-check on DEM sampling
accuracy/artifacts, including revisiting the `vertical_offset` unsnapped-hut cases found earlier in
this conversation (`data/osm/unsnapped_huts.json`).
