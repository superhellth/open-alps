# Tour search frontend rewrite — design

Date: 2026-08-26
Status: approved in brainstorming, ready for implementation planning
Scope: `huts/` app — TypeScript migration, tour-search engine correctness/perf fixes, unified MUI
UI shell, map integration. Does not touch `pipeline/` or the static data contract it emits.

## Why

`huts/src/tourSearch/` (plain JS) has two correctness bugs and a performance cliff, found during
a review of the engine ahead of a planned UI rewrite:

1. **Transit (öpnv) mode allows mixed start/end types.** `mode === 'car'` enforces loop closure
   (`exitLeg.startId === entryLeg.startId`), which incidentally also forces the same source type
   since it's the same point. `mode === 'transit'` has no equivalent constraint at all — a result
   can start at a parking lot and finish at a train station, or vice versa. Requirement: transit
   tours must be station → …huts… → station.
2. **Car mode should be parking-only**, symmetrically: today it only checks *same point*, not
   *point is a parking lot*. A car tour closing its loop at a train station's lot is currently
   accepted; it shouldn't be.
3. **Exponential blowup past `legCountMax` ≈ 3.** The search seeds its frontier from every hut
   that has *any* approach leg — i.e. simultaneously from every parking lot and station in the
   country, not from a single query-specified trailhead (deliberately: nationwide search is a
   requirement, not a bug — see "Rejected: start-region scoping" below). Each additional layer
   multiplies an already-large multi-source frontier by the branching factor again. On top of
   that, the current state is keyed by the full ordered path, so distinct *orderings* of the same
   hut set are tracked as separate states — a permutation blowup on top of the combinatorial one.

Bundling the fixes into the TS migration (rather than fixing twice) because the migration touches
every engine file regardless.

## Rejected: start-region scoping

Considered constraining the search to a user-picked trailhead/region as the perf fix. Rejected:
nationwide "any trailhead in Austria" search is a real requirement, not an accidental side effect
to design away. Perf must be solved within that constraint, not by removing it.

## Rejected: best-effort / beam search

Considered capping states-per-layer to a top-N by running duration (approximate, would silently
drop valid tours). Rejected: exhaustiveness (find every valid tour, given the query's filters) is
a hard requirement. The dominance-pruning approach below is exact — it never discards a state that
could produce a genuinely distinct final result — so it was preferred over an approximate method.

## A. Engine correctness fixes (`tourSearch/search.js` → `.ts`)

Both fixes live at the two existing chokepoints, no new chokepoints needed:

- **Seed step** (building the initial layer from `getApproachLegs`): filter
  `approachLeg.sourceType === SOURCE_TYPE_STATION` when `mode === 'transit'`, or
  `approachLeg.sourceType === SOURCE_TYPE_PARKING` when `mode === 'car'`.
- **Finish step** (`collectFinished`'s `getExitLegs` loop): filter
  `exitLeg.sourceType === SOURCE_TYPE_STATION` when `mode === 'transit'`, or
  `exitLeg.sourceType === SOURCE_TYPE_PARKING` when `mode === 'car'` — *in addition to* the
  existing `mode === 'car' → exitLeg.startId === s.startId` check (both must hold for car).

`SOURCE_TYPE_STATION` / `SOURCE_TYPE_PARKING` constants currently live only in `App.jsx`
(`1`/`2`); move them into the engine's `types.ts` as the canonical source, imported by both the
engine and the UI.

No change to `resolveVariant.js`, `legFilters.js`, `adjacency.js`, `reverseLeg.js`,
`dinDuration.js`, `binaryColumns.js` — these are unaffected by either fix.

## B. Engine performance fix: dominance pruning by visited-set

**Key fact this relies on:** a state's future expansion possibilities — which edges it can still
take, whether it can still close a loop — depend only on `(currentHut, startId, visitedSet)`.
No per-leg filter (`maxLegTimeH`, ascent cap, `maxEleM`, via-ferrata) is a function of anything
accumulated so far; each is evaluated against the *next* leg in isolation. Accumulated
`totalDurationH`/`totalAscentM`/`totalDescentM`/`totalDistanceM` matter only for the final
duration-sort and for display — never for whether a future leg is legal.

**Consequence:** two states sharing `(currentHut, startId, visitedSet)` — reached via different
orderings of the same huts — are functionally interchangeable from that point forward. Only one
needs to survive: the one with the lower `totalDurationH` (the finished list's sort key). This is
exact, not approximate — discarding the higher-duration twin never removes a *distinct final
result*, because:

- Both twins, if extended identically, produce the same final `visitedSet` with the same set of
  huts — the only difference is internal ordering up to the collapse point.
- `suppressSimilar` (unordered hut-set overlap, `diversity.js`) already treats any two chains with
  identical hut sets as maximally overlapping (100%) and keeps only one, at any threshold ≤ 1. So
  even without pruning, only one such twin would ever survive to the shown results.
- `dedupeReversePairs` operates on exact forward/reverse order and is unaffected — pruning happens
  per-layer, before that step, and never touches genuinely order-distinct tours (different edges
  taken, not just different visitation order of a shared prefix... **caveat**, see below).

**Caveat — this only collapses identical-*set* twins, not "similar-route" twins.** Two states with
different visited sets are never merged, regardless of duration. The pruning is scoped exactly to
what's provably safe.

### Implementation

Per layer, replace the plain `Map<hutIndex, State[]>` with a dominance map keyed by a composite of
`(hutIndex, startId, visitedSetKey)`:

- `visitedSetKey`: a `bigint` bitmask over hut index (`graphData.hutEdges.hutIds.length` is
  ~956–1173 today — comfortably a `bigint`, no external bitset library needed). Built
  incrementally: `nextKey = key | (1n << BigInt(h2))`.
- Composite key: template-string `` `${hutIndex}|${startId}|${visitedSetKey}` `` (string key into a
  plain `Map`; simplest correct option, revisit only if profiling shows it's hot).
- On inserting a state whose key already exists, keep whichever of the two has the lower
  `totalDurationH`; drop the other.

This replaces state *storage* only — `legPasses`, `buildAdjacency`, `getApproachLegs`/
`getExitLegs`, the layer-by-layer loop structure, and the revisit check (`s.path.includes(h2)`,
which still needs the *ordered* `path` for output and for the revisit check itself) are unchanged.
`killCounters` gains no new counter for this — it's not a query-constraint rejection, it's an
internal representation change. (A `deduped`/`dominated` diagnostic counter is a nice-to-have, not
required.)

### Target and validation

Baseline target: `legCountMax` 6–8 should be comfortably fast; up to 14 should remain usable
(exact numeric budget to be confirmed empirically during implementation — no fixed ms target was
set, this is "materially better than today's cliff at 3-4", validated by the smoke test below).

Test plan for this section:
- Unit test: on a small synthetic graph, assert output (chain set, ignoring internal ordering
  quirks) is identical with and without pruning — proves exactness.
- Extend `realData.smoke.test.js` (or a new perf-focused smoke test) to run at `legCountMax` up to
  14 against the real shipped payload and assert it completes (no fixed wall-clock assertion
  needed in CI, but useful as a manual benchmark during implementation).

## C. TypeScript migration

Whole `huts/` app, not just the engine — one consistent codebase, strict mode from day one.

- `huts/tsconfig.json`: `"strict": true`, targeting the existing Vite + `@vitejs/plugin-react`
  setup (no build-tool change needed; Vite handles `.ts`/`.tsx` natively).
- New `package.json` script: `"typecheck": "tsc --noEmit"`, run alongside `lint`/`test` (not
  merged into either — keep them independently invokable, matching existing script granularity).
- All `.js`/`.jsx` under `huts/src/` convert to `.ts`/`.tsx`, including every `tourSearch/*.js`
  module and its paired `*.test.js` (vitest runs `.test.ts` natively, no config change needed).
- New `huts/src/tourSearch/types.ts`: `ApproachRecord`, `HutEdgeRecord`, `Leg`, `ChainState`,
  `Query`, `TourResult`, `KillCounters`, plus the `SOURCE_TYPE_STATION`/`SOURCE_TYPE_PARKING`
  constants moved here from `App.jsx` (see section A).
- `findTours`/`loadTourSearchData`'s public shape (`index.js` → `index.ts`) is unchanged — this is
  an internal typing pass, not an API redesign.

## D. Unified UI shell (MUI)

New dependencies: `@mui/material`, `@emotion/react`, `@emotion/styled`.

- `huts/src/theme.ts`: one `createTheme()` call — palette, spacing, typography — single source for
  later theming. No dark-mode requirement stated; theme structure should not preclude it later but
  implementing it now is out of scope.
- `huts/src/AppShell.tsx`: MUI `AppBar` + `Tabs` (or equivalent) for the three destinations —
  Karte (`App.jsx`'s map), Trail-Graph (`GraphPage.jsx`), Tourensuche (`TourSearchPage.jsx`) —
  replacing the copy-pasted `<header>`/`nav-link` block each page currently rolls on its own.
  Router stays the existing hash-based `useSyncExternalStore` approach in `main.jsx` — no
  react-router; the shell wraps whichever page component the router picks, it doesn't replace the
  router.
- `main.tsx`: wrap `<Router />` in `<ThemeProvider theme={theme}><CssBaseline />...`.
- `TourSearchPage.tsx` form fields → MUI (`TextField`, `Select`, `Checkbox`, `Slider` where a
  range fits better than two number inputs — e.g. leg-count min/max, leg-time min/max). Results
  list → MUI `List`/`Card`. `CircularProgress` shown while `findTours` runs (still a synchronous
  call on submit; a spinner requires deferring the heavy call a tick via `setTimeout`/
  `requestAnimationFrame` so React can paint the spinner first — no Web Worker in this spec's
  scope, since section B's fix is expected to make the synchronous cost acceptable at the stated
  target range; a worker remains a reasonable future follow-up if a query still stalls the UI
  noticeably).
- `App.jsx`'s existing map (all ~1173 hut markers) is visually restyled to sit under the new shell
  but its rendering logic is untouched by this spec.

## E. Map integration: selected tour → map

Selecting a result in `TourSearchPage` draws that tour's route. Rather than lifting shared state
into `App.jsx`'s big all-hut map (a separate hash-router destination, and cluttered with markers
irrelevant to one tour), `TourSearchPage.tsx` embeds its **own**, smaller `react-leaflet`
`MapContainer` instance in the results pane:

- Base OSM tile layer (same as `App.jsx`).
- On result selection: a `Polyline` through the selected chain's hut coordinates (looked up from
  `huts.geojson`, already fetched on mount) plus a marker for the start/end trailhead(s) (from
  `stations.geojson`/`parking.geojson`, already fetched and joined via `idFromOsmFeatureId`).
  No markers for huts outside the selected tour.
- No new data fetches — reuses the three GeoJSON responses `TourSearchPage` already loads on
  mount for hut-name/start-point lookups.

This keeps `App.jsx` untouched functionally and avoids introducing cross-hash-route shared state
into the router for a single feature.

## F. Testing

- **Engine**: vitest, as today — every existing `*.test.js` ports to `*.test.ts` unchanged in
  intent. New tests: station-only transit (seed + finish), parking-only car (seed + finish),
  dominance-pruning exactness (small synthetic graph, with/without pruning → same result set),
  `legCountMax` up to 14 against real shipped data (extends the existing smoke test).
- **UI**: new — `@testing-library/react` + jsdom environment (vitest config gains
  `environment: 'jsdom'` for UI test files, or a separate vitest project if engine tests should
  stay on the faster default environment — decide during implementation based on what's simplest
  in the existing single `vitest.config`, if one exists, or CLI flags). Flow test on
  `TourSearchPage`: change a form field → submit → results render → click a result → route/marker
  state updates. `react-leaflet` mocked per standard RTL pattern (assert on component
  state/props/rendered marker count, not on actual Leaflet DOM/tile behavior).
- `typecheck` script added; expected to be run manually/in CI alongside `lint`/`test` (no CI
  pipeline exists in this repo today per `CLAUDE.md` — "No test setup exists yet" is now stale and
  should be corrected there once this ships).

## Non-goals

- No backend/server — data sources unchanged (ArcGIS layer, OHRS, static pipeline outputs).
- No change to `pipeline/` or the data contract in `docs/tour-suggestion-payload.md`.
- No dark mode, no i18n beyond the existing German UI strings.
- No Web Worker offload for the search call (see section D) — revisit only if pruning doesn't
  bring perceived latency down enough.
- No react-router adoption — existing hash router stays.
