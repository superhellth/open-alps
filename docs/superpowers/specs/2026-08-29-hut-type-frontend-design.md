# Hut-type frontend consumption (AV / sonstige / Selbstversorger / Partnerbetrieb) design

Date: 2026-08-29
Status: draft, for planning (revised 2026-08-29 after review)

## Problem

`docs/superpowers/specs/2026-08-28-hut-classification-design.md` shipped hut classification data
(`hutType`, `serviced` in `huts.geojson`; `partner_betriebe.geojson`; `TYPE_PARTNER` hub type
routed through the pipeline into `start-edges.pmtiles`/`approaches.*`) but explicitly deferred all
frontend consumption. As a result:

- `GraphPage.tsx` and `TourSearchPage.tsx` render every hut identically regardless of who runs it
  or whether it's staffed — a user planning a multi-day tour can't tell AV huts from other clubs'
  huts, or staffed huts from self-service (Biwak/Jugendherberge) ones, without leaving the app.
- Tour search has no way to restrict a route to (for example) only AV huts, even though this is a
  common real planning constraint (AV membership discounts, familiarity, booking channel).
- `partner_betriebe.geojson` (Bergsteigerdörfer partner businesses / ÖAV Vertragshaus lodging) is
  built by the pipeline but not copied to `huts/public/data/` and has no consumer — despite its
  routing edges already existing.

This spec covers making that data visible and useful in the two surfaces that deal with individual
huts: `GraphPage` (raw network debug view) and `TourSearchPage` (the tour planner). It does not
touch `App.jsx` (the public overview map), by explicit decision — see Non-goals.

## Data reality check (verified 2026-08-29)

The pipeline side is further along than the previous draft assumed. Verified against the files
actually shipped in `huts/public/data/` and `data/osm/`:

- `huts/public/data/huts.geojson` already carries `hutType`/`serviced`/`elevation` (846 features,
  Partnerbetriebe already split out). No pipeline run is needed for the hut-category work.
- `huts/public/data/approaches.bin` already carries **198 `TYPE_PARTNER` approach legs** across
  **56 distinct partner start points** (source_type counts: parking 1154 / station 477 /
  partner 198). No pipeline run is needed for the Bergsteigerdorf mode either.
- `data/osm/partner_betriebe.geojson` exists (110 features). It is missing only from `PUBLIC_FILES`
  and therefore from `huts/public/data/` — a **file copy**, not a compute job.
- `huts.geojson`'s `properties.id` is an ArcGIS **GUID string** (`{593D0233-…}`), and
  `hut-edge-payload.json`'s `hut_ids` is the same GUID list. `TourResult.huts` holds **indices**
  into that list. See §0.
- `partner_betriebe.geojson` features have **no top-level `id`**; the id is a plain int in
  `properties.id` (ArcGIS OBJECTID, range 30–1167 among snapped points). Station/parking OSM node
  ids start at 13,925,786, so the two id spaces cannot collide inside `startById`.

## Decisions (confirmed with user)

- Scope: `GraphPage` + `TourSearchPage` only, not `App.jsx`.
- Category filtering in `TourSearchPage` is a **hard filter**: an excluded category's huts are
  removed from tour search entirely (never appear anywhere in a result chain, not just as
  endpoints) — not just visually deprioritized.
- **Two orthogonal filter axes, not three collapsed buckets** (revised): operator
  (`av` / `sonstige`) and servicing (`serviced` / self-service) are independent. Collapsing every
  unserviced hut into one `self_service` bucket would make "AV membership terms apply here"
  inexpressible — an AV-run Selbstversorgerhütte still carries AV terms and the AV key, and is
  exactly what a member filtering for "AV" wants included. The two-axis split costs the same UI and
  preserves both real constraints.
- **Self-service defaults to off** (revised): a Selbstversorgerhütte means no warden, no meals,
  often a section key and first-come-first-served. Silently mixing those into a hut-to-hut tour
  produces trips most users cannot actually book. The checkbox sits right there for anyone who
  wants them.
- Filter UI is multi-select checkboxes, not a single "AV only" toggle or a preset dropdown.
- New `TourMode` for Bergsteigerdorf starts, as a **third mutually exclusive mode** alongside
  car/transit. The mode select answers "where does the tour begin and end", and a Bergsteigerdorf
  start is a genuine third answer to that. It behaves like `transit` (open point-to-point: start
  and end at any, possibly different, partner access point) rather than like `car` (round-trip to
  the same point).
- **Terminology** (revised): the user-facing term is **Bergsteigerdorf** / **Partnerbetrieb**,
  never "Dorfhütte" — the classification spec's own decision is that a Partnerbetrieb is not a hut,
  and `Bergsteigerdorf` is the AV's actual program name.
- Category display appears in both `TourList` (badge next to hut names) and `ResultsMap` (marker
  color), not just one.
- `GraphPage`'s category controls **dim** rather than hard-hide (revised): `HutEdgeTilesLayer`
  renders hut-to-hut edges from `hut-edges.pmtiles` and cannot be filtered client-side, so hiding
  markers would leave edge lines terminating at nothing — actively misleading in a debug view whose
  job is reading the network. `TourSearchPage`'s hard-filter semantics stay hard there, where they
  affect results rather than a network drawing.

## Invariant: every tour contains at least one hut night

Guaranteed by construction and to be kept that way. `searchChains` seeds every state as
`path: [h]` from an approach leg (`search.ts:59-74`), and station/parking/partner points only ever
appear as `startId`/`exitStartId` — never inside `path`, since `adjacency` is built from hut-to-hut
edges only. The shortest possible chain is therefore `Startpunkt → Hütte → Startpunkt`: two legs,
one hut, one night. The Bergsteigerdorf mode inherits this unchanged — a partner-to-partner tour
still has to sleep in the mountains.

This is currently implicit. It gets written down here and covered by a test (§7), because a future
change to `adjacency` or to approach seeding could break it silently.

One inert UI wrinkle exposed by this: `LegCountSlider` has `min={1}` (`LegCountSlider.tsx:33`), and
1 Etappe = 0 Übernachtungen by its own caption — a tour the engine can never return. `nightsMin`
just floors at 0 and the search still yields one-hut chains, so the setting does nothing rather
than misbehaving. Change the slider's `min` to `2`.

## Design

### 0. Fix the hut-index ↔ hut-id join (prerequisite, pre-existing bug)

`TourResult.huts` holds indices into `hutEdges.hutIds` (`search.ts:59`, `path: [h]`), but
`TourSearchPage` builds `hutNameById`/`hutCoordsById` keyed by `huts.geojson`'s `properties.id` —
a GUID string. `hutNameById.get(h)` with a numeric index therefore always misses. Live symptoms
today: expanded tour cards render hut names as raw numbers, and `chainPositions`
(`ResultsMap.tsx:22`) drops every hut, drawing start→end only. The existing tests don't catch it
because they key the maps by index (`ResultsMap.test.tsx:28-29`).

This must be fixed before anything below, because §5/§6 would otherwise inherit the same broken
join and silently render no categories at all.

Fix: key every per-hut lookup by **hut index**, built once from `graphData.hutEdges.hutIds`:

```ts
// in TourSearchPage's load effect, after both huts.geojson and graphData are available
const byGuid = new Map(hutsFc.features.map((f) => [f.properties.id, f]))
const hutsByIndex = graphData.hutEdges.hutIds.map((guid) => byGuid.get(guid) ?? null)
```

`hutNameById`/`hutCoordsById` become index-keyed arrays (or keep the `Map<number, …>` shape with
index keys — the component prop types don't change). Add a regression test that a chain's hut name
and coordinate resolve when the geojson uses GUID ids, which is what production data looks like.

### 1. Copy `partner_betriebe.geojson` to the frontend

Add `"partner_betriebe.geojson"` to `PUBLIC_FILES` in `pipeline/dodo.py:88-105`. The source file
already exists at `data/osm/partner_betriebe.geojson`, so this is a copy, not a compute job — but
it still only lands in `huts/public/data/` when `copy_public_data` next runs, which needs explicit
confirmation per the project's standing rule.

**The frontend must not depend on that having happened.** `TourSearchPage`'s load is a
`Promise.all` whose `.catch` sets `error` and renders `Fehler: …` with no map and no search
(`TourSearchPage.tsx:36-42`) — a missing partner file would kill the entire tour planner for every
user in every mode. Give the partner fetch its own catch:

```ts
fetch(PARTNER_URL).then((r) => r.json()).catch(() => ({ type: 'FeatureCollection', features: [] }))
```

Same tolerance in `GraphPage`. With an empty collection the Bergsteigerdorf mode simply returns no
tours; everything else keeps working.

### 2. Shared hut-classification module

New module `huts/src/hutClass.ts`:

```ts
export type HutOperator = 'av' | 'sonstige'

export interface HutClass {
  operator: HutOperator
  serviced: boolean
}

export const OPERATOR_LABEL: Record<HutOperator, string> = {
  av: 'AV-Hütte',
  sonstige: 'Sonstige Hütte',
}

/** Full user-facing label, e.g. "AV-Hütte (Selbstversorger)". */
export function hutClassLabel(c: HutClass): string

/** Two-to-four character text badge, e.g. "AV", "AV·SV", "SO", "SO·SV" — text, not colour alone. */
export function hutClassBadge(c: HutClass): string

export const OPERATOR_COLOR: Record<HutOperator, string> = { /* ... */ }

export const PARTNER_LABEL = 'Partnerbetrieb (Bergsteigerdorf)'
export const PARTNER_COLOR = '/* ... */'
```

Visual encoding uses **two channels, not one colour ramp**: operator drives colour, servicing
drives fill (solid = bewirtschaftet, hollow/ringed = Selbstversorger). Four hues distinguishable by
hue alone would fail for colour-vision-deficient users, and at `radius={4}` overview markers
(`ResultsMap.tsx:141-152`) it is marginal for everyone. Text badges carry the same information in
`TourList`, following the existing `difficulty-badge` pattern in `GraphPage.tsx`.

Colours are picked to be distinguishable in both light and dark map tile contexts and distinct from
the existing snapped/unsnapped green/gray used elsewhere in `GraphPage`; exact values are an
implementation-time detail, not fixed by this spec.

This module is imported by both `GraphPage.tsx` and the `tourSearchPage/` components so colours,
labels and badges are identical everywhere they appear.

### 3. `GraphPage.tsx`

- Extend the `Hut` type/loading code to read `hutType`/`serviced` from `huts.geojson` properties
  (currently only `id`/`name`/`lat`/`lng` are read, `GraphPage.tsx:325-332`).
- Load `partner_betriebe.geojson` with its own catch (§1) and render its points as a distinct
  marker style using `PARTNER_COLOR`.
- **Both signals survive on one marker**: category drives `fillColor`, the existing snapped/
  unsnapped state (`connectedIds`, `GraphPage.tsx:373-377`) drives stroke `color` + `radius`. The
  snapped/unsnapped split is this page's primary diagnostic — which huts failed to join the graph —
  and must not be traded away for category colour.
- Add a checkbox group (operator av/sonstige, servicing bewirtschaftet/Selbstversorger, partner)
  that **dims** non-matching markers (lower `fillOpacity`, thinner stroke) rather than removing
  them, per the revised decision above.
- Hut tooltips gain the class label so hovering answers "what kind of hut is this".

### 4. `TourSearchPage.tsx` — new mode and filter UI

- `huts/src/tourSearch/types.ts`: add `SOURCE_TYPE_PARTNER = 3` and widen `SourceType`/`TourMode`
  (new mode value `'village'`).
- `TourSearchPage.tsx`: fetch `partner_betriebe.geojson` alongside `stations.geojson`/
  `parking.geojson`, adding its points to `startById` with `sourceType: SOURCE_TYPE_PARTNER`.
  **Do not use `idFromOsmFeatureId` here** — partner features have no top-level `f.id`, so it would
  reduce `Number("")` to `0` and collapse all 110 points onto one key. Read `properties.id`
  directly; the pipeline documents the same distinction in `filter_start_points.py:74-77`.
- Add a third `MenuItem` to the mode `Select`: `Start im Bergsteigerdorf (offene Strecke)`,
  alongside the existing `Auto (Rundtour zum Ausgangspunkt)` / `ÖPNV (offene Strecke)`.
- `search.ts`'s `requiredSourceType(mode)`: return `SOURCE_TYPE_PARTNER` for `'village'`. No
  `exitLeg.startId !== s.startId` round-trip check is added for it (that check is `car`-specific
  today), giving it the same open point-to-point behaviour as `transit`.
- Add checkbox groups (`FormControlLabel`+`Checkbox`, matching the existing `allowUngraded`/
  `allowViaFerrata` pattern) for the two axes. Lives in `FormState` (`formState.ts`):

  ```ts
  allowedOperators: Set<HutOperator>   // default: new Set(['av', 'sonstige'])
  allowServiced: boolean               // default: true
  allowSelfService: boolean            // default: false
  ```

  Label the self-service box with its implication, not just its name:
  `Selbstversorgerhütten (unbewirtschaftet, ggf. Schlüssel nötig)`.
- **Guard the empty selection**: if `allowedOperators` is empty, or neither servicing box is
  checked, disable the submit button with a hint rather than running a search that cannot return
  anything.

### 5. Category filter enforcement in search

- `TourSearchPage.tsx` derives an **index-keyed** allow-set from `hutsByIndex` (§0) and the form
  state: a hut passes iff `allowedOperators.has(operator) && (serviced ? allowServiced :
  allowSelfService)`.
- `buildQuery` carries it as `Query.allowedHutIndices?: Set<number>` (`undefined` = everything
  allowed). Passing indices rather than categories keeps the engine name- and category-agnostic,
  matching how `LegSummary`/`TourResult` already stay label-free.
- Enforcement point: `searchChains`' initial-layer seeding loop (`search.ts:59-74`) and the main
  per-hop DFS loop (`search.ts:100-126`) both skip any hut index not in the set — so an excluded
  hut never enters a chain at any position, not just start/end. This is a filter on which hut
  indices are ever added to `layer`/`nextLayer`, not a post-hoc filter on finished chains (which
  would be correct but wasteful — pruning early keeps the DFS from exploring dead branches).
- **Add a kill counter.** `KillCounters` gets `hutFiltered`, incremented on each skip, and
  `KILL_COUNTER_GUIDANCE` (`helpers.ts:29-45`) gets a matching entry — otherwise a user who
  unchecks "sonstige" and gets nothing sees only the generic "Keine Touren gefunden. Filter
  lockern" with no hint which filter did it. Suggested text:
  `${n} mögliche Etappenziele wurden durch den Hüttenfilter ausgeschlossen — Hüttenarten wieder aktivieren`.
- **Mode-specific empty state.** Only 56 partner points are connected to the trail network (vs. 238
  stations / 703 parking lots), so `'village'` will return zero far more often than the other two
  modes. When the result is empty and the mode is `'village'`, add a line explaining that rather
  than letting the generic message imply the user's other filters are at fault.

### 6. Display — `TourList.tsx` and `ResultsMap.tsx`

- `TourList`: a text badge from `hutClassBadge()` (coloured per `OPERATOR_COLOR`) next to each hut
  name, in the expanded view's waypoint list (`legWaypointLabels` output) and the hut-chain sentence
  (`chain.huts.map(...)`). The collapsed card summary is `startLabel(...) → … → startLabel(...)` and
  carries no per-hut information, so it is unchanged.
- `ResultsMap`: `CircleMarker` styling driven by the hut's class for both the "show all huts"
  overview markers (`ResultsMap.tsx:141-152`) and the selected-chain path markers
  (`ResultsMap.tsx:166-173`); partner-type start/exit points (`startById.get(id).sourceType ===
  SOURCE_TYPE_PARTNER`) get `PARTNER_COLOR` and a distinct radius from stations/parking.
- **The overview layer respects the filter too.** Because the filter is hard, every hut inside a
  result already satisfies it — so the badges only inform when everything is checked. The surface
  where the classification actually earns its place is the unfiltered "show all huts" overview: a
  user who filtered to AV-only must not still see a map full of huts that can no longer appear in
  any result. Excluded huts are dimmed there (matching `GraphPage`'s treatment), not removed, so
  the map still reads as a network.
- A small legend (class → colour/fill/label) near the list or map, built from `OPERATOR_LABEL`/
  `hutClassLabel`/`PARTNER_LABEL` so it can't drift from the marker styling.
- `helpers.ts`'s `SOURCE_TYPE_LABEL` gets a `SOURCE_TYPE_PARTNER: 'Partnerbetrieb'` entry so
  `startLabel()` renders partner access points correctly — e.g. `FeWo Bergmann (Partnerbetrieb)`,
  parallel to how it already handles station/parking.

### 7. Testing

- `hutClass.ts`: unit tests over all `hutType`×`serviced` combinations, asserting that operator and
  servicing stay independent — specifically that an AV Selbstversorgerhütte still classifies as
  operator `av` (the case the collapsed three-bucket model got wrong).
- §0 regression: a chain's hut name and coordinates resolve when `huts.geojson` uses GUID
  `properties.id` and `TourResult.huts` holds indices — i.e. the production data shape, not the
  index-keyed maps the current tests hand in.
- `search.ts` / `search.test.ts`:
  - a hut excluded by the filter never appears in any returned chain, including as a *mid-route*
    hut, not just as a would-be start/end (this is the behaviour that most needs a regression test,
    since it's easy to accidentally only filter endpoints);
  - the hut-night invariant: every returned chain has `huts.length >= 1`, including in `'village'`
    mode and including at `legCountMin = 1`;
  - `hutFiltered` counts up when the filter prunes.
- `TourSearchPage.test.tsx`: the new checkboxes and mode option render and wire into `buildQuery`;
  `partner_betriebe.geojson` is mocked following the existing `parking.geojson`/`stations.geojson`
  pattern (`TourSearchPage.test.tsx:42-48`); partner ids are read from `properties.id`; a **404 on
  `partner_betriebe.geojson` still leaves the page usable** in car/transit mode; submit is disabled
  when the filter selection is empty.
- `TourList`/`ResultsMap` component tests: class badge/marker styling renders per hut and excluded
  huts are dimmed in the overview layer, following existing patterns in those files
  (`ResultsMap.test.tsx`).
- `GraphPage`: the checkbox group dims non-matching markers while leaving them on the map, and the
  snapped/unsnapped stroke signal survives the category colouring.

## Non-goals

- Not touching `App.jsx` (the public overview map) — explicit scope decision, may be a follow-up.
- Not re-running any compute-heavy `pipeline/` task. Nothing here needs one: `huts.geojson` already
  carries `hutType`/`serviced` and `approaches.bin` already carries `TYPE_PARTNER` legs (see "Data
  reality check"). Only `copy_public_data` needs to run, to copy the already-built
  `partner_betriebe.geojson` — and per the standing rule that still needs explicit confirmation.
- Not deciding exact colour/hex values or marker shapes here — implementation-time detail,
  constrained by "distinguishable in both themes, distinct from existing snapped/unsnapped colours,
  never colour-alone".
- Not adding availability/booking-channel information (OHRS) tied to hut class — unrelated, no
  per-hut availability fetching exists anywhere in the app yet.
- Not building a `sonstige Hütte` sub-filter by club/`verein_nr` (e.g. "CAI only") — out of scope.
- Not adding a fourth mode or a transport dimension on top of the Bergsteigerdorf mode. The mode
  select stays one exclusive choice of "where does the tour begin and end".

## Follow-up (separate task, not this one)

- Consuming `hutType`/`serviced`/`partner_betriebe.geojson` in `App.jsx` (the public map), if
  wanted later.
- Revisiting whether class filtering should also gate the OHRS availability feature once that's
  built (currently no per-hut availability fetching exists in the app at all).
- Widening partner-point coverage: only 56 of 110 Partnerbetriebe currently snap into the trail
  network, which is what makes the Bergsteigerdorf mode sparse. If that matters, it's a `pipeline/`
  question (hub-range/snapping), not a frontend one.
