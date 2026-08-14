# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A React map that plots all Austrian/German Alpine Club huts (`huts/`), built on data endpoints
reverse-engineered from the Alpenverein "Bettencheck" tool. There is no backend of our own — the
app fetches public third-party APIs directly from the browser.

`caa.alpenverein.at.har` (29 MB) is the source network capture the endpoints were derived from.
It is reference material, not build input.

## Commands

Run from `huts/`:

```bash
npm run dev      # Vite dev server, http://localhost:5173
npm run build    # production build to huts/dist
npm run lint     # oxlint
npm run preview  # serve the built bundle
```

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

A separate, not-yet-integrated effort to build a hut-to-hut trail graph (nodes = huts, edges =
real trail paths/distances) so route planning isn't limited to the Alpenverein's 26 predefined
tours (`toursearchApi` / `AVT_CAA_TOUR_View_L`, see `docs/alpenverein-api.md` §3). Edges are
derived from OSM hiking ways, not the Alpenverein data.

This is entirely an offline precompute pipeline living under `data/` — it does not touch `huts/`
yet and doesn't change the app's backend-free architecture; the eventual output ships as a static
GeoJSON asset for the app to fetch. Full reproduction steps and scripts: **`data/README.md`**.
Design rationale for the OSM extract/filter/merge steps: **`docs/osm-trail-pipeline.md`**.

Pipeline is plain Python, no bash/Node/Docker: config-driven — every hyperparameter (region list,
hut bbox, trail tag filter, max-edge-km / max-snap-m) lives in `data/pipeline.config.json` — and
`data/scripts/run_all.py` runs the whole thing end to end, idempotently, inside the `alpen-osm`
conda env (see `data/README.md` "Setup" for how that env was created — via `micromamba`, not
`conda create`, since this machine's `base` conda env hangs solving `-c conda-forge` specs).
Current status: `data/osm/hut-edges.geojson` (hut-to-hut edges, distance-capped shortest paths
over the full unclipped trail network via streamed pyosmium + igraph) is built and up to date for
Austria+Bavaria. Not done: wiring it into `huts/` as a fetched asset, and extending scope past
AT+Bayern.
