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
messaging) at the cost of showing fewer tours today. Against the current pipeline output
(`data/osm/tour-match-gaps.json`, not the stale copy under `huts/public/data/` — see §5):

| Tour | Routed legs | Gaps |
|---|---|---|
| Kaisertour | 1 of 4 | legs 0, 2, 3 — `leg_endpoint_unsnapped` (2.0 km / 2.1 km from the nearest hub) |
| Welser Höhenweg | 4 of 5 | leg 0 only — valley station 232 m from the trace |

so the official-tours list starts **empty**. That's an accepted starting state. Note that Welser
Höhenweg misses only its valley approach leg — its four hut-to-hut stages are contiguous and fully
routed — i.e. today's empty list is largely a snap-threshold artifact. Closing that is a
**pipeline-side** concern (snap thresholds, hub coverage, more `pipeline/tours/` folders), tracked
against the pipeline and explicitly not worked around here. The empty state must read as "there are
no complete official tours yet", not as a stuck loading spinner — exact wording in §3.2.

## 2. Data layer (`huts/src/tourSearch/`)

- **`loadOfficialTours.ts`** — fetches `tours.json` as-is: per tour, `tourId`, `name`, ordered legs
  of `{legIndex, from: {type, id} | null, to: {type, id} | null}`. `type` is one of
  `'hut' | 'station' | 'parking' | 'partner_betrieb'` — the exact strings `lib/hubs.py`'s
  `HUB_TYPE_JSON_NAMES` emits. Note `partner_betrieb`, **not** `partner`: the frontend's own
  `SOURCE_TYPE_PARTNER` naming does not apply to this file, and a mismatch here would silently drop
  partner endpoints.
- **`loadTourEdges.ts`** — mirrors `loadHutEdges.ts` against `tour-edge-payload.bin/json` via the
  existing `readColumns` helper, reading the extra `tour_id`/`leg_index` columns the payload already
  carries (`binfmt.VARIANT_NAMES["4"] == "OFFICIAL"` — informational only, every row here is already
  that variant by construction of the source file). Each record carries `edgeId: i`, its **payload
  row index** — exactly as `loadHutEdges` does — because that index is what
  `tour-edge-geometry.json`'s `point_counts` is keyed by; nothing else in the payload identifies the
  geometry. Returns records in a `Map<`tourId,legIndex`, TourEdgeRecord>` keyed for the join in §3,
  not a flat array like `loadHutEdges` — there is no chain-search consumer here that wants array
  order.
- **`loadLegGeometry.ts`**: add `'tour_edges'` to `GeometryLayer` and a `LAYER_FILES` entry for
  `tour-edge-geometry.bin`/`.json`. No other change — the byte-range-fetch logic is layer-agnostic
  already.
- **`officialTours.ts`** — `buildOfficialTourViews(tours, tourEdgeRecords)`: joins §2's two sources
  per tour. A tour is included only if every leg has a non-null `from`/`to` **and** a matching
  `tourEdgeRecords` entry; otherwise dropped (§1). For an included tour, computes leg-level DIN
  duration (`dinDurationH`, already shared) and tour-level totals (distance/ascent/descent/duration)
  by summing legs. Output type `OfficialTourView`:
  ```ts
  type TourEndpointType = 'hut' | 'station' | 'parking' | 'partner_betrieb'
  interface OfficialTourLeg {
    legIndex: number
    from: { type: TourEndpointType; id: number }
    to: { type: TourEndpointType; id: number }
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
  enough data shape that branching inside `TourList` would just be a large prop-optional mess).
  Clicking a card sets `selectedOfficialTour` (mirrors `expandedChain`'s role) and is shown in the
  same `ResultsMap` (§4). Empty list (§1's starting state): a plain `Typography` message, no
  spinner, once `officialTourViews` has been computed (not still `null`).

`loadOfficialTours()`/`loadTourEdges()` run once in the existing `useEffect` alongside the current
`Promise.all` fetches; `buildOfficialTourViews` runs once via `useMemo` off their results.

### 3.1 What an `OfficialTourList` card shows

A card whose collapsed form is only name + totals does not answer the two questions a user picks an
official tour by — **which huts** and **where** — so it mirrors `TourList`'s card structure rather
than inventing a thinner one:

- **Collapsed:** name, leg count, total duration/↑/↓/distance (same one-line format as `TourList`).
- **Expanded:** the waypoint chain (`Hütte A → Hütte B → … → Bahnhof X`) with the same
  `hutClassBadge`/`OPERATOR_COLOR` badges `TourList` renders, then the per-leg
  `Etappe | Dauer | ↑ | ↓ | Distanz` table. §2 already computes every field this needs; only the
  rendering is new.
- **Waypoint labels are mixed-type.** A tour endpoint is a hut *or* a start point — Welser
  Höhenweg's last leg ends at a station — so label `type: 'hut'` via `hutNameById` and every other
  type via the existing `startLabel`. Reuse `helpers.ts`'s labelling rather than a second
  formatter.
- **Stage numbers are displayed as `legIndex + 1`.** `legIndex` is 0-based but derives from
  `1.gpx…5.gpx`, and users cross-check the list against the tour's own published "Etappe 3". A
  0-based table is an off-by-one against every description of the route.
- **Keep the collapse chevron.** `TourList`'s `‹`/`›` widen the map to full width; on a map-first
  page that affordance must not disappear just because the mode changed. Sort/paging controls are
  deliberately dropped (§"Out of scope") — the collapse is not.

### 3.2 Mode switching must not leave stale state on screen

- **`excludedHutIndices` is reset in `official` mode.** It is derived from `form`
  (`TourSearchPage.tsx:139-148`) and dims the overview hut markers. Hiding the filter form does not
  reset `form`, so without this the user sees greyed-out huts caused by controls they cannot see.
  Pass an empty `Set` while `viewMode === 'official'`.
- **Switching mode clears the other mode's selection** (`setExpandedChain(null)` /
  `setSelectedOfficialTour(null)`), so the map never keeps drawing a route that is not in the
  visible list.
- **`result` itself is preserved** across a toggle round-trip — coming back to `search` must not
  discard a search the user already ran. This is intentional, not an oversight.
- **Empty-state wording** avoids pipeline vocabulary: "matched" reads to a user like a search that
  failed. Use e.g. *„Für die offiziellen Touren liegen derzeit keine durchgehend berechneten Routen
  vor."*

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

`RecenterOnSelect` is re-typed to `Route` along with the rest, and **switches from
`map.setView(midpoint, 11)` to `fitBounds` over the route's waypoints.** The fixed zoom 11 was tuned
for 2–4-leg search chains; official tours are 4–8 legs over much longer distances (Welser Höhenweg
alone spans four stages), and at zoom 11 such a route runs off both edges of the viewport the moment
it is selected. Its existing "do nothing when the selection goes back to `null`" behavior — so
deselecting never yanks the user's pan/zoom — is kept as is.

Marker/hut-class rendering (the non-chain overview markers, operator legend) is untouched — it only
depends on `hutCoordsById`/`hutClassByIndex`, not on which mode produced the route.

## 5. Testing

- `loadTourEdges.test.ts`: column round-trip against a synthetic manifest+buffer (same style as
  `loadHutEdges.test.ts`), keyed lookup by `(tourId, legIndex)`.
- `officialTours.test.ts`: a tour with all legs resolved is included with correct summed totals; a
  tour with one gapped leg (`from: null`, or a `legIndex` absent from `tourEdgeRecords`) is dropped
  entirely; DIN duration per leg matches `dinDurationH` directly.
- `officialTours.ts` label/type handling: a leg endpoint of type `partner_betrieb` resolves (guards
  the §2 naming trap), and a mixed hut→station tour labels both endpoints correctly.
- `ResultsMap`'s generalized `Route` shape: existing search-chain rendering behavior is unchanged
  (regression via existing tests/manual check), plus a case constructing a `Route` from an
  `OfficialTourView` renders one `Polyline` per leg on the `tour_edges` layer.
- `OfficialTourList`: a card renders stage numbers as `legIndex + 1`; switching `viewMode` clears
  the other mode's selection while leaving `result` intact.
- Manual check once wired: toggle to "Offizielle Touren" with the current (empty) dataset shows the
  empty-state message, not a stuck spinner; add a temporary fixture tour with all legs resolved (or
  once a real one clears the pipeline gap) to verify list card → map selection end to end.

**Prerequisite — `huts/public/data/` is stale.** Its `tours.json` (Aug 29) is the pre-folder-ingestion
25-tour `{tourId, globalId, name, shortCode, isLoop, homepage, hutIndices}` shape, and its
`tour-edge-payload.*`/`tour-match-gaps.json` are from the same old run; `data/osm/` (Sep 1) holds the
current 2-tour `legs`-shaped output. Since `realData.smoke.test.ts` reads `../../public/data/`
directly, any tour test or dev-server check written today runs against a file whose shape does not
match §2 at all. `copy_public_data` has to run before this work is verifiable — and per
`pipeline/CLAUDE.md` that needs explicit user confirmation before any `doit` invocation.

## Out of scope

- Any pipeline-side change to reduce gap legs (snap thresholds, more `pipeline/tours/` folders) —
  tracked against the pipeline, not here.
- Sorting/filtering the official-tour list, difficulty-based filtering — revisit once the list is
  larger than a handful of tours.
- Showing partially-matched tours (§1) — revisit only if the empty/near-empty list proves to be a
  real usability problem once more tours are added upstream.
- `GraphPage`'s `#graph` route — `tour-edges.pmtiles` stays unused there; out of scope per the
  brainstorming answer that placed this feature inside `TourSearchPage`.
