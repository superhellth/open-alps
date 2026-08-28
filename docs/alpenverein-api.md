# Alpenverein hut data — API reference

Reverse-engineered from `caa.alpenverein.at.har` (network capture of
<https://caa.alpenverein.at/service/bettencheck.html>, the "Bettencheck" availability tool) and
from its decoded app bundle `static/js/index-BR4qdKga.js`.

Two independent backends:

| Data | Backend |
| --- | --- |
| Hut master data + coordinates | ArcGIS Online hosted feature layer |
| Bed availability | OHRS (hut-reservation.org), via a PHP proxy on caa.alpenverein.at |

Join key between them: `ohrs_hut_id` (string on the ArcGIS side, integer in OHRS responses).

---

## 1. Hut locations — ArcGIS Feature Service

Base:

```
https://services1.arcgis.com/PHS4LHADrqt5glC9/ArcGIS/rest/services/AVT_GEO_CAA_HUETTEN_View_P/FeatureServer/0
```

**Auth: none.** No `Authorization` header, no `token=` param, no cookies anywhere in the capture;
`sharing/rest/portals/self` returns `user: null`. Public layer. The browser sends
`Referer: https://caa.alpenverein.at/` — not required in practice, but pass it if a request is
ever rejected.

### Fetch all huts

```
GET {base}/query
  ?f=json                    # site itself uses f=pbf; json is easier
  &where=1%3D1
  &outFields=*
  &outSR=4326                # site uses 102100 (Web Mercator)
  &returnGeometry=true
  &resultRecordCount=8000    # layer maxRecordCount is 2000; factor override below
  &orderByFields=OBJECTID%20ASC
```

~1173 point features, extent roughly lon 4.97–16.40 / lat 45.30–52.96 (Alps + Germany).
The site's actual call adds `f=pbf&cacheHint=true&maxRecordCountFactor=4&resultOffset=0`.

`returnCountOnly=true` gives count + extent cheaply.

### Fields

| Field | Type | Notes |
| --- | --- | --- |
| `OBJECTID` | oid | |
| `id` | string | GUID-ish hut id used in URL params (`cabinIds`) |
| `verein_nr` | int | club number — **this is the OHRS `tenantCode`** (8 = ÖAV, 5 = DAV, 3 = Alpenverein Südtirol). Fetched by `fetch_huts.py` and drives its classification alongside `kategorie_nr` — see `docs/superpowers/specs/2026-08-28-hut-classification-design.md` for the full `verein_nr`/`kategorie_nr` → `hutType` table. |
| `verein_name` | string | |
| `nr` | int | |
| `name` | string | hut name |
| `kategorie_nr` / `kategorie` | int / string | `kategorie_nr` is fetched by `fetch_huts.py` and drives its hut/Selbstversorger/Partnerbetrieb classification (`docs/superpowers/specs/2026-08-28-hut-classification-design.md`); `kategorie` (the string label) is not fetched. |
| `meereshoehe` | int | elevation, m. Fetched by `fetch_huts.py` since 2026-08-28 and shipped as `huts.geojson`'s `elevation` property; `0` means missing (not sea level) — a handful of records have no value entered. |
| `bild` | string | image reference |
| `email`, `homepage`, `telefon` | string | |
| `ohrs_hut_id` | string | join key to OHRS; **null for direct-booking-only huts** |
| `huettenwirt_name` | string | |

### Hut classification

`fetch_huts.py` fetches `kategorie_nr`/`verein_nr` (alongside `id`/`name`/`meereshoehe`) and
classifies every record using logic recovered from the AV's own ArcGIS layer renderer (an Arcade
`valueExpression`, decoded from a HAR capture of the raw map view — see
`docs/superpowers/specs/2026-08-28-hut-classification-design.md` for the full recovery and the
investigation numbers behind it). Records classified `"partner"` (Bergsteigerdörfer partner
businesses, private lodging — not Alpine Club huts) are written to `partner_betriebe.geojson`
instead of `huts.geojson`, and routed through the pipeline as an access-point hub type
(`binfmt.TYPE_PARTNER`) alongside stations/parking, not as a hut.

Related layer referenced by the app (tours, not used by this project):
`.../AVT_CAA_TOUR_View_L/FeatureServer/0` — fields `GlobalID`, `Huettenliste` (comma-separated hut
ids), `Bezeichnung`, `Kurzbezeichnung`, `Rundtour`, `Homepage`, `Download`.

---

## 2. Bed availability — OHRS proxy

```
POST https://caa.alpenverein.at/service/server/callOHRS_REST.php
Content-Type: application/json
```

No auth. Responds `Access-Control-Allow-Origin: *`, so it is callable directly from a browser app.
Server-side it forwards to OHRS `/api/v1/external/hutsAvailability`.
**All dates are `DD.MM.YYYY`.**

### 2a. Map-wide — which huts have free places on one date

```json
{"startDate":"20.08.2026","numOfPeople":1,"collectAll":true}
```

Response: flat array of OHRS hut IDs with availability, e.g. `[62,72,86,88,89,...]` (~230 entries).
One call covers the whole map — use this for map colouring.

### 2b. Per-hut detail — bed categories and free places per day

```json
{
  "startDate": "20.08.2026",
  "endDate":   "21.08.2026",
  "huts":      ["179"],
  "numOfPeople": "2",
  "onlyAvailablePlaces": false,
  "page": 0,
  "tenantCode": 8
}
```

`tenantCode` must be the hut's `verein_nr`. A wrong or missing value returns
`{"messageId":302,"description":"Tenant code not found","statusCode":400}`.

Response:

```json
[{"page":0,"resultsPerPage":1,"totalPages":1,"hutsAvailability":[{
  "hutID":179,"hutName":"Pfeis-Hütte",
  "calendarDays":[{
    "day":"20.08.2026",
    "reservationMode":"SERVICED",
    "status":"RESERVATION_NOT_POSSIBLE",
    "bedCategoriesData":[
      {"totalPlaces":37,"occupation":"HIGH","totalFreePlaces":0,
       "hutBedCategoryLanguagesData":[{"language":"DE_DE","label":"Matratzenlager","shortLabel":"ML"}]},
      {"totalPlaces":23,"occupation":"HIGH","totalFreePlaces":0,
       "hutBedCategoryLanguagesData":[{"language":"DE_DE","label":"Mehrbettzimmer","shortLabel":"MBZ"}]}
    ]}]}]}]
```

The client reads `data[0].hutsAvailability[0].calendarDays`, keeps entries that have a `status`, and
falls back to `[{status:"TECHNICAL_ERROR"}]` on failure.

**Cost:** 2b is one request per hut. Never loop it over all 1173 huts — use 2a for overview and 2b
only for the selected hut.

### Booking deep link

```
https://www.hut-reservation.org/reservation/book-hut/{ohrs_hut_id}/wizard?dateFrom={DD.MM.YYYY}&dateTo={DD.MM.YYYY}
```

`&lang=` is appended for `fr`, `en`, `it` only (German is the default).

### Status vocabulary (from the app's German language file)

| Client string | Meaning |
| --- | --- |
| `TOOL_CABINTICKET_NOTINOHRSSYSTEM` → "nur Direktbuchung" | hut has no `ohrs_hut_id` |
| `TOOL_CABINTICKET_CURRENTDATENOTAVAILABLE` → "ausgebucht" | full on that date |
| `TOOL_CABINTICKET_OHRS_TECHNICALERROR` → "dzt. nicht möglich" | OHRS call failed |

---

## 3. Other endpoints seen in the capture (unused here)

- `server/tourSelection.php` — POST with null body, returns the tour catalogue used by "Tourensuche".
- `/service//resources/config.xml` — search limits (max 9 persons, max 9 nights per cabin).
- `/service//resources/languages/{de,en}.xml` — UI strings.
- Basemaps: ArcGIS `OpenStreetMap_v2` vector tiles, `World_Hillshade`, `World_Contours_v2`.
  This project uses plain OSM raster tiles instead.
