# Trip Planner Reenvision — Frontend Design

## Problem

The current `TourSearchPage.tsx` is a search tool: a filter form produces a list of candidate
routes, one of which can be shown on a map. It does not help a user get from "where should I go?"
to "I have a booked, saved trip." Gaps:

1. **Form-first flow.** Form → list → map is rigid. Users cannot see *where* matching tours exist
   before committing to a start point, and the default order (shortest total duration first) is a
   poor answer to "best tour for me".
2. **No planning object.** A selected route is ephemeral. It cannot be edited, saved or revisited.
   The user can only accept or reject a precomputed chain.
3. **No path to booking.** Availability is a filter/badge on results, not tied to a concrete
   itinerary. Booking is N separate reservations (one per hut and night, no cart), and the app does
   not help the user keep track of them.
4. **Dated, generic visual design.** Default MUI theme, light OSM tiles.

Data trust in results is a pipeline-layer concern (this repo fixes data problems at their root
layer). It is not part of this design; `docs/backlog.md` tracks the derived UI need.

## Customer & job-to-be-done

Primary customer: **solo/small-group hikers planning a multi-day Alpine-Club-hut tour.** The job:
go from a rough idea ("somewhere with ~4 days, moderate difficulty") to a concrete, saved, bookable
itinerary they can take on the trip.

## Scope

One coherent journey, **Discover → Customize → Plan nights → Take along**, designed as one spec
because the four steps share one object (the trip) and one graph.

**Out of scope:**
- `#admin` routing-graph debug view: untouched.
- In-app booking transactions: the app deep-links to the booking system or shows contact info.
- Mobile: desktop is the design target. A phone view (e.g. a read-only trip view as the share-link
  landing) is postponed; `docs/backlog.md` tracks it.
- Accounts/backend: trips live in `localStorage`, leave the browser via share link/export.
- Pipeline changes and data-quality UI.

## Journey

### Discover

The filter bar sets day count, walking time per day, difficulty, hut types (AV / other, serviced /
self-service), mode (`car` / `transit` / `village`), and the start date and party size copied into a picked trip. It
never lists tours itself.

Each filter change runs one whole-graph search and yields the matching tours **grouped by start
point**. The map shows one marker per start point (station, parking spot, Bergsteigerdorf partner),
clustered by zoom level: a cluster shows the sum of its members' match counts, so zooming out gives
a feel for how many tours exist per region, and zooming in resolves to single start points. There is
no separate "region" filter; the viewport is the region.

Clicking a marker or cluster opens the ranked tour list for that area (a cluster zooms in first).
Hovering a tour previews its route on the map; only the focused tour's geometry is fetched, never
the whole result set. Official tours appear in the same lists, tagged as such, instead of a
separate view mode.

The default ranking is **fit to targets** (see "Search, ranking, clustering"). A sort control stays
for ascent, distance, duration.

### Customize

Picking a tour makes it the active trip. The trip is then edited leg by leg (see "Trip editor").
Every edit stays inside the routing graph, so a trip is always a routable chain.

### Plan nights

The trip panel shows, per night: the hut, availability for the trip's start date and party size, a
booking link (or contact info for direct-booking-only huts) and a booking status. The app has no
booking data: the status is a checklist the user sets by hand ("offen" → "angefragt" →
"bestätigt"), because a hut request often waits days for confirmation.
At trip level it answers which start dates make the whole chain bookable, and sliding the whole
trip by a day is one action.

"Unknown" availability (huts with no `ohrs_hut_id`, failed fetches) is a distinct state from "full"
everywhere it is shown, filtered or ranked.

Per-night states always pair a shape with text, never colour alone:

| Availability | Shape | Text |
|---|---|---|
| free | filled dot | "12 Plätze frei" |
| few (free beds < 2 × party size) | half dot | "3 Plätze frei" |
| full | crossed-out ring | "ausgebucht" |
| unknown | circled "?" | "Verfügbarkeit unbekannt – direkt anfragen" |

The booking status is a three-step control on the stage's signpost; "bestätigt" adds a check mark.
A night that no longer resolves ("changed since saved", see the data model) renders its signpost
as an outline without the yellow fill, reading "Seit dem Speichern geändert – nicht mehr im
Wegenetz". It offers no replacement; the user fixes it through the trip editor.

### Take along

The trip leaves the browser via a share link (URL-encoded trip; opening one offers to import it
into the saved trips), with GPX export and a print view as follow-ons. `localStorage` alone would
keep the itinerary on one browser. The share link opens the desktop layout; a phone-optimised view
is postponed (see Out of scope).

## Screens

- **Planner (default route).** The map is the main surface, with one switching column on the left.
  In discover mode the column holds the filter bar and ranked results. Picking a tour swaps it for
  the trip panel; "← Ergebnisse" swaps back, keeping the result list's scroll position. Filter
  changes only ever touch the results, never the active trip. There is no third column, so the map
  keeps its width on a 1366px screen. Before the first pick the Planner is map + filter bar + (on
  first visit) a short prompt explaining that the markers are start points and their numbers are
  matching tours. The prompt closes on the first click on the map or a marker and, remembered in
  `localStorage`, never returns.
- **`#trips`.** Saved trips: switch the active one, rename, delete with undo (autosave means there
  is no unsaved state, so deletion is the only destructive action).
- **`#admin`.** Unchanged, unlinked from the customer nav.

Routes stay hashes; `main.tsx`'s hash router has no library and this spec does not change that.
Data loading (graph payload, huts, start points, official tours) moves **above the router** into a
provider, because switching Planner ↔ Trips would otherwise reload and reparse everything on mount.
`AppShell.tsx`'s tabs become Planner / Trips, labelled "Planen" / "Meine Touren".

**Copy language:** user-facing text stays German. Names such as "Planner" and "Trips" are code
identifiers; the nav renders German labels.

### Loading and empty states

- **No matches.** The map shows no markers; the results column reads "Keine Touren für diese
  Filter. Mehr Tage oder längere Gehzeit pro Tag zulassen." (fixed hint, not derived from which
  filter rejected most chains).
- **Search running.** Markers keep their previous counts, dimmed; a thin progress line runs under
  the filter bar. New results replace the old ones in one step.
- **Route geometry loading.** Hover or keyboard focus on a result immediately draws dashed straight
  lines between its huts, replaced by the real geometry once fetched. Focus and hover trigger the
  same preview.
- **First load.** The map is visible and pannable at once; the filter bar is disabled and reads
  "Wegenetz wird geladen …" until the payload and worker are ready.

## Trip data model & persistence

```
Trip {
  id, name, createdAt, updatedAt: string
  startDate: string | null             // ISO date of the first night
  partySize: number                    // 1-9 (OHRS bound)
  start: { startId: number, sourceType: SourceType }
  huts: string[]                       // hut GUIDs, in order
  exit:  { startId: number, sourceType: SourceType }
  variant: { sacCeiling: number | null, allowUngraded: boolean }   // to re-derive legs
  nights: { status: 'open' | 'requested' | 'confirmed' }[]         // one per hut
  source?: { kind: 'official', tourId: number }
  notes?: string
}
```

- **No edge ids are stored.** `hutIndex`/`edgeId` are array positions in the payload; a pipeline
  rerun can reorder them. Hut GUIDs are stable (`tourSearch/hutIdentity.ts` resolves them to the
  current payload's indices) and start points are identified by OSM node id / ArcGIS `OBJECTID`.
  Legs are **re-derived from these on every load** by `legsFromTrip`.
- **Failure mode.** A hut GUID or start point that no longer resolves, or a hut pair with no edge in
  the loaded graph, marks that night "changed since saved" in the trip panel. The app never
  substitutes another hut and never guesses.
- `startDate` and `partySize` are trip fields: the dates decide bookability. Today's
  `form.startDate`/`form.numOfPeople` move onto the trip. The filter bar edits a search draft; a
  picked tour copies the draft's values into the new trip, and from then on the trip panel edits
  them.
- Persisted as a list of trips in `localStorage`; one trip is active. Storage access is wrapped in
  try/catch, and the trips list offers a JSON export/import as a backup against cleared browser
  data.
- Official tours: a tour whose huts resolve becomes the same `start/huts/exit` shape with
  `source` set. Its legs are re-derived from the hut graph like any other trip (the tour-edge
  layer is only used to *draw and preview* the official GPX route).

## Trip editor

All edits are pure functions in `tourSearch/`, tested against a synthetic `GraphData`.

- **Swap a hut.** For hut *i*, the candidates are the huts with a hut-to-hut edge (at the trip's
  variant) to hut *i−1* and to hut *i+1*, found via the existing adjacency. They highlight on the
  map with both leg times; picking one replaces hut *i*.
- **Swap an end hut.** One neighbour constrains it; the approach/exit legs come from
  `getApproachLegs`/`getExitLegs`.
- **Extend.** The first and last hut offer a "next hut" handle listing every hut reachable from
  them.
- **Trim.** Removing a hut is allowed only if a direct edge exists between its neighbours;
  otherwise the control is disabled with a reason.
- **Change start or exit point.** These are the end huts' approach candidates, filtered by mode.
  In `car` mode the exit is locked to the start.
- **Constraints.** Revisiting a hut is blocked. Track overlap (which search forbids) is a
  **warning** on manual edits ("Etappe 3 überschneidet sich mit Etappe 1"), not a block.
- New functions: `legsFromTrip(graphData, trip)`, `swapCandidates`, `extendCandidates`,
  `trimAllowed`.

## Search, ranking, clustering

- **Search runs in a Web Worker.** `searchChains` already enumerates every start point in the
  graph; the new part is running it on every filter change. Filter changes are debounced, a new
  query terminates the running one, and the worker fetches its own copy of the payload so
  main-thread editing is never blocked. The `legCountMax > 8` slow warning stays. The plan's first
  task measures the whole-Alps search time and the payload memory before the worker design is
  committed to.
- **Output.** Chains grouped by `startId`, after `dedupeReversePairs` and `suppressSimilar` (which
  stay global), with a per-start count.
- **Ranking** is a new pure `rankFit` module on the main thread, not part of the engine. Filters
  stay hard limits; within them the score combines: distance of the day count from the target,
  distance of per-day walking time from the middle of the range, day-to-day variance, and — with a
  start date — availability, where "unknown" scores neutral.
- **Clustering.** `supercluster` over the start-point markers with a `reduce` that sums match
  counts. A marker shows its match count as its label, and its size scales with that count
  (sub-linearly, e.g. by square root, with a fixed minimum and maximum so single start points stay
  clickable and large clusters don't cover the map). Viewport changes only re-cluster; they never
  re-search.
- **Availability** stays a search filter (`fetchAvailabilityByOffset`) and gains the per-night trip
  badge. The "which start dates work" answer reuses the same per-date cached calls, so shifting by
  ±1 day adds two fetches. Per-hut detail (`fetchHutDetail`) stays one request per hut for the
  active trip only, never a loop over the hut list.

## Visual design language

Grounded in the hiker's own visual world: Alpenverein map paper, trail paint, yellow signposts.

- **Light panels.** Surfaces are a cool map-paper tone with dark ink text, so the UI reads as a
  continuation of the topo map and prints without a separate theme.
- **Signpost yellow is the accent** (Austrian trail-signpost yellow, near RAL 1023), used for
  selection and primary actions. It is used as a fill with dark text on top, never as text or a
  thin line on the light surface (contrast). A selected route on the map is yellow with a dark
  casing.
- **Trail colours keep their trail meaning.** Red, blue and black mean trail difficulty
  (medium / alpine / difficult) wherever difficulty is shown, and are not reused for UI state.

Starting tokens (tuned at implementation):

| Token | Hex | Role |
|---|---|---|
| paper | `#EDEFE9` | panel surfaces |
| ink | `#23272B` | text, dark casing |
| signpost | `#F5B700` | accent fill: selection, primary action |
| trail-red | `#C8102E` | medium difficulty only |
| alpine-blue | `#1F5FA8` | alpine difficulty only |

**Typography: Barlow**, one family in two widths. Barlow Semi Condensed carries signposts, stage
labels and figures; Barlow Regular carries body text. All figures (hours, ascent, dates, bed
counts) use tabular numerals so columns align. Fonts are self-hosted via `@fontsource/barlow` and
`@fontsource/barlow-semi-condensed`, never loaded from Google's servers (GDPR: German case law on
IP leakage).

**The signpost is the one bold element.** A leg renders as a yellow Austrian trail signpost: an
arrow-shaped plate with the destination hut (Semi Condensed) and the walking time right-aligned,
ascent/descent below. It appears in three places: the trip panel (the stacked signposts are the
itinerary timeline, one per stage), the swap-candidate markers on the map (both leg times), and
the hover preview of a tour. Everything else stays quiet: no cards, shadows or gradient washes.

```
 ┌──────────────────────────────┐
 │ Gruttenhütte          3½ Std ▶
 │ ↑ 820 m  ↓ 240 m             │
 └──────────────────────────────┘
```

Walking times are written signpost-style: rounded to the quarter hour, vulgar fractions
(`¾ Std`, `3½ Std`, `5¼ Std`), never `3:30 h`.

`theme.ts` gets this palette and typography. The map tiles must fit: recommended OpenTopoMap
(contour look, hiking focus; attribution required). Its usage policy and the fallback (OSM tiles
under a muted overlay) are checked in the plan's first task, not at the end. In discover mode the
tiles render muted (desaturated, lightened) so the count markers stand out; with a trip open they
render in full colour.

**Map markers carry no hues of their own**; the topo map already supplies colour, and signpost
yellow is the only accent. Hut class is two independent axes: shape = operator (house symbol = AV,
circle = other), fill = service (ink fill = serviced, ink outline = self-catering). A hut on the
selected tour or active trip keeps its shape, filled signpost yellow with an ink outline. Start
points appear as count markers in discover mode only; on a trip, start and exit get small symbols
(train / P / village). `OPERATOR_COLOR` and `PARTNER_COLOR` in `hutClass.ts` are replaced by these
shape/fill definitions; the text badges (`hutClassBadge`) stay.

## What's kept, extended, rebuilt

**Kept:** `tourSearch/` engine internals and loaders, `availability/`, `hutClass.ts`,
`hutIdentity.ts`, the pipeline and its contracts, `#admin`.

**Extended:** `formState.ts` (drops `startDate`/`numOfPeople`, gains target fields for ranking),
`tourSearch/` (new trip-editing functions), `helpers.ts` (`chainToRoute`/`officialTourToRoute`
adapt to trips).

**Rebuilt:** `TourSearchPage.tsx` → Planner composition; `ResultsMap.tsx` → clustered
start-point map plus focused-route/trip rendering; `TourList.tsx`/`OfficialTourList.tsx` → one
ranked list; `theme.ts`; `AppShell.tsx`.

**New:** data provider above the router, search worker, `rankFit`, `Trip` type + persistence
module, trip panel (dates, party, nights, booking status, start-date answer), filter bar, `#trips`
screen, share link (+ GPX/print follow-ons).

**Removed from the previous version of this spec:** the `viewMode` toggle; a region/start-point
`Query` extension (viewport and start markers replace it); the append-or-replace flow for search
results; the "stable ids" pipeline prerequisite (superseded by GUID-based trips re-derived on
load).

## Testing

- Unit: `rankFit`, `legsFromTrip` (including an unresolvable GUID and a missing edge),
  `swapCandidates`/`extendCandidates`/`trimAllowed`, trip persistence (round-trip, storage
  unavailable), aggregation of results by start point.
- Component: trip panel, clustered map, filter bar, following the existing `*.test.tsx` style.
- No new pipeline tests.

## Non-goals

- Accounts/backend, in-app booking, mobile-first layout, `#admin` changes, pipeline changes,
  data-quality UI, rest days and multi-night stays (the model is one night per hut on consecutive
  days).

## Measured findings (2026-09-21)

Whole-graph transit search in Node on the shipped payload (`MEASURE_SEARCH=1 npx vitest run src/tourSearch/measure.smoke.test.ts`).

- Payload load (incl. `hut-edge-ids` + `start-edge-ids`): 401 ms.
- Memory after load: `heapUsed` 48 MB, `arrayBuffers` 189 MB.

| Profile | legCountMax | Time | Chains |
|---|---|---|---|
| default (4–8 h legs) | 3 | 201 ms | 344 |
| default | 4 | 205 ms | 346 |
| default | 5 | 243 ms | 346 |
| default | 6 | 322 ms | 346 |
| default | 7 | 420 ms | 346 |
| permissive (0–8 h legs) | 3 | 172 ms | 377 |
| permissive | 4 | 383 ms | 379 |
| permissive | 5 | 885 ms | 379 |
| permissive | 6 | 1615 ms | 379 |
| permissive | 7 | 2631 ms | 379 |

Decisions:
- **D1** `LEG_COUNT_SLIDER_MAX = 7` (highest value measured; permissive search finishes in 2.6 s, under the 5 s bound).
- **D2** memory ≈ 237 MB, far below 1 GB: no pipeline change needed.
- **D3** worker respawn cost ≈ 0.4 s (< 3 s): terminate-and-respawn on a new query stays as specified.
- **Map tiles**: OpenTopoMap is CC-BY-SA, free for third-party use with visible attribution ("Kartendaten: © OpenStreetMap-Mitwirkende, SRTM | Kartendarstellung: © OpenTopoMap (CC-BY-SA)"); no numeric rate limit, only a request to avoid mass downloads, and no availability guarantee. Interactive viewing is within policy → use OpenTopoMap with attribution; the OSM tile server (interactive viewing only, no prefetching, visible attribution "© OpenStreetMap contributors", best-effort) is the fallback.
