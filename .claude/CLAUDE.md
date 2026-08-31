# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A React map that plots all Austrian/German Alpine Club huts (`huts/`) and allow multi-leg tour planning.
All data processing that allows easy route planning lives in `pipeline/`.

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

`huts/src/main.tsx` is a hash-based router with no library, wrapped in MUI's `ThemeProvider`
(`theme.ts`)/`CssBaseline`: the default route (no hash) renders `tourSearchPage/TourSearchPage.tsx`,
`#graph` renders `GraphPage.tsx`. Both pages are wrapped in the shared `AppShell.tsx` (top app bar +
tab nav between the two routes).

`huts/src/tourSearchPage/TourSearchPage.tsx` is the main page: a form
(`formState.ts` builds the `Query` from user input) over the client-side tour search engine in
`huts/src/tourSearch/`, plus a results list (`TourList.tsx`) and map (`ResultsMap.tsx`). It fetches
`/data/huts.geojson`, `/data/parking.geojson`, `/data/stations.geojson` and
`/data/partner_betriebe.geojson` (the last fetched best-effort — 404 degrades to no partner
businesses) to label/render search results, and loads the routing graph itself via
`tourSearch/index.ts`'s `loadTourSearchData()`. `hutClass.ts` classifies each hut as AV-run vs.
other, serviced vs. unserviced, for filtering/badging.

`huts/src/tourSearch/` is the client-side tour search engine: `loadHutEdges.ts`/
`loadApproaches.ts`/`loadHutEdgeIds.ts` fetch and parse the pipeline's binary edge-payload/approach
outputs (`hut-edge-payload.bin`+`.json`, `approaches.bin`+`.json`, contract documented in
`docs/tour-suggestion-payload.md`) into an in-memory `GraphData`; `search.ts` searches hut-chains
against a `Query` (leg count/time bounds, mode, start point); `diversity.ts` dedupes
reversed-direction duplicates and suppresses near-identical routes; `adjacency.ts`,
`legFilters.ts`, `dinDuration.ts`, `overlap.ts`, `resolveVariant.ts`, `reverseLeg.ts` are the
supporting graph/filtering primitives. (`pipeline/CLAUDE.md`'s "Deferred" note still describes this
client as not-yet-built — that note is stale.)

`huts/src/GraphPage.tsx` (the `#graph` route) is the opt-in raw-network view for the hut-to-hut
routing graph described below: renders `/data/trails.pmtiles` and `/data/hut-edges.pmtiles` via
`protomaps-leaflet`, plus `/data/huts.geojson` and `/data/hut-edge-stats.json`.

## Hut-to-hut routing graph

Offline trail-graph precompute pipeline under `pipeline/` (code, orchestrated as a
[doit](https://pydoit.org) task DAG via `pipeline/dodo.py`) writing into `data/` (gitignored
raw/generated inputs+outputs), whose outputs (`huts.geojson`, `trails.pmtiles`, `hut-edges.pmtiles`,
`hut-edge-stats.json`, `start-edges.pmtiles`, `start-edge-stats.json`, `stations.geojson`,
`parking.geojson`, `unsnapped_huts.json`, `approaches.bin`, `approaches.json`,
`hut-edge-payload.bin`, `hut-edge-payload.json`) are copied into `huts/public/data/` by the
pipeline's own `copy_public_data` task. `huts.geojson`, `trails.pmtiles`,
`hut-edges.pmtiles`/`hut-edge-stats.json`, `stations.geojson`, `parking.geojson` are rendered by
`GraphPage.tsx`; `approaches.*` and `hut-edge-payload.*` feed the client-side tour search engine
(`huts/src/tourSearch/`, see "App structure" above) that runs entirely in the browser off these
static files — no query-time backend. The hut-edge payload contract (columns, dtypes, what's
deliberately not shipped) is documented in `docs/tour-suggestion-payload.md` — see
`pipeline/CLAUDE.md` for pipeline details.

`pipeline/tours/` holds hand-curated official-tour reference data (one directory per tour, e.g.
`Kaisertour/`, `Welser Höhenweg/`, each a set of per-leg `.gpx` tracks) — raw input to the
official-tours-integration work, tracked in git (unlike `data/`), see
`docs/superpowers/specs/2026-08-30-tour-folder-ingestion-design.md` and
`docs/superpowers/specs/2026-08-29-official-tours-integration-design.md`.

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

## All documentation and plans live in docs/

Especially skill invocations should honor to put the docs they produce in the according docs/ directory.
After completing a backlog task, remove it from `backlog.md` and remove the corresponding `.md`-file
if it existed.