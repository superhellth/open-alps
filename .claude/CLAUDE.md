# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A React map that plots all Austrian/German Alpine Club huts (`huts/`), built on data endpoints
reverse-engineered from the Alpenverein "Bettencheck" tool. There is no backend of our own — the
app fetches public third-party APIs directly from the browser.

`caa.alpenverein.at.har` (29 MB) is the source network capture the endpoints were derived from.
It is reference material, not build input.

No test setup exists yet.

## Data sources

Full request/response details, field lists and gotchas: **`docs/alpenverein-api.md`**. Read it
before touching any fetch code. Summary:

- **Hut master data + coordinates** — public ArcGIS feature layer
  `services1.arcgis.com/PHS4LHADrqt5glC9/.../AVT_GEO_CAA_HUETTEN_View_P/FeatureServer/0/query`.
  No auth of any kind. ~1173 points in one request.
- **Bed availability** — `POST https://caa.alpenverein.at/service/server/callOHRS_REST.php`,
  no auth, CORS `*`. One call (`collectAll:true`) returns every available hut for a date; a second
  shape returns per-day bed categories for a single hut and needs `tenantCode` = the hut's
  `verein_nr`.
- The two are joined on `ohrs_hut_id`, which is **null for huts that are direct-booking only**.
  Any availability feature has to handle that case explicitly.

Dates going to OHRS are `DD.MM.YYYY`. Per-hut availability is one HTTP request per hut — it must
not be called in a loop over the whole hut list.

## App structure

`huts/src/App.jsx` is the whole app: one `useEffect` fetch of the ArcGIS layer, mapped into flat
`{id, name, elevation, category, club, lat, lng}` objects, rendered as react-leaflet
`CircleMarker` + hover `Tooltip` over OSM raster tiles. Requesting `outSR=4326` is what makes
`geometry.x/y` directly usable as lng/lat by Leaflet.

## Re-inspecting the HAR

Response bodies in the HAR are base64 (`content.encoding`), so plain grep over the file misses
almost everything. Decode first — the app bundle `static/js/index-BR4qdKga.js` is where the
endpoint config (`ohrsApi`, `toursearchApi`, layer URLs, field names) lives.

## Hut-to-hut routing graph (in progress, offline)

Offline, not-yet-integrated trail-graph precompute pipeline under `data/` — see
`data/CLAUDE.md` for details.
