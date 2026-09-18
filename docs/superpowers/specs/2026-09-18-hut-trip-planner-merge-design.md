# Merging hut-trip-planner into open-alps — GPX-only official tours

## Context

`~/hut-trip-planner` started on 2026-09-14 as a copy of open-alps trimmed to "official tours only"
(its `docs/superpowers/specs/2026-09-14-pipeline-trim-design.md` and
`2026-09-14-gpx-hut-snap-design.md`). The two repos share no git history: hut-trip-planner's first
commit is a snapshot of open-alps' `docs/` + `pipeline/`. Since then hut-trip-planner has:

- deleted the free-routing engine (`build_hub_edges`, `build_access_edges`, the approach table, the
  routing-variant grid) and the OSM base graph (`build_base_graph`, `snap_hubs`, HMM matching);
- replaced `match_tour_edges.py` with a GPX-only version: distance, ascent, descent, duration and
  geometry come from the leg's own GPX trace plus a DEM sample; only the two endpoints are resolved
  to a hub, by nearest-point distance (`lib/hubs.py`'s `nearest_hub_to_point`);
- added `tools/fetch_alpenvereinaktiv_tour.py` (one GPX per leg from an alpenvereinaktiv.com link),
  more tour folders, and a dev-only GPX editor (`huts/src/gpxEditor/`, `huts/tools/gpxEditorPlugin.ts`);
- started a new frontend (Planner/Trips shell, MUI theme) that only consumes official tours.

open-alps is the mature project: free routing over the OSM graph stays valuable there, and its
frontend, availability client, and data-quality layer are further along. Goal of this spec: bring
hut-trip-planner's official-tour work into open-alps **without** giving up free routing, and
without a pipeline run that drags the ~4 h `build_base_graph` step into tour work.

## Goals

1. Official / third-party tours are **never snapped to OSM ways**. Their geometry stays the raw GPX
   points. Their endpoints are assigned a hub id by distance only.
2. `doit match_tour_edges` (and the tour tile/check tasks downstream) depend on **no** base-graph
   task. Iterating on tours never triggers `build_base_graph`, `snap_hubs`, or
   `compute_edge_profiles`.
3. Free routing (`hut_edges`, `start_edges`, approach table, variants grid) is unchanged.
4. Ship the GPX editor and the alpenvereinaktiv fetch tool in open-alps.

## Decisions (made with the repo owner)

- The HMM/corridor matcher is **deleted**, not kept as an option. Git history keeps it.
- Tours **lose** `sac_rank`, `via_ferrata`, `road_m`, `ungraded_m`, `inferred_m`, `snap_m` and the
  base-edge-id fields. They were derived from OSM way tags via graph matching. Getting a trail
  grade back later would mean reading OSM tags near the trace, not matching to ways (non-goal here).
- **No RDP simplification** of tour geometry anywhere (see "Output side").

## Non-goals

- Adopting hut-trip-planner's Planner/Trips frontend shell. open-alps' own
  `2026-09-04-trip-planner-reenvision-design.md` covers that direction; this spec only wires official
  tours into the existing open-alps frontend.
- Any change to free routing, `build_base_graph`, or hut/start-edge outputs.
- Reintroducing per-tour trail difficulty or via-ferrata flags.
- Merging git history. Porting is by copying files onto a branch in open-alps.

## Design

### Pipeline: tour matching (`phases/graph_building/match_tour_edges.py`)

Replace the body with hut-trip-planner's version (same file path). Per tour folder and leg
(`lib.tour_folder`):

1. Resolve the first/last GPX point via `lib.hubs.nearest_hub_to_point` within `graph.maxSnapM`.
   Interior (overnight) endpoints must resolve to a hut; the tour's first `from` and last `to` may
   be any hub type. An unresolved endpoint records a `leg_endpoint_unsnapped` gap and skips the
   leg's record. The leg stays in `tours.json` with the unresolved endpoint as `null` and
   `edgeId: null` (open-alps' current contract; hut-trip-planner drops the leg instead, which is
   not ported).
2. Sample the DEM along the raw trace (`lib/dem_sample.py`), smooth and merge segments
   (`lib/elevation_profile.py`), and compute ascent/descent.
3. Distance is the sum of raw point-to-point haversine distances. Duration comes from
   `lib.speed.edge_time_s` (unchanged Tobler model) over the merged segments, clamped by
   `graph.speedModel.minSpeedMs`.
4. Geometry is the raw GPX point list, unmodified. The hub id is an attribute of the endpoint; the
   trace is not extended, trimmed, or moved to the hub.

The script writes `tour_edges/{records.npy, geometry.npy, profiles.npy}`, `tours.json`,
`tour-match-gaps.json` and `hubs.json` (the hub set it snaps against, read by the GPX editor).
`profiles.npy` is now written here, not by `build_profiles`.

New library files, copied as-is: `lib/dem_sample.py`, `lib/elevation_profile.py`
(+ `tests/test_dem_sample.py`, `tests/test_elevation_profile.py`).

`tours.json` follows hut-trip-planner's shape, plus `edgeId` (so the frontend can join a leg to its
geometry/elevation row without guessing) and `maxEleM`:

```json
{ "tourId": 0, "name": "...", "numDays": 4,
  "legs": [ { "legIndex": 0, "edgeId": 12, "distanceM": 12500.0, "ascentM": 900.0,
              "descentM": 200.0, "durationS": 14400.0, "maxEleM": 2650.0,
              "from": {"type": "station", "id": 12}, "to": {"type": "hut", "id": 45} },
            { "legIndex": 1, "edgeId": null, "from": {"type": "hut", "id": 45}, "to": null } ] }
```

`edgeId` is the row index into `tour_edges/records.npy`, i.e. `len(matched_legs)` at the moment the
leg is appended. A gap leg carries only `legIndex`, `edgeId: null`, `from` and `to` (one or both
`null`); scalar fields are absent. Every leg of a tour folder appears, so `legs.length == numDays`.

### Pipeline: binfmt

Add `TOUR_LEG_DTYPE` (fields as in hut-trip-planner: `from_id`, `to_id`, `from_type`, `to_type`,
`distance_m`, `ascent_m`, `descent_m`, `duration_s`, `max_ele_m`, `geom_offset`, `geom_count`,
`profile_offset`, `profile_count`). `RECORD_DTYPE` stays; `hut_edges` and `start_edges` still use it.
Delete `TOUR_META_DTYPE` and `VARIANT_OFFICIAL` (no consumers once tours leave `RECORD_DTYPE`).
`VARIANT_NAMES` is embedded in `hut-edge-payload.json`'s manifest, so that manifest loses its
`OFFICIAL` entry the next time `build_edge_payload` runs; no free-routing record changes.

Do **not** bump `RECORD_SCHEMA_VERSION`: it is a tracking param of `build_hub_edges` and
`build_access_edges` only, so a bump forces the multi-hour free-routing rebuild and does nothing for
tours. `match_tour_edges` reruns anyway because its params, `file_dep` and targets all change. Add a
separate `TOUR_LEG_SCHEMA_VERSION` tracking param on `match_tour_edges` alone for future dtype
changes.

### Pipeline: DAG wiring

- `task_match_tour_edges` (`dag/graph_building.py`): no `task_dep` on `compute_edge_profiles` or
  `snap_hubs`. `file_dep`: `huts.geojson`, `start_points.npy`, `dem.tif`, every
  `tours/*/*.gpx`. Params: `max_snap_m`, `smoothing_kernel_m`, `min_slope_segment_m`,
  `profile_points`, `speed_*`, `min_speed_ms`. Targets: the `tour_edges/` files, `tours.json`,
  `tour-match-gaps.json`, `hubs.json`.
- `task_build_profiles` (`dag/elevation.py`): drop `tour_edges` from `file_dep`, `task_dep`
  (`match_tour_edges`) and `targets`. doit forbids two tasks sharing a target, so this is required,
  not cosmetic. `phases/elevation/build_profiles.py` loses its `tour_edges` layer.
- `dag/postprocessing.py`: `build_tour_edge_tiles` runs the new `build_tour_tiles.py` with
  `task_dep` `match_tour_edges` (not `build_profiles`), `file_dep` `tour_edges/records.npy` and
  `start_points_id_table.json`, and only the min/max-zoom params — no `simplify_tolerance_deg`, so
  it stops using `_hut_edge_tiles_params()`. `build_tour_edge_payload` is deleted (scalars live in
  `tours.json`).
- `dodo.py`: `PUBLIC_FILES` drops `tour-edge-payload.bin/json`, adds `hubs.json` only if the editor
  is wanted in production data (default: keep it out of `PUBLIC_FILES`; the editor reads
  `data/osm/hubs.json` directly). `default_tasks` drops `build_tour_edge_payload`.
- `dag/quality.py`: the check tasks that listed `match_tour_edges` alongside graph tasks are split so
  a tour-only run does not require graph checks (see "Quality"). Concretely:
  `check_graph_building` drops `match_tour_edges` from `task_dep` and `tour_edges/*` +
  `tour-match-gaps.json` from `file_dep`; `check_elevation` drops `tour_edges/records.npy` from
  `file_dep`; `check_postprocessing` drops `build_tour_edge_payload` from `task_dep` and
  `tour-edge-payload.json` from `file_dep`, and adds `tours.json`.

### Pipeline: output side

- New `phases/postprocessing/build_tour_tiles.py`, forked from hut-trip-planner's. It reads
  `TOUR_LEG_DTYPE` and writes `tour-edges.pmtiles`, `tour-edge-stats.json`,
  `tour-edge-geometry.bin/json`, `tour-edge-elevation.bin/json`. `build_edge_tiles.py` stays for
  hut/start edges only.
- **RDP is removed for tours.** hut-trip-planner's `build_tour_tiles.py` still runs
  `rdp_keep_indices` (default tolerance `0.0003`); the fork deletes that function, its
  `--simplify-tolerance-deg` flag, and its test cases. Hut and start edges keep RDP via
  `build_edge_tiles.py` (`hutEdgeTiles.simplifyToleranceDeg`), unchanged.
  `tour-edge-geometry.bin` holds every raw GPX point, in the same
  `f4` lon/lat layout and `point_counts` manifest the frontend already reads for hut edges. `f4`
  resolution is about 0.1 m (lon) / 0.4 m (lat) at these coordinates, so no simplification tolerance
  and no `simplifyToleranceDeg` use for tours. The PMTiles input was already unsimplified; tippecanoe
  does per-zoom simplification for display. If payload size becomes a problem later, add
  simplification back as an explicit, config-driven step (`tourTiles.simplifyToleranceDeg`,
  default 0 = off) rather than a hardcoded one.
- `id_table` resolution of non-hut endpoint ids (station/parking/partner) is kept as in
  hut-trip-planner.

### Pipeline: deletions

`lib/hmm_match.py`, `lib/hmm_reconstruct.py`, `tests/test_hmm_match.py`,
`tests/test_hmm_reconstruct.py`, `analysis/corridor_match_quality.py`, the `tourMatch.*` block in
`pipeline.config.json`, the old HMM cases in `tests/test_match_tour_edges.py` (rewritten for the
new script), and `build_edge_payload.py`'s `--tour-meta` flag plus `pack_edges`' `tour_meta`
parameter and their tests. Before deleting `lib/edge_output.py` or `lib/hub_snap.py`, grep for remaining callers
(`build_hub_edges`, `build_access_edges`, `snap_hubs` still use them; expected: keep both).

### Quality

- Add `phases/quality/check_tour_matching.py` (+ test) from hut-trip-planner's current version. It
  asserts every resolved leg endpoint has the hub type its position requires and that
  distance/ascent/descent/duration/maxEle are finite and non-negative, and flags every
  `tour-match-gaps.json` entry with its reason and detail (so skipped legs stay visible). It skips
  scalar checks on gap legs (`edgeId: null`).
- The new check also takes over tour elevation checks: the per-record profile/elevation checks
  hut-trip-planner's `check_elevation.py` runs on `tour_edges` (its only layer there) move into
  `check_tour_matching`, so tour QA never depends on base-graph files.
- `check_graph_building.py`: remove the `tour_edges` layer from `EDGE_LAYERS` and delete
  `check_tour_gaps` (moved into the new check).
- `check_elevation.py`: remove `tour_edges` from `EDGE_LAYERS`.
- `check_postprocessing.py`: replace the `tour-edge-payload` row in its layer table with checks on
  `tours.json` and the tour geometry files.
- `dag/quality.py`: a `check_tour_matching` task depends only on tour outputs;
  `quality_summary` aggregates it with the others.

### Tooling and data

- Copy `lib/alpenvereinaktiv.py`, `tools/fetch_alpenvereinaktiv_tour.py`,
  `tests/test_alpenvereinaktiv.py`, `tests/test_fetch_alpenvereinaktiv_tour.py`.
- Copy the four extra tour folders (Lechquellenrunde, Pitztaltour, Silvretta-Runde,
  Tauernhöhenweg) into `pipeline/tours/`.
- GPX editor: copy `huts/src/gpxEditor/`, `huts/gpx-editor.html`, `huts/tools/gpxEditorPlugin.ts`,
  `pipeline/tests/fixtures/snap_cases.json`, `pipeline/tests/fixtures/gpx_edited/`,
  `pipeline/tests/test_snap_cases.py`, `pipeline/tests/test_gpx_editor_roundtrip.py`, and
  `docs/gpx-editor.md`. Open-alps' huts app has `vite.config.js`, one `tsconfig.json`, and
  `vitest.config.js`, while hut-trip-planner uses `vite.config.ts`, `vitest.config.ts` and
  `tsconfig.app.json`, so the config changes are adapted, not copied: register the plugin in
  `vite.config.js`, add a second tsconfig (or an `include`) covering `tools/`, and make vitest pick up
  `tools/**` tests. Still dev-only: `vite build` builds only `index.html`.

### Frontend (official tours only)

- `tourSearch/loadTourEdges.ts` is deleted; nothing reads `tour-edge-payload.*`. Official-tour
  scalars come from `tours.json` (`loadOfficialTours.ts` already loads it; `RawTourLeg` gains
  `edgeId`, `distanceM`, `ascentM`, `descentM`, `durationS`, `maxEleM`); `officialTours.ts` builds
  `OfficialTourView` from those. The completeness rule is unchanged: a tour with any leg whose
  `from`, `to` or `edgeId` is `null` is not shown.
- `OfficialTourLeg` drops `sacRank` and `viaFerrata` and keeps `maxEleM`; `OfficialTourList` and
  any map styling that used them lose those fields. `durationH` uses the pipeline's `durationS`
  instead of the client-side `dinDurationH` estimate for tour legs.
- The admin page does not render tour tiles; it is unaffected.
- Tour geometry and elevation loaders (`loadLegGeometry.ts`, `loadLegElevation.ts`) keep their
  binary formats; they now read the unsimplified tour geometry.
- Do not copy hut-trip-planner's `huts/src/tourSearch/` over open-alps' (same directory name,
  different modules). Its pieces (`enrich`, `hubIndex`, `search`) are not ported by this spec.
- Do not copy hut-trip-planner's top-level `availability/`; open-alps already has
  `huts/src/availability/`. Diff them first and reconcile only real improvements.

### Docs

Update `pipeline/CLAUDE.md` and the phase READMEs (`phases/graph_building`, `phases/elevation`,
`phases/postprocessing`) to describe GPX-only tour matching. Port the two hut-trip-planner specs
(`gpx-hut-snap`, `gpx-editor-design`) into `docs/superpowers/specs/`. Mark
`2026-08-30-tour-folder-ingestion` and `2026-09-01-corridor-hmm-map-matching` as superseded for the
matching part in `STATUS.md`.

## Ordering

1. Pipeline core: library files, `TOUR_LEG_DTYPE`, new `match_tour_edges`, DAG wiring, tests.
2. Output and quality: `build_tour_tiles`, `check_tour_matching`, profile/quality edits, deletions.
3. Tooling and data: fetch tool, tours, unsnapped-hub flag, GPX editor.
4. Frontend: official-tour loaders and list UI.
5. Docs and `STATUS.md`.

Each step leaves `pixi run test` green and the free-routing outputs untouched.

## Verification

- `pixi run test` passes in `pipeline/` and `npm test` / `npm run build` in `huts/`.
- `pixi run doit info match_tour_edges` lists no `build_base_graph`, `snap_hubs`, or
  `compute_edge_profiles` dependency; a wiring test in `test_dodo_wiring.py` asserts this.
- With `data/` populated, `pixi run doit match_tour_edges build_tour_edge_tiles check_tour_matching`
  runs without touching any graph task, and free-routing tasks report up to date.
- For each tour leg, `tour_edges/geometry.npy` points equal the GPX `<trkpt>` list exactly (a test
  on a fixture GPX).
- For each non-gap leg, `tours.json`'s scalars equal `records.npy[edgeId]`; a fixture with one
  unsnappable endpoint yields a leg with `edgeId: null` and `legs.length == numDays` (test).
- Load the app: official tours render with GPX-accurate lines; no `sacRank`/`viaFerrata` references
  remain (`grep`).

## Risks

- **Hub coverage.** Distance-only snapping fails where a hut is missing from `huts.geojson`
  (e.g. Heidelberger Hütte dropped by the Austria boundary filter, per hut-trip-planner's backlog).
  Those legs surface as `leg_endpoint_unsnapped` gaps; the GPX editor and the hub data, not the
  matcher, are the fix.
- **Shared-file drift.** `lib/speed.py`, `fetch_stations_parking.py`, and `test_binfmt.py` differ
  between the repos. Diff each before overwriting; open-alps' `technical_time_s` and
  `technicalPaceMs` stay because free routing still uses them.
- **Stricter endpoint rule.** open-alps currently snaps every endpoint against all hubs. The
  "interior endpoint must be a hut" rule is new and can turn legs that pass today into gaps (e.g. an
  overnight stop whose nearest hub is a station or partner business).
- **Positional `tourId`.** `tourId` is the index of the folder in sorted order, so adding the four
  tour folders shifts existing ids (Welser Höhenweg goes from 1 to 5). Nothing persists `tourId`
  today; the folder name is the stable key. Reconcile with
  `2026-09-04-stable-tour-ids-design.md` when that lands.
