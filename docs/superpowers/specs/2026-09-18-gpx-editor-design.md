# GPX editor — dev-only UI to inspect and repair tour GPX files

## Context

`pipeline/phases/graph_building/match_tour_edges.py` resolves each tour leg's first and last GPX
point to a hub (hut, parking, station, partner) by pure nearest-point distance
(`lib/hubs.py`'s `nearest_hub_to_point`, threshold `graph.maxSnapM` in `pipeline.config.json`,
currently 100 m). A leg whose endpoint has no hub in range is skipped and recorded in
`data/osm/tour-match-gaps.json` as `leg_endpoint_unsnapped`; `phases/quality/check_tour_matching.py`
surfaces those (e.g. Kaisertour legs 2 and 3, endpoint 2.1 km from hut 229).

The input tours are hand-curated GPX files, `pipeline/tours/<TourName>/<N>.gpx` (one file per leg,
tracked in git, one `<trk>`/`<trkseg>` each, 99-4,701 `<trkpt>` each). Folder names may contain
spaces and non-ASCII characters (`Welser Höhenweg`). When a snap fails, the GPX geometry itself is
wrong or too coarse near a hut. Today the only fix is editing XML by hand.

This spec adds a browser tool to look at each tour's legs against the hubs, see live which
endpoints snap, and repair the track by dragging vertices, writing the result back to the GPX file.

## Goals

1. Show every tour and leg on a map together with the pipeline's hubs, marking leg endpoints as
   snapped or unsnapped exactly as `match_tour_edges.py` would.
2. Repair a leg by dragging, inserting and deleting individual trackpoints, with live snap
   feedback, then save to `pipeline/tours/<Tour>/<N>.gpx`.

Non-goals: editing hub positions (when a gap is caused by a wrong or missing hub, editing the GPX
is still the chosen fix, or the hub is fixed upstream by hand); re-running
the pipeline from the UI (after saving, the user runs `doit` as today; the DAG already lists every
`pipeline/tours/*/*.gpx` as a `file_dep` of `match_tour_edges`); shipping the tool in the
production build.

## Architecture

Dev-only second entry page `huts/gpx-editor.html`, code in `huts/src/gpxEditor/`. `vite build`
builds only `index.html`, so the editor never ships. A Vite plugin, `huts/tools/gpxEditorPlugin.ts`,
registered in `huts/vite.config.ts` for dev only (`apply: "serve"`), exposes:

| Route | Behaviour |
|---|---|
| `GET /api/gpx/tours` | `[{name, legs: [n, ...]}]`, read from `pipeline/tours/`, legs sorted numerically |
| `GET /api/gpx/tours/:tour/:leg` | raw GPX text; `X-Gpx-Mtime` response header carries the file's `mtimeMs` as a string |
| `PUT /api/gpx/tours/:tour/:leg` | writes GPX text; `If-Gpx-Mtime` request header carries the mtime string the client loaded |
| `GET /api/gpx/hubs` | contents of `data/osm/hubs.json` (see below) |
| `GET /api/gpx/config` | `{maxSnapM}` from `pipeline.config.json` `graph.maxSnapM` |

Validation: `:tour` is `decodeURIComponent`-decoded, NFC-normalized, and must equal the
NFC-normalized name of an existing folder under `pipeline/tours/` (no path separators, no `.`/`..`);
the plugin then uses the folder's on-disk name. `:leg` must match `^\d+$` and an existing
`<leg>.gpx`. PUT writes to a temp file in the same directory then `rename`s (atomic). If the
file's current mtime string differs from `If-Gpx-Mtime`, PUT returns 409 and writes nothing
(guards against `fetch_alpenvereinaktiv_tour.py --force` rewriting a file while the editor is
open). A successful PUT returns the new mtime.

`pipeline/tours/` is tracked in git, so git is the undo for saves; the plugin makes no backups.

### Hub set

The editor must snap against exactly the hubs the pipeline uses. `huts/public/data/{parking,
stations}.geojson` are not that set: they are the raw OSM exports (~238k parking, ~123k stations,
58 MB), while the pipeline uses `load_all_hubs`, i.e. `huts.geojson` plus `start_points.npy`
(`filter_start_points.py`'s output: only points within `graph.maxEdgeKm` of a hut, private/gated
points dropped). Hut ids also differ: the pipeline's hut id is the index into `huts.geojson` (what
`tour-match-gaps.json` reports), the public file carries GUIDs.

So `match_tour_edges.py` additionally writes `data/osm/hubs.json`, the `load_all_hubs` result it
already holds, as `[{id, type, lon, lat, name}]` with `type` as the `HUB_TYPE_JSON_NAMES` string.
It is added to that task's targets in `pipeline/dag/graph_building.py`. The plugin serves it
from `data/osm/`; it is not copied to `huts/public/data/`. Ids in the editor then match gap
reports.

### Editing model

The client parses the GPX with `DOMParser` and edits `<trkpt>` elements in place, then serializes
the same document on save. Metadata, `<ele>`, and vendor extensions survive; `<trkpt>` elements
the user did not touch serialize unchanged. (The pipeline ignores `<ele>`; it reads only lon/lat.)

Rules:
- New `<trkpt>` elements are created with
  `createElementNS("http://www.topografix.com/GPX/1/1", "trkpt")`. A plain `createElement` yields a
  null-namespace element that serializes as `<trkpt xmlns="">`, which `lib/tour_folder.py`'s
  namespaced `findall` silently skips.
- A newly inserted point has no `<ele>`.
- `lat`/`lon` of moved and inserted points are written with 6 decimals, matching the existing
  files.
- `XMLSerializer` drops the XML declaration. On save, the client re-prepends the original prolog
  (the source text before the root element) so the file header is unchanged.

The acceptance check is a git diff after a real save in the browser: only edited `<trkpt>` lines
change. The jsdom-based unit tests cannot prove this, because jsdom's serializer differs from the
browser's.

### Modules (pure, unit-tested)

- `gpxDoc.ts` — parse; list points; move / insert-after / delete point; serialize (with prolog).
- `history.ts` — undo/redo stack over document edits.
- `snap.ts` — mirrors `nearest_hub_to_point`: haversine distance; among hubs within `maxSnapM`
  prefer huts, else any type; also reports the nearest hub in the pool and its distance regardless
  of range. Endpoint requirement mirrors `match_tour_edges.py`: the first point of the first leg
  and the last point of the last leg (by position in the numerically sorted leg list, not by leg
  number) may snap to any hub type; every other endpoint must snap to a hut, with the pool
  restricted to huts, so "nearest" is then the nearest hut. The editor needs the tour's leg list
  (from `/tours`) to apply this. Hubs are pre-bucketed into a coarse grid so a lookup during a
  drag checks only nearby cells.
- `decimate.ts` — chooses which vertices get a drag handle (see UI).
- `densify.ts` — points every ≤ 25 m along a straight segment (used by "Snap to hub").

The snap rule exists in Python and TypeScript. A shared fixture,
`pipeline/tests/fixtures/snap_cases.json` (hubs, point, `maxSnapM`, `requireHut`, expected chosen
hub id/type and nearest distance to a tolerance), is read by both a pytest against
`nearest_hub_to_point` and a vitest against `snap.ts`, so the two cannot drift. Because both sides
also read the same `hubs.json` data, the editor's verdict matches the pipeline's.

## UI

**Layout.** Left sidebar: tours, each expanding to its legs. Each leg shows a status badge — `ok`,
or `start unsnapped` / `end unsnapped` — updated live from `snap.ts` on the in-memory edit, plus a
dirty dot when there are unsaved edits, plus a `long segment` badge when any segment exceeds
150 m (existing legs run ≤ ~105 m between points, except the coarse `Lechquellenrunde/5.gpx`).
A tour whose leg N ends at a different hub than leg N+1 starts shows a `discontinuous` badge
(informational; the pipeline does not enforce continuity). The rest is a Leaflet map (existing
dependency) with the app's trail basemap.

**Map layers.**
- Hubs from `hubs.json` inside the viewport as small canvas dots coloured by type.
- The selected leg as a canvas polyline.
- A ring on each leg endpoint: green if it snaps to a valid hub, red if not.
- A dashed line from each endpoint to its nearest hub in the pool, labelled with the distance in
  metres.
- Segments longer than 150 m highlighted.

**Vertex handles.** Handles appear only for points inside the viewport, decimated so handles sit
at least ~12 px apart on screen, plus both endpoints always. Zooming in reveals more. A dragged
handle moves exactly its own point.

**Edit actions.**
- Drag a handle: move the point.
- Click the polyline: insert a point at the click, between its neighbours.
- Right-click a handle, or `Del` with it selected (ignored while focus is in a text input): delete
  the point. Endpoints cannot be deleted, only moved.
- `Ctrl+Z` / `Ctrl+Shift+Z`: undo / redo.
- `Ctrl+S` or Save button: PUT the file. Switching legs with unsaved edits prompts; a
  `beforeunload` guard covers reload/close while any leg is dirty.
- "Snap to hub" button on a red endpoint: moves it exactly onto its nearest valid hub's
  coordinates and fills the gap between the old endpoint and the hub with densified points
  (`densify.ts`), so a long move does not leave one straight segment with only two DEM samples
  (which would undercount ascent/descent in `match_leg`). One undo step.
  While dragging an endpoint the nearest hub highlights.

## Errors

- Failed PUT: leg stays dirty, server message shown, nothing lost.
- 409 (file changed on disk): the tool asks whether to overwrite or reload.
- Hub or config load failure (e.g. `data/osm/hubs.json` not built yet): snap overlay disabled with
  a visible warning naming the missing file; editing still works.
- Atomic write as above, so a crash cannot leave a half-written GPX.

## Testing

- vitest (`// @vitest-environment jsdom` where `DOMParser` is needed): `gpxDoc.ts` (inserted point
  is in the GPX namespace; prolog preserved; untouched `<trkpt>` serialize unchanged; 6-decimal
  coordinates), `history.ts`, `snap.ts` (shared fixture plus endpoint-requirement cases),
  `decimate.ts`, `densify.ts`.
- pytest: `nearest_hub_to_point` against the shared fixture; a checked-in GPX fixture produced by
  `gpxDoc.ts` (moved, inserted and deleted points) parses through `parse_leg_gpx` with the expected
  point list; `match_tour_edges.py` writes `hubs.json` matching `load_all_hubs`.
- Plugin tests against a temp `pipeline/tours/` directory: path validation (including a
  non-ASCII, space-containing tour name and `..`), 409 on stale mtime, atomic write.
- React component tests only for the sidebar's badges. Map drag behaviour and the real-browser
  save diff are verified by hand (jsdom has no real Leaflet layout).

## Files

New: `huts/gpx-editor.html`; `huts/src/gpxEditor/{main.tsx,EditorApp.tsx,EditorMap.tsx,Sidebar.tsx,
gpxDoc.ts,history.ts,snap.ts,decimate.ts,densify.ts}` with tests; `huts/tools/gpxEditorPlugin.ts`
with tests; `pipeline/tests/fixtures/snap_cases.json` and its pytest; the GPX round-trip fixture
and its pytest.

Changed: `huts/vite.config.ts` (register the plugin, dev only); `huts/vitest.config.ts` (include
`tools/**/*.test.ts`); `huts/tsconfig.json` / `huts/tsconfig.app.json` (include
`src/gpxEditor` and `tools`); `pipeline/phases/graph_building/match_tour_edges.py` (write
`hubs.json`) and `pipeline/dag/graph_building.py` (add it to targets); a short "GPX editor" run
note under `docs/`; remove the "gpx tailoring tool" line from `docs/backlog.md` when done.
