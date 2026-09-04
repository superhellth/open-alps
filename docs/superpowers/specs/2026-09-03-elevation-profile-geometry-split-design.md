# Byte-range-fetchable elevation profiles for hut/start/tour edges — design

Date: 2026-09-03
Status: approved in brainstorming, ready for implementation planning
Scope: `pipeline/phases/postprocessing/build_edge_tiles.py`, `pipeline/dag/postprocessing.py`,
`pipeline/dodo.py`'s `PUBLIC_FILES`, plus `huts/src/adminPage/` (`AdminPage.tsx`,
`decodeEdgeGeometry.ts`-adjacent new decoder, `types.ts`). Does not touch `tourSearch/`,
`ResultsMap.tsx`, or search/routing behavior.

## Why

`docs/backlog.md`'s "No point-by-point elevation profile for approach/exit legs" item: hut-to-hut
legs carry a point-by-point `elevation_profile` in `hut-edge-stats.json`, but the equivalent
`start-edge-stats.json` was deliberately dropped from `PUBLIC_FILES` by
`docs/superpowers/specs/2026-08-27-tour-geometry-design.md` (654 MB at the time, no consumer) —
so approach/exit legs can never get a height-profile chart, only aggregate `ascent_m`/`descent_m`.

That prior spec already solved the identical problem for `positions` (geometry): split it out of
`<layer>-stats.json` into a byte-range-fetchable `f4` binary + a small manifest, so a client can
range-fetch one edge's data instead of downloading every edge's. `elevation_profile` is the exact
same shape of problem — a `list[float]` per edge, currently only shippable inline — and gets the
same fix.

Per the root `CLAUDE.md`'s "fix problems at their root layer" and "treat hut-to-hut and access legs
as similarly as possible, share as much code as possible": this is a pipeline/data-contract change,
not a client workaround, and it must not special-case `start_edges` relative to `hut_edges`.

## Measured baseline

Measured against the currently-built `data/osm/` outputs (2026-09-03):

| quantity | value |
| --- | --- |
| `hut-edge-stats.json` rows / elevation points | 7,533 rows / 225,990 points |
| `start-edge-stats.json` rows / elevation points | 274,725 rows / 8,241,750 points |
| `tour-edge-stats.json` rows / elevation points | 4 rows / 120 points |
| `hut-edge-elevation.bin` (projected) | 225,990 × 4 B = **0.90 MB** |
| `start-edge-elevation.bin` (projected) | 8,241,750 × 4 B = **32.97 MB** |
| `tour-edge-elevation.bin` (projected) | negligible |
| `start-edge-stats.json` without `elevation_profile` | 194 MB → **56.6 MB** |

All three are well within byte-range-fetch territory, same order of magnitude as
`hut-edge-geometry.bin` (8.0 MB) / `start-edge-geometry.bin` (~150 MB) from the precedent spec.

## A. Third layer in scope: `tour_edges`

`build_edge_tiles.py` is actually invoked **three** times by `dodo.py`
(`task_build_hut_edge_tiles`, `task_build_start_edge_tiles`, `task_build_tour_edge_tiles` —
`pipeline/dag/postprocessing.py:49,74,96`), all through the same `build_stats()` function. The
2026-08-27 geometry spec predates `tour_edges` and only mentions the first two; this change touches
shared code, so it applies to all three call sites uniformly — no special-casing `tour_edges` out.
`tour-edge-stats.json` is tiny (4 rows today, official-tours-integration work in progress) but
follows the identical code path.

## B. New pipeline artifact: byte-range-fetchable elevation

`build_stats()` (`build_edge_tiles.py:64-112`) currently reads `profiles.npy` per edge
(`p_off, p_count = r["profile_offset"], r["profile_count"]`) and inlines the slice as
`elevation_profile` in the stats dict. Split it out exactly like `positions` already was:

- **`hut-edge-elevation.bin` / `start-edge-elevation.bin` / `tour-edge-elevation.bin`** — every
  edge's elevation-profile values, back to back, in `edge_id` order (same `edge_id` domain as
  `<layer>-geometry.bin` — the row index into that layer's `records.npy`), each value as `f4` (4
  bytes). No framing between edges.
- **`hut-edge-elevation.json` / `start-edge-elevation.json` / `tour-edge-elevation.json`** —
  manifest: `profile_counts`, one integer per edge_id (0 for a degenerate edge with `profile_count
  == 0`, otherwise `config["dem"]["profilePoints"]`, default 30). Named `profile_counts` rather than
  reusing `point_counts` — same prefix-sum-offset shape as the geometry manifest, but it counts
  elevation samples, not geometry points, and the two arrays are not the same length per edge (RDP
  simplification varies point count per edge; the elevation profile is always sampled onto a fixed
  `n_points`).
- **`<layer>-stats.json`** loses the `elevation_profile` field entirely — keeps every other field
  (`edge_id, from_hut_id, to_hut_id, distance_m, road_m, ascent_m, descent_m, sac_scale,
  via_ferrata`).

**Flags.** `build_edge_tiles.py` gains `--out-elevation-bin`/`--out-elevation-json`, same pattern as
the existing `--out-geometry-bin`/`--out-geometry-json` (explicit paths, not derived from
`--layer-name`, since the output names are the singular-hyphen form the script's other outputs
already use).

`f4` is sufficient: elevation values are already rounded to 0.1 m by
`build_profiles.py:elevation_profile()`'s `round(v, 1)` before being stored in `profiles.npy`
(`binfmt.PROFILE_DTYPE`); `f4`'s precision at plausible elevation magnitudes (hundreds to low
thousands of meters) is sub-millimeter, far under that existing rounding.

## C. `dodo.py` / `copy_public_data` wiring

- `task_build_hut_edge_tiles` / `task_build_start_edge_tiles` / `task_build_tour_edge_tiles`: add
  the two new `--out-elevation-bin`/`--out-elevation-json` arguments and their paths to each task's
  `targets`.
- `PUBLIC_FILES` (`dodo.py:103`) gains six new files: `hut-edge-elevation.bin`,
  `hut-edge-elevation.json`, `start-edge-elevation.bin`, `start-edge-elevation.json`,
  `tour-edge-elevation.bin`, `tour-edge-elevation.json`.
- `hut-edge-stats.json` and `tour-edge-stats.json` remain in `PUBLIC_FILES`, both shrunk (their
  consumers — `AdminPage`'s hover panel for the former; none yet for the latter beyond whatever
  reads `tours.json`/`tour-edge-stats.json` today — keep working off the remaining fields).
- **`start-edge-stats.json` stays out of `PUBLIC_FILES`.** It shrinks from 194 MB to ~57 MB after
  this change, but still has no client consumer anywhere in `huts/src/` (confirmed by grep before
  writing this spec) — shipping unread data has no benefit regardless of size. Re-adding it is a
  separate call for whenever a consumer appears (e.g. the "make legs hoverable" backlog item, if it
  ends up needing non-elevation, non-geometry start-edge fields client-side).

No new pipeline task, no change to `build_base_graph`/`build_hub_edges`/anything upstream of tiling
— same postprocessing-stage-only footprint as the precedent geometry change. Per the root
`CLAUDE.md`, running any `doit` task remains gated on an explicit ask even though this rerun only
touches `build_hut_edge_tiles`/`build_start_edge_tiles`/`build_tour_edge_tiles`/`copy_public_data`.

## D. `AdminPage.tsx` / `EdgeHoverPanel.tsx` migration

`AdminPage.tsx` is the only current reader of `elevation_profile` (`AdminPage.tsx:62`, reading
`s.elevation_profile` straight off `hut-edge-stats.json`). It migrates the same way it already
migrated for geometry:

- New `huts/src/adminPage/decodeEdgeElevation.ts`, structurally identical to
  `decodeEdgeGeometry.ts`'s prefix-sum-over-manifest decode, but yielding `number[]` per edge
  (elevation values) instead of `L.LatLngExpression[]` (lon/lat pairs) — one value per manifest
  slot instead of one coordinate pair.
- `AdminPage.tsx`'s load effect adds two more `fetch()`s (`hut-edge-elevation.json` as JSON,
  `hut-edge-elevation.bin` as `arrayBuffer()`) to the existing `Promise.all`, decodes with the new
  module, and zips `elevationProfile: perEdgeElevation[i]` into the same `edges.map()` that already
  zips in `positions`/`bounds` from the geometry decode — same "same `build_stats()` pass, same
  `edge_id` order, zip by index" reasoning already documented at `AdminPage.tsx:49-50`.
- `EdgeStatsEntry` (`huts/src/adminPage/types.ts`) drops `elevation_profile`; gains nothing (the
  decode produces the value directly, no new manifest type needed beyond a
  `ElevationManifest = { profile_counts: number[] }` alongside the existing
  `EdgeGeometryManifest`).
- `Edge.elevationProfile` (existing field) and `EdgeHoverPanel.tsx`'s `ElevationSparkline` are
  unchanged — this is purely a data-sourcing change, not a rendering change.

`start-edge-elevation.bin`/`.json` and `tour-edge-elevation.bin`/`.json` are built and shipped (§C)
but have **no client consumer** after this change — `AdminPage` doesn't render `start_edges` or
`tour_edges` today (confirmed: `GraphPage`/`AdminPage` only fetches the `hut-edge-*` family). That
asymmetry is intentional and already flagged in §Why: covering approach/exit-leg hoverability is the
separate "make legs of selected tour hoverable" backlog item, which this change is a prerequisite
for, not a part of.

## E. Documentation

- `pipeline/phases/postprocessing/README.md`'s `build_edge_tiles.py` section (`:41-73`) currently
  says "invoked twice" and lists `elevation_profile` as one of `build_stats()`'s inlined fields —
  update to "invoked three times" (`tour_edges` included) and move `elevation_profile` into the new
  `*-edge-elevation.bin`/`.json` bullet alongside the existing `*-edge-geometry.bin`/`.json` one.
- `docs/backlog.md`: remove the "No point-by-point elevation profile for approach/exit legs" entry
  once this lands (per root `CLAUDE.md`'s backlog-completion rule).

## Testing

`pipeline/tests/test_build_edge_tiles.py` already covers `build_stats()`'s split of `positions` out
of the stats dicts (`test_build_stats_resolves_ids_via_id_table` and friends) — extend it, don't
create a new file:

- `elevation.bin`'s byte layout matches `elevation.json`'s `profile_counts` (prefix sums land on
  real value boundaries, total length == `sum(profile_counts) * 4`).
- `<layer>-stats.json` dicts no longer have an `elevation_profile` key.
- A degenerate edge (`profile_count == 0`, e.g. `geom_count < 2` per `build_profiles.py`'s early
  return) round-trips as a zero-length slice, not an error.

Client side:

- `huts/src/adminPage/decodeEdgeElevation.test.ts` (new, mirrors whatever test coverage
  `decodeEdgeGeometry.ts` has, if any — if none exists today, this is the first, not a gap
  introduced by this change).
- `AdminPage`'s existing jsdom test fixtures extend to mock the two new fetches and assert
  `elevationProfile` is still populated per edge.

## Rejected alternatives

**Reusing `point_counts`/`EdgeGeometryManifest` for the elevation manifest instead of a new
`profile_counts` field.** Rejected: geometry point count (RDP-simplified, varies per edge, no fixed
target) and elevation sample count (always `config.dem.profilePoints` or 0) are different
quantities that happen to currently correlate loosely in magnitude — conflating them into one field
name would make a future retune of either `--simplify-tolerance-deg` or `--profile-points`
(independently controllable today, per `build_profiles.py`'s docstring) silently produce a
misleading manifest.

**Leaving `tour_edges` out of scope, only touching `hut_edges`/`start_edges`.** Rejected:
`build_stats()` is one shared function across all three call sites; splitting its output for two
callers and not the third would leave `tour-edge-stats.json` carrying `elevation_profile` inline
while its siblings don't, for no reason other than the precedent spec predating `tour_edges` — an
avoidable inconsistency in a codebase whose `CLAUDE.md` explicitly asks for shared handling across
edge-set layers.

**Re-adding `start-edge-stats.json` to `PUBLIC_FILES` now that it's smaller.** Rejected (per
explicit decision during brainstorming): size was never the reason it has no consumer; shipping
57 MB of data nothing reads is still waste. Revisit if/when a client consumer for its non-elevation,
non-geometry fields (`distance_m`, `road_m`, `sac_scale`, `via_ferrata`, aggregate `ascent_m`/
`descent_m`) actually appears.
