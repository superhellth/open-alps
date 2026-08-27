# Real trail geometry on the tour search results map — design

Date: 2026-08-27
Status: approved in brainstorming, revised after technical review, ready for implementation planning
Scope: `pipeline/`'s edge-tiling/approach-table scripts and static data contract, plus
`huts/src/tourSearch/` (engine) and `huts/src/tourSearchPage/ResultsMap.tsx` and
`huts/src/GraphPage.tsx`. Does not touch routing, search, or any other part of either app.

## Why

`ResultsMap.tsx` currently draws a selected tour as one dashed straight-line polyline through
start → huts → exit — "schematic", explicitly labelled as not the real trail. The real trail
geometry already exists in the pipeline (`hut_edges/geometry.npy`, `start_edges/geometry.npy`) and
is already tiled for map rendering (`hut-edges.pmtiles`, `start-edges.pmtiles`), but no client code
can look up "the geometry for this one specific edge" cheaply: `hut-edges.pmtiles` is a rendering
format (vector tiles), and the sidecar that does carry parseable per-edge point arrays
(`hut-edge-stats.json`, `start-edge-stats.json`) ships every edge in one JSON blob — 33.1 MB and
654 MB respectively — un-fetchable per tour.

Goal: render the tour's actual routed trail (hut-to-hut legs and the start/exit approach legs)
using the already-computed geometry, fetching only the handful of edges a given tour uses.

## Measured baseline

Every size and count below was measured against the currently shipped `huts/public/data/` and
`data/osm/` outputs (2026-08-27), not estimated. Earlier drafts of this spec carried stale figures
inherited from `build_edge_payload.py`'s docstring; these supersede them.

| quantity | value |
| --- | --- |
| `hut_edges/records.npy` rows | **12,416** (4 variants × ~3,104 pairs) |
| `start_edges/records.npy` rows | **234,918** |
| variants | **4** — `FAST_ANY`, `FAST_T2`, `FAST_T3`, `FAST_T3_UNGRADED` |
| `hut-edge-stats.json` | 33.1 MB, of which `positions` is **24.3 MB** |
| `hut-edge-stats.json` without `positions` | **8.6 MB** (now dominated by `elevation_profile`, 372,480 points) |
| `hut-edge-geometry.bin` | **8.0 MB** — 1,005,914 points × 8 B; avg **81 pts/edge**, max 186 |
| `hut-edge-geometry.json` | **41.5 KB** raw / 13.9 KB gzipped |
| `start-edge-geometry.json` (projected) | **~790 KB** raw / ~260 KB gzipped (same bytes-per-row, 234,918 rows) |
| `start-edge-geometry.bin` (projected) | **~150 MB** (`start_edges/geometry.npy` is 18.6× `hut_edges`') |
| `approaches.json` | 12.3 MB raw / 1.50 MB gzipped; `reverse_index` is 36,864 rows, serialized twice |
| per-leg range fetch | **~650 B** (81 pts × 8 B) → a 5-leg tour is **3–5 KB** total |

That last row is the point of the whole design: opening a tour costs single-digit kilobytes.

## A. New pipeline artifact: byte-range-fetchable geometry

`phases/postprocessing/build_edge_tiles.py` already computes RDP-simplified `[lon, lat]` positions
per edge (`build_stats()`'s `coords[keep]`) for the `positions` field of `<layer>-stats.json`. That
function is refactored to split its output in two:

- **`hut-edge-geometry.bin` / `start-edge-geometry.bin`** — every edge's simplified points, back to
  back, in `edge_id` order (edge_id = row index into that layer's `records.npy`, unchanged from
  today), each point as an `f4` lon/lat pair (8 bytes). No framing between edges — boundaries come
  from the manifest.
- **`hut-edge-geometry.json` / `start-edge-geometry.json`** — manifest: `point_counts` (one integer
  per edge_id, a plain JSON array). A client derives edge_id `i`'s byte range as a prefix sum over
  `point_counts[0..i)`, computed once per session, not per lookup.
- **`<layer>-stats.json`** keeps every other field it has today (`from_hut_id`, `to_hut_id`,
  `distance_m`, `road_m`, `ascent_m`, `descent_m`, `elevation_profile`, `sac_scale`, `via_ferrata`,
  `edge_id`) — only `positions` moves out. This is what takes `hut-edge-stats.json` from 33.1 MB to
  8.6 MB.

**Naming and flags.** The output names above are the singular-hyphen form the repo already uses
(`hut-edge-stats.json`, `hut-edge-payload.bin`) — note they are *not* derivable from `--layer-name`
(`hut_edges`), which is why the existing script takes `--out-tiles`/`--out-stats` explicitly. Add
`--out-geometry-bin` and `--out-geometry-json` the same way; do not derive filenames from
`--layer-name`.

`f4` is sufficient: ulp is ~7 cm in longitude at 13°E and ~42 cm in latitude at 47.5°N, both far
under the simplification tolerance below.

`--hover-simplify-tolerance-deg` (existing flag, default `0.0003` per `pipeline.config.json`'s
`hutEdgeTiles.hoverSimplifyToleranceDeg`) controls the same simplification for both consumers below
— no new config knob. At ~11-33 m this is visually indistinguishable from full-resolution trail
geometry at any zoom level a Leaflet map renders at. Two notes for the implementer:
`build_edge_tiles.py:118` still hardcodes a stale `0.0001` argparse fallback that disagrees with
both the config file and `dodo.py`'s `_hut_edge_tiles_params()` — align it while in the file. And
once this geometry is the *rendered* trail rather than only a hover hit-test, the `hover` in the
flag and config key is a misnomer; renaming to `--simplify-tolerance-deg` /
`simplifyToleranceDeg` is in scope for this change, since both call sites are being touched anyway.

This one script change covers both `hut_edges` and `start_edges` (it's already invoked twice —
`task_build_hut_edge_tiles` / `task_build_start_edge_tiles` — with `--layer-name`/`--edges-dir` as
the only difference). Both layers emit both files and all four are shipped (see §G).

## B. Two consumption patterns against the same file

- **`ResultsMap.tsx` (new):** small `Range`-header `fetch()`s for the ~5-10 edge_ids the selected
  tour actually uses (~650 B each). Cached per edge_id for the session.
- **`GraphPage.tsx`'s hover feature (migrated):** `HoverInspector` tests cursor proximity against
  *every* edge's geometry at once (that's the documented point of it — surfacing every trail in a
  stack of overlapping ones), and `GraphPage.tsx:284` also precomputes each edge's
  `L.latLngBounds` from the same points, so it cannot range-fetch on demand; it does one full,
  non-`Range` `GET` of `hut-edge-geometry.bin` and decodes the whole typed array up front.

  Sized honestly, that migration takes `GraphPage`'s load from **33.1 MB of JSON** to **8.6 MB of
  JSON + 8.0 MB of binary** — roughly a 2× win, not an order of magnitude, and it still
  `JSON.parse`s 8.6 MB. The residual is `elevation_profile` (372,480 points), which is
  deliberately **out of scope** here; if `GraphPage` load time is a goal in its own right, that is
  the next thing to attack, not this. `GraphPage` does not consume `start-edge-geometry.bin` — it
  doesn't render `start_edges` today and this doesn't change that.

Both patterns read the same static file; nothing pipeline-side needs to know which is in play.

**Hosting constraints.** Two requirements, only the first of which is already proven in production:

1. `huts/public/data/` must be served with `Range` support. Already relied on —
   `hut-edges.pmtiles`/`start-edges.pmtiles` are fetched exactly this way by the existing `pmtiles`
   library, and Vite's dev server (sirv) supports it.
2. `*-geometry.bin` must be served **identity-encoded**. The pmtiles precedent does *not* transfer
   here: `.pmtiles` escapes host gzip because it isn't in any default compressible-mime list,
   whereas `application/octet-stream` frequently is. If a host transform-encodes the file, byte
   offsets computed against the uncompressed data no longer address the wire bytes.

§E carries the client-side guard for the case where either assumption fails.

## C. `start_edges` needs one new column: `edge_id`

`phases/postprocessing/build_approach_table.py` iterates `start_edges/records.npy` (`for r in
records`) but never records which row a selected approach came from, so today there is no way to
map an approach/exit leg back to its geometry. Change:

- Iterate with `enumerate()` and carry `edge_id = i` (the `start_edges/records.npy` row index —
  the same domain `<layer>-geometry.bin`/`.json` are keyed on for `start_edges`) into every row
  `select_approaches` and `build_tables` build.
- Add `edge_id` as a new **u4** column on `approaches.bin` (u2 tops out at 65,536; `start_edges`
  has **234,918** rows) and as a field on every `reverse_index` row (`hut_to_starts[hut_id]` /
  `start_to_huts[start_id]` entries) in `approaches.json`.

This is additive only — no existing column, row selection, or ranking logic changes.

**Cost:** `approaches.bin` grows 4 B × 2,139 rows (~8.5 KB, negligible). `approaches.json` grows
~1.3 MB raw (a `"edge_id":NNNNNN` field on 36,864 rows, serialized twice because `build_tables`
appends the *same* dict object to both `hut_to_starts` and `start_to_huts` and `json.dump` does no
object dedup) on a 12.3 MB / 1.5 MB-gzipped file. Acceptable, but see the note below.

**Deliberately not fixed here:** `start_to_huts` has no client consumer at all. `getExitLegs`
(`approaches.ts:15`) reads only `hut_to_starts`; every other reference to `start_to_huts` in
`huts/src/` is a `{}` test mock. It is 36,864 duplicated rows — roughly half of `approaches.json` —
and this change makes it half of the growth too. Dropping it belongs to the payload contract
(`docs/tour-suggestion-payload.md` §6), not to this spec; file it there rather than working around
it client-side.

## D. Direction / reversal

Per `docs/tour-suggestion-payload.md` §3, a leg walked opposite to how its record is stored needs
its ascent/descent swapped and its geometry/profile reversed for display. The engine already has
this exact fork point (`reverseLeg.ts`'s `forwardHutLeg`/`reverseHutLeg`/`forwardStartLeg`/
`reverseStartLeg`); it currently only handles the numeric fields.

- `HutEdgeRecord`/`ApproachRecord` (client types, `types.ts`) gain an `edgeId: number` field,
  populated at load time (`loadHutEdges.ts`, `loadApproaches.ts`) directly from the new columns —
  for `hut_edges` this is just the record's own array index (verified: `build_edge_payload.py`'s
  `pack_edges` preserves `records.npy` order 1:1, and `hut-edge-payload.json` reports 12,416 rows
  against a 12,416-row `records.npy`), now made explicit the same way `loadHutEdgesData` already
  assigns `records[i]`; for `approaches.bin` it's the new `edge_id` column from §C.
- **`ReverseIndexEntry` (`types.ts:121`) gains `edge_id: number`, and `getExitLegs`
  (`approaches.ts:14-29`) must thread it into the `ApproachRecord` it synthesizes.** This is not
  optional and not covered by the `loadApproaches.ts` bullet above: exit legs are *not* built from
  the records `loadApproachesData` returns — `getExitLegs` constructs an `ApproachRecord`
  field-by-field out of `reverseIndex.hut_to_starts` entries. Miss this and every exit leg gets
  `edgeId: undefined`, so the last leg of every tour renders as a permanent straight-line fallback.
- `HutLeg`/`StartLeg` gain `edgeId: number` (copied through unchanged by both forward/reverse) and
  `reversed: boolean` (`false` from `forward*`, `true` from `reverse*`).
- `LegSummary` (`search.ts`) and `TourResult.legs` gain the same two fields — mechanical threading,
  no behavior change to the search itself (dominance pruning, filters, sort order are all
  untouched: `edgeId`/`reversed` are display-only fields, never compared or branched on inside
  `search.ts`).

Orientation is unambiguous from the record direction: `start_edges` records store from = start
point, to = hut, so `forwardStartLeg` (approach) yields start→hut and `reverseStartLeg` (exit)
yields hut→start, which is exactly what each leg needs.

## E. Client geometry module

New `tourSearch/loadLegGeometry.ts`:

- `loadGeometryManifest(layer: 'hut_edges' | 'start_edges', baseUrl?)` — fetches and caches
  `<layer>-geometry.json` once, computes the prefix-sum byte-offset table. Fetched lazily, on the
  first tour opened, not at app load: 13.9 KB gzipped for `hut_edges`, ~260 KB for `start_edges`.
- `loadLegGeometry(layer, edgeId, reversed, baseUrl?)` — looks up the byte range, issues a `Range`
  `fetch()` against `<layer>-geometry.bin`, decodes the `f4` pairs into `[number, number][]`
  (`[lat, lng]`, matching `ResultsMap`'s existing convention), reverses the array if `reversed` is
  `true`. Results cached by `` `${layer}:${edgeId}` `` for the session — a tour reopened, or two
  tours sharing a leg, never refetch.
- **Must check for HTTP `206`.** A host that ignores `Range` answers `200` with the entire body —
  8 MB for `hut_edges`, ~150 MB for `start_edges`, per leg. On a non-`206` response, slice the
  requested range out of the returned buffer if the full body did arrive, and cache that decision
  so the whole-file download happens at most once per layer per session rather than once per leg.
  Do not silently retry.

## F. `ResultsMap.tsx` integration

For the selected chain, resolve each leg's `(layer, edgeId, reversed)` — `hut_edges` for
`chain.legs[1..-2]` (hut-to-hut), `start_edges` for the first and last leg (approach/exit) — and
fetch all of them in parallel via §E. `TourResult.legs` is documented (`types.ts:75-78`) as leg 0 =
`startId→huts[0]`, legs `1..len-2` = hut-to-hut, last = `huts[-1]→exitStartId`; a single-hut tour
has exactly two legs and no hut-to-hut slice, which the range handles without special-casing.

Concatenate the resulting point arrays in tour order into one polyline. **This relies on each leg's
geometry starting and ending exactly at that leg's own endpoints — verified**: across 4,000 hut
edges, the distance between an edge's first geometry point and its `from_hut_id` coordinate in
`huts.geojson` is 0 m at median, p90 and max. So real geometry lands exactly on the existing hut
`CircleMarker`s, with no snap offset and no visible jump when a leg switches from fallback to real
rendering. Junctions will carry one duplicated consecutive point (leg `i` ends where leg `i+1`
begins); harmless for Leaflet, no dedup needed. **Not yet verified for `start_edges`** — confirm
that a start edge's endpoint coincides with the corresponding `stations.geojson`/`parking.geojson`
coordinate before relying on the same guarantee for the approach and exit legs.

While a leg's fetch is in flight (or if it fails), render a straight dashed segment between that
leg's two endpoints as an immediate fallback — this is exactly today's rendering, scoped down to
one leg instead of the whole tour, so the tour is never blank while loading. The existing
"Schematische Verbindung, nicht der reale Wegverlauf" caption is shown only while at least one leg
is still on the fallback straight-line rendering; once every leg has resolved real geometry it's
removed.

`RecenterOnSelect` (existing, from the prior fix) is unaffected — it centers on the same computed
midpoint regardless of which rendering (straight or real) each leg currently uses.

## G. `dodo.py` / `copy_public_data` wiring

- `task_build_hut_edge_tiles` / `task_build_start_edge_tiles`: add the two new
  `--out-geometry-bin`/`--out-geometry-json` arguments and add their paths to each task's
  `targets`. `hut-edges.pmtiles`/`start-edges.pmtiles` themselves are unchanged — still built the
  same way, still used by `GraphPage`'s always-on tile layer for the visible line rendering (only
  the hover hit-test path changes, per §B).
- `task_build_approach_table`: no new targets, `approaches.bin`/`approaches.json` unchanged in
  name, `approaches.bin` grows one column.
- `PUBLIC_FILES` (dodo.py:109) gains all four new files: `hut-edge-geometry.bin`,
  `hut-edge-geometry.json`, `start-edge-geometry.bin`, `start-edge-geometry.json`. All four have a
  client consumer — the two `hut-edge-*` files by `GraphPage` and `ResultsMap`, the two
  `start-edge-*` files by `ResultsMap`'s approach/exit legs.
- `hut-edge-stats.json` remains in `PUBLIC_FILES` (shrunk 33.1 → 8.6 MB, not removed —
  `GraphPage`'s hover panel still reads its non-position fields at `GraphPage.tsx:10`).
- **`start-edge-stats.json` is removed from `PUBLIC_FILES`.** An earlier draft of this spec kept it
  on the grounds that "`GraphPage`'s hover panel still reads their non-position fields" — that is
  false. `GraphPage.tsx:10` reads only `/data/hut-edge-stats.json`, and grepping `huts/src/` for
  `start-edge-stats` returns nothing: the file has never had a consumer. It is 654 MB of shipped,
  unread data today. Since `ResultsMap` is the first-ever client consumer of start-edge data, this
  is the moment to stop copying it. It still gets built into `data/osm/` — only the copy into
  `huts/public/data/` goes away.
- **Flagged, not fixed here:** `start-edges.pmtiles` (106 MB) has no consumer either — nothing in
  `huts/src/` references it. Dropping it from `PUBLIC_FILES` is the same argument as
  `start-edge-stats.json` but is not implicated by this change; call it separately.

No new pipeline task, no change to `build_base_graph`/`build_hub_edges`/anything upstream of
tiling — this only touches the already-cheap postprocessing/tiling stage
(`build_edge_tiles.py` measures in the tens-of-seconds range per `pipeline/CLAUDE.md`'s
`build_edge_tiles` phase table, not hours). Rerunning the full `doit` DAG after this lands will
redo `build_hut_edge_tiles`, `build_start_edge_tiles`, `build_approach_table`, and
`copy_public_data` — **not** `build_base_graph`/`build_hub_edges`, since neither script's inputs
change. Per the root `CLAUDE.md`, running any `doit` task is still gated on an explicit ask even
though this particular rerun is cheap.

## Rejected alternatives

**Client-side MVT decoding of `hut-edges.pmtiles`/`start-edges.pmtiles` directly** (new
`@mapbox/vector-tile` + `pbf` dependencies, computing z14 tile coverage for each leg's bounding
box, stitching per-tile clipped line pieces back together by nearest-endpoint chaining). Rejected:
pmtiles/MVT is a *rendering* format — tippecanoe clips one LineString into multiple per-tile
fragments with no ordering metadata connecting them back together, so reconstructing one edge's
full path requires ad hoc geometric stitching with no correctness guarantee, on top of a new
undocumented reliance on tile-index math. The byte-range approach (§A-E) reuses a format this
codebase already has a working, tested convention for (`hut-edge-payload.bin` + `readColumns`) and
needs no new dependencies.

**Shipping full geometry inline in `hut-edge-payload.bin`** (no lazy fetch at all). Rejected:
defeats the entire reason `docs/tour-suggestion-payload.md` §1 kept geometry out of that payload in
the first place — it's loaded whole, up front, on every session, and is deliberately kept at
~43 KB gzipped. Embedding even RDP-simplified geometry for all 12,416 hut-edge rows would add 8.0 MB
raw to a 484 KB file, blowing that budget by orders of magnitude for the common case where a session
never opens a single tour.

**Carrying `geom_offset`/`geom_count` on approach rows instead of a `start_edges` manifest**
(so `ResultsMap` needs no manifest fetch for its two start-edge lookups per tour). Rejected on
measurement: two extra fields on 36,864 `reverse_index` rows, serialized twice, add ~3 MB raw to
`approaches.json` — a file loaded up front on *every* session — to avoid a ~790 KB / ~260 KB
gzipped manifest fetched lazily only when a user first opens a tour. It also forces a new DAG edge,
since `build_approach_table.py` has no access to the RDP-simplified point counts (`records.npy`'s
`geom_offset` indexes the full-resolution `geometry.npy`, not `*-geometry.bin`) and would have to
take `start-edge-geometry.json` as an input. Strictly worse on both counts.

**Leaving `hut-edge-stats.json`/`GraphPage` as they are, additive-only change.** Considered and
rejected in favor of migrating `GraphPage` too (explicit user decision): maintaining two on-disk
formats for the same underlying per-edge geometry (the old inline-JSON `positions` field and the
new byte-range binary) is exactly the kind of divergence this change should avoid, and `GraphPage`'s
own fetch gets faster, not slower, as a side effect (§B).

## Testing

Both pipeline scripts **already have colocated test files** — extend them, do not create new ones:

- **`pipeline/tests/test_build_edge_tiles.py`** (exists; `test_rdp_keep_indices_collapses_straight_line`,
  `test_rdp_keep_indices_preserves_a_corner`, `test_build_stats_resolves_ids_via_id_table`).
  `test_build_stats_resolves_ids_via_id_table` calls `build_stats(...)` directly and asserts on the
  dicts it returns — **splitting `build_stats`'s output will break it**, so updating it is part of
  the change, not a follow-up. Add: `geometry.bin`'s byte layout matches `geometry.json`'s
  `point_counts` (prefix sums land on real point boundaries, total length == `sum(point_counts) * 8`),
  and `<layer>-stats.json` no longer has a `positions` key.
- **`pipeline/tests/test_build_approach_table.py`** (exists; 7 tests covering access filtering,
  k-selection and the reverse index). Add: `edge_id` round-trips correctly through
  `select_approaches`/`build_tables` and lands in both `approaches.bin` and every `reverse_index`
  row, and that it is the true `start_edges/records.npy` row index (not a per-hut counter).
- `pipeline/tests/test_dodo_wiring.py` asserts nothing about `targets` or `PUBLIC_FILES`, so §G
  needs no change there.

Client side:

- `huts/src/tourSearch/loadLegGeometry.test.ts` (new) covers manifest offset-table construction,
  `Range` header correctness, point decoding, the `reversed` flag flipping point order, and the
  non-`206` fallback path from §E.
- `reverseLeg.test.ts` extends to assert `edgeId`/`reversed` propagate correctly through
  `forwardHutLeg`/`reverseHutLeg`/`forwardStartLeg`/`reverseStartLeg`.
- `approaches.test.ts` extends to assert `getExitLegs` threads `edge_id` from the `hut_to_starts`
  entry onto the synthesized leg (the §D trap — without this test, exit-leg geometry silently
  never renders).
- `loadApproaches.test.ts` and `loadHutEdges.test.ts` extend to assert `edgeId` is populated.
- `huts/src/tourSearchPage/`: existing `// @vitest-environment jsdom` UI-test pattern extends to
  `ResultsMap` — mock `loadLegGeometry`, assert the fallback-straight-line vs. real-geometry
  rendering switches correctly per leg and that the caption disappears once every leg resolves.
