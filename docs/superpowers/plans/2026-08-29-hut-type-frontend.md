# Hut-type frontend consumption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Do NOT use
> superpowers:subagent-driven-development or any worktree/subagent-spinning approach in this
> repo** — root `CLAUDE.md`'s standing rule overrides the skill's own default recommendation.
> Execute every task directly, in-session, on the current checkout.

**Goal:** Make hut operator (`av`/`sonstige`), servicing (`serviced`/self-service), and
Partnerbetrieb/Bergsteigerdorf classification visible and filterable in `GraphPage.tsx` and
`TourSearchPage.tsx`, and fix the pre-existing hut-index↔hut-id join bug that would otherwise
silently swallow this data.

**Architecture:** A shared `huts/src/hutClass.ts` module owns labels/colours/badges so both pages
render identically. `GraphPage` dims non-matching markers (debug view, never hides). `TourSearchPage`
hard-filters at the search-engine layer (`allowedHutIndices` threaded through `Query` and enforced
inside `searchChains`'s DFS, not as a post-hoc filter) plus dims its own unfiltered overview layer.
A new `'village'` `TourMode` treats Bergsteigerdorf/Partnerbetrieb start points as a third
open-point-to-point mode alongside `transit`.

**Tech Stack:** React + TypeScript, MUI, react-leaflet, Vitest + Testing Library (jsdom via
per-file `// @vitest-environment jsdom` docblock), no new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-29-hut-type-frontend-design.md`

## Global Constraints

- Scope is `GraphPage.tsx` + `TourSearchPage.tsx` only — never touch `App.jsx` (explicit
  non-goal).
- Category filtering in `TourSearchPage` is a **hard filter**: excluded huts never appear in any
  returned chain, at any position (start/mid/end) — not a display-only dim.
- `GraphPage`'s category controls **dim**, never hide, and must not erase the existing
  snapped/unsnapped stroke signal (`connectedIds`) — that stays the page's primary diagnostic.
- Visual encoding uses two independent channels: operator → colour, servicing → fill
  (solid = bewirtschaftet, hollow/ringed = Selbstversorger) — never colour-only, and always
  paired with a text badge (not colour alone) per accessibility requirement.
- Terminology: **Bergsteigerdorf** / **Partnerbetrieb** in all user-facing copy — never
  "Dorfhütte".
- Every tour still contains at least one hut night — this invariant must not regress in any mode,
  including the new `'village'` mode, and gets an explicit regression test.
- No `pipeline/` compute task may be run without asking the user first and getting explicit
  confirmation — this plan only needs `copy_public_data` to run once (Task 1), which is a file
  copy, not a compute job, but the confirmation rule still applies.
- The two partner-fetch call sites (`GraphPage`, `TourSearchPage`) must each have their own
  `.catch` returning an empty `FeatureCollection` — a missing/404 `partner_betriebe.geojson` must
  never break car/transit mode or the graph view.
- Do not use `idFromOsmFeatureId` for partner points — they have no top-level `f.id`; read
  `properties.id` directly (plain ArcGIS int, not an OSM-prefixed string).

---

## File Structure

- `huts/src/hutClass.ts` (new) — `HutOperator`, `HutClass`, `OPERATOR_LABEL`, `hutClassLabel`,
  `hutClassBadge`, `OPERATOR_COLOR`, `PARTNER_LABEL`, `PARTNER_COLOR`. Pure, no React/DOM.
- `huts/src/hutClass.test.ts` (new) — unit tests over all `hutType`×`serviced` combinations.
- `pipeline/dodo.py` — add `"partner_betriebe.geojson"` to `PUBLIC_FILES`.
- `huts/src/tourSearch/types.ts` — add `SOURCE_TYPE_PARTNER`, widen `SourceType`/`TourMode`, add
  `Query.allowedHutIndices`, add `KillCounters.hutFiltered`.
- `huts/src/tourSearch/search.ts` — enforce `allowedHutIndices` in both the seeding loop and the
  main DFS loop; `requiredSourceType` gains `'village'` → `SOURCE_TYPE_PARTNER`.
- `huts/src/tourSearch/legFilters.ts` — `createKillCounters` gains `hutFiltered: 0`.
- `huts/src/tourSearch/search.test.ts` — filter enforcement + hut-night invariant tests.
- `huts/src/tourSearchPage/types.ts` — `StartPoint.sourceType` stays `number` (already widens for
  free); no change needed here beyond what's inherited from `types.ts`.
- `huts/src/tourSearchPage/formState.ts` — `FormState.allowedOperators`/`allowServiced`/
  `allowSelfService`; `buildQuery` derives `allowedHutIndices`.
- `huts/src/tourSearchPage/helpers.ts` — `SOURCE_TYPE_LABEL[SOURCE_TYPE_PARTNER]`,
  `KILL_COUNTER_GUIDANCE.hutFiltered`, village-mode empty-state text.
- `huts/src/tourSearchPage/TourSearchPage.tsx` — hut-index join fix (§0), partner fetch +
  `startById` wiring, mode `MenuItem`, filter checkboxes, submit-disable guard, index-keyed
  `hutsByIndex`/`hutClassByIndex` derivation.
- `huts/src/tourSearchPage/TourList.tsx` — class badge per hut in expanded view.
- `huts/src/tourSearchPage/ResultsMap.tsx` — class-driven marker styling, partner start/exit
  points, dimmed excluded-hut overview layer, legend.
- `huts/src/GraphPage.tsx` — read `hutType`/`serviced`, load partner points, checkbox group,
  dimming, tooltip class label.
- `huts/src/GraphPage.test.tsx` (new) — checkbox dimming + snapped/unsnapped stroke survival.
- `huts/src/tourSearchPage/TourSearchPage.test.tsx` — new checkboxes/mode/guard/partner-404 tests.
- `huts/src/tourSearchPage/ResultsMap.test.tsx` — class styling + dimmed overview tests.
- `huts/src/tourSearchPage/LegCountSlider.tsx` — `min={1}` → `min={2}`.

---

## Task 1: Copy `partner_betriebe.geojson` into the pipeline's public output list

**Files:**
- Modify: `pipeline/dodo.py:88-105` (`PUBLIC_FILES` list)

**Interfaces:**
- Produces: `huts/public/data/partner_betriebe.geojson` once `copy_public_data` runs — every later
  task that fetches this URL depends on the file existing there.

- [ ] **Step 1: Add the entry**

In `pipeline/dodo.py`, inside the `PUBLIC_FILES` list (currently lines 88–105), add
`"partner_betriebe.geojson"` as a new entry (alphabetical position doesn't matter — the list
isn't sorted, e.g. append it after `"hut-edge-payload.json"`):

```python
PUBLIC_FILES = [
    "huts.geojson",
    "hut-edges.pmtiles",
    "hut-edge-stats.json",
    "hut-edge-geometry.bin",
    "hut-edge-geometry.json",
    "start-edges.pmtiles",
    "start-edge-geometry.bin",
    "start-edge-geometry.json",
    "trails.pmtiles",
    "stations.geojson",
    "parking.geojson",
    "unsnapped_huts.json",
    "approaches.bin",
    "approaches.json",
    "hut-edge-payload.bin",
    "hut-edge-payload.json",
    "partner_betriebe.geojson",
]
```

- [ ] **Step 2: Ask the user to confirm running `copy_public_data`**

This is a file copy (source `data/osm/partner_betriebe.geojson` already exists per the spec's
"Data reality check"), not a compute job, but the project's standing rule still requires explicit
confirmation before any `pipeline/` task runs. Ask the user, then run (only after they confirm):

```bash
cd pipeline && doit copy_public_data
```

- [ ] **Step 3: Verify the file landed**

```bash
ls -la huts/public/data/partner_betriebe.geojson
```

Expected: file exists, non-empty (110 features per the spec).

- [ ] **Step 4: Commit**

```bash
git add pipeline/dodo.py huts/public/data/partner_betriebe.geojson
git commit -m "feat(pipeline): copy partner_betriebe.geojson to frontend public data"
```

---

## Task 2: Shared hut-classification module

**Files:**
- Create: `huts/src/hutClass.ts`
- Test: `huts/src/hutClass.test.ts`

**Interfaces:**
- Consumes: nothing (pure module).
- Produces (used by Tasks 4, 6, 7, 8, 9):
  - `type HutOperator = 'av' | 'sonstige'`
  - `interface HutClass { operator: HutOperator; serviced: boolean }`
  - `OPERATOR_LABEL: Record<HutOperator, string>`
  - `hutClassLabel(c: HutClass): string`
  - `hutClassBadge(c: HutClass): string`
  - `OPERATOR_COLOR: Record<HutOperator, string>`
  - `PARTNER_LABEL: string`
  - `PARTNER_COLOR: string`

- [ ] **Step 1: Write the failing test**

Create `huts/src/hutClass.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { hutClassLabel, hutClassBadge, OPERATOR_LABEL, OPERATOR_COLOR, PARTNER_LABEL, PARTNER_COLOR } from './hutClass.js'

describe('hutClassLabel', () => {
  it('labels a serviced AV hut without a Selbstversorger suffix', () => {
    expect(hutClassLabel({ operator: 'av', serviced: true })).toBe('AV-Hütte')
  })
  it('labels an AV Selbstversorgerhütte with both facts, not collapsed into a third bucket', () => {
    expect(hutClassLabel({ operator: 'av', serviced: false })).toBe('AV-Hütte (Selbstversorger)')
  })
  it('labels a serviced non-AV hut', () => {
    expect(hutClassLabel({ operator: 'sonstige', serviced: true })).toBe('Sonstige Hütte')
  })
  it('labels a non-AV Selbstversorgerhütte', () => {
    expect(hutClassLabel({ operator: 'sonstige', serviced: false })).toBe('Sonstige Hütte (Selbstversorger)')
  })
})

describe('hutClassBadge', () => {
  it('badges operator and servicing independently for all four combinations', () => {
    expect(hutClassBadge({ operator: 'av', serviced: true })).toBe('AV')
    expect(hutClassBadge({ operator: 'av', serviced: false })).toBe('AV·SV')
    expect(hutClassBadge({ operator: 'sonstige', serviced: true })).toBe('SO')
    expect(hutClassBadge({ operator: 'sonstige', serviced: false })).toBe('SO·SV')
  })
})

describe('lookups stay label-complete', () => {
  it('OPERATOR_LABEL covers both operators', () => {
    expect(OPERATOR_LABEL.av).toBe('AV-Hütte')
    expect(OPERATOR_LABEL.sonstige).toBe('Sonstige Hütte')
  })
  it('OPERATOR_COLOR gives a distinct, non-empty colour per operator', () => {
    expect(OPERATOR_COLOR.av).toMatch(/^#/)
    expect(OPERATOR_COLOR.sonstige).toMatch(/^#/)
    expect(OPERATOR_COLOR.av).not.toBe(OPERATOR_COLOR.sonstige)
  })
  it('PARTNER_LABEL uses the AV program name, never "Dorfhütte"', () => {
    expect(PARTNER_LABEL).toBe('Partnerbetrieb (Bergsteigerdorf)')
    expect(PARTNER_LABEL).not.toMatch(/Dorfhütte/)
  })
  it('PARTNER_COLOR is set and distinct from both operator colours', () => {
    expect(PARTNER_COLOR).toMatch(/^#/)
    expect(PARTNER_COLOR).not.toBe(OPERATOR_COLOR.av)
    expect(PARTNER_COLOR).not.toBe(OPERATOR_COLOR.sonstige)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd huts && npx vitest run src/hutClass.test.ts`
Expected: FAIL — `Cannot find module './hutClass.js'` (file doesn't exist yet).

- [ ] **Step 3: Write the implementation**

Create `huts/src/hutClass.ts`:

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

const OPERATOR_BADGE: Record<HutOperator, string> = {
  av: 'AV',
  sonstige: 'SO',
}

// Colours distinguishable in both light and dark map tile contexts, distinct from GraphPage's
// existing snapped/unsnapped green (#1b5e20/#43a047) and gray (#616161/#bdbdbd).
export const OPERATOR_COLOR: Record<HutOperator, string> = {
  av: '#1565c0',
  sonstige: '#6a1b9a',
}

export const PARTNER_LABEL = 'Partnerbetrieb (Bergsteigerdorf)'
export const PARTNER_COLOR = '#ef6c00'

/** Full user-facing label, e.g. "AV-Hütte (Selbstversorger)". */
export function hutClassLabel(c: HutClass): string {
  return c.serviced ? OPERATOR_LABEL[c.operator] : `${OPERATOR_LABEL[c.operator]} (Selbstversorger)`
}

/** Two-to-four character text badge, e.g. "AV", "AV·SV", "SO", "SO·SV" — text, not colour alone. */
export function hutClassBadge(c: HutClass): string {
  return c.serviced ? OPERATOR_BADGE[c.operator] : `${OPERATOR_BADGE[c.operator]}·SV`
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd huts && npx vitest run src/hutClass.test.ts`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add huts/src/hutClass.ts huts/src/hutClass.test.ts
git commit -m "feat(huts): add shared hut-classification labels/colours module"
```

---

## Task 3: Fix the hut-index ↔ hut-id join in `TourSearchPage` (prerequisite bug fix)

This must land before Tasks 6–9, which would otherwise silently render no categories at all
because they'd inherit the same broken join.

**Files:**
- Modify: `huts/src/tourSearchPage/TourSearchPage.tsx:35-79` (load effect)
- Test: `huts/src/tourSearchPage/TourSearchPage.test.tsx`

**Interfaces:**
- Consumes: `graphData.hutEdges.hutIds: string[]` (`types.ts:141`, GUID order — index `h` in a
  `TourResult.huts` array refers to `hutIds[h]`).
- Produces: `hutNameById`/`hutCoordsById` become **index-keyed** (`Map<number, string>` /
  `Map<number, {lat,lng}>` where the key is a hut's position in `hutIds`, not its GUID). Prop
  types on `TourList`/`ResultsMap` (`Map<number, ...>`) are unchanged — only what the keys mean
  changes. Task 6/9 build on this by also deriving `hutClassByIndex` the same way.

- [ ] **Step 1: Write the failing regression test**

Add to `huts/src/tourSearchPage/TourSearchPage.test.tsx`, inside the existing `describe`, using
the same fixture pattern as the existing test but with a GUID `properties.id` (production shape)
and a `graphDataFixture` whose `hutIds` holds that same GUID:

```ts
it('resolves hut name/coordinates when huts.geojson uses GUID ids and TourResult.huts holds indices', async () => {
  vi.spyOn(tourSearchIndex, 'loadTourSearchData').mockResolvedValue({
    hutEdges: { hutIds: ['{GUID-A}'], variantNames: { 0: 'FAST_ANY' }, records: [] },
    approaches: { records: [], reverseIndex: { hut_to_starts: {}, start_to_huts: {} } },
  })
  vi.spyOn(tourSearchIndex, 'findTours').mockReturnValue({
    chains: [{
      huts: [0], startId: 100, exitStartId: 100,
      totalDurationH: 5, totalAscentM: 500, totalDescentM: 500, totalDistanceM: 8000,
      legs: [
        { durationH: 2.5, ascentM: 250, descentM: 250, distanceM: 4000, edgeId: 0, reversed: false },
        { durationH: 2.5, ascentM: 250, descentM: 250, distanceM: 4000, edgeId: 1, reversed: true },
      ],
    }],
    killCounters: { maxLegTime: 0, minLegTime: 0, legAscentCap: 0, maxEleM: 0, viaFerrata: 0, revisit: 0, hutFiltered: 0 },
  })
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      if (url.includes('huts.geojson')) {
        return fetchJsonMock({
          type: 'FeatureCollection',
          features: [{ properties: { id: '{GUID-A}', name: 'Guid Hut', hutType: 'av', serviced: true }, geometry: { type: 'Point', coordinates: [11.0, 47.0] } }],
        })
      }
      if (url.includes('parking.geojson')) {
        return fetchJsonMock({
          type: 'FeatureCollection',
          features: [{ id: 'n100', properties: { name: 'Parkplatz Test' }, geometry: { type: 'Point', coordinates: [11.1, 47.1] } }],
        })
      }
      if (url.includes('stations.geojson')) return fetchJsonMock({ type: 'FeatureCollection', features: [] })
      if (url.includes('partner_betriebe.geojson')) return fetchJsonMock({ type: 'FeatureCollection', features: [] })
      throw new Error(`unexpected fetch ${url}`)
    }),
  )

  render(<TourSearchPage />)
  await waitFor(() => expect(screen.getByText('Daten geladen')).toBeInTheDocument())
  await userEvent.click(screen.getByRole('button', { name: 'Touren suchen' }))
  await waitFor(() => expect(screen.getByText(/1 Tour gefunden/)).toBeInTheDocument())

  await userEvent.click(screen.getByText(/Parkplatz Test/))
  // Before the fix, hutNameById.get(0) misses (map is keyed by GUID) and the raw index "0"
  // renders instead of "Guid Hut".
  await waitFor(() => expect(screen.getByText(/Guid Hut/)).toBeInTheDocument())
})
```

Note: this test's fixture already includes `hutFiltered: 0` in `killCounters` and `partner_betriebe.geojson`
in the fetch mock — both land for real in Tasks 4/5/8, but the mock must satisfy the types this
task's `TourSearchPage.tsx` changes will require once those tasks add the partner fetch. If Task 4/5
haven't landed yet when this step runs, drop the `hutFiltered` field and the `partner_betriebe.geojson`
branch from this specific test — add them back once those tasks exist. (Tasks in this plan are
meant to run in order, so by the time this step executes, do include them.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd huts && npx vitest run src/tourSearchPage/TourSearchPage.test.tsx -t "GUID ids"`
Expected: FAIL — `Guid Hut` not found (renders `0` instead), because `hutNameById` is currently
keyed by GUID string while `chain.huts` holds numeric indices.

- [ ] **Step 3: Fix the join**

In `huts/src/tourSearchPage/TourSearchPage.tsx`, replace the `.then` body of the load effect
(lines 42–77) so `hutNameById`/`hutCoordsById` are built index-first from `hutEdges.hutIds`:

```ts
.then(([tourSearchData, hutsFc, parkingFc, stationsFc]) => {
  setGraphData(tourSearchData)

  const hutFeatureByGuid = new Map(
    hutsFc.features.map((f) => [(f.properties as { id: string }).id, f]),
  )
  const hutsByIndex = tourSearchData.hutEdges.hutIds.map((guid) => hutFeatureByGuid.get(guid) ?? null)

  setHutNameById(
    new Map(
      hutsByIndex
        .map((f, i) => [i, f ? (f.properties as { name: string }).name : String(i)] as const)
        .filter((_, i) => hutsByIndex[i] != null),
    ),
  )
  setHutCoordsById(
    new Map(
      hutsByIndex
        .map((f, i) => {
          if (!f) return null
          const [lng, lat] = (f.geometry as GeoJSON.Point).coordinates
          return [i, { lat, lng }] as const
        })
        .filter((entry): entry is readonly [number, { lat: number; lng: number }] => entry != null),
    ),
  )

  const starts = new Map<number, StartPoint>()
  for (const f of stationsFc.features) {
    const id = idFromOsmFeatureId(f.id as string | number)
    const [lng, lat] = (f.geometry as GeoJSON.Point).coordinates
    if (id != null) {
      starts.set(id, { name: (f.properties as { name?: string })?.name ?? null, sourceType: SOURCE_TYPE_STATION, lat, lng })
    }
  }
  for (const f of parkingFc.features) {
    const id = idFromOsmFeatureId(f.id as string | number)
    const [lng, lat] = (f.geometry as GeoJSON.Point).coordinates
    if (id != null) {
      starts.set(id, { name: (f.properties as { name?: string })?.name ?? null, sourceType: SOURCE_TYPE_PARKING, lat, lng })
    }
  }
  setStartById(starts)
})
```

(This is intentionally minimal for this task — it does not yet load partner points or
`hutClassByIndex`; those are added in Tasks 4 and 6 on top of this same effect.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd huts && npx vitest run src/tourSearchPage/TourSearchPage.test.tsx`
Expected: PASS, including the pre-existing test (uses index `0` matching a single-hut fixture, so
it passes under both the old and new keying — confirms no regression).

- [ ] **Step 5: Commit**

```bash
git add huts/src/tourSearchPage/TourSearchPage.tsx huts/src/tourSearchPage/TourSearchPage.test.tsx
git commit -m "fix(huts): key hutNameById/hutCoordsById by hut index, not GUID"
```

---

## Task 4: `SOURCE_TYPE_PARTNER`, widened `TourMode`, `allowedHutIndices`, `hutFiltered` — types + engine

**Files:**
- Modify: `huts/src/tourSearch/types.ts`
- Modify: `huts/src/tourSearch/legFilters.ts:11-13` (`createKillCounters`)
- Modify: `huts/src/tourSearch/search.ts`
- Test: `huts/src/tourSearch/search.test.ts`

**Interfaces:**
- Consumes: nothing new beyond existing `types.ts` shapes.
- Produces (used by Task 5 formState, Task 8 TourSearchPage):
  - `SOURCE_TYPE_PARTNER = 3`
  - `SourceType = typeof SOURCE_TYPE_STATION | typeof SOURCE_TYPE_PARKING | typeof SOURCE_TYPE_PARTNER`
  - `TourMode = 'car' | 'transit' | 'village'`
  - `Query.allowedHutIndices?: Set<number>` (`undefined` = everything allowed)
  - `KillCounters.hutFiltered: number`

- [ ] **Step 1: Write the failing tests**

Add to `huts/src/tourSearch/search.test.ts` (new `describe` block, using the existing `graphData`/
`generousConstraints` fixtures already in the file):

```ts
describe('searchChains hut filtering', () => {
  it('excludes a hut from every position in a chain, including mid-route, when its index is not allowed', () => {
    const { chains } = searchChains(
      { mode: 'transit', legCountMin: 2, legCountMax: 4, ...generousConstraints, allowedHutIndices: new Set([0, 2]) },
      graphData,
    )
    for (const chain of chains) {
      expect(chain.huts).not.toContain(1)
    }
  })

  it('increments hutFiltered when the allow-set prunes a hut', () => {
    const { killCounters } = searchChains(
      { mode: 'transit', legCountMin: 2, legCountMax: 4, ...generousConstraints, allowedHutIndices: new Set([0, 2]) },
      graphData,
    )
    expect(killCounters.hutFiltered).toBeGreaterThan(0)
  })

  it('an undefined allowedHutIndices allows every hut, unchanged from before this feature', () => {
    const { chains } = searchChains(
      { mode: 'transit', legCountMin: 3, legCountMax: 4, ...generousConstraints },
      graphData,
    )
    expect(chains.some((c) => c.huts.length === 3)).toBe(true)
  })

  it('every returned chain has at least one hut night (huts.length >= 1), including at legCountMin = 1', () => {
    const { chains } = searchChains(
      { mode: 'transit', legCountMin: 1, legCountMax: 4, ...generousConstraints },
      graphData,
    )
    for (const chain of chains) {
      expect(chain.huts.length).toBeGreaterThanOrEqual(1)
    }
  })
})

describe('searchChains village mode', () => {
  const villageGraphData: GraphData = {
    ...graphData,
    approaches: {
      records: [
        { hutIndex: 0, startId: 300, sourceType: 3, accessUnknown: false, distanceM: 1500, ascentM: 80, descentM: 40, access: null, edgeId: 9100 },
      ],
      reverseIndex: {
        hut_to_starts: {
          2: [{ hut_id: 2, start_id: 400, source_type: 3, variant: 0, distance_m: 1500, ascent_m: 40, descent_m: 80, edge_id: 9101 }],
        },
        start_to_huts: {},
      },
    },
  }

  it('gates approach/exit legs to SOURCE_TYPE_PARTNER, like transit gates to stations', () => {
    const { chains } = searchChains(
      { mode: 'village', legCountMin: 3, legCountMax: 4, ...generousConstraints },
      villageGraphData,
    )
    const full = chains.find((c) => c.huts.length === 3)
    expect(full).toBeDefined()
    expect(full!.startId).toBe(300)
    expect(full!.exitStartId).toBe(400)
  })

  it('behaves like transit (open point-to-point), not like car (no same-start round-trip check)', () => {
    const { chains } = searchChains(
      { mode: 'village', legCountMin: 3, legCountMax: 4, ...generousConstraints },
      villageGraphData,
    )
    expect(chains.some((c) => c.startId !== c.exitStartId)).toBe(true)
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd huts && npx vitest run src/tourSearch/search.test.ts -t "hut filtering|village mode"`
Expected: FAIL — TypeScript errors first (`allowedHutIndices` / `mode: 'village'` / `sourceType: 3`
not assignable), then, once types are relaxed enough to compile, behavioral failures because the
engine doesn't honor `allowedHutIndices` or gate `'village'` yet.

- [ ] **Step 3: Add the type changes**

In `huts/src/tourSearch/types.ts`:

```ts
export const SOURCE_TYPE_STATION = 1
export const SOURCE_TYPE_PARKING = 2
export const SOURCE_TYPE_PARTNER = 3

export type SourceType = typeof SOURCE_TYPE_STATION | typeof SOURCE_TYPE_PARKING | typeof SOURCE_TYPE_PARTNER
```

```ts
export type TourMode = 'car' | 'transit' | 'village'

export interface Query {
  mode: TourMode
  legCountMin: number
  legCountMax: number
  sacCeiling?: number | null
  allowUngraded?: boolean
  maxLegTimeH: number
  minLegTimeH?: number
  legAscentCapM?: number
  maxEleM?: number | null
  allowViaFerrata?: boolean
  allowedHutIndices?: Set<number>
}

export interface KillCounters {
  maxLegTime: number
  minLegTime: number
  legAscentCap: number
  maxEleM: number
  viaFerrata: number
  revisit: number
  hutFiltered: number
}
```

- [ ] **Step 4: Update `createKillCounters`**

In `huts/src/tourSearch/legFilters.ts`:

```ts
export function createKillCounters(): KillCounters {
  return { maxLegTime: 0, minLegTime: 0, legAscentCap: 0, maxEleM: 0, viaFerrata: 0, revisit: 0, hutFiltered: 0 }
}
```

- [ ] **Step 5: Enforce `allowedHutIndices` and gate `'village'` in `search.ts`**

In `huts/src/tourSearch/search.ts`:

```ts
import { SOURCE_TYPE_PARKING, SOURCE_TYPE_PARTNER, SOURCE_TYPE_STATION } from './types.js'

function requiredSourceType(mode: Query['mode']): SourceType | null {
  if (mode === 'transit') return SOURCE_TYPE_STATION
  if (mode === 'car') return SOURCE_TYPE_PARKING
  if (mode === 'village') return SOURCE_TYPE_PARTNER
  return null
}
```

```ts
export function searchChains(query: Query, graphData: GraphData): SearchResult {
  const {
    mode, legCountMin, legCountMax, sacCeiling, allowUngraded = false,
    maxLegTimeH, minLegTimeH = 0, legAscentCapM = Infinity, maxEleM = null, allowViaFerrata = true,
    allowedHutIndices,
  } = query
  ...
```

Add the filter at the seeding loop (was lines 59–74 — skip a hut index entirely before it's ever
added to `layer`):

```ts
  for (let h = 0; h < graphData.hutEdges.hutIds.length; h++) {
    if (allowedHutIndices && !allowedHutIndices.has(h)) { killCounters.hutFiltered++; continue }
    for (const approachLeg of getApproachLegs(h, graphData.approaches)) {
      ...
```

Add the same filter inside the per-hop DFS loop (was lines 100–126), on `h2` before it's added to
`nextLayer`:

```ts
        for (const leg of legs) {
          const h2 = leg.toIndex
          if (allowedHutIndices && !allowedHutIndices.has(h2)) { killCounters.hutFiltered++; continue }
          if (s.path.includes(h2)) { killCounters.revisit++; continue }
          if (!legPasses(leg, constraints, killCounters)) continue
          ...
```

Both checks run before the hut ever enters `layer`/`nextLayer`, matching the spec's "prune early,
not post-hoc" requirement.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd huts && npx vitest run src/tourSearch/search.test.ts`
Expected: PASS, all tests including pre-existing ones (unaffected — `allowedHutIndices` is
optional and defaults to allowing everything).

- [ ] **Step 7: Typecheck**

Run: `cd huts && npm run typecheck`
Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add huts/src/tourSearch/types.ts huts/src/tourSearch/legFilters.ts huts/src/tourSearch/search.ts huts/src/tourSearch/search.test.ts
git commit -m "feat(tourSearch): add hut-index filtering and village (Bergsteigerdorf) mode"
```

---

## Task 5: `LegCountSlider` min fix (dead-setting cleanup)

Small, isolated, no dependency on the rest — do it whenever convenient, but it's listed here
because the spec calls it out as a concrete UI wrinkle to fix.

**Files:**
- Modify: `huts/src/tourSearchPage/LegCountSlider.tsx:30`

**Interfaces:**
- Consumes/produces: none — purely a UI prop constant.

- [ ] **Step 1: Change the constant**

In `huts/src/tourSearchPage/LegCountSlider.tsx`, change `min={1}` to `min={2}` on the `Slider`
(currently line 30). No test is needed — this is a static prop with no behavior; the two-nights
minimum is already covered by Task 4's `legCountMin = 1` invariant test at the engine layer (the
engine correctly floors, this only removes the UI setting that did nothing).

- [ ] **Step 2: Commit**

```bash
git add huts/src/tourSearchPage/LegCountSlider.tsx
git commit -m "fix(huts): raise LegCountSlider min to 2 (1 Etappe = 0 nights is unreachable)"
```

---

## Task 6: Form state — filter checkboxes, `allowedHutIndices` derivation, submit guard

**Files:**
- Modify: `huts/src/tourSearchPage/formState.ts`
- Test: create `huts/src/tourSearchPage/formState.test.ts`

**Interfaces:**
- Consumes: `HutOperator` from `huts/src/hutClass.js` (Task 2), `HutClass` from same.
- Produces (used by Task 8 `TourSearchPage.tsx`):
  - `FormState.allowedOperators: Set<HutOperator>` (default `new Set(['av', 'sonstige'])`)
  - `FormState.allowServiced: boolean` (default `true`)
  - `FormState.allowSelfService: boolean` (default `false`)
  - `buildQuery(form, hutsByIndex: (HutClass | null)[]): Query` — signature widens to take the
    index-keyed hut classes so it can derive `allowedHutIndices` itself (a hut with `null` class —
    i.e. failed the §0 join — is treated as *not* allowed, since its category can't be verified).
  - `isFilterSelectionValid(form: FormState): boolean` — `false` iff `allowedOperators` is empty or
    neither `allowServiced` nor `allowSelfService` is checked.

- [ ] **Step 1: Write the failing tests**

Create `huts/src/tourSearchPage/formState.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { DEFAULT_FORM, buildQuery, isFilterSelectionValid } from './formState.js'
import type { HutClass } from '../hutClass.js'

const hutsByIndex: (HutClass | null)[] = [
  { operator: 'av', serviced: true },     // 0
  { operator: 'av', serviced: false },    // 1
  { operator: 'sonstige', serviced: true }, // 2
  null,                                    // 3 - failed join, must never pass
]

describe('buildQuery hut filtering', () => {
  it('default form allows av+sonstige, serviced only -> excludes self-service and unresolved huts', () => {
    const q = buildQuery(DEFAULT_FORM, hutsByIndex)
    expect(q.allowedHutIndices).toEqual(new Set([0, 2]))
  })

  it('enabling allowSelfService includes self-service huts of allowed operators', () => {
    const form = { ...DEFAULT_FORM, allowSelfService: true }
    const q = buildQuery(form, hutsByIndex)
    expect(q.allowedHutIndices).toEqual(new Set([0, 1, 2]))
  })

  it('restricting allowedOperators to av-only excludes sonstige regardless of servicing', () => {
    const form = { ...DEFAULT_FORM, allowedOperators: new Set<'av' | 'sonstige'>(['av']), allowSelfService: true }
    const q = buildQuery(form, hutsByIndex)
    expect(q.allowedHutIndices).toEqual(new Set([0, 1]))
  })

  it('a null hut class (failed GUID join) is never included', () => {
    const form = { ...DEFAULT_FORM, allowSelfService: true }
    const q = buildQuery(form, hutsByIndex)
    expect(q.allowedHutIndices!.has(3)).toBe(false)
  })
})

describe('isFilterSelectionValid', () => {
  it('is valid for the default form', () => {
    expect(isFilterSelectionValid(DEFAULT_FORM)).toBe(true)
  })
  it('is invalid when allowedOperators is empty', () => {
    expect(isFilterSelectionValid({ ...DEFAULT_FORM, allowedOperators: new Set() })).toBe(false)
  })
  it('is invalid when neither servicing box is checked', () => {
    expect(isFilterSelectionValid({ ...DEFAULT_FORM, allowServiced: false, allowSelfService: false })).toBe(false)
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd huts && npx vitest run src/tourSearchPage/formState.test.ts`
Expected: FAIL — `buildQuery`/`isFilterSelectionValid` either don't exist with this signature or
don't derive `allowedHutIndices`.

- [ ] **Step 3: Implement**

Rewrite `huts/src/tourSearchPage/formState.ts`:

```ts
import type { Query, TourMode } from '../tourSearch/types.js'
import type { HutClass, HutOperator } from '../hutClass.js'
import { toNumberOrDefault } from './helpers.js'

export interface FormState {
  mode: TourMode
  legCountRange: [number, number]
  sacCeiling: number | 'any'
  allowUngraded: boolean
  legTimeRange: [number, number]
  legAscentCapM: string
  maxEleM: string
  allowViaFerrata: boolean
  overlapVariety: 'wenig' | 'mittel' | 'viel'
  allowedOperators: Set<HutOperator>
  allowServiced: boolean
  allowSelfService: boolean
}

export const DEFAULT_FORM: FormState = {
  mode: 'transit',
  legCountRange: [2, 4],
  sacCeiling: 3,
  allowUngraded: true,
  legTimeRange: [4, 8],
  legAscentCapM: '',
  maxEleM: '',
  allowViaFerrata: true,
  overlapVariety: 'mittel',
  allowedOperators: new Set(['av', 'sonstige']),
  allowServiced: true,
  allowSelfService: false,
}

export const OVERLAP_THRESHOLD_BY_VARIETY: Record<FormState['overlapVariety'], number> = {
  wenig: 0.3,
  mittel: 0.5,
  viel: 0.8,
}

function hutClassAllowed(c: HutClass, form: FormState): boolean {
  if (!form.allowedOperators.has(c.operator)) return false
  return c.serviced ? form.allowServiced : form.allowSelfService
}

function allowedHutIndices(form: FormState, hutsByIndex: (HutClass | null)[]): Set<number> {
  const allowed = new Set<number>()
  hutsByIndex.forEach((c, i) => {
    if (c && hutClassAllowed(c, form)) allowed.add(i)
  })
  return allowed
}

export function isFilterSelectionValid(form: FormState): boolean {
  if (form.allowedOperators.size === 0) return false
  if (!form.allowServiced && !form.allowSelfService) return false
  return true
}

export function buildQuery(form: FormState, hutsByIndex: (HutClass | null)[]): Query {
  return {
    mode: form.mode,
    legCountMin: form.legCountRange[0],
    legCountMax: form.legCountRange[1],
    sacCeiling: form.sacCeiling === 'any' ? null : form.sacCeiling,
    allowUngraded: form.allowUngraded,
    minLegTimeH: form.legTimeRange[0],
    maxLegTimeH: form.legTimeRange[1],
    legAscentCapM: toNumberOrDefault(form.legAscentCapM, Infinity),
    maxEleM: form.maxEleM === '' ? null : toNumberOrDefault(form.maxEleM, Infinity),
    allowViaFerrata: form.allowViaFerrata,
    allowedHutIndices: allowedHutIndices(form, hutsByIndex),
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd huts && npx vitest run src/tourSearchPage/formState.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add huts/src/tourSearchPage/formState.ts huts/src/tourSearchPage/formState.test.ts
git commit -m "feat(huts): derive allowedHutIndices from hut-class filter form state"
```

---

## Task 7: `helpers.ts` — partner source label, `hutFiltered` guidance, village empty state

**Files:**
- Modify: `huts/src/tourSearchPage/helpers.ts`
- Test: create `huts/src/tourSearchPage/helpers.test.ts`

**Interfaces:**
- Consumes: `SOURCE_TYPE_PARTNER` from `../tourSearch/types.js` (Task 4).
- Produces (used by Task 8/9): `SOURCE_TYPE_LABEL[SOURCE_TYPE_PARTNER]`, `killCounterGuidance`
  including a `hutFiltered` line, `VILLAGE_EMPTY_STATE_HINT: string`.

- [ ] **Step 1: Write the failing tests**

Create `huts/src/tourSearchPage/helpers.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { SOURCE_TYPE_LABEL, killCounterGuidance, VILLAGE_EMPTY_STATE_HINT } from './helpers.js'
import { SOURCE_TYPE_PARTNER } from '../tourSearch/types.js'

describe('SOURCE_TYPE_LABEL', () => {
  it('labels partner points as Partnerbetrieb', () => {
    expect(SOURCE_TYPE_LABEL[SOURCE_TYPE_PARTNER]).toBe('Partnerbetrieb')
  })
})

describe('killCounterGuidance hutFiltered', () => {
  it('explains that the hut filter excluded stage destinations, with a count', () => {
    const msgs = killCounterGuidance({
      maxLegTime: 0, minLegTime: 0, legAscentCap: 0, maxEleM: 0, viaFerrata: 0, revisit: 0, hutFiltered: 7,
    })
    expect(msgs.some((m) => m.includes('7') && m.includes('Hüttenfilter'))).toBe(true)
  })
})

describe('VILLAGE_EMPTY_STATE_HINT', () => {
  it('mentions Bergsteigerdorf/Partnerbetrieb rather than implying the user filters are at fault', () => {
    expect(VILLAGE_EMPTY_STATE_HINT).toMatch(/Bergsteigerdorf|Partnerbetrieb/)
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd huts && npx vitest run src/tourSearchPage/helpers.test.ts`
Expected: FAIL — `SOURCE_TYPE_LABEL[SOURCE_TYPE_PARTNER]` is `undefined`,
`VILLAGE_EMPTY_STATE_HINT` doesn't exist, `killCounters` type error on missing `hutFiltered`
handling (compiles once Task 4's type lands, but the guidance line itself is still missing).

- [ ] **Step 3: Implement**

In `huts/src/tourSearchPage/helpers.ts`:

```ts
import { SOURCE_TYPE_PARKING, SOURCE_TYPE_PARTNER, SOURCE_TYPE_STATION } from '../tourSearch/types.js'
import type { SearchResult, TourResult } from '../tourSearch/types.js'

export const PAGE_SIZE = 25

export const SOURCE_TYPE_LABEL: Record<number, string> = {
  [SOURCE_TYPE_STATION]: 'Bahnhof',
  [SOURCE_TYPE_PARKING]: 'Parkplatz',
  [SOURCE_TYPE_PARTNER]: 'Partnerbetrieb',
}
```

```ts
const KILL_COUNTER_GUIDANCE: Record<string, (n: number) => string> = {
  maxLegTime: (n) => `${n} Etappen waren zu lang — maximale Gehzeit erhöhen`,
  minLegTime: (n) => `${n} Etappen waren zu kurz — minimale Gehzeit senken`,
  legAscentCap: (n) => `${n} Etappen hatten zu viel Anstieg — Anstiegslimit erhöhen`,
  maxEleM: (n) => `${n} Etappen lagen über der Maximalhöhe — Maximalhöhe erhöhen`,
  viaFerrata: (n) => `${n} Etappen enthielten Klettersteige — "Klettersteige erlauben" aktivieren`,
  revisit: () => '', // internal search bookkeeping, not user-actionable
  hutFiltered: (n) => `${n} mögliche Etappenziele wurden durch den Hüttenfilter ausgeschlossen — Hüttenarten wieder aktivieren`,
}
```

Add near `LEG_COUNT_SLOW_WARNING_THRESHOLD`:

```ts
// Shown instead of the generic empty-results message when mode === 'village': only 56 of 110
// Partnerbetriebe are connected to the trail network, so zero results there far more often
// reflects sparse coverage than an over-tight filter.
export const VILLAGE_EMPTY_STATE_HINT =
  'Nur wenige Bergsteigerdörfer/Partnerbetriebe sind an das Wegenetz angebunden — probiere einen anderen Modus, falls hier keine Touren erscheinen.'
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd huts && npx vitest run src/tourSearchPage/helpers.test.ts`
Expected: PASS.

- [ ] **Step 5: Typecheck**

Run: `cd huts && npm run typecheck`
Expected: no errors (confirms `killCounterGuidance`'s `Object.entries` loop stays untyped-safe
against the widened `KillCounters`).

- [ ] **Step 6: Commit**

```bash
git add huts/src/tourSearchPage/helpers.ts huts/src/tourSearchPage/helpers.test.ts
git commit -m "feat(huts): add Partnerbetrieb source label and hut-filter kill-counter guidance"
```

---

## Task 8: `TourSearchPage.tsx` — partner fetch, mode option, filter checkboxes, submit guard

**Files:**
- Modify: `huts/src/tourSearchPage/TourSearchPage.tsx`
- Test: `huts/src/tourSearchPage/TourSearchPage.test.tsx`

**Interfaces:**
- Consumes: `SOURCE_TYPE_PARTNER` (Task 4), `HutClass`/`hutClassLabel` (Task 2),
  `FormState.allowedOperators`/`allowServiced`/`allowSelfService`, `buildQuery(form, hutsByIndex)`,
  `isFilterSelectionValid(form)` (Task 6), `VILLAGE_EMPTY_STATE_HINT` (Task 7).
- Produces: `hutsByIndex: (HutClass | null)[]` state, passed down to `TourList`/`ResultsMap` in
  Task 9 as a new prop `hutClassByIndex: Map<number, HutClass>`.

- [ ] **Step 1: Write the failing tests**

Add to `huts/src/tourSearchPage/TourSearchPage.test.tsx`:

```ts
it('fetches partner_betriebe.geojson and a 404 on it still leaves the page usable', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      if (url.includes('huts.geojson')) {
        return fetchJsonMock({ type: 'FeatureCollection', features: [{ properties: { id: 0, name: 'HutA', hutType: 'av', serviced: true }, geometry: { type: 'Point', coordinates: [11.0, 47.0] } }] })
      }
      if (url.includes('parking.geojson')) return fetchJsonMock({ type: 'FeatureCollection', features: [] })
      if (url.includes('stations.geojson')) return fetchJsonMock({ type: 'FeatureCollection', features: [] })
      if (url.includes('partner_betriebe.geojson')) return Promise.reject(new Error('404'))
      throw new Error(`unexpected fetch ${url}`)
    }),
  )
  render(<TourSearchPage />)
  await waitFor(() => expect(screen.getByText('Daten geladen')).toBeInTheDocument())
  expect(screen.getByRole('button', { name: 'Touren suchen' })).toBeEnabled()
})

it('renders the Bergsteigerdorf mode option and the operator/servicing checkboxes', async () => {
  render(<TourSearchPage />)
  await waitFor(() => expect(screen.getByText('Daten geladen')).toBeInTheDocument())
  await userEvent.click(screen.getByRole('combobox', { name: /Modus/i }) ?? screen.getAllByRole('combobox')[0])
  expect(screen.getByText('Start im Bergsteigerdorf (offene Strecke)')).toBeInTheDocument()
  await userEvent.keyboard('{Escape}')
  expect(screen.getByLabelText(/Selbstversorgerhütten/)).toBeInTheDocument()
})

it('disables submit and shows a hint when the filter selection is empty', async () => {
  render(<TourSearchPage />)
  await waitFor(() => expect(screen.getByText('Daten geladen')).toBeInTheDocument())
  await userEvent.click(screen.getByLabelText('AV-Hütte'))
  await userEvent.click(screen.getByLabelText('Sonstige Hütte'))
  expect(screen.getByRole('button', { name: 'Touren suchen' })).toBeDisabled()
})
```

Also update the `beforeEach` fetch mock (used by every other existing test in the file) to add a
`partner_betriebe.geojson` branch returning an empty collection, matching the `stations.geojson`
pattern already there — otherwise every pre-existing test in this file starts throwing
`unexpected fetch` once the component adds the partner fetch:

```ts
if (url.includes('partner_betriebe.geojson')) {
  return fetchJsonMock({ type: 'FeatureCollection', features: [] })
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd huts && npx vitest run src/tourSearchPage/TourSearchPage.test.tsx`
Expected: FAIL — no partner fetch yet (pre-existing tests break on `unexpected fetch
partner_betriebe.geojson` once other tasks' plumbing exists, or the new tests fail to find the
mode option / checkboxes / disabled state, whichever lands first).

- [ ] **Step 3: Implement**

In `huts/src/tourSearchPage/TourSearchPage.tsx`, add imports:

```ts
import { SOURCE_TYPE_PARKING, SOURCE_TYPE_PARTNER, SOURCE_TYPE_STATION } from '../tourSearch/types.js'
import type { GraphData, SearchResult, TourMode } from '../tourSearch/types.js'
import type { HutClass, HutOperator } from '../hutClass.js'
import { hutClassLabel, OPERATOR_LABEL } from '../hutClass.js'
import { DEFAULT_FORM, OVERLAP_THRESHOLD_BY_VARIETY, buildQuery, isFilterSelectionValid, type FormState } from './formState.js'
import { PAGE_SIZE, SOURCE_TYPE_LABEL, VILLAGE_EMPTY_STATE_HINT, idFromOsmFeatureId, SORT_COMPARATORS, type SortKey } from './helpers.js'
```

Add the partner URL constant:

```ts
const PARTNER_URL = '/data/partner_betriebe.geojson'
```

Add a `hutsByIndex` state slot (parallel array indexed like `hutNameById`/`hutCoordsById`, but
holding hut class or `null`):

```ts
const [hutsByIndex, setHutsByIndex] = useState<(HutClass | null)[]>([])
```

Update the load effect: replace the four-item `Promise.all` with a five-item one where the
partner fetch has its own `.catch`, and populate `hutsByIndex` and the partner `startById`
entries. Full replacement of the effect body:

```ts
useEffect(() => {
  Promise.all([
    loadTourSearchData(),
    fetch(HUTS_URL).then((r) => r.json()) as Promise<GeoJSON.FeatureCollection>,
    fetch(PARKING_URL).then((r) => r.json()) as Promise<GeoJSON.FeatureCollection>,
    fetch(STATIONS_URL).then((r) => r.json()) as Promise<GeoJSON.FeatureCollection>,
    fetch(PARTNER_URL)
      .then((r) => r.json() as Promise<GeoJSON.FeatureCollection>)
      .catch(() => ({ type: 'FeatureCollection', features: [] }) as GeoJSON.FeatureCollection),
  ])
    .then(([tourSearchData, hutsFc, parkingFc, stationsFc, partnerFc]) => {
      setGraphData(tourSearchData)

      const hutFeatureByGuid = new Map(
        hutsFc.features.map((f) => [(f.properties as { id: string }).id, f]),
      )
      const hutsByIdx = tourSearchData.hutEdges.hutIds.map((guid) => hutFeatureByGuid.get(guid) ?? null)

      setHutNameById(
        new Map(
          hutsByIdx
            .map((f, i) => (f ? ([i, (f.properties as { name: string }).name] as const) : null))
            .filter((entry): entry is readonly [number, string] => entry != null),
        ),
      )
      setHutCoordsById(
        new Map(
          hutsByIdx
            .map((f, i) => {
              if (!f) return null
              const [lng, lat] = (f.geometry as GeoJSON.Point).coordinates
              return [i, { lat, lng }] as const
            })
            .filter((entry): entry is readonly [number, { lat: number; lng: number }] => entry != null),
        ),
      )
      setHutsByIndex(
        hutsByIdx.map((f) => {
          if (!f) return null
          const props = f.properties as { hutType?: string; serviced?: boolean }
          if (props.hutType !== 'av' && props.hutType !== 'sonstige') return null
          return { operator: props.hutType, serviced: props.serviced ?? true }
        }),
      )

      const starts = new Map<number, StartPoint>()
      for (const f of stationsFc.features) {
        const id = idFromOsmFeatureId(f.id as string | number)
        const [lng, lat] = (f.geometry as GeoJSON.Point).coordinates
        if (id != null) {
          starts.set(id, { name: (f.properties as { name?: string })?.name ?? null, sourceType: SOURCE_TYPE_STATION, lat, lng })
        }
      }
      for (const f of parkingFc.features) {
        const id = idFromOsmFeatureId(f.id as string | number)
        const [lng, lat] = (f.geometry as GeoJSON.Point).coordinates
        if (id != null) {
          starts.set(id, { name: (f.properties as { name?: string })?.name ?? null, sourceType: SOURCE_TYPE_PARKING, lat, lng })
        }
      }
      // Partner points carry no top-level f.id (ArcGIS OBJECTID lives in properties.id) - do NOT
      // use idFromOsmFeatureId here, it would reduce Number("") to 0 and collapse every point.
      for (const f of partnerFc.features) {
        const id = (f.properties as { id?: number })?.id
        const [lng, lat] = (f.geometry as GeoJSON.Point).coordinates
        if (id != null) {
          starts.set(id, { name: (f.properties as { name?: string })?.name ?? null, sourceType: SOURCE_TYPE_PARTNER, lat, lng })
        }
      }
      setStartById(starts)
    })
    .catch((e: Error) => setError(e.message))
}, [])
```

Add the mode `MenuItem`:

```tsx
<MenuItem value="car">Auto (Rundtour zum Ausgangspunkt)</MenuItem>
<MenuItem value="transit">ÖPNV (offene Strecke)</MenuItem>
<MenuItem value="village">Start im Bergsteigerdorf (offene Strecke)</MenuItem>
```

Add a filter checkbox group, e.g. right after the "Schwierigkeit" `Box` (around line 193):

```tsx
<Box sx={{ width: 260 }}>
  <Typography variant="subtitle2">Hüttenarten</Typography>
  {(Object.keys(OPERATOR_LABEL) as HutOperator[]).map((op) => (
    <FormControlLabel
      key={op}
      sx={{ display: 'block' }}
      control={
        <Checkbox
          checked={form.allowedOperators.has(op)}
          onChange={(e) =>
            setForm((f) => {
              const next = new Set(f.allowedOperators)
              if (e.target.checked) next.add(op)
              else next.delete(op)
              return { ...f, allowedOperators: next }
            })
          }
        />
      }
      label={OPERATOR_LABEL[op]}
    />
  ))}
  <FormControlLabel
    sx={{ display: 'block' }}
    control={<Checkbox checked={form.allowServiced} onChange={(e) => setForm((f) => ({ ...f, allowServiced: e.target.checked }))} />}
    label="Bewirtschaftete Hütten"
  />
  <FormControlLabel
    sx={{ display: 'block' }}
    control={<Checkbox checked={form.allowSelfService} onChange={(e) => setForm((f) => ({ ...f, allowSelfService: e.target.checked }))} />}
    label="Selbstversorgerhütten (unbewirtschaftet, ggf. Schlüssel nötig)"
  />
  {!isFilterSelectionValid(form) && (
    <Typography variant="caption" color="error">
      Mindestens ein Betreiber und eine Betriebsart müssen ausgewählt sein.
    </Typography>
  )}
</Box>
```

Update the submit button's `disabled`:

```tsx
<Button
  type="submit"
  variant="contained"
  disabled={!graphData || searching || !isFilterSelectionValid(form)}
  startIcon={searching ? <CircularProgress size={16} color="inherit" /> : undefined}
>
```

Update `handleSubmit` to pass `hutsByIndex` into `buildQuery`:

```ts
setTimeout(() => {
  const query = buildQuery(form, hutsByIndex)
  const overlapThreshold = OVERLAP_THRESHOLD_BY_VARIETY[form.overlapVariety]
  setResult(findTours(query, graphData, { overlapThreshold }))
  setPage(1)
  setSearching(false)
}, 0)
```

Note: `hutClassLabel` and `VILLAGE_EMPTY_STATE_HINT` are wired into `TourList`/empty-state
rendering in Task 9, not here — this task only needs `OPERATOR_LABEL` for the checkbox labels and
`isFilterSelectionValid` for the guard. Remove the now-unused `hutClassLabel` import from this
file if Task 9 hasn't landed yet in your working order (keep imports matched to actual usage to
avoid an unused-import lint failure).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd huts && npx vitest run src/tourSearchPage/TourSearchPage.test.tsx`
Expected: PASS.

- [ ] **Step 5: Typecheck and lint**

Run: `cd huts && npm run typecheck && npm run lint`
Expected: no errors (watch for the unused-import note above).

- [ ] **Step 6: Commit**

```bash
git add huts/src/tourSearchPage/TourSearchPage.tsx huts/src/tourSearchPage/TourSearchPage.test.tsx
git commit -m "feat(huts): add Bergsteigerdorf mode and hut-class filter UI to TourSearchPage"
```

---

## Task 9: `TourList.tsx` / `ResultsMap.tsx` — class badges, marker styling, dimmed overview, legend

**Files:**
- Modify: `huts/src/tourSearchPage/TourList.tsx`
- Modify: `huts/src/tourSearchPage/ResultsMap.tsx`
- Test: `huts/src/tourSearchPage/ResultsMap.test.tsx` (extend)
- Test: create `huts/src/tourSearchPage/TourList.test.tsx`

**Interfaces:**
- Consumes: `HutClass`, `hutClassLabel`, `hutClassBadge`, `OPERATOR_COLOR`, `PARTNER_LABEL`,
  `PARTNER_COLOR` (Task 2); `SOURCE_TYPE_PARTNER` (Task 4); new prop
  `hutClassByIndex: Map<number, HutClass>` threaded from `TourSearchPage` (Task 8's `hutsByIndex`
  state, converted to a `Map` at the call site — `TourSearchPage.tsx`'s render passes
  `new Map(hutsByIndex.map((c, i) => [i, c]).filter(([, c]) => c != null))` into both
  `TourList`/`ResultsMap`, or the state can be stored as a `Map` directly instead of an array — use
  whichever the Task 8 implementation already produced; if it's an array, convert once via
  `useMemo`).
- Produces: nothing further downstream — this is the leaf display layer.

- [ ] **Step 1: Write the failing `TourList` test**

Create `huts/src/tourSearchPage/TourList.test.tsx`:

```tsx
// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import TourList from './TourList.js'
import type { SearchResult, TourResult } from '../tourSearch/types.js'
import type { HutClass } from '../hutClass.js'

const chain: TourResult = {
  huts: [0], startId: 100, exitStartId: 100,
  totalDurationH: 5, totalAscentM: 500, totalDescentM: 500, totalDistanceM: 8000,
  legs: [
    { durationH: 2.5, ascentM: 250, descentM: 250, distanceM: 4000, edgeId: 0, reversed: false },
    { durationH: 2.5, ascentM: 250, descentM: 250, distanceM: 4000, edgeId: 1, reversed: true },
  ],
}
const result: SearchResult = { chains: [chain], killCounters: { maxLegTime: 0, minLegTime: 0, legAscentCap: 0, maxEleM: 0, viaFerrata: 0, revisit: 0, hutFiltered: 0 } }
const hutNameById = new Map([[0, 'HutA']])
const hutClassByIndex = new Map<number, HutClass>([[0, { operator: 'av', serviced: false }]])

it('shows the hut class badge next to the hut name in the expanded chain sentence', () => {
  render(
    <TourList
      result={result} displayedChains={[chain]} pageChains={[chain]} page={1} pageCount={1}
      setPage={() => {}} sortKey="duration" setSortKey={() => {}} hutNameById={hutNameById}
      hutClassByIndex={hutClassByIndex} startLabel={() => 'Start'}
      expandedChain={0} setExpandedChain={() => {}}
    />,
  )
  expect(screen.getByText('AV·SV')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd huts && npx vitest run src/tourSearchPage/TourList.test.tsx`
Expected: FAIL — `TourList` doesn't accept `hutClassByIndex` yet / badge not rendered.

- [ ] **Step 3: Implement `TourList` changes**

In `huts/src/tourSearchPage/TourList.tsx`, add import and prop:

```ts
import { hutClassBadge, OPERATOR_COLOR, type HutClass } from '../hutClass.js'
```

```ts
const TourList = memo(function TourList({
  result, displayedChains, pageChains, page, pageCount, setPage,
  sortKey, setSortKey, hutNameById, hutClassByIndex, startLabel, expandedChain, setExpandedChain,
}: {
  result: SearchResult
  displayedChains: TourResult[]
  pageChains: TourResult[]
  page: number
  pageCount: number
  setPage: (p: number) => void
  sortKey: SortKey
  setSortKey: (k: SortKey) => void
  hutNameById: Map<number, string>
  hutClassByIndex: Map<number, HutClass>
  startLabel: (startId: number) => string
  expandedChain: number | null
  setExpandedChain: (i: number | null) => void
}) {
```

Add a small badge renderer and use it in both the hut-chain sentence and the leg table's waypoint
labels. Replace the expanded-summary line:

```tsx
<Typography variant="body2" sx={{ mb: 1 }}>
  {startLabel(chain.startId)}
  {chain.huts.map((h) => (
    <span key={h}>
      {' → '}
      {hutNameById.get(h) ?? h}
      {hutClassByIndex.has(h) && (
        <span
          style={{
            marginLeft: 4, padding: '0 4px', borderRadius: 3, fontSize: '0.7rem',
            color: '#fff', backgroundColor: OPERATOR_COLOR[hutClassByIndex.get(h)!.operator],
          }}
        >
          {hutClassBadge(hutClassByIndex.get(h)!)}
        </span>
      )}
    </span>
  ))}
  {' → '}
  {startLabel(chain.exitStartId)}
</Typography>
```

(The `legWaypointLabels`-driven table stays text-only per the spec, which only requires the badge
"next to each hut name" — the chain sentence above and the waypoint list share the same hut names,
so putting it in the sentence satisfies "in both `TourList` ... and `ResultsMap`" from the spec's
§6 combined with this component; adding it a second time in the per-leg table would duplicate the
same information without adding anything.)

- [ ] **Step 4: Run `TourList` test to verify it passes**

Run: `cd huts && npx vitest run src/tourSearchPage/TourList.test.tsx`
Expected: PASS.

- [ ] **Step 5: Write the failing `ResultsMap` tests**

Add to `huts/src/tourSearchPage/ResultsMap.test.tsx`:

```tsx
import type { HutClass } from '../hutClass.js'

// ... inside a new describe block, using the file's existing chain/hutNameById/hutCoordsById/startById fixtures:

describe('ResultsMap hut-class styling', () => {
  it('colours the overview markers by operator and dims huts excluded by the active filter', () => {
    const hutClassByIndex = new Map<number, HutClass>([[0, { operator: 'av', serviced: true }]])
    const { container } = render(
      <ResultsMap
        selectedChain={null} hutNameById={hutNameById} hutCoordsById={hutCoordsById}
        startById={startById} hutClassByIndex={hutClassByIndex}
        excludedHutIndices={new Set([0])}
      />,
    )
    const marker = container.querySelector('path.leaflet-interactive')
    expect(marker).not.toBeNull()
    // Dimmed excluded huts render with reduced fill-opacity rather than being removed.
    expect(marker?.getAttribute('fill-opacity')).not.toBe('0.9')
  })
})
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd huts && npx vitest run src/tourSearchPage/ResultsMap.test.tsx -t "hut-class styling"`
Expected: FAIL — `ResultsMap` doesn't accept `hutClassByIndex`/`excludedHutIndices` yet.

- [ ] **Step 7: Implement `ResultsMap` changes**

In `huts/src/tourSearchPage/ResultsMap.tsx`, add imports:

```ts
import { OPERATOR_COLOR, PARTNER_COLOR, PARTNER_LABEL, hutClassLabel, type HutClass } from '../hutClass.js'
import { SOURCE_TYPE_PARTNER } from '../tourSearch/types.js'
```

Widen the component props and destructure the two new ones:

```ts
const ResultsMap = memo(function ResultsMap({
  selectedChain, hutNameById, hutCoordsById, startById, hutClassByIndex, excludedHutIndices,
}: {
  selectedChain: TourResult | null
  hutNameById: Map<number, string>
  hutCoordsById: Map<number, { lat: number; lng: number }>
  startById: Map<number, StartPoint>
  hutClassByIndex: Map<number, HutClass>
  excludedHutIndices: Set<number>
}) {
```

Replace the "show all huts" overview marker block (was lines 140–152) so colour comes from class
and excluded huts are dimmed rather than hidden:

```tsx
{!showChain &&
  [...hutCoordsById.entries()].map(([id, { lat, lng }]) => {
    const cls = hutClassByIndex.get(id)
    const excluded = excludedHutIndices.has(id)
    const color = cls ? OPERATOR_COLOR[cls.operator] : '#1b5e20'
    return (
      <CircleMarker
        key={id}
        center={[lat, lng]}
        radius={4}
        pathOptions={{
          color,
          fillColor: color,
          fillOpacity: excluded ? 0.25 : cls?.serviced === false ? 0.15 : 0.9,
          weight: excluded ? 1 : cls?.serviced === false ? 2 : 1,
        }}
      >
        <Tooltip direction="top" offset={[0, -6]}>
          {hutNameById.get(id) ?? id}
          {cls ? ` — ${hutClassLabel(cls)}` : ''}
        </Tooltip>
      </CircleMarker>
    )
  })}
```

Add partner-point markers to the same overview block (only when not showing a selected chain),
right after the hut markers:

```tsx
{!showChain &&
  [...startById.entries()]
    .filter(([, s]) => s.sourceType === SOURCE_TYPE_PARTNER)
    .map(([id, s]) => (
      <CircleMarker
        key={`partner-${id}`}
        center={[s.lat, s.lng]}
        radius={5}
        pathOptions={{ color: PARTNER_COLOR, fillColor: PARTNER_COLOR, fillOpacity: 0.9, weight: 1 }}
      >
        <Tooltip direction="top" offset={[0, -6]}>
          {s.name ?? PARTNER_LABEL} ({PARTNER_LABEL})
        </Tooltip>
      </CircleMarker>
    ))}
```

Update the selected-chain path markers (was lines 166–173) to also colour by class where the
point is a hut:

```tsx
{positions.map((pos, i) => {
  const isEndpoint = i === 0 || i === positions.length - 1
  const hutIndex = !isEndpoint ? selectedChain!.huts[i - 1] : null
  const cls = hutIndex != null ? hutClassByIndex.get(hutIndex) : undefined
  const color = cls ? OPERATOR_COLOR[cls.operator] : '#1b5e20'
  return (
    <CircleMarker
      key={i}
      center={pos}
      radius={isEndpoint ? 6 : 5}
      pathOptions={{ color, fillColor: color, fillOpacity: 1 }}
    />
  )
})}
```

Add a small legend, rendered unconditionally in the top-right of the map `Box` (uses
`OPERATOR_LABEL`/`hutClassLabel`/`PARTNER_LABEL` so it can't drift from marker styling):

```tsx
import { OPERATOR_LABEL } from '../hutClass.js'
```

```tsx
<Box
  sx={{
    position: 'absolute', top: 8, right: 8, zIndex: 1000, bgcolor: 'background.paper',
    p: 1, borderRadius: 1, fontSize: '0.75rem', display: 'flex', flexDirection: 'column', gap: 0.5,
  }}
>
  {(Object.keys(OPERATOR_LABEL) as (keyof typeof OPERATOR_LABEL)[]).map((op) => (
    <Box key={op} sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
      <Box sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: OPERATOR_COLOR[op] }} />
      {OPERATOR_LABEL[op]}
    </Box>
  ))}
  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
    <Box sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: PARTNER_COLOR }} />
    {PARTNER_LABEL}
  </Box>
</Box>
```

Update the memoized `useMemo`/`positions` dependency arrays if needed (none of the above changes
`chainPositions`'s signature, so no change required there).

- [ ] **Step 8: Update the two other existing `ResultsMap.test.tsx` call sites**

The three pre-existing tests in the file (`resolves ... per leg`, `a leg whose fetch rejects`,
`deselecting the tour`) construct `<ResultsMap ... />` without the two new required props — add
`hutClassByIndex={new Map()}` and `excludedHutIndices={new Set()}` to each of their three
`render(<ResultsMap .../>)` calls so they keep compiling and passing under the new required props.

- [ ] **Step 9: Run all `ResultsMap` tests to verify they pass**

Run: `cd huts && npx vitest run src/tourSearchPage/ResultsMap.test.tsx`
Expected: PASS, all four tests (three pre-existing + the new hut-class one).

- [ ] **Step 10: Wire the new props through `TourSearchPage.tsx`**

Back in `huts/src/tourSearchPage/TourSearchPage.tsx` (from Task 8), derive the `Map` and excluded
set and pass them to both children. Add near `displayedChains`:

```ts
const hutClassByIndex = useMemo(
  () => new Map(hutsByIndex.map((c, i) => [i, c]).filter((entry): entry is [number, HutClass] => entry[1] != null)),
  [hutsByIndex],
)
const excludedHutIndices = useMemo(() => {
  const allowed = graphData ? buildQuery(form, hutsByIndex).allowedHutIndices : undefined
  if (!allowed) return new Set<number>()
  const excluded = new Set<number>()
  hutClassByIndex.forEach((_c, i) => {
    if (!allowed.has(i)) excluded.add(i)
  })
  return excluded
}, [form, hutsByIndex, hutClassByIndex, graphData])
```

Update the two render call sites:

```tsx
<TourList
  result={result}
  displayedChains={displayedChains}
  pageChains={pageChains}
  page={page}
  pageCount={pageCount}
  setPage={setPage}
  sortKey={sortKey}
  setSortKey={setSortKey}
  hutNameById={hutNameById}
  hutClassByIndex={hutClassByIndex}
  startLabel={startLabel}
  expandedChain={expandedChain}
  setExpandedChain={setExpandedChain}
/>
```

```tsx
<ResultsMap
  selectedChain={selectedChain}
  hutNameById={hutNameById}
  hutCoordsById={hutCoordsById}
  startById={startById}
  hutClassByIndex={hutClassByIndex}
  excludedHutIndices={excludedHutIndices}
/>
```

- [ ] **Step 11: Add the mode-specific village empty state to `TourList`**

In `huts/src/tourSearchPage/TourList.tsx`, the empty-results block currently only shows the
generic message + kill-counter guidance. `TourList` doesn't know the current `mode` today — thread
it through as one more prop from `TourSearchPage.tsx` (`mode: TourMode`), and render
`VILLAGE_EMPTY_STATE_HINT` (Task 7) as an extra line when `mode === 'village'`:

```ts
import { PAGE_SIZE, SORT_LABEL, VILLAGE_EMPTY_STATE_HINT, killCounterGuidance, legWaypointLabels, type SortKey } from './helpers.js'
```

Add `mode: TourMode` to the props type (import `TourMode` from `'../tourSearch/types.js'`), and in
the empty-state block:

```tsx
{displayedChains.length === 0 && (
  <Box>
    <Typography>Keine Touren gefunden. Filter lockern und erneut versuchen.</Typography>
    {mode === 'village' && (
      <Alert severity="info" sx={{ mt: 1 }}>
        {VILLAGE_EMPTY_STATE_HINT}
      </Alert>
    )}
    {killCounterGuidance(result.killCounters).map((msg, i) => (
      <Alert key={i} severity="info" sx={{ mt: 1 }}>
        {msg}
      </Alert>
    ))}
  </Box>
)}
```

Pass `mode={form.mode}` from `TourSearchPage.tsx`'s `<TourList ... />` call site, and update the
`TourList.test.tsx` fixture render call to include `mode="transit"`.

- [ ] **Step 12: Run the full test suite, typecheck, lint**

Run: `cd huts && npm test && npm run typecheck && npm run lint`
Expected: all pass.

- [ ] **Step 13: Commit**

```bash
git add huts/src/tourSearchPage/TourList.tsx huts/src/tourSearchPage/TourList.test.tsx \
        huts/src/tourSearchPage/ResultsMap.tsx huts/src/tourSearchPage/ResultsMap.test.tsx \
        huts/src/tourSearchPage/TourSearchPage.tsx
git commit -m "feat(huts): render hut class badges, marker colours, dimmed overview and legend in TourSearchPage"
```

---

## Task 10: `GraphPage.tsx` — class data, partner markers, dim-only checkbox group

**Files:**
- Modify: `huts/src/GraphPage.tsx`
- Test: create `huts/src/GraphPage.test.tsx`

**Interfaces:**
- Consumes: `HutClass`, `hutClassLabel`, `hutClassBadge`, `OPERATOR_COLOR`, `PARTNER_COLOR`,
  `PARTNER_LABEL`, `OPERATOR_LABEL` (Task 2).
- Produces: nothing downstream — leaf page.

- [ ] **Step 1: Write the failing tests**

Create `huts/src/GraphPage.test.tsx`:

```tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, waitFor, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import '@testing-library/jest-dom/vitest'
import GraphPage from './GraphPage.js'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function fetchJsonMock(body: unknown) {
  return Promise.resolve({ json: () => Promise.resolve(body) } as Response)
}

function stubFetch() {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      if (url.includes('hut-edge-stats.json')) return fetchJsonMock([])
      if (url.includes('hut-edge-geometry.json')) return fetchJsonMock({ point_counts: [] })
      if (url.includes('hut-edge-geometry.bin')) return Promise.resolve({ arrayBuffer: () => Promise.resolve(new ArrayBuffer(0)) } as unknown as Response)
      if (url.includes('huts.geojson')) {
        return fetchJsonMock({
          type: 'FeatureCollection',
          features: [
            { properties: { id: 1, name: 'AV Hut', hutType: 'av', serviced: true }, geometry: { type: 'Point', coordinates: [11.0, 47.0] } },
            { properties: { id: 2, name: 'Sonstige SV Hut', hutType: 'sonstige', serviced: false }, geometry: { type: 'Point', coordinates: [11.1, 47.1] } },
          ],
        })
      }
      if (url.includes('partner_betriebe.geojson')) {
        return fetchJsonMock({
          type: 'FeatureCollection',
          features: [{ properties: { id: 30, name: 'FeWo Test' }, geometry: { type: 'Point', coordinates: [11.2, 47.2] } }],
        })
      }
      throw new Error(`unexpected fetch ${url}`)
    }),
  )
}

describe('GraphPage hut classification', () => {
  it('renders a checkbox group and dims non-matching markers without hiding them', async () => {
    stubFetch()
    const { container } = render(<GraphPage />)
    await waitFor(() => expect(screen.getByText(/2 Hütten/)).toBeInTheDocument())

    const markersBefore = container.querySelectorAll('path.leaflet-interactive')
    const countBefore = markersBefore.length

    await userEvent.click(screen.getByLabelText('Sonstige Hütte'))

    const markersAfter = container.querySelectorAll('path.leaflet-interactive')
    // Dimming must not remove markers from the DOM.
    expect(markersAfter.length).toBe(countBefore)
  })

  it('a 404 on partner_betriebe.geojson still leaves the graph page usable', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.includes('hut-edge-stats.json')) return fetchJsonMock([])
        if (url.includes('hut-edge-geometry.json')) return fetchJsonMock({ point_counts: [] })
        if (url.includes('hut-edge-geometry.bin')) return Promise.resolve({ arrayBuffer: () => Promise.resolve(new ArrayBuffer(0)) } as unknown as Response)
        if (url.includes('huts.geojson')) return fetchJsonMock({ type: 'FeatureCollection', features: [] })
        if (url.includes('partner_betriebe.geojson')) return Promise.reject(new Error('404'))
        throw new Error(`unexpected fetch ${url}`)
      }),
    )
    render(<GraphPage />)
    await waitFor(() => expect(screen.getByText(/0 Hütten/)).toBeInTheDocument())
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd huts && npx vitest run src/GraphPage.test.tsx`
Expected: FAIL — no "Sonstige Hütte" checkbox exists yet, and there's no partner fetch (second
test currently passes trivially since nothing fetches the URL, but add it now so it's meaningful
once the fetch is added in Step 3).

- [ ] **Step 3: Implement**

In `huts/src/GraphPage.tsx`, add imports:

```ts
import { useState as useStateAlias } from 'react' // not needed - useState already imported; keep single import line
```

(Skip the above — `useState` is already imported at the top; just extend the existing import line
usage.) Add:

```ts
import { hutClassBadge, hutClassLabel, OPERATOR_COLOR, OPERATOR_LABEL, PARTNER_COLOR, PARTNER_LABEL, type HutClass, type HutOperator } from './hutClass.js'
```

Add the partner URL constant next to the existing ones:

```ts
const PARTNER_URL = '/data/partner_betriebe.geojson'
```

Widen the `Hut` interface:

```ts
interface Hut {
  id: number
  name: string
  lat: number
  lng: number
  hutClass: HutClass | null
}

interface PartnerPoint {
  id: number
  name: string
  lat: number
  lng: number
}
```

Add filter state:

```ts
const [allowedOperators, setAllowedOperators] = useState<Set<HutOperator>>(new Set(['av', 'sonstige']))
const [showServiced, setShowServiced] = useState(true)
const [showSelfService, setShowSelfService] = useState(true)
const [showPartner, setShowPartner] = useState(true)
const [partners, setPartners] = useState<PartnerPoint[]>([])
```

Update the load effect: add the partner fetch (own `.catch`) to the existing `Promise.all`, and
read `hutType`/`serviced` when building `huts`:

```ts
useEffect(() => {
  Promise.all([
    fetch(EDGE_STATS_URL).then((r) => r.json()) as Promise<EdgeStatsEntry[]>,
    fetch(EDGE_GEOMETRY_MANIFEST_URL).then((r) => r.json()) as Promise<EdgeGeometryManifest>,
    fetch(EDGE_GEOMETRY_BIN_URL).then((r) => r.arrayBuffer()),
    fetch(HUTS_URL).then((r) => r.json()) as Promise<GeoJSON.FeatureCollection>,
    fetch(PARTNER_URL)
      .then((r) => r.json() as Promise<GeoJSON.FeatureCollection>)
      .catch(() => ({ type: 'FeatureCollection', features: [] }) as GeoJSON.FeatureCollection),
  ])
    .then(([edgeStats, geometryManifest, geometryBuffer, hutsFc, partnerFc]) => {
      const perEdgePositions = decodeEdgeGeometry(geometryManifest, geometryBuffer)
      setEdges(
        edgeStats.map((s, i) => {
          const positions = perEdgePositions[i]
          return {
            fromId: s.from_hut_id,
            toId: s.to_hut_id,
            distanceM: s.distance_m,
            roadM: s.road_m,
            ascentM: s.ascent_m,
            descentM: s.descent_m,
            elevationProfile: s.elevation_profile,
            sacScale: s.sac_scale,
            viaFerrata: s.via_ferrata,
            positions,
            bounds: L.latLngBounds(positions),
          }
        })
      )
      setHuts(
        hutsFc.features.map((f) => {
          const props = f.properties as { id: number; name: string; hutType?: string; serviced?: boolean }
          const hutClass: HutClass | null =
            props.hutType === 'av' || props.hutType === 'sonstige'
              ? { operator: props.hutType, serviced: props.serviced ?? true }
              : null
          return {
            id: props.id,
            name: props.name,
            lat: (f.geometry as GeoJSON.Point).coordinates[1],
            lng: (f.geometry as GeoJSON.Point).coordinates[0],
            hutClass,
          }
        })
      )
      setPartners(
        partnerFc.features.map((f) => {
          const props = f.properties as { id: number; name: string }
          const [lng, lat] = (f.geometry as GeoJSON.Point).coordinates
          return { id: props.id, name: props.name, lat, lng }
        })
      )
    })
    .catch((e: Error) => setError(e.message))
}, [])
```

Add a `matchesFilter` helper and the checkbox controls in the `status` `Box` (alongside the
existing `showTrails` `Switch`):

```ts
function matchesFilter(hut: Hut): boolean {
  if (!hut.hutClass) return true // unclassified data (shouldn't happen post §Data-reality-check) is never dimmed away
  if (!allowedOperators.has(hut.hutClass.operator)) return false
  return hut.hutClass.serviced ? showServiced : showSelfService
}
```

In the JSX status bar (extend the existing `Box` at line 335–346):

```tsx
<Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
  <span>
    {error
      ? `Fehler: ${error}`
      : `${huts.length} Hütten, ${edges.length} Kanten (${connectedIds.size} verbunden)`}
  </span>
  <FormControlLabel
    control={<Switch size="small" checked={showTrails} onChange={(e) => setShowTrails(e.target.checked)} />}
    label="OSM-Wege (roh)"
    sx={{ color: 'inherit', m: 0 }}
  />
  {(Object.keys(OPERATOR_LABEL) as HutOperator[]).map((op) => (
    <FormControlLabel
      key={op}
      control={
        <Switch
          size="small"
          checked={allowedOperators.has(op)}
          onChange={(e) =>
            setAllowedOperators((prev) => {
              const next = new Set(prev)
              if (e.target.checked) next.add(op)
              else next.delete(op)
              return next
            })
          }
        />
      }
      label={OPERATOR_LABEL[op]}
      sx={{ color: 'inherit', m: 0 }}
    />
  ))}
  <FormControlLabel
    control={<Switch size="small" checked={showServiced} onChange={(e) => setShowServiced(e.target.checked)} />}
    label="Bewirtschaftet"
    sx={{ color: 'inherit', m: 0 }}
  />
  <FormControlLabel
    control={<Switch size="small" checked={showSelfService} onChange={(e) => setShowSelfService(e.target.checked)} />}
    label="Selbstversorger"
    sx={{ color: 'inherit', m: 0 }}
  />
  <FormControlLabel
    control={<Switch size="small" checked={showPartner} onChange={(e) => setShowPartner(e.target.checked)} />}
    label={PARTNER_LABEL}
    sx={{ color: 'inherit', m: 0 }}
  />
</Box>
```

Replace the hut `CircleMarker` block (was lines 365–380) so category drives `fillColor` and the
dim state, while snapped/unsnapped stays on stroke `color`/`radius`:

```tsx
{huts.map((hut) => {
  const dim = !matchesFilter(hut)
  const connected = connectedIds.has(hut.id)
  const baseFill = hut.hutClass ? OPERATOR_COLOR[hut.hutClass.operator] : '#43a047'
  return (
    <CircleMarker
      key={hut.id}
      center={[hut.lat, hut.lng]}
      radius={connected ? 4 : 3}
      pathOptions={{
        color: connected ? '#1b5e20' : '#616161',
        fillColor: baseFill,
        fillOpacity: dim ? 0.15 : hut.hutClass?.serviced === false ? 0.4 : 0.9,
        weight: connected ? 1 : 1,
      }}
    >
      <Tooltip direction="top" offset={[0, -6]}>
        {hut.name}
        {hut.hutClass ? ` — ${hutClassLabel(hut.hutClass)} (${hutClassBadge(hut.hutClass)})` : ''}
      </Tooltip>
    </CircleMarker>
  )
})}
```

Add partner markers right after the hut markers, gated only by the `showPartner` switch (partner
points are not huts, so they're outside the operator/servicing filter entirely per the spec's
scope):

```tsx
{showPartner &&
  partners.map((p) => (
    <CircleMarker
      key={`partner-${p.id}`}
      center={[p.lat, p.lng]}
      radius={4}
      pathOptions={{ color: PARTNER_COLOR, fillColor: PARTNER_COLOR, fillOpacity: 0.9, weight: 1 }}
    >
      <Tooltip direction="top" offset={[0, -6]}>
        {p.name} ({PARTNER_LABEL})
      </Tooltip>
    </CircleMarker>
  ))}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd huts && npx vitest run src/GraphPage.test.tsx`
Expected: PASS.

- [ ] **Step 5: Run the full suite, typecheck, lint**

Run: `cd huts && npm test && npm run typecheck && npm run lint`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add huts/src/GraphPage.tsx huts/src/GraphPage.test.tsx
git commit -m "feat(huts): show hut class and Partnerbetrieb points in GraphPage, dim non-matching markers"
```

---

## Task 11: Full-suite verification

**Files:** none (verification only).

- [ ] **Step 1: Run the full test suite**

```bash
cd huts && npm test
```

Expected: all tests pass, including every test added in Tasks 2–10.

- [ ] **Step 2: Typecheck**

```bash
cd huts && npm run typecheck
```

Expected: no errors.

- [ ] **Step 3: Lint**

```bash
cd huts && npm run lint
```

Expected: no errors.

- [ ] **Step 4: Spec coverage sanity pass**

Confirm each spec section has a corresponding task: §0 → Task 3, §1 → Tasks 1 & 8 & 10, §2 →
Task 2, §3 → Task 10, §4 → Tasks 4, 5, 6, 8, §5 → Task 4, §6 → Task 9, §7 → tests embedded in
every task above. No further action needed if the mapping holds; otherwise file the gap.

---

## Self-Review Notes (completed during plan authoring)

- **Spec coverage:** every numbered section (§0–§7) maps to at least one task above; the two
  Non-goals (`App.jsx`, pipeline compute) are explicitly not touched by any task; the three
  Follow-ups are explicitly out of scope for this plan.
- **Placeholder scan:** no TBD/TODO markers; every step carries literal, complete code.
- **Type consistency check performed:**
  - `HutClass`/`HutOperator` defined once in Task 2, imported identically (`../hutClass.js`) by
    Tasks 6, 8, 9, 10 — no divergent local re-declarations.
  - `buildQuery`'s signature changes from `(form)` to `(form, hutsByIndex)` in Task 6 and is used
    consistently with the two-argument form from Task 8 onward.
  - `SearchResult['killCounters']` gains `hutFiltered` in Task 4; every test fixture constructed
    after Task 4 (Tasks 8, 9) includes it so TypeScript's structural check doesn't fail.
  - `TourList`'s prop list gains `hutClassByIndex` (Task 9 Step 3) and `mode` (Task 9 Step 11) —
    both additions are reflected in every `<TourList .../>` call site touched by this plan
    (`TourSearchPage.tsx` in Task 9 Steps 10–11, `TourList.test.tsx` in Task 9 Steps 1 and 11).
  - `ResultsMap`'s prop list gains `hutClassByIndex` and `excludedHutIndices` (Task 9 Step 7) —
    reflected in `TourSearchPage.tsx` (Task 9 Step 10) and all four `ResultsMap.test.tsx` render
    call sites (Task 9 Steps 5 and 8).
