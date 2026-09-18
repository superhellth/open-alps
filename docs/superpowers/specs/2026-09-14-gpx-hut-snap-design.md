# GPX-only tour matching — drop road/graph snapping, snap legs to huts

## Context

The hut-trip-planner repo's pipeline-trim design (not carried over into this repo)
trimmed the pipeline to an official-tours-only shape but kept `match_tour_edges.py`'s HMM
map-matching of each tour leg's GPX trace onto the persisted OSM base graph (roads/trails), so a
leg's distance/ascent/descent/geometry came from a routed path over that graph, not from the GPX
trace itself.

The app's actual first-iteration goal doesn't need road/trail-network data at all: filter official
tours by length (days) and estimated duration per leg (from the GPX trace's own geometry + DEM
elevation), and snap each leg's endpoints to huts so hut booking-availability search can be wired
up per leg. This spec drops the entire OSM-graph-matching subsystem and replaces it with direct
GPX+DEM computation.

## What's cut entirely

The base graph and everything that only existed to route a leg's trace onto it:

- `phases/graph_building/build_base_graph.py` — nothing consumes its output once nothing routes
  against it. `phases/postprocessing/build_trail_tiles.py` (the map's trail background layer,
  unchanged, see "What's kept") renders straight from `trails.osm.pbf`, not from this.
- `phases/graph_building/snap_hubs.py`'s graph-snapping half (`hub_snap.snap_hub_to_subgraph`,
  `hub_snaps.npy`/`hub_snap_interior.npy`/`unsnapped_huts.json`) — endpoint hub resolution becomes
  a pure nearest-point-to-hub distance check (`lib/hubs.py`'s `nearest_hub_to_point`, which never
  needed the graph). Its DEM hub-elevation sampling (`hub_snap.sample_hub_elevations`) also goes:
  it only existed to compute `gap_dz_m` for the graph-snap-quality check, which no longer exists;
  huts already carry their own `elevation` field from source data (`fetch_huts.py`'s
  `meereshoehe`).
- `phases/elevation/sample_base_elevation.py`, `phases/elevation/compute_edge_profiles.py` —
  base-graph-node/edge-specific. Their portable math (DEM bilinear sampling; distance-weighted
  kernel smoothing + min-segment merge for ascent/descent) is extracted into new `lib/` modules
  (see "New/moved library code") and reused by the new tour-matching script.
- `lib/hub_snap.py`, `lib/cell_igraph.py`, `lib/subgraph.py`, `lib/hmm_match.py`,
  `lib/hmm_reconstruct.py`, `lib/edge_output.py`, `lib/variants.py` — all graph/HMM-matching
  machinery with no remaining caller.
- `binfmt.RECORD_DTYPE`, `binfmt.TOUR_META_DTYPE`, `binfmt.VARIANT_*`, `binfmt.EDGE_SCHEMA_VERSION`
  — replaced by a new, leaner tour-leg dtype (see "Output schema").
- `phases/postprocessing/build_edge_tiles.py` — forked into a new, trimmed `build_tour_tiles.py`
  (see "Output schema") rather than kept and fed stub values for its now-meaningless
  `road_m`/`sac_rank`/`via_ferrata`/edge-id fields.
- `lib/speed.py`'s `technical_time_s` and the `speedModel.technicalPaceMs` config key — via-ferrata
  pacing was keyed off OSM way tags, which nothing touches anymore.

Corresponding removal work: `dag/graph_building.py`'s `task_build_base_graph`/`task_snap_hubs`
wiring; `dag/elevation.py`'s `task_sample_base_elevation`/`task_compute_edge_profiles` wiring;
`phases/quality/check_graph_building.py` (folds into a trimmed check on the new tour output, see
"Quality checks"); `phases/quality/check_elevation.py`'s base-graph-edge assertions; test files for
every removed script/module.

## What's kept, unchanged

- `phases/downloads/`, `phases/preprocessing/` — unchanged (per the prior spec).
- `phases/elevation/build_dem_vrt.py` — unchanged; `data/dem/dem.tif` is still needed, now as the
  raster the new tour-matching script samples GPX traces against directly.
- `phases/postprocessing/build_trail_tiles.py` — unchanged; still renders straight from
  `trails.osm.pbf`.
- `pipeline/tours/` (hand-curated GPX folders) and `lib/tour_folder.py` — unchanged.
- `pipeline/analysis/routing_probe.py` and `lib/speed.py`'s Tobler model (minus `technical_time_s`)
  — the calibrated speed model is reused as-is, just fed GPX-trace segments instead of
  base-graph-edge segments.

## New/moved library code

- `lib/dem_sample.py` (new): the DEM-window-read + bilinear-sample logic currently in
  `sample_base_elevation.py` (`sample_bilinear` and its windowed-read caller), generalized to take
  an arbitrary ordered list of (lon, lat) points rather than base-graph node/interior arrays. Used
  by the new tour-matching script to sample elevation along a leg's raw GPX trace.
- `lib/elevation_profile.py` (new): `compute_edge_profiles.py`'s `smooth_profile` (distance-weighted
  triangular-kernel smoothing) and `merge_segments` (min-run-length segment merge) — both already
  pure functions over an elevation array + segment-length array, no base-graph dependency in their
  signatures. Also gains a small `ascent_descent(elevations) -> (ascent_m, descent_m)` helper
  (positive/negative delta sums over the smoothed, merged profile) so the new script doesn't
  re-derive that summation inline.

## New tour-matching script

Replaces `phases/graph_building/match_tour_edges.py` in place (same file path, entirely new body).
For each tour folder (`lib.tour_folder.load_all_tour_folders`) and each leg
(`lib.tour_folder.load_tour_folder`):

1. Resolve both endpoints via `lib.hubs.nearest_hub_to_point` against the leg's first/last GPX
   point, within `graph.maxSnapM` (repurposed from a graph-snap radius to a hut-endpoint snap
   radius — same config key, new meaning documented in its own comment). Overnight (inter-leg)
   endpoints must resolve to a hut; the tour's very first and very last leg endpoint may resolve to
   any hub type (hut/station/parking/partner). An unresolved endpoint records a
   `leg_endpoint_unsnapped` gap (same shape as today, minus the now-irrelevant HMM/corridor gap
   reasons) and skips the leg.
2. Sample DEM elevation along the raw GPX trace via `lib.dem_sample`, smooth it and compute
   ascent/descent via `lib.elevation_profile`.
3. Sum horizontal distance directly from the raw GPX trace's own point-to-point haversine
   distances (no route reconstruction).
4. Compute per-segment time via `lib.speed.edge_time_s` (the same calibrated Tobler model) over the
   smoothed profile's segments, summed to a leg `duration_s`.
5. Geometry for map display is the raw GPX trace itself — no snapping/reconstruction alters it.

Writes: `data/osm/tour_edges/{records.npy, geometry.npy, profiles.npy}` (new `TOUR_LEG_DTYPE`, see
below), `data/osm/tours.json`, `data/osm/tour-match-gaps.json` (same three output files as today,
new/simplified contents).

## Output schema

`tours.json` — the frontend's sole input for day-count/duration filtering, no geometry needed:

```json
{
  "tourId": 0, "name": "...", "numDays": 4,
  "legs": [
    {"legIndex": 0, "distanceM": 12500.0, "ascentM": 900.0, "descentM": 200.0,
     "durationS": 14400.0, "from": {"type": "station", "id": 12}, "to": {"type": "hut", "id": 45}}
  ]
}
```

`numDays` = leg count (one GPX file = one day, per this spec's scope — no separate rest-day
metadata).

`tour-match-gaps.json` — same shape as today, but only ever carries `reason:
"leg_endpoint_unsnapped"` now (the HMM/corridor failure reasons no longer exist).

`binfmt.TOUR_LEG_DTYPE` (new, replaces `RECORD_DTYPE` for tour output): `from_id`, `to_id`,
`from_type`, `to_type`, `distance_m`, `ascent_m`, `descent_m`, `duration_s`, `max_ele_m`,
`geom_offset`, `geom_count`, `profile_offset`, `profile_count`. Drops `road_m`, `sac_rank`,
`via_ferrata`, `snap_m`, and every `base_edge_ids`-related field (`edge_id_offset/count`,
`prefix_ids`/`suffix_ids` and their counts) — none of that is derivable without OSM-way matching.

`phases/postprocessing/build_tour_tiles.py` (new, forked from `build_edge_tiles.py`): same
tiling/stats/geometry/elevation-binary output shape (`tour-edges.pmtiles`, `tour-edge-stats.json`,
`tour-edge-geometry.bin/json`, `tour-edge-elevation.bin/json`), reading `TOUR_LEG_DTYPE` records
instead of `RECORD_DTYPE`. Per-edge stats drop `road_m`/`sac_scale`/`via_ferrata`, gain
`duration_s`. The `rdp_keep_indices` simplification and `id_table`-based display-id resolution for
non-hut endpoint types are kept as-is (still needed for station/parking/partner endpoints at tour
start/end).

## Config changes

`pipeline.config.json`:

- `graph.maxEdgeKm`, `graph.roadHighwayTags`, `graph.tileSizeKm` — removed (base-graph-only).
- `graph.maxSnapM` — kept, repurposed as the hut-endpoint snap radius (its comment/docstring
  updated to say so; same key, no config-file restructuring needed).
- `graph.maxSnapAscentM` — removed (was the graph-snap ascent-quality check; no longer applies once
  endpoint resolution is a plain nearest-hub distance check).
- `graph.speedModel.technicalPaceMs` — removed (see `lib/speed.py` above).
- `tourMatch.corridorBufferM`, `tourMatch.lengthDivergenceRatio`, `tourMatch.hmm*`,
  `tourMatch.endpointBridgeMaxM` — removed (all HMM/corridor-specific). `tourMatch` keeps no keys
  of its own; the new script reads `dem.smoothingKernelM`/`dem.minSlopeSegmentM` (already present,
  shared with nothing else now that `compute_edge_profiles.py` is gone) instead of duplicating
  them under `tourMatch`.

`dodo.py`'s `PUBLIC_FILES` drops `unsnapped_huts.json` (no longer produced).

## Quality checks

- `phases/quality/check_graph_building.py` — deleted; nothing in `graph_building/` produces
  graph-shaped output anymore.
- `phases/quality/check_elevation.py` — loses its base-graph-edge assertions; DEM vrt/tif checks
  stay (still produced, still consumed by the new script).
- A new (or `check_postprocessing.py`-folded) check on the new tour output asserts: every leg
  endpoint resolves to a hub of the type the position (interior vs. tour-start/end) requires,
  `distance_m`/`ascent_m`/`descent_m`/`duration_s` are finite and non-negative, and every
  `tour-match-gaps.json` entry's `reason` is `leg_endpoint_unsnapped`.

## Testing

Deleted along with their subjects: tests for `build_base_graph.py`, `snap_hubs.py`'s graph-snap
path, `lib/hub_snap.py`, `lib/cell_igraph.py`, `lib/subgraph.py`, `lib/hmm_match.py`,
`lib/hmm_reconstruct.py`, `lib/edge_output.py`, `lib/variants.py`, `sample_base_elevation.py`,
`compute_edge_profiles.py`'s base-graph-specific cases, and the old `match_tour_edges.py`'s
HMM-path test cases. Exact file list is left to the implementation plan.

New tests: `lib/dem_sample.py` (bilinear sampling against a synthetic raster), `lib/
elevation_profile.py` (smoothing/merge/ascent-descent math — largely portable from
`compute_edge_profiles.py`'s existing tests, now exercised as standalone functions), and the new
tour-matching script (endpoint-type rules for interior vs. tour-start/end legs, the single
remaining gap reason, and distance/ascent/descent/duration numbers against a synthetic GPX+DEM
fixture).

## Non-goals

- No trail-difficulty/SAC-scale or via-ferrata classification this iteration — that was derived
  from OSM way tags via graph matching, which this spec removes; reintroducing it (e.g. by
  buffering the GPX trace against OSM tag data directly, without full graph matching) is future
  scope, not addressed here.
- No tour-level aggregate fields (total distance/ascent/days) precomputed into `tours.json` — the
  per-leg array already has everything needed to sum client-side; adding precomputed aggregates is
  a cheap follow-up if the frontend spec wants it, not decided here.
- No change to how tours are sourced or to hut/DEM data — both stay as-is (per the prior spec).
