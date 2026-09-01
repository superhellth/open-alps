# Official Tours — Frontend Integration Design

**Problem:** The pipeline now ships matched official-tour data (`data/osm/tour_edges/` →
`huts/public/data/tour-edges.pmtiles`, `tour-edge-payload.bin/json`, `tour-edge-geometry.bin/json`,
`tours.json`) for tours defined in `pipeline/tours/` (currently Kaisertour, Welser Höhenweg — see
`docs/superpowers/specs/2026-08-29-official-tours-integration-design.md`,
`docs/superpowers/specs/2026-08-30-tour-folder-ingestion-design.md`). None of it is consumed by
`huts/src` yet. This spec covers only the client-side consumption — the pipeline contract is fixed
and out of scope.

**Goal:** Let a user browse the official tours as fixed itineraries (not a search result) inside
`TourSearchPage`, see each tour's legs (distance/ascent/descent/difficulty) and its real routed
geometry on the map, reusing the existing search UI's map/list machinery rather than building a
parallel page.

## 1. Scope decision: filter out tours with any gap leg

`match_tour_edges.py` legitimately produces some legs with no matched row (`tour-match-gaps.json`
— an endpoint too far from any hub, `hmm_match_broken`, etc. — see the backend spec §2.5). Faking a
missing leg (straight line, zero stats) would misrepresent a real, waymarked route — the same
"never faked" principle the backend spec already applies to `records.npy`.

Per user decision: a tour with **any** gapped leg is filtered out of the list entirely, not shown
partially. This keeps the UI simple (no gap badges, no broken-line rendering, no "N legs missing"
messaging) at the cost of showing fewer tours today — with the current two source tours both
carrying gaps (`tour-match-gaps.json`), the official-tours list starts **empty**. That's an accepted
starting state; more tours clearing the filter is a pipeline-side improvement (better snap
thresholds, more `pipeline/tours/` folders), not a frontend concern. The empty state must read as
"no fully-matched official tours yet", not as a stuck loading spinner.

## 2. Data layer (`huts/src/tourSearch/`)

- **`loadOfficialTours.ts`** — fetches `tours.json` as-is: per tour, `tourId`, `name`, ordered legs
  of `{legIndex, from: {type, id} | null, to: {type, id} | null}`.
- **`loadTourEdges.ts`** — mirrors `loadHutEdges.ts` against `tour-edge-payload.bin/json` via the
  existing `readColumns` helper, reading the extra `tour_id`/`leg_index` columns the payload already
  carries (`binfmt.VARIANT_NAMES["4"] == "OFFICIAL"` — informational only, every row here is already
  that variant by construction of the source file). Returns records in a `Map<`tourId,legIndex`,
  TourEdgeRecord>` keyed for the join in §3, not a flat array like `loadHutEdges` — there is no
  chain-search consumer here that wants array order.
- **`loadLegGeometry.ts`**: add `'tour_edges'` to `GeometryLayer` and a `LAYER_FILES` entry for
  `tour-edge-geometry.bin`/`.json`. No other change — the byte-range-fetch logic is layer-agnostic
  already.
- **`officialTours.ts`** — `buildOfficialTourViews(tours, tourEdgeRecords)`: joins §2's two sources
  per tour. A tour is included only if every leg has a non-null `from`/`to` **and** a matching
  `tourEdgeRecords` entry; otherwise dropped (§1). For an included tour, computes leg-level DIN
  duration (`dinDurationH`, already shared) and tour-level totals (distance/ascent/descent/duration)
  by summing legs. Output type `OfficialTourView`:
  ```ts
  interface OfficialTourLeg {
    legIndex: number
    from: { type: 'hut' | 'station' | 'parking' | 'partner'; id: number }
    to: { type: 'hut' | 'station' | 'parking' | 'partner'; id: number }
    edgeId: number
    reversed: false // tour_edges rows are already directional src->tgt, never re-oriented
    distanceM: number; ascentM: number; descentM: number; durationH: number
    maxEleM: number; sacRank: number; viaFerrata: boolean
  }
  interface OfficialTourView {
    tourId: number
    name: string
    legs: OfficialTourLeg[]
    totalDistanceM: number; totalAscentM: number; totalDescentM: number; totalDurationH: number
  }
  ```

## 3. Page composition (`TourSearchPage.tsx`)

A `ToggleButtonGroup` ("Freie Suche" / "Offizielle Touren") above the existing filter form, backed
by `const [viewMode, setViewMode] = useState<'search' | 'official'>('search')`.

- **`search` mode**: today's behavior, unchanged.
- **`official` mode**: the filter form (mode/leg-count/leg-time/difficulty/hut-type boxes) is
  hidden — there is no query to build, the list is fixed. `TourList`'s search-result list is
  replaced by a new `OfficialTourList` (own file, not a variant prop on `TourList` — different
  enough data shape that branching inside `TourList` would just be a large prop-optional mess) that
  renders `OfficialTourView[]` as cards: name, leg count, total distance/ascent/descent/duration.
  Clicking a card sets `selectedOfficialTour` (mirrors `expandedChain`'s role) and is shown in the
  same `ResultsMap` (§4). Empty list (§1's starting state): a plain `Typography` message, no
  spinner, once `officialTourViews` has been computed (not still `null`).

`loadOfficialTours()`/`loadTourEdges()` run once in the existing `useEffect` alongside the current
`Promise.all` fetches; `buildOfficialTourViews` runs once via `useMemo` off their results.

## 4. Map rendering — generalize `ResultsMap`, don't fork it

`ResultsMap`'s `chainPositions`/`useLegGeometries`/`chainSegments` are typed to `TourResult`
specifically (search chains: hut/start-point waypoints, `hut_edges`/`start_edges` geometry layers).
Generalize to a shape both a search chain and an official tour can produce, since after §1's filter
every leg is fully resolved (no null waypoints, no null edgeId to special-case):

```ts
interface RouteWaypoint { lat: number; lng: number }
interface RouteLeg { edgeId: number; reversed: boolean; layer: GeometryLayer }
interface Route { waypoints: RouteWaypoint[]; legs: RouteLeg[] } // waypoints.length === legs.length + 1
```

`ResultsMap` takes `route: Route | null` instead of `selectedChain: TourResult | null`.
`TourSearchPage` adapts whichever is selected:
- search chain → today's `chainPositions` logic, legs `legLayer(i, legs.length)` exactly as now.
- official tour → waypoints from each leg's `from`/`to` looked up in the same `hutCoordsById`/
  `startById` maps already loaded (a tour leg's hut/station ids live in the same index space as
  search results — confirmed against the backend spec, no new lookup table needed), legs all on the
  `'tour_edges'` layer.

Marker/hut-class rendering (the non-chain overview markers, operator legend) is untouched — it only
depends on `hutCoordsById`/`hutClassByIndex`, not on which mode produced the route.

## 5. Testing

- `loadTourEdges.test.ts`: column round-trip against a synthetic manifest+buffer (same style as
  `loadHutEdges.test.ts`), keyed lookup by `(tourId, legIndex)`.
- `officialTours.test.ts`: a tour with all legs resolved is included with correct summed totals; a
  tour with one gapped leg (`from: null`, or a `legIndex` absent from `tourEdgeRecords`) is dropped
  entirely; DIN duration per leg matches `dinDurationH` directly.
- `ResultsMap`'s generalized `Route` shape: existing search-chain rendering behavior is unchanged
  (regression via existing tests/manual check), plus a case constructing a `Route` from an
  `OfficialTourView` renders one `Polyline` per leg on the `tour_edges` layer.
- Manual check once wired: toggle to "Offizielle Touren" with the current (empty) dataset shows the
  empty-state message, not a stuck spinner; add a temporary fixture tour with all legs resolved (or
  once a real one clears the pipeline gap) to verify list card → map selection end to end.

## Out of scope

- Any pipeline-side change to reduce gap legs (snap thresholds, more `pipeline/tours/` folders) —
  tracked against the pipeline, not here.
- Sorting/filtering the official-tour list, difficulty-based filtering — revisit once the list is
  larger than a handful of tours.
- Showing partially-matched tours (§1) — revisit only if the empty/near-empty list proves to be a
  real usability problem once more tours are added upstream.
- `GraphPage`'s `#graph` route — `tour-edges.pmtiles` stays unused there; out of scope per the
  brainstorming answer that placed this feature inside `TourSearchPage`.
