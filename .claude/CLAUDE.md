# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A React map that plots all Austrian/German Alpine Club huts (`huts/`), built on data endpoints
reverse-engineered from the Alpenverein "Bettencheck" tool. There is no backend of our own — the
app fetches public third-party APIs directly from the browser.

`caa.alpenverein.at.har` (29 MB) is the source network capture the endpoints were derived from.
It is reference material, not build input.

`huts/` has a vitest test suite (`npm test`, `npm run typecheck`, `npm run lint` from `huts/`) —
engine tests run under the default `node` environment, UI tests opt into `jsdom` per-file via a
`// @vitest-environment jsdom` docblock (see `huts/src/TourSearchPage.test.tsx`). No CI pipeline
runs these automatically yet.

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
`hut-edge-stats.json`, `start-edges.pmtiles`, `start-edge-stats.json`, `stations.geojson`,
`parking.geojson`, `unsnapped_huts.json`, `approaches.bin`, `approaches.json`,
`hut-edge-payload.bin`, `hut-edge-payload.json`) are copied into `huts/public/data/` by the
pipeline's own `copy_public_data` task. The first group (`huts.geojson`, `trails.pmtiles`,
`hut-edges.pmtiles`/`hut-edge-stats.json`, `stations.geojson`, `parking.geojson`) is rendered by
`GraphPage.jsx`/`App.jsx` above today; `start-edges.pmtiles`/`start-edge-stats.json`,
`unsnapped_huts.json`, `approaches.*` and `hut-edge-payload.*` are the tour-suggestion backend's
static outputs — built and shipped, but not yet fetched by any client code (the client-side tour
search that would consume them is out of scope for this pipeline work, see "Deferred" in
`docs/superpowers/plans/2026-08-22-tour-suggestion-backend.md`). The hut-edge payload contract
(columns, dtypes, what's deliberately not shipped) is documented in
`docs/tour-suggestion-payload.md` — see `pipeline/CLAUDE.md` for pipeline details.

**Never run any `pipeline/` task (individually via `doit <task>`, or the full `doit` DAG) without
first asking the user and getting explicit confirmation.** `build_base_graph` alone has measured at
~4 hours (see `data/timings.jsonl`) and is a normal dependency of the default `doit` run — a
freshness check can still decide it's stale and silently kick off a multi-hour job. This applies
even to tasks that look cheap or read-only. (`build_profiles` is hardcoded to always run when
selected, but is genuinely cheap — seconds, and never reopens the DEM.)

## Fix problems at their root layer

**The frontend must not paper over backend/data problems, and the pipeline must not paper over
frontend problems.** If a defect's root cause is in `pipeline/` or the emitted data contract (bad,
missing or unusable data — e.g. stations that aren't actually served, huts that failed to snap,
wrong durations), the fix belongs in `pipeline/`, not in a client-side filter or workaround in
`huts/`. Likewise, presentation/interaction problems are fixed in `huts/`, never by reshaping
pipeline output to suit one UI.

When reviewing or planning, classify each issue by its root layer first, and route it there — a
scope boundary ("that's not this spec") is a reason to file it against the right layer, not a
reason to fix it in the wrong one.

## No git worktrees, no subagent-driven development

**Never create or remove a git worktree in this repo, for any reason.** `git worktree remove`
deletes the entire worktree directory from disk, including gitignored content — it destroyed
`data/`'s multi-hour pipeline outputs (raw OSM extracts, DEM, base graph) because `DATA_DIR`
resolves relative to each worktree's own path, so nothing was shared with the main checkout.
Work directly on branches in the main checkout instead.

**Never use `superpowers:subagent-driven-development` or any other approach that spins up
worktrees/subagents to execute plan tasks in this repo, even if a skill recommends it.** Execute
plan tasks directly, in-session, on the current checkout.
