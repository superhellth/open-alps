# Hut-type frontend consumption (AV / sonstige / Selbstversorger / Partnerbetrieb) design

Date: 2026-08-29
Status: draft, for planning

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

## Decisions (confirmed with user)

- Scope: `GraphPage` + `TourSearchPage` only, not `App.jsx`.
- Category filtering in `TourSearchPage` is a **hard filter**: an excluded category's huts are
  removed from tour search entirely (never appear anywhere in a result chain, not just as
  endpoints) — not just visually deprioritized.
- Four visually distinguished categories: `av`, `sonstige`, `self_service` (self-service collapses
  both AV- and non-AV-run Selbstversorger huts into one visual bucket, since the operational
  distinction that matters to a hiker is staffed-vs-not), and `partner` (Partnerbetrieb access
  points, a different entity type from huts, not a fourth hut category).
- Filter UI is multi-select checkboxes (av / sonstige / self-service), not a single "AV only"
  toggle or a preset dropdown — lets a user include any combination.
- New `TourMode` for Partnerbetrieb access, behaving like `transit` (open point-to-point: start and
  end at any, possibly different, partner access point) rather than like `car` (round-trip to the
  same point).
- Category display appears in both `TourList` (badge next to hut names) and `ResultsMap` (marker
  color), not just one.
- `GraphPage`'s category checkboxes also hard-hide non-matching huts/markers, matching
  `TourSearchPage`'s semantics, rather than being visual-only there.

## Design

### 1. Copy `partner_betriebe.geojson` to the frontend

Add `"partner_betriebe.geojson"` to `PUBLIC_FILES` in `pipeline/dodo.py` (currently lists
`huts.geojson`, `stations.geojson`, `parking.geojson`, etc. but not this file — see
`pipeline/dodo.py:88-105`). This is a one-line addition to `copy_public_data`'s file list, not a
pipeline run; the actual file only appears in `huts/public/data/` after `doit`/`copy_public_data`
next executes, which needs separate explicit confirmation per the project's standing rule.

### 2. Shared hut-category classifier

New module `huts/src/hutCategory.ts`:

```ts
export type HutCategory = 'av' | 'sonstige' | 'self_service'

export function hutCategory(hutType: 'av' | 'sonstige', serviced: boolean): HutCategory {
  if (!serviced) return 'self_service'
  return hutType
}

export const HUT_CATEGORY_LABEL: Record<HutCategory, string> = {
  av: 'AV-Hütte',
  sonstige: 'Sonstige Hütte',
  self_service: 'Selbstversorgerhütte',
}

export const HUT_CATEGORY_COLOR: Record<HutCategory, string> = { /* ... */ }

export const PARTNER_LABEL = 'Dorfhütte / Partnerbetrieb'
export const PARTNER_COLOR = '/* ... */'
```

Colors are picked to be distinguishable in both light and dark map tile contexts and distinct from
the existing snapped/unsnapped green/gray used elsewhere in `GraphPage`; exact values are an
implementation-time detail, not fixed by this spec.

This module is imported by both `GraphPage.tsx` and the `tourSearchPage/` components so category
colors/labels are identical everywhere they appear.

### 3. `GraphPage.tsx`

- Extend the `Hut` type/loading code to read `hutType`/`serviced` from `huts.geojson` properties
  (currently only `id`/`name`/`lat`/`lng` are read) and compute `category` via `hutCategory()`.
- Optionally load `partner_betriebe.geojson` (new fetch, tolerating 404/empty until step 1 has run)
  and render its points as a distinct marker style using `PARTNER_COLOR`.
- Color `CircleMarker`s by category instead of (or in addition to — TBD at implementation time
  which existing snapped/unsnapped signal takes precedence) the current green/gray snapped state.
- Add a checkbox-group control (av / sonstige / self-service / partner) that hides non-matching
  markers entirely when unchecked — mirroring `TourSearchPage`'s hard-filter semantics.

### 4. `TourSearchPage.tsx` — new mode and filter UI

- `huts/src/tourSearch/types.ts`: add `SOURCE_TYPE_PARTNER = 3` and widen `SourceType`/`TourMode`
  (a new mode value, e.g. `'village'`).
- `TourSearchPage.tsx`: fetch `partner_betriebe.geojson` alongside `stations.geojson`/
  `parking.geojson`, adding its points to `startById` with `sourceType: SOURCE_TYPE_PARTNER`
  (same shape stations/parking already use, per `StartPoint`/`idFromOsmFeatureId`).
- Add a third `MenuItem` to the mode `Select` (e.g. "Dorfhütte-Zustieg").
- `search.ts`'s `requiredSourceType(mode)`: return `SOURCE_TYPE_PARTNER` for the new mode. No
  `exitLeg.startId !== s.startId` round-trip check is added for it (that check is `car`-specific
  today), giving it the same open point-to-point behavior as `transit`.
- Add a checkbox group (`FormControlLabel`+`Checkbox`, matching the existing `allowUngraded`/
  `allowViaFerrata` pattern) for the three hut categories, defaulting to all checked. Lives in
  `FormState` (`formState.ts`) as e.g. `allowedCategories: Set<HutCategory>`.

### 5. Category filter enforcement in search

- `TourSearchPage.tsx` builds `hutCategoryById: Map<number, HutCategory>` from the already-fetched
  `huts.geojson` features (alongside the existing `hutNameById`/`hutCoordsById` construction).
- `buildQuery`/`Query` (or a new parameter passed alongside `graphData` into `findTours`/
  `searchChains`) carries the allowed-category set through to `search.ts`.
- Enforcement point: `searchChains`' initial-layer seeding loop (`search.ts:59-74`, iterating every
  `h` from approach legs) and the main per-hop DFS loop (`search.ts:100-126`, iterating `adjacency`
  edges) both skip any hut index whose category isn't in the allowed set — so an excluded category
  never enters a chain at any position, not just start/end. This is a filter on which hut indices
  are ever added to `layer`/`nextLayer`, not a post-hoc filter on finished chains (which would be
  correct but wasteful — pruning early keeps the DFS from exploring dead branches).

### 6. Display — `TourList.tsx` and `ResultsMap.tsx`

- `TourList`: a small colored dot/badge (using `HUT_CATEGORY_COLOR`) next to each hut name, in the
  collapsed card's `startLabel(...) → … → startLabel(...)` summary is not per-hut so this applies
  to the expanded view's waypoint list (`legWaypointLabels` output) and the hut-chain sentence
  (`chain.huts.map(...)`).
- `ResultsMap`: `CircleMarker` `pathOptions.fillColor` driven by `hutCategoryById.get(id)` for both
  the "show all huts" overview markers (`ResultsMap.tsx:141-152`) and the selected-chain path
  markers (`ResultsMap.tsx:166-173`); partner-type start/exit points (when `startById.get(id)
  .sourceType === SOURCE_TYPE_PARTNER`) get `PARTNER_COLOR`/a distinct radius or shape from
  stations/parking.
- A small legend (category → color/label) near the list or map, using `HUT_CATEGORY_LABEL`/
  `PARTNER_LABEL` so it can't drift from the marker colors.
- `helpers.ts`'s `SOURCE_TYPE_LABEL` gets a `SOURCE_TYPE_PARTNER` entry so `startLabel()` renders
  partner access points correctly (parallel to how it already handles station/parking).

### 7. Testing

- `hutCategory()`: unit tests covering all `hutType`×`serviced` combinations, confirming
  `serviced: false` always yields `self_service` regardless of `hutType`.
- `search.ts` / `search.test.ts`: a hut excluded by the category filter never appears in any
  returned chain — including as a *mid-route* hut, not just as a would-be start/end (this is the
  behavior that most needs a regression test, since it's easy to accidentally only filter
  endpoints).
- `TourSearchPage.test.tsx`: new checkboxes and the new mode option render and wire into
  `buildQuery`/the mocked `fetch` for `partner_betriebe.geojson`, following the existing
  `parking.geojson`/`stations.geojson` mock pattern (`TourSearchPage.test.tsx:42-48`).
- `TourList`/`ResultsMap` component tests: category badge/marker color renders per hut, following
  existing test patterns in those files (`ResultsMap.test.tsx`).
- `GraphPage` (if it has existing tests): checkbox filter hides/shows markers correctly.

## Non-goals

- Not touching `App.jsx` (the public overview map) — explicit scope decision, may be a follow-up.
- Not re-running any `pipeline/` task to actually produce a fresh `partner_betriebe.geojson` copy
  or refreshed `start-edges.pmtiles`/`approaches.*` with live `TYPE_PARTNER` data — per the
  project's standing rule, needs separate explicit confirmation after this code lands.
- Not deciding exact color/hex values or icon shapes here — implementation-time detail, constrained
  only by "distinguishable in both themes, distinct from existing snapped/unsnapped colors."
- Not adding availability/booking-channel information (OHRS) tied to hut category — unrelated,
  no per-hut availability fetching exists anywhere in the app yet (see prior investigation in this
  conversation).
- Not building a `sonstige Hütte` sub-filter by club/`verein_nr` (e.g. "CAI only") — out of scope,
  the three-category split is what was decided.

## Follow-up (separate task, not this one)

- Consuming `hutType`/`serviced`/`partner_betriebe.geojson` in `App.jsx` (the public map), if
  wanted later.
- Revisiting whether category filtering should also gate the OHRS availability feature once that's
  built (currently no per-hut availability fetching exists in the app at all).
