# Official ÖAV/DAV Tours Integration — Design

**Problem:** The Alpenverein publishes 26 official multi-day trekking routes (Karnischer
Höhenweg, Peter-Habeler-Runde, Berliner Höhenweg, various Hüttenrunden, ...) via a separate ArcGIS
layer, `AVT_CAA_TOUR_View_L` (`docs/alpenverein-api.md` §3, `pipeline/CLAUDE.md`). Today the
hut-to-hut pipeline treats this layer as reference material only — its own graph
(`build_hub_edges.py`) finds *shortest* paths between huts, which is a deliberate design choice for
free-form trip planning but is the wrong answer for "show me the real Peter-Habeler-Runde": the
official route does not always coincide with our shortest path, and distorting it to match would
misrepresent a named, waymarked trail.

**Goal:** Ship the 26 official tours with the same per-leg data our own hut-edges already carry —
distance, ascent/descent, time, elevation profile, difficulty facts (`sac_rank`/`via_ferrata`/
`ungraded_m`) — computed from the *same* DEM/elevation pipeline, without needing a second elevation
pass, and without distorting the tour's real route to a shortest path.

**Core idea:** the AV tour layer's geometry is a real-world polyline (an `esriGeometryPolyline`,
confirmed by direct query), not just a hut list. Map-match that polyline onto our own base graph
(`pipeline/phases/graph_building/build_base_graph.py`'s `base_graph/`) instead of routing a new
path. A matched tour leg is then literally a sequence of existing base-graph edges, which
`elevation/compute_edge_profiles.py` has *already* stamped with `time_s`/`ascent_m`/`descent_m` —
hub-agnostically, before any hub-edge routing runs. So map-matching gets "the same DEM data" for
free: no new elevation sampling, just summing already-computed per-edge values along the matched
path.

## 0. Source data — `AVT_CAA_TOUR_View_L`

Confirmed by direct query against `services1.arcgis.com/PHS4LHADrqt5glC9/.../AVT_CAA_TOUR_View_L/FeatureServer/0`
(same backend/auth as the hut layer, no auth, `outSR=4326` reprojects cleanly):

- **26 features total.** One is garbage: `Kurzbezeichnung="#DUMMY"`, `Bezeichnung=null`, geometry
  in Bolivia — must be filtered by `Kurzbezeichnung == "#DUMMY"`, not by a fragile null-name check
  (one legitimate tour, "Karwendel Höhenweg", also lacks a distinct `Bezeichnung`/`Kurzbezeichnung`
  pair but is real).
- Fields: `GlobalID`, `Bezeichnung` (display name), `Kurzbezeichnung` (short code), `Rundtour`
  (0/1 loop flag), `Homepage`, `Download` (both external links, mostly to alpenvereinaktiv.com or
  regional tourism sites — not structured data, not needed since geometry ships in this layer
  directly), `Huettenliste` (comma-separated hut `GlobalID`s, **in tour order**).
- Geometry: `esriGeometryPolyline`, multi-part (`paths: [[...], [...]]`), point-dense (609–22,336
  points per tour depending on digitization source). One record (`Wiener Höhenweg`) has
  `Huettenliste = null` — has geometry but no hut chain; out of scope for leg-splitting (§2) until
  someone supplies its hut list, tracked as a known gap, not blocking the other 25.
- Full dataset (26 tours, geometry + attrs, `outSR=4326`) is **~3.5 MB** in one request — same
  order of magnitude as the existing hut-layer fetch.
- `Huettenliste` ids are the ArcGIS `id`/`GlobalID` values from the *hut* layer
  (`AVT_GEO_CAA_HUETTEN_View_P`), **not** the positional index `RECORD_DTYPE.from_id`/`to_id` uses
  when `from_type/to_type == TYPE_HUT` (that index is `huts.geojson`'s feature array position,
  `lib/hubs.py:22`). Resolving a `Huettenliste` GUID to that index means joining against
  `huts.geojson`'s own `id` property, which `fetch_huts.py` already carries through from the same
  ArcGIS hut layer.

## 1. New `downloads/` task: `fetch_tours.py`

Mirrors `fetch_huts.py`'s shape (plain `f=json&outSR=4326` GET, no auth, no pagination needed at
26 records). Params: none beyond the standard `--osm-dir`.

- Fetches all fields + geometry from `AVT_CAA_TOUR_View_L`.
- Drops the `#DUMMY` record.
- Resolves each `Huettenliste` GUID against `huts.geojson`'s `id` property to `RECORD_DTYPE`'s
  positional hut index. A GUID that doesn't resolve (hut reclassified to
  `partner_betriebe.geojson`, or genuinely absent from `huts.geojson`) is dropped from that tour's
  hut list and recorded in a `tour-fetch-gaps.json` sidecar — never silently reindexed or
  substituted.
- Writes `tours.json`: one record per tour — `{tourId, name, shortCode, isLoop, homepage,
  hutIndices: [int, ...]}` — plus the raw per-tour polyline (lon/lat pairs, `outSR=4326`) needed by
  `match_tour_edges.py` (§2). `tourId` is the array index into this file, stable for the life of one
  pipeline run (same convention as hut indices).
- **doit wiring**: `file_dep=[]` (network fetch, like `fetch_huts.py`), `targets=[tours.json]`.

## 2. New `graph_building/` task: `match_tour_edges.py`

Runs after `compute_edge_profiles.py` (needs `base_graph/edges.npy`'s `time_s`/`ascent_m`/
`descent_m` filled — UNSET before that) and `snap_hubs.py` (needs every tour hut's persisted snap
point, `hub_snaps.npy`). Independent of `gather_route_subgraphs.py`/`build_hub_edges.py` — matching
doesn't route, so it never touches the routing engine or `graph.variants`.

**Per tour, per leg (`hutIndices[i] → hutIndices[i+1]`):**

1. **Slice the raw polyline into a leg sub-trace.** For each hut in `hutIndices`, find the trace
   vertex closest to that hut's coordinate (arc-length position along the polyline) — huts sit
   right on the trail by construction, so nearest-vertex is a reliable stage-boundary heuristic.
   Slice the polyline between consecutive huts' positions to get one sub-trace per leg. A hut whose
   nearest trace vertex is implausibly far away (threshold TBD at implementation, start from
   `snap_hubs.py`'s own `--max-snap-m`) means the AV geometry and hut list disagree — record to
   `tour-match-gaps.json`, skip that leg.
2. **Map-match the sub-trace onto `base_graph/`** using `leuvenmapmatching` (PyPI, pure Python,
   only depends on `numpy`/`scipy` at its core — far lighter to add to the `alpen-osm` pixi env than
   `fmm`'s C++/GDAL/Boost stack). Build the library's graph representation from `base_graph/nodes.npy`
   + `edges.npy` **once per pipeline run** (not once per tour/leg) and reuse it — this is the same
   node/edge data `lib/cell_igraph.py` already turns into an `igraph.Graph` per cell, just consumed
   whole here since matching, unlike routing, doesn't need per-cell tiling (26 tours is a small,
   bounded workload, not the all-pairs hub cost `build_hub_edges.py` tiles to survive).
   Anchor the match's start/end to the adjacent huts' already-persisted `snap_hubs.py` snap points
   (append each hut's exact snap coordinate as the first/last observation) so consecutive legs join
   exactly at the hut, the same node `hub_snaps.npy` already recorded for that hut.
3. **Walk the matched path's edges** to collect: total `dist`, `road_m`, `ungraded_m`, `inferred_m`,
   summed `time_s`/`ascent_m`/`descent_m` (already computed, per §"Core idea"), max `sac_rank`,
   `via_ferrata` (OR across matched edges), and the full-resolution geometry (concatenated
   `interior.npy` slices, exactly as `build_hub_edges.py`'s `accumulate_path` already does for
   routed paths — reuse that accumulation code rather than duplicating it, factoring out the
   edge-list-to-summary step it currently does inline in `lib/cell_igraph.py`).
4. **Match confidence / coverage gap.** A leg with matched-path length wildly divergent from the
   AV geometry's own length (threshold TBD at implementation — start from a 2x ratio, matching the
   generosity of `--max-edge-km`'s own headroom), or whose sub-trace has points outside the
   AT+Bayern OSM extract bbox (Rieserfernerdurchquerung's South Tyrol legs are the known case),
   is **not matched** — recorded to `tour-match-gaps.json` with the tour/leg identity and reason,
   never faked with a straight-line or partial-distance placeholder.

**Output** (`data/osm/tour_edges/`, same directory shape as `hut_edges/`/`start_edges/`):

- `records.npy` — `RECORD_DTYPE`, unchanged (no new columns on the shared dtype, so this doesn't
  force a schema-version bump or rerun on `hut_edges`/`start_edges` consumers). `from_type`/
  `to_type` are always `TYPE_HUT`. `variant` is a new sentinel, `VARIANT_OFFICIAL` (add to
  `binfmt.py` alongside `VARIANT_FAST_ANY`/etc. — a matched tour leg is not a member of the
  `graph.variants` search grid, so it must not collide with an existing variant id).
  `geom_offset`/`geom_count` and `profile_offset`/`profile_count` populate exactly as `hut_edges`
  does today, so `build_profiles.py` needs no tour-specific logic. `edge_id_offset`/`edge_id_count`/
  `prefix_ids`/`suffix_ids` (the overlap-check columns from `docs/superpowers/specs/
  2026-08-29-avoid-overlapping-tracks-design.md`) are populated the same way `hut_edges` populates
  them today — free correctness if official tours are ever mixed into overlap-aware search later,
  though no such feature is in scope here.
- `geometry.npy` — `COORD_DTYPE`, matched-path full-resolution geometry, same as `hut_edges`.
- `edge_ids.npy` — same shape as `hut_edges/edge_ids.npy` (§1 of the overlap-tracks spec), for free
  given records reuse the same accumulation path.
- `tour_meta.npy` — **new, tour-specific sidecar**, row-aligned 1:1 with `records.npy` (not folded
  into `RECORD_DTYPE` itself, to avoid touching the shared dtype other consumers depend on):
  `TOUR_META_DTYPE = [("tour_id", "u1"), ("leg_index", "u1")]`. 26 tours × ≤20 legs each fits `u1`
  comfortably.
- Legs that hit a gap (§2.4) are simply absent from `records.npy` — `tour-match-gaps.json` is the
  record of what's missing and why, same pattern as `unsnapped_huts.json`.

**doit wiring**: `file_dep=[base_graph/edges.npy (post-profiles), hub_snaps.npy, tours.json]`,
`targets=[tour_edges/records.npy]`. Track a `tourEdgeSchemaVersion`-style param only if
`match_tour_edges.py`'s own logic changes shape — it doesn't own `RECORD_DTYPE`, so it never needs
to move `record_schema_version` and force a `build_hub_edges` rerun.

## 3. Postprocessing — reuse existing generalized scripts, third invocation

`build_edge_tiles.py`, `build_profiles.py`, and `build_edge_payload.py` are already parametrized
over `--edges-dir`/`--layer-name` (`dodo.py` invokes each twice today, `hut_edges`/`start_edges`).
Add a third invocation pointed at `tour_edges/`:

- `build_profiles.py --edges-dir tour_edges` → fills `tour_edges/records.npy`'s `profile_*` fields
  in place, same as it does for `hut_edges`.
- `build_edge_tiles.py --edges-dir tour_edges --layer-name tour_edges` → `tour-edges.pmtiles`,
  `tour-edge-stats.json`, `tour-edge-geometry.bin`/`.json`.
- `build_edge_payload.py --edges-dir tour_edges` → `tour-edge-payload.bin`/`.json`, plus needs a
  small addition: since payload rows must carry `tour_id`/`leg_index` for the client to reconstruct
  "which tour is this leg part of" (the existing hut-edge payload has no such concept), extend
  `build_edge_payload.py` to optionally fold in a sidecar array (`tour_meta.npy`) as two extra
  payload columns when present — additive, `hut_edges`/`start_edges` payloads are unaffected since
  neither directory has a `tour_meta.npy`.
- Ship `tours.json` itself (§1) alongside as a small metadata file the client fetches directly for
  the tour list/detail UI (name, `isLoop`, ordered hut list, homepage link) — no postprocessing
  needed, it's already client-shaped.
- Add all of `tour-edges.pmtiles`, `tour-edge-stats.json`, `tour-edge-geometry.bin`/`.json`,
  `tour-edge-payload.bin`/`.json`, `tours.json` to `dodo.py`'s `PUBLIC_FILES` and
  `DOIT_CONFIG["default_tasks"]`.

## 4. Access edges — no new pipeline work

A tour's start/end are existing hub huts (they're drawn from the same hut set `start_edges`/
`approaches.bin` already cover). The client answers "how do I reach this tour" by looking up the
existing approach table (`approaches.bin`/`.json`, `build_approach_table.py`) keyed by the tour's
first/last hut index (either endpoint, for a `Rundtour`) — no tour-specific access-edge computation
is needed, and none is proposed here.

## 5. Filtering — scoped to this dataset only

This section applies **only** to `tour_edges/`, not to `hut_edges/`. Free-form hut-to-hut browsing
keeps its full `graph.variants` grid (`FAST_ANY`/`FAST_T2`/`FAST_T3`/`FAST_T3_UNGRADED`) exactly as
it works today — unaffected by anything in this spec.

For official tours specifically: since a matched leg's geometry is fixed to the one route the AV
publishes, there is nothing to search among — `graph.variants` does not apply as a *routing*
choice, hence `VARIANT_OFFICIAL` rather than reusing one of the search variant ids. The per-leg
facts that do carry over (`sac_rank`, `via_ferrata`, `ungraded_m`, all populated on `records.npy`
exactly as for `hut_edges`) let the client filter/display *which tours* to show by difficulty
tier, but not offer alternate physical routes for a given tour.

## Out of scope (explicitly deferred)

- Client-side rendering/UI for tours (tour list, detail panel, hover profile) — this spec covers
  only the pipeline's data contract; consuming it in `huts/` is separate follow-up work.
- `Wiener Höhenweg` (`Huettenliste = null`) — geometry exists but has no hut chain to split legs
  against; left out of `tours.json`'s matched-leg output until a hut list is available, tracked as
  a known gap rather than guessed at.
- Tours (or partial legs) outside the AT+Bayern OSM extract (South Tyrol/Italy portions) — a real
  coverage limit of the underlying `pipeline.config.json` region list, not something this feature
  works around; surfaced via `tour-match-gaps.json`, fixed only by extending pipeline region scope
  (out of scope here).
- `tourSelection.php` (mentioned in `docs/alpenverein-api.md` §3) — never observed in the HAR
  capture, response shape unconfirmed; not needed since `AVT_CAA_TOUR_View_L` already supplies
  geometry + hut list directly.
- Mixing official tours into the "avoid overlapping tracks" search (`docs/superpowers/specs/
  2026-08-29-avoid-overlapping-tracks-design.md`) — `tour_edges/` populates the same overlap-check
  columns for free (§2), but no search-side feature consumes them yet.

## Testing

- **`fetch_tours.py`**: unit test the `#DUMMY` filter and the `Huettenliste` GUID → hut-index join,
  including the case where a GUID doesn't resolve (asserts it lands in `tour-fetch-gaps.json`, not
  silently dropped or crashing the run).
- **Leg-slicing heuristic**: unit test nearest-trace-vertex hut-position finding against a synthetic
  polyline + known hut coordinates, including the "hut too far from any trace vertex" gap case.
- **Base-graph → `leuvenmapmatching` adapter**: unit test building the library's graph
  representation from a tiny synthetic `base_graph/` fixture (a handful of nodes/edges), asserting
  node/edge counts and connectivity survive the conversion.
- **Golden end-to-end match**: one small real tour (Chiemgautour, 3 huts, 2 legs) matched against a
  fixture subgraph built from real OSM data around those huts — assert the matched edge sequence is
  connected end-to-end, touches both hut's known `snap_hubs.py` snap points, and sums to sane
  time/ascent (order-of-magnitude check against the tour's known real-world stats, not exact
  equality).
- **Coverage-gap handling**: a leg whose sub-trace strays outside the base graph's bbox is recorded
  to `tour-match-gaps.json` with tour/leg identity, and does **not** produce a `records.npy` row.
- **`build_edge_payload.py` tour-meta extension**: round-trip test — with a `tour_meta.npy` present,
  payload output gains the two extra columns; without it (the `hut_edges`/`start_edges` case),
  output is byte-identical to today's, confirming the extension is additive.
