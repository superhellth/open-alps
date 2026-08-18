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

`huts/src/main.jsx` is a hash-based router with no library: `#graph` renders `GraphPage.jsx`,
anything else renders `App.jsx`.

`huts/src/App.jsx` is the main hut map: fetches the ArcGIS hut layer plus
`/data/stations.geojson` and `/data/parking.geojson` (outputs of `data/`'s pipeline, copied into
`huts/public/data/`), mapped into flat `{id, name, elevation, category, club, lat, lng}` objects,
rendered as react-leaflet `CircleMarker` + hover `Tooltip` over OSM raster tiles. Requesting
`outSR=4326` is what makes `geometry.x/y` directly usable as lng/lat by Leaflet.

`huts/src/GraphPage.jsx` (the `#graph` route) is the opt-in raw-network view for the hut-to-hut
routing graph described below: renders `/data/trails.pmtiles` and `/data/hut-edges.pmtiles` via
`protomaps-leaflet`, plus `/data/huts.geojson` and `/data/hut-edge-stats.json`.

## Re-inspecting the HAR

Response bodies in the HAR are base64 (`content.encoding`), so plain grep over the file misses
almost everything. Decode first — the app bundle `static/js/index-BR4qdKga.js` is where the
endpoint config (`ohrsApi`, `toursearchApi`, layer URLs, field names) lives.

## Hut-to-hut routing graph

Offline trail-graph precompute pipeline under `pipeline/` (code, orchestrated as a
[doit](https://pydoit.org) task DAG via `pipeline/dodo.py`) writing into `data/` (gitignored
raw/generated inputs+outputs), whose outputs (`huts.geojson`, `trails.pmtiles`, `hut-edges.pmtiles`,
`hut-edge-stats.json`, `stations.geojson`, `parking.geojson`) are copied into `huts/public/data/`
by the pipeline's own `copy_public_data` task and rendered by `GraphPage.jsx`/`App.jsx` above —
see `pipeline/CLAUDE.md` for details.

**Never run any `pipeline/` task (individually via `doit <task>`, or the full `doit` DAG) without
first asking the user and getting explicit confirmation.** `build_hut_graph` and `add_elevation`
are hardcoded to always run, not freshness-checked, and `build_hut_graph` alone has measured at
~4 hours (see `data/timings.jsonl`) — an unfiltered run can silently kick off a multi-hour job.
This applies even to tasks that look cheap or read-only.
