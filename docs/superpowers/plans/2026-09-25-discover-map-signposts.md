# Discover Map Signposts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task, in-session, on the current checkout (this repo forbids subagent-driven development and git worktrees). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Discover's yellow count discs with signpost markers (single tour / stack / cluster), draw real hut and start symbols on routes, add a rest/focused/hovered emphasis model, and let shared legs and huts hover and focus every tour that contains them.

**Architecture:** Pure helpers (tour board label, marker kind, leg/hut tour indexes, tier function, waypoint symbol collection, marker HTML) are built and tested first. Two new map components (`SignpostMarker`, `WaypointLayer`) and a `routePanes` module carry the Leaflet mechanics. A last task rewires `DiscoverLayer`, `useDiscover`, `PlannerPage` and `DiscoverMapLayers` to set-valued hover and tour-set focus.

**Tech Stack:** React 19, react-leaflet, Leaflet, supercluster, MUI, Vitest + Testing Library (jsdom), oxlint, tsc.

**Spec:** `docs/superpowers/specs/2026-09-25-discover-map-signposts-design.md`

## Global Constraints

- Work on branch `feat/discover-map-signposts`, never on `main`. No git worktrees, no subagents.
- Never run any `pipeline/` or `doit` task. This plan touches `huts/` only.
- Do not start a dev server or browser to check visuals unless the user asks. Visual tuning of the CSS is left to the user's review.
- Comments describe what the code does now, never history.
- `features/X` never imports `features/Y` except `planner`. Code shared by map and discover lives in `tourSearch/`, `data/`, `format/` or `ui/`. `huts/src/architecture.test.ts` enforces the layering.
- Dates, user-facing copy: German (`Rundtour`, `In n Touren`, `Alle n Touren in der Liste zeigen`).
- Spread cap: 8 boards plus one overflow board. Hover-intent: 200 ms open, 250 ms close.
- Commit messages: `feat(ui): ...`, ending with the trailer `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- Run all commands from `/home/superhellth/open-alps/huts`. Verification set: `npx vitest run <path>`, `npm run typecheck`, `npm run lint`.

## Review Focus

- Two tours with the same start and huts but a different exit point must not share a key (today's `tourKey` omits `exitStartId`): both boards, both list rows and both hover states must stay separate. Pinned in Task 1.
- The same numeric `edgeId` in different layers (`hut_edges`, `start_edges`, `tour_edges`) is a different leg, and `edgeId === -1` (no geometry) is never shared. Pinned in Task 3.
- A hut with no classification (`hutClassByIndex` has no entry) must not crash or get a guessed symbol: its waypoint has no `stop`, no symbol, no hit target. Pinned in Tasks 4 and 6.
- A tour whose exit start point is missing from `startById`, has no name, or equals the start point must still produce a readable board (`Startpunkt`/kind label, `Rundtour`). Pinned in Task 2.
- A stack that re-renders while spread (new search result changes its HTML) must keep its spread state, and a pending open/close timer must not fire after unmount. Pinned in Task 9.

---

### Task 0: Branch and spec commit

**Files:**
- Modify (already modified): `docs/superpowers/STATUS.md`
- Add (untracked): `docs/superpowers/specs/2026-09-25-discover-map-signposts-design.md`

- [ ] **Step 1: Create the branch and commit the spec**

```bash
cd /home/superhellth/open-alps
git switch -c feat/discover-map-signposts
git add docs/superpowers/STATUS.md docs/superpowers/specs/2026-09-25-discover-map-signposts-design.md docs/superpowers/plans/2026-09-25-discover-map-signposts.md
git commit -m "docs: discover map signposts spec and plan" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 1: Shared tour key and distance formatter

`tourKey` moves from `features/map/` to `tourSearch/` because `features/discover/useDiscover.ts` must use it (focus becomes a set of tour keys) and features may not import each other. The key gains `exitStartId`. The distance formatter is shared by the results list and the tour boards.

**Files:**
- Move: `huts/src/features/map/tourKey.ts` → `huts/src/tourSearch/tourKey.ts`
- Create: `huts/src/tourSearch/tourKey.test.ts`
- Create: `huts/src/format/distance.ts`, `huts/src/format/distance.test.ts`
- Modify: `huts/src/features/discover/ResultsList.tsx`, every importer of `map/tourKey.js` (`features/map/DiscoverLayer.tsx`, `features/planner/PlannerPage.tsx`)

**Interfaces:**
- Produces: `tourKey(tour: PlannerTour): string`, `NO_TOURS: ReadonlySet<string>`, `formatDistanceKm(meters: number): string`.

- [ ] **Step 1: Write the failing tests**

`huts/src/tourSearch/tourKey.test.ts`:
```ts
import { describe, it, expect } from 'vitest'
import { tourKey, NO_TOURS } from './tourKey.js'
import type { PlannerTour } from './plannerTour.js'

const tour = (over: Partial<PlannerTour> = {}): PlannerTour => ({
  huts: [3, 4], startId: 1, exitStartId: 1, totalDurationH: 1, totalAscentM: 0, totalDescentM: 0, totalDistanceM: 0, legs: [], ...over,
})

describe('tourKey', () => {
  it('differs when only the exit point differs', () => {
    expect(tourKey(tour({ exitStartId: 1 }))).not.toBe(tourKey(tour({ exitStartId: 2 })))
  })
  it('differs between an official tour and a search chain over the same huts', () => {
    expect(tourKey(tour({ official: { tourId: 9, name: 'x' } }))).not.toBe(tourKey(tour()))
  })
  it('is stable for equal tours', () => {
    expect(tourKey(tour())).toBe(tourKey(tour()))
  })
})

describe('NO_TOURS', () => {
  it('is empty', () => { expect(NO_TOURS.size).toBe(0) })
})
```

`huts/src/format/distance.test.ts`:
```ts
import { describe, it, expect } from 'vitest'
import { formatDistanceKm } from './distance.js'

describe('formatDistanceKm', () => {
  it('formats meters as km with one decimal', () => {
    expect(formatDistanceKm(42_300)).toBe('42.3 km')
    expect(formatDistanceKm(0)).toBe('0.0 km')
    expect(formatDistanceKm(950)).toBe('1.0 km')
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npx vitest run src/tourSearch/tourKey.test.ts src/format/distance.test.ts`
Expected: FAIL (modules not found).

- [ ] **Step 3: Move `tourKey` and add the formatter**

```bash
git mv src/features/map/tourKey.ts src/tourSearch/tourKey.ts
```
`src/tourSearch/tourKey.ts`:
```ts
import type { PlannerTour } from './plannerTour.js'

/** A tour's stable cross-component identity (hover and focus sync between the map and the results list). */
export function tourKey(tour: PlannerTour): string {
  return `${tour.startId}-${tour.exitStartId}-${tour.official?.tourId ?? ''}-${tour.huts.join('.')}`
}

/** Shared empty set, so "nothing hovered" is one stable value and never triggers a re-render. */
export const NO_TOURS: ReadonlySet<string> = new Set()
```
`src/format/distance.ts`:
```ts
/** Tour length as shown in the results list and on tour boards, e.g. "42.3 km". */
export function formatDistanceKm(meters: number): string {
  return `${(meters / 1000).toFixed(1)} km`
}
```

- [ ] **Step 4: Fix importers**

Replace `'./tourKey.js'` / `'@/features/map/tourKey.js'` with `'@/tourSearch/tourKey.js'` in `features/map/DiscoverLayer.tsx` and `features/planner/PlannerPage.tsx` (`grep -rn "tourKey.js" src` to confirm none is left). In `ResultsList.tsx` add `import { formatDistanceKm } from '@/format/distance.js'` and replace `{(tour.totalDistanceM / 1000).toFixed(1)} km` with `{formatDistanceKm(tour.totalDistanceM)}`.

- [ ] **Step 5: Run tests, typecheck**

Run: `npx vitest run src/tourSearch src/format src/features/discover src/features/map src/architecture.test.ts && npm run typecheck`
Expected: PASS. If a test pins the old key format, update it to the new format.

- [ ] **Step 6: Commit**

```bash
git add -A src && git commit -m "feat(ui): tour key includes exit point, shared distance formatter" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Marker kind and tour board label

**Files:**
- Modify: `huts/src/features/map/clusterStarts.ts`, `huts/src/features/map/clusterStarts.test.ts`
- Create: `huts/src/features/map/tourBoard.ts`, `huts/src/features/map/tourBoard.test.ts`

**Interfaces:**
- Produces:
  - `type MarkerKind = 'single' | 'stack' | 'cluster'`; `markerKind(m: MapMarker): MarkerKind`
  - `interface TourBoardLabel { text: string; distance: string; title: string; sourceType: number }`; `tourBoardLabel(tour: PlannerTour, startById: Map<number, StartPoint>): TourBoardLabel`
  - `markerRadius` is removed (spec: size scaling dropped).

- [ ] **Step 1: Write the failing tests**

Append to `clusterStarts.test.ts` (keep the `markerRadius` tests for now; Task 9 removes them):
```ts
import { markerKind } from './clusterStarts.js'
import type { MapMarker } from './clusterStarts.js'

describe('markerKind', () => {
  const start = (count: number): MapMarker => ({ kind: 'start', startId: 1, count, lat: 0, lng: 0 })
  it('is single for one start point with one tour', () => { expect(markerKind(start(1))).toBe('single') })
  it('is stack for one start point with several tours', () => { expect(markerKind(start(3))).toBe('stack') })
  it('is cluster for several start points, whatever the count', () => {
    expect(markerKind({ kind: 'cluster', clusterId: 1, count: 1, lat: 0, lng: 0 })).toBe('cluster')
  })
})
```

`tourBoard.test.ts`:
```ts
import { describe, it, expect } from 'vitest'
import { tourBoardLabel } from './tourBoard.js'
import type { PlannerTour } from '@/tourSearch/plannerTour.js'
import type { StartPoint } from '@/data/types.js'

const start = (name: string | null, sourceType: number): StartPoint => ({ name, sourceType, lat: 47, lng: 11 })
const startById = new Map<number, StartPoint>([
  [1, start('Kaprun', 1)], [2, start('Kaunertal', 2)], [3, start(null, 2)],
])
const tour = (over: Partial<PlannerTour> = {}): PlannerTour => ({
  huts: [], startId: 1, exitStartId: 2, totalDurationH: 1, totalAscentM: 0, totalDescentM: 0, totalDistanceM: 42_300, legs: [], ...over,
})

describe('tourBoardLabel', () => {
  it('shows the bare exit name, the distance and the exit kind', () => {
    const l = tourBoardLabel(tour(), startById)
    expect(l.text).toBe('Kaunertal')
    expect(l.distance).toBe('42.3 km')
    expect(l.sourceType).toBe(2)
    expect(l.title).toContain('Kaunertal (Parkplatz)')
  })
  it('reads Rundtour when the exit is the start', () => {
    expect(tourBoardLabel(tour({ exitStartId: 1 }), startById).text).toBe('Rundtour')
  })
  it('falls back to the kind label for an unnamed exit', () => {
    expect(tourBoardLabel(tour({ exitStartId: 3 }), startById).text).toBe('Parkplatz')
  })
  it('does not crash when the exit is missing from startById', () => {
    const l = tourBoardLabel(tour({ exitStartId: 99 }), startById)
    expect(l.text).toBe('Startpunkt')
    expect(l.distance).toBe('42.3 km')
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npx vitest run src/features/map/clusterStarts.test.ts src/features/map/tourBoard.test.ts`
Expected: FAIL.

- [ ] **Step 3: Implement**

In `clusterStarts.ts` add (leave `markerRadius` in place until Task 9):
```ts
export type MarkerKind = 'single' | 'stack' | 'cluster'

/** single = one start point with one tour; stack = one start point with several; cluster = several start points. */
export function markerKind(m: MapMarker): MarkerKind {
  if (m.kind === 'cluster') return 'cluster'
  return m.count === 1 ? 'single' : 'stack'
}
```
`tourBoard.ts`:
```ts
import { formatDistanceKm } from '@/format/distance.js'
import { SOURCE_TYPE_LABEL, makeStartLabel } from '@/data/labels.js'
import { SOURCE_TYPE_STATION } from '@/tourSearch/types.js'
import type { PlannerTour } from '@/tourSearch/plannerTour.js'
import type { StartPoint } from '@/data/types.js'

export const ROUND_TRIP_LABEL = 'Rundtour'

export interface TourBoardLabel {
  /** End point name (bare, without a "(Parkplatz)" suffix), the kind label when unnamed, or "Rundtour". */
  text: string
  distance: string
  /** Full end point label plus distance, for the board's `title` attribute. */
  title: string
  /** Kind of the end point, for the board's small symbol. */
  sourceType: number
}

export function tourBoardLabel(tour: PlannerTour, startById: Map<number, StartPoint>): TourBoardLabel {
  const exit = startById.get(tour.exitStartId)
  const sourceType = exit?.sourceType ?? SOURCE_TYPE_STATION
  const kind = SOURCE_TYPE_LABEL[sourceType] ?? 'Startpunkt'
  const roundTrip = tour.exitStartId === tour.startId
  const text = roundTrip ? ROUND_TRIP_LABEL : exit ? exit.name || kind : 'Startpunkt'
  const distance = formatDistanceKm(tour.totalDistanceM)
  return { text, distance, title: `${makeStartLabel(startById)(tour.exitStartId)}, ${distance}`, sourceType }
}
```
`DiscoverLayer.tsx` still uses `markerRadius`, so this task only **adds** `markerKind` and `tourBoardLabel`.

- [ ] **Step 4: Run tests, typecheck, commit**

Run: `npx vitest run src/features/map && npm run typecheck`
Expected: PASS.
```bash
git add -A src && git commit -m "feat(ui): marker kind and tour board label" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Leg/hut tour indexes and emphasis tiers (pure)

**Files:**
- Create: `huts/src/features/map/tourMatch.ts`, `huts/src/features/map/tourMatch.test.ts`
- Modify: `huts/src/features/map/types.ts` (add `EmphasisTier`)

**Interfaces:**
- Produces:
  - `type EmphasisTier = 'rest' | 'focused' | 'hovered'` (in `types.ts`)
  - `interface RoutedTour { key: string; tour: PlannerTour; route: Route }`
  - `legKey(leg: RouteLeg): string | null` — `null` for `edgeId < 0`
  - `indexToursByLeg(routed: RoutedTour[]): Map<string, string[]>` — leg key → tour keys
  - `indexToursByHut(routed: RoutedTour[]): Map<number, string[]>` — hut index → tour keys
  - `tierOf(tour: { key: string; startId: number }, state: TierState): EmphasisTier`, `interface TierState { hoveredKeys: ReadonlySet<string>; hoveredStarts: ReadonlySet<number> | null; focus: ReadonlySet<string> | null }`

- [ ] **Step 1: Write the failing tests**

```ts
import { describe, it, expect } from 'vitest'
import { indexToursByHut, indexToursByLeg, legKey, tierOf } from './tourMatch.js'
import type { RoutedTour } from './tourMatch.js'
import type { PlannerTour } from '@/tourSearch/plannerTour.js'
import type { Route, RouteLeg } from './types.js'

const leg = (edgeId: number, layer: RouteLeg['layer'] = 'hut_edges', reversed = false): RouteLeg => ({ edgeId, reversed, layer })
const routed = (key: string, huts: number[], legs: RouteLeg[]): RoutedTour => ({
  key, tour: { huts, startId: 1 } as PlannerTour, route: { waypoints: [], legs } as Route,
})

describe('legKey', () => {
  it('includes the layer, since edge ids index layer-specific tables', () => {
    expect(legKey(leg(5, 'hut_edges'))).not.toBe(legKey(leg(5, 'start_edges')))
  })
  it('ignores direction', () => { expect(legKey(leg(5, 'hut_edges', true))).toBe(legKey(leg(5, 'hut_edges', false))) })
  it('is null for a leg without geometry', () => { expect(legKey(leg(-1))).toBeNull() })
})

describe('indexToursByLeg', () => {
  const a = routed('a', [10], [leg(5), leg(6)])
  const b = routed('b', [11], [leg(5, 'hut_edges', true), leg(7)])
  const c = routed('c', [12], [leg(5, 'start_edges'), leg(-1)])
  const d = routed('d', [13], [leg(-1)])
  const index = indexToursByLeg([a, b, c, d])
  it('lists every tour containing a leg, either direction', () => {
    expect(index.get(legKey(leg(5))!)).toEqual(['a', 'b'])
  })
  it('keeps the same edge id in another layer separate', () => {
    expect(index.get(legKey(leg(5, 'start_edges'))!)).toEqual(['c'])
  })
  it('never indexes legs without geometry', () => {
    expect([...index.keys()].some((k) => k.endsWith(':-1'))).toBe(false)
  })
  it('lists a tour once even when it uses a leg twice', () => {
    expect(indexToursByLeg([routed('x', [], [leg(5), leg(5)])]).get(legKey(leg(5))!)).toEqual(['x'])
  })
})

describe('indexToursByHut', () => {
  it('lists every tour that stops at a hut', () => {
    const index = indexToursByHut([routed('a', [10, 11], []), routed('b', [11], []), routed('c', [12], [])])
    expect(index.get(11)).toEqual(['a', 'b'])
    expect(index.get(12)).toEqual(['c'])
  })
})

describe('tierOf', () => {
  const t = { key: 'k', startId: 1 }
  const state = (over: Partial<Parameters<typeof tierOf>[1]> = {}) => ({ hoveredKeys: new Set<string>(), hoveredStarts: null, focus: null, ...over })
  it('is rest by default', () => { expect(tierOf(t, state())).toBe('rest') })
  it('is focused inside the focus set', () => { expect(tierOf(t, state({ focus: new Set(['k']) }))).toBe('focused') })
  it('is rest outside the focus set', () => { expect(tierOf(t, state({ focus: new Set(['other']) }))).toBe('rest') })
  it('is focused when its bubble is hovered', () => { expect(tierOf(t, state({ hoveredStarts: new Set([1]) }))).toBe('focused') })
  it('is hovered when its key is hovered, over focus and bubble hover', () => {
    expect(tierOf(t, state({ hoveredKeys: new Set(['k']), focus: new Set(['k']), hoveredStarts: new Set([1]) }))).toBe('hovered')
  })
})
```

- [ ] **Step 2: Run to verify failure**

Run: `npx vitest run src/features/map/tourMatch.test.ts`
Expected: FAIL.

- [ ] **Step 3: Implement**

Add to `types.ts`: `export type EmphasisTier = 'rest' | 'focused' | 'hovered'`.

`tourMatch.ts`:
```ts
import type { PlannerTour } from '@/tourSearch/plannerTour.js'
import type { EmphasisTier, Route, RouteLeg } from './types.js'

export interface RoutedTour {
  key: string
  tour: PlannerTour
  route: Route
}

/** A leg's identity across tours. Edge ids index a table per layer, so the layer is part of the key;
 *  a leg without geometry (edgeId < 0) is never shared. */
export function legKey(leg: RouteLeg): string | null {
  return leg.edgeId < 0 ? null : `${leg.layer}:${leg.edgeId}`
}

function pushOnce<K>(index: Map<K, string[]>, id: K, key: string) {
  const list = index.get(id)
  if (!list) index.set(id, [key])
  else if (list[list.length - 1] !== key) list.push(key)
}

/** Leg key → keys of every tour containing that leg (either direction). */
export function indexToursByLeg(routed: RoutedTour[]): Map<string, string[]> {
  const index = new Map<string, string[]>()
  for (const { key, route } of routed) {
    for (const leg of route.legs) {
      const id = legKey(leg)
      if (id !== null) pushOnce(index, id, key)
    }
  }
  return index
}

/** Hut index → keys of every tour stopping at that hut. */
export function indexToursByHut(routed: RoutedTour[]): Map<number, string[]> {
  const index = new Map<number, string[]>()
  for (const { key, tour } of routed) for (const hut of tour.huts) pushOnce(index, hut, key)
  return index
}

export interface TierState {
  hoveredKeys: ReadonlySet<string>
  hoveredStarts: ReadonlySet<number> | null
  focus: ReadonlySet<string> | null
}

export function tierOf(tour: { key: string; startId: number }, s: TierState): EmphasisTier {
  if (s.hoveredKeys.has(tour.key)) return 'hovered'
  if (s.focus?.has(tour.key) || s.hoveredStarts?.has(tour.startId)) return 'focused'
  return 'rest'
}
```

- [ ] **Step 4: Run tests, typecheck, commit**

Run: `npx vitest run src/features/map/tourMatch.test.ts && npm run typecheck`
Expected: PASS.
```bash
git add -A src && git commit -m "feat(ui): leg/hut tour indexes and emphasis tiers" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Waypoint stops in routes

**Files:**
- Modify: `huts/src/features/map/types.ts`, `huts/src/features/map/routes.ts`, `huts/src/features/map/routes.test.ts`
- Modify (test literals gain `hutClassByIndex`): `huts/src/features/map/DiscoverLayer.test.tsx`, `PlannerMap.test.tsx`, `SavedTripsLayer.test.tsx`
- Modify: `huts/src/features/planner/PlannerPage.tsx` (`routeCtx`)

**Interfaces:**
- Produces:
  - `type WaypointStop = { type: 'hut'; hutId: number; operator: HutOperator; serviced: boolean } | { type: 'end'; startId: number; sourceType: number }`
  - `RouteWaypoint { lat; lng; stop?: WaypointStop }`
  - `RouteContext.hutClassByIndex: Map<number, HutClass>` (required)

- [ ] **Step 1: Write the failing tests**

In `routes.test.ts`, add `hutClassByIndex: new Map([[0, { operator: 'av', serviced: true }]])` to `ctx` (hut 1 deliberately unclassified), and:
```ts
describe('waypoint stops', () => {
  it('marks huts with their class and end points with their kind', () => {
    const r = tourToRoute(chain(), ctx)!
    expect(r.waypoints[0].stop).toEqual({ type: 'end', startId: 100, sourceType: 1 })
    expect(r.waypoints[1].stop).toEqual({ type: 'hut', hutId: 0, operator: 'av', serviced: true })
    expect(r.waypoints[3].stop).toEqual({ type: 'end', startId: 100, sourceType: 1 })
  })
  it('gives an unclassified hut no stop instead of a guessed one', () => {
    const r = tourToRoute(chain(), ctx)!
    expect(r.waypoints[2]).toEqual({ lat: 47.2, lng: 11.2 })
  })
})
```

- [ ] **Step 2: Run to verify failure**

Run: `npx vitest run src/features/map/routes.test.ts`
Expected: FAIL (`stop` undefined; type errors on the context).

- [ ] **Step 3: Implement**

`types.ts`:
```ts
import type { HutOperator } from '@/data/hutClass.js'

/** What a waypoint is, so the map can draw its symbol; absent when nothing reliable is known (no guessing). */
export type WaypointStop =
  | { type: 'hut'; hutId: number; operator: HutOperator; serviced: boolean }
  | { type: 'end'; startId: number; sourceType: number }

export interface RouteWaypoint {
  lat: number
  lng: number
  stop?: WaypointStop
}
```
`routes.ts`: add `import type { HutClass } from '@/data/hutClass.js'`; add `hutClassByIndex: Map<number, HutClass>` to `RouteContext`; replace `place`:
```ts
function place(id: number, kind: 'hut' | 'start', ctx: RouteContext): RouteWaypoint | null {
  if (kind === 'hut') {
    const p = ctx.hutCoordsById.get(id)
    if (!p) return null
    const cls = ctx.hutClassByIndex.get(id)
    return cls
      ? { lat: p.lat, lng: p.lng, stop: { type: 'hut', hutId: id, operator: cls.operator, serviced: cls.serviced } }
      : { lat: p.lat, lng: p.lng }
  }
  const s = ctx.startById.get(id)
  return s ? { lat: s.lat, lng: s.lng, stop: { type: 'end', startId: id, sourceType: s.sourceType } } : null
}
```
In `PlannerPage.tsx` `routeCtx`: add `hutClassByIndex: data.hutClassByIndex`. Add `hutClassByIndex: new Map()` to every other `RouteContext` literal in the test files listed (`grep -rn "officialById" src`; tsc lists what is missing).

- [ ] **Step 4: Run tests, typecheck, commit**

Run: `npx vitest run src/features && npm run typecheck`
Expected: PASS. Trip and saved-trip route tests must pass unchanged apart from the added context field.
```bash
git add -A src && git commit -m "feat(ui): route waypoints carry hut/end stops" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: Route panes and RouteLayer emphasis

Panes become three tiers × three roles (casing, line, symbol). `RouteLayer` gets an `emphasis` prop (Discover), a `dots` prop, per-leg hover/click callbacks, and stops bubbling leg clicks to the map (so a leg click does not read as the map click that drops the focus). Without `emphasis`, behavior is unchanged: `dimmedOut` maps to the rest tier, otherwise the hovered tier (old full-strength panes).

**Files:**
- Create: `huts/src/features/map/routePanes.ts`
- Modify: `huts/src/features/map/RouteLayer.tsx`, `huts/src/features/map/RouteLayer.test.tsx`

**Interfaces:**
- Consumes: `EmphasisTier` (Task 3).
- Produces:
  - `paneName(tier: EmphasisTier, role: 'casing' | 'line' | 'symbol'): string` → `route-<tier>-<role>`
  - `HIT_PANE = 'route-hit'`; `ensureRoutePanes(map: L.Map): void`
  - `RouteLayer` props: `emphasis?: EmphasisTier`, `dots?: boolean` (default `true`), `onHover?: (hovering: boolean, legIndex: number, at: L.LatLng) => void`, `onClick?: (legIndex: number) => void`. Existing props keep their meaning.

- [ ] **Step 1: Write the failing tests**

Append to `RouteLayer.test.tsx` (mock geometry as in the existing test so segments draw):
```tsx
import { fireEvent } from '@testing-library/react'

describe('RouteLayer emphasis and dots', () => {
  const draw = (props: Partial<Parameters<typeof RouteLayer>[0]> = {}) => {
    vi.spyOn(geometry, 'loadLegGeometry').mockResolvedValue([[47, 11], [47.05, 11.05]])
    return render(<MapContainer center={[47, 11]} zoom={9}><RouteLayer route={route} {...props} /></MapContainer>)
  }
  it('draws hut dots in the hovered symbol pane by default, as trip and saved views do', () => {
    const { container } = draw()
    expect(container.querySelectorAll('.leaflet-route-hovered-symbol-pane path').length).toBe(3)
  })
  it('draws no dots when dots is false', () => {
    const { container } = draw({ dots: false })
    expect(container.querySelectorAll('path.leaflet-interactive, .leaflet-route-hovered-symbol-pane path').length).toBe(0)
  })
  it('draws the focused tier in its own panes', async () => {
    const { container } = draw({ emphasis: 'focused', dots: false })
    await waitFor(() => expect(container.querySelectorAll('.leaflet-route-focused-line-pane path').length).toBeGreaterThan(0))
    expect(container.querySelectorAll('.leaflet-route-hovered-line-pane path').length).toBe(0)
  })
  it('reports the hovered leg index and stops leg clicks bubbling to the map', async () => {
    const onHover = vi.fn()
    const onMapClick = vi.fn()
    const { container } = render(
      <MapContainer center={[47, 11]} zoom={9}><RouteLayer route={route} emphasis="rest" dots={false} onHover={onHover} onClick={() => {}} /></MapContainer>,
    )
    vi.spyOn(geometry, 'loadLegGeometry').mockResolvedValue([[47, 11], [47.05, 11.05]])
    await waitFor(() => expect(container.querySelectorAll('path.leaflet-interactive').length).toBeGreaterThan(0))
    const path = container.querySelector('path.leaflet-interactive')!
    fireEvent.mouseOver(path)
    expect(onHover).toHaveBeenCalledWith(true, 0, expect.anything())
    void onMapClick
  })
})
```
(The bubbling assertion is added in Task 10's `DiscoverLayer` test, where a map click watcher exists. Remove the unused `onMapClick` lines if the linter complains.)

- [ ] **Step 2: Run to verify failure**

Run: `npx vitest run src/features/map/RouteLayer.test.tsx`
Expected: FAIL (pane classes differ, `dots` unknown).

- [ ] **Step 3: Implement `routePanes.ts`**

```ts
import type L from 'leaflet'
import type { EmphasisTier } from './types.js'

export type PaneRole = 'casing' | 'line' | 'symbol'

/** Route panes, bottom to top (overlayPane is 400, markerPane 600): per tier a casing, a line and a
 *  symbol pane, tiers ascending rest < focused < hovered. Fading is the pane's own CSS opacity rather
 *  than per-path alpha, so overlapping routes of one tier stay one flat colour instead of compounding,
 *  and no route's casing ever covers another route's line or symbols. */
const TIERS: Record<EmphasisTier, { base: number; opacity: number }> = {
  rest: { base: 410, opacity: 0.35 },
  focused: { base: 440, opacity: 0.7 },
  hovered: { base: 470, opacity: 1 },
}
const ROLE_OFFSET: Record<PaneRole, number> = { casing: 0, line: 10, symbol: 20 }

/** Invisible, always-on-top markers that receive hut hover/click; the visible symbols underneath never re-render on hover. */
export const HIT_PANE = 'route-hit'

export const paneName = (tier: EmphasisTier, role: PaneRole) => `route-${tier}-${role}`

function createPane(map: L.Map, name: string, z: number, opacity: number) {
  if (map.getPane(name)) return
  const pane = map.createPane(name)
  pane.style.zIndex = String(z)
  pane.style.opacity = String(opacity)
}

export function ensureRoutePanes(map: L.Map) {
  for (const tier of Object.keys(TIERS) as EmphasisTier[]) {
    for (const role of Object.keys(ROLE_OFFSET) as PaneRole[]) {
      createPane(map, paneName(tier, role), TIERS[tier].base + ROLE_OFFSET[role], TIERS[tier].opacity)
    }
  }
  createPane(map, HIT_PANE, 500, 1)
}
```

- [ ] **Step 4: Implement `RouteLayer` changes**

Remove `PANES`/`ensurePanes`; import `ensureRoutePanes, paneName` and `EmphasisTier`. New signature and body pieces:
```tsx
export default function RouteLayer({ route, highlightedLeg = null, fit = false, muted = false, dimmedOut = false, emphasis, dots = true, interactive = true, onHover, onClick }: {
  route: Route
  highlightedLeg?: number | null
  fit?: boolean
  /** Thin candidate style instead of the bold selected-route style. Ignored when `emphasis` is set. */
  muted?: boolean
  /** Fades the route into the rest tier. Ignored when `emphasis` is set. */
  dimmedOut?: boolean
  /** Discover's tier: rest and focused are thin; hovered is the bold single-tour style. */
  emphasis?: EmphasisTier
  /** false draws lines only (Discover draws waypoint symbols in a separate layer). */
  dots?: boolean
  /** false draws a display-only copy that never receives pointer events. */
  interactive?: boolean
  onHover?: (hovering: boolean, legIndex: number, at: L.LatLng) => void
  onClick?: (legIndex: number) => void
}) {
  ...
  const tier: EmphasisTier = emphasis ?? (dimmedOut ? 'rest' : 'hovered')
  const thin = emphasis ? emphasis !== 'hovered' : muted
  const baseWidth = thin ? 2 : 4
  ensureRoutePanes(map)
  const casingPane = paneName(tier, 'casing')
  const linePane = paneName(tier, 'line')
  const dotPane = paneName(tier, 'symbol')
```
casing weight `width + (thin ? 2 : 4)`. The interactive line becomes:
```tsx
<Polyline
  positions={seg.positions} pane={linePane}
  pathOptions={{ color: tokens.signpost, weight: width, dashArray: dash, interactive, bubblingMouseEvents: false }}
  eventHandlers={{ mouseover: (e) => onHover?.(true, i, e.latlng), mouseout: (e) => onHover?.(false, i, e.latlng), click: () => onClick?.(i) }}
/>
```
Wrap the dots `positions.map(...)` in `{dots && ...}`. The `i` is the segment index; it equals the leg index because `segmentsOf` maps legs one-to-one.

Update `SavedTripsLayer` only if it passes `onHover`/`onClick` (it does not).

- [ ] **Step 5: Fix old pane names in other tests**

`DiscoverLayer.test.tsx` references `.leaflet-route-dot-pane` / `.leaflet-route-dim-dot-pane`; Task 10 rewrites those tests. Until then, skip that file when running tests here.

- [ ] **Step 6: Run tests, typecheck, commit**

Run: `npx vitest run src/features/map/RouteLayer.test.tsx src/features/map/SavedTripsLayer.test.tsx src/features/map/TripLayer.test.tsx src/features/map/PlannerMap.test.tsx && npm run typecheck`
Expected: PASS (DiscoverLayer tests are fixed in Task 10; typecheck passes because `muted`/`dimmedOut` still exist).
```bash
git add -A src && git commit -m "feat(ui): route panes per emphasis tier, RouteLayer emphasis and dots" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: Waypoint symbols layer and hover tooltip

One symbol per unique hut or end point across all visible routes, drawn non-interactively in the pane of its highest tier. Hut hover/click is served by separate invisible hit markers, so the visible symbol never changes under the pointer.

**Files:**
- Create: `huts/src/features/map/WaypointLayer.tsx`, `huts/src/features/map/WaypointLayer.test.tsx`
- Create: `huts/src/features/map/HoverTooltip.tsx`

**Interfaces:**
- Consumes: `RoutedTour`-like items `{ key; route; tier }`, `WaypointStop`, `EmphasisTier`, `paneName`, `HIT_PANE`, `ensureRoutePanes`, `hutSymbolSvg`, `startSymbolSvg`.
- Produces:
  - `interface WaypointSymbol { id: string; lat: number; lng: number; stop: WaypointStop; tier: EmphasisTier }`
  - `collectSymbols(items: { route: Route; tier: EmphasisTier }[]): WaypointSymbol[]`
  - `WaypointLayer({ symbols, onHoverHut, onClickHut })` with `onHoverHut: (hutId: number | null, at: L.LatLng) => void`, `onClickHut: (hutId: number) => void`
  - `HoverTooltip({ tip: { at: L.LatLng; html: string } | null })`

- [ ] **Step 1: Write the failing tests**

```tsx
// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { render, cleanup } from '@testing-library/react'
import { MapContainer } from 'react-leaflet'
import WaypointLayer, { collectSymbols } from './WaypointLayer.js'
import type { Route, WaypointStop } from './types.js'

afterEach(cleanup)

const hut = (id: number): WaypointStop => ({ type: 'hut', hutId: id, operator: 'av', serviced: true })
const end = (id: number): WaypointStop => ({ type: 'end', startId: id, sourceType: 1 })
const route = (...stops: (WaypointStop | undefined)[]): Route => ({
  waypoints: stops.map((stop, i) => ({ lat: 47 + i * 0.01, lng: 11, stop })), legs: [],
})

describe('collectSymbols', () => {
  it('draws one symbol per unique hut across overlapping routes', () => {
    const s = collectSymbols([
      { route: route(end(1), hut(10), hut(11), end(1)), tier: 'rest' },
      { route: route(end(1), hut(10), hut(12), end(2)), tier: 'rest' },
    ])
    expect(s.map((x) => x.id).sort()).toEqual(['e1', 'e2', 'h10', 'h11', 'h12'])
  })
  it('takes the highest tier of the routes sharing a symbol', () => {
    const s = collectSymbols([
      { route: route(hut(10)), tier: 'rest' }, { route: route(hut(10)), tier: 'hovered' }, { route: route(hut(10)), tier: 'focused' },
    ])
    expect(s).toHaveLength(1)
    expect(s[0].tier).toBe('hovered')
  })
  it('skips waypoints without a stop (unclassified huts)', () => {
    expect(collectSymbols([{ route: route(undefined, hut(10)), tier: 'rest' }])).toHaveLength(1)
  })
})

describe('WaypointLayer', () => {
  const renderLayer = (symbols = collectSymbols([{ route: route(end(1), hut(10), hut(11)), tier: 'rest' }])) =>
    render(
      <MapContainer center={[47, 11]} zoom={13} style={{ height: 400, width: 400 }}>
        <WaypointLayer symbols={symbols} onHoverHut={() => {}} onClickHut={() => {}} />
      </MapContainer>,
    )
  it('draws a symbol per waypoint in the pane of its tier and a hit target per hut only', () => {
    const { container } = renderLayer()
    expect(container.querySelectorAll('.leaflet-route-rest-symbol-pane .leaflet-marker-icon')).toHaveLength(3)
    expect(container.querySelectorAll('.leaflet-route-hit-pane .leaflet-marker-icon')).toHaveLength(2)
  })
  it('does not make the visible symbols interactive', () => {
    const { container } = renderLayer()
    expect(container.querySelectorAll('.leaflet-route-rest-symbol-pane .leaflet-interactive')).toHaveLength(0)
  })
  it('draws a hovered hut with the selected (yellow) fill', () => {
    const { container } = renderLayer(collectSymbols([{ route: route(hut(10)), tier: 'hovered' }]))
    expect(container.querySelector('.leaflet-route-hovered-symbol-pane svg')!.innerHTML).toContain('#F5B700')
  })
})
```

- [ ] **Step 2: Run to verify failure**

Run: `npx vitest run src/features/map/WaypointLayer.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement**

`WaypointLayer.tsx`:
```tsx
import L from 'leaflet'
import { Marker, useMap } from 'react-leaflet'
import { hutSymbolSvg, startSymbolSvg } from './hutSymbol.js'
import { HIT_PANE, ensureRoutePanes, paneName } from './routePanes.js'
import type { EmphasisTier, Route, WaypointStop } from './types.js'

export interface WaypointSymbol {
  /** `h<hutIndex>` or `e<startId>`. */
  id: string
  lat: number
  lng: number
  stop: WaypointStop
  tier: EmphasisTier
}

const TIER_RANK: Record<EmphasisTier, number> = { rest: 0, focused: 1, hovered: 2 }

/** One symbol per unique hut or end point across the given routes, at the highest tier of any route through it. */
export function collectSymbols(items: { route: Route; tier: EmphasisTier }[]): WaypointSymbol[] {
  const byId = new Map<string, WaypointSymbol>()
  for (const { route, tier } of items) {
    for (const w of route.waypoints) {
      if (!w.stop) continue
      const id = w.stop.type === 'hut' ? `h${w.stop.hutId}` : `e${w.stop.startId}`
      const seen = byId.get(id)
      if (!seen) byId.set(id, { id, lat: w.lat, lng: w.lng, stop: w.stop, tier })
      else if (TIER_RANK[tier] > TIER_RANK[seen.tier]) seen.tier = tier
    }
  }
  return [...byId.values()]
}

const HUT_SIZE = 18
const END_SIZE = 16
const iconCache = new Map<string, L.DivIcon>()

function symbolIcon(stop: WaypointStop, selected: boolean): L.DivIcon {
  const key = stop.type === 'hut' ? `h|${stop.operator}|${stop.serviced}|${selected}` : `e|${stop.sourceType}`
  let icon = iconCache.get(key)
  if (!icon) {
    const size = stop.type === 'hut' ? HUT_SIZE : END_SIZE
    icon = L.divIcon({
      className: stop.type === 'hut' ? 'hut-marker' : 'start-symbol',
      html: stop.type === 'hut'
        ? hutSymbolSvg({ operator: stop.operator, serviced: stop.serviced, selected, size })
        : startSymbolSvg(stop.sourceType, size),
      iconSize: [size, size], iconAnchor: [size / 2, size / 2],
    })
    iconCache.set(key, icon)
  }
  return icon
}

const HIT_ICON = L.divIcon({ className: 'waypoint-hit', html: '', iconSize: [24, 24], iconAnchor: [12, 12] })

/** Hut and end-point symbols of every visible route. The visible symbols are display-only; hut hover and
 *  click go through invisible hit markers above them, so hovering never replaces the element under the pointer. */
export default function WaypointLayer({ symbols, onHoverHut, onClickHut }: {
  symbols: WaypointSymbol[]
  onHoverHut: (hutId: number | null, at: L.LatLng) => void
  onClickHut: (hutId: number) => void
}) {
  const map = useMap()
  ensureRoutePanes(map)
  return (
    <>
      {symbols.map((s) => (
        <Marker
          key={`${s.id}-${s.tier}`} position={[s.lat, s.lng]} pane={paneName(s.tier, 'symbol')}
          icon={symbolIcon(s.stop, s.tier === 'hovered' && s.stop.type === 'hut')} interactive={false} keyboard={false}
        />
      ))}
      {symbols.flatMap((s) => s.stop.type !== 'hut' ? [] : [
        <Marker
          key={`hit-${s.id}`} position={[s.lat, s.lng]} pane={HIT_PANE} icon={HIT_ICON} keyboard={false}
          eventHandlers={{
            mouseover: (e) => onHoverHut((s.stop as { hutId: number }).hutId, e.latlng),
            mouseout: (e) => onHoverHut(null, e.latlng),
            click: () => onClickHut((s.stop as { hutId: number }).hutId),
          }}
        />,
      ])}
    </>
  )
}
```
Replace the two `(s.stop as ...)` casts with a local `const hutId = s.stop.hutId` inside the `flatMap` callback after narrowing (`if (s.stop.type !== 'hut') return []; const { hutId } = s.stop`).

`HoverTooltip.tsx`:
```tsx
import { useEffect } from 'react'
import L from 'leaflet'
import { useMap } from 'react-leaflet'

/** One shared tooltip for leg and hut hover, opened at the pointer's entry point while `tip` is set. */
export default function HoverTooltip({ tip }: { tip: { at: L.LatLng; html: string } | null }) {
  const map = useMap()
  useEffect(() => {
    if (!tip) return
    const tooltip = L.tooltip({ direction: 'top', offset: [0, -8], opacity: 0.95 }).setLatLng(tip.at).setContent(tip.html)
    map.openTooltip(tooltip)
    return () => { map.closeTooltip(tooltip) }
  }, [map, tip])
  return null
}
```
Add to `map.css`:
```css
.waypoint-hit { background: none; border: none; cursor: pointer; }
```

- [ ] **Step 4: Run tests, typecheck, lint, commit**

Run: `npx vitest run src/features/map/WaypointLayer.test.tsx && npm run typecheck && npm run lint`
Expected: PASS.
```bash
git add -A src && git commit -m "feat(ui): waypoint symbol layer with hut hit targets" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: Signpost marker HTML (pure) and CSS

The marker element is 0×0 at the geographic point; every visible part is an absolutely positioned child, so the element never resizes and its children can overflow into the spread column. A stack's HTML holds the body sign, an invisible backdrop and every board at once; spreading is a CSS class.

**Files:**
- Create: `huts/src/features/map/signpostHtml.ts`, `huts/src/features/map/signpostHtml.test.ts`
- Modify: `huts/src/features/map/map.css` (remove the `.start-count-marker*` rules, add the signpost rules)

**Interfaces:**
- Consumes: `TourBoardLabel` (Task 2), `startSymbolSvg`.
- Produces:
  - `SPREAD_CAP = 8`
  - `interface BoardTour { key: string; label: TourBoardLabel }`
  - `singleHtml(tour: BoardTour): string`, `stackHtml(tours: BoardTour[]): string`, `clusterHtml(count: number): string`, `escapeHtml(text: string): string`
  - DOM contract used by Task 8: body sign = `.sign` (focusable, `role="button"`); tour boards = `.board[data-tour-key]` (a single marker's `.sign` also carries `data-tour-key`); overflow = `.board.overflow[data-overflow]`; backdrop = `.spread-backdrop`.

- [ ] **Step 1: Write the failing tests**

```ts
import { describe, it, expect } from 'vitest'
import { SPREAD_CAP, clusterHtml, escapeHtml, singleHtml, stackHtml } from './signpostHtml.js'
import type { BoardTour } from './signpostHtml.js'

const bt = (i: number, text = `Ziel ${i}`): BoardTour => ({
  key: `k${i}`, label: { text, distance: `${i}.0 km`, title: `Ziel ${i} (Parkplatz), ${i}.0 km`, sourceType: 2 },
})
const doc = (html: string) => { const d = document.createElement('div'); d.innerHTML = html; return d }

describe('singleHtml', () => {
  it('is one focusable board with the tour key, end point, distance and title', () => {
    const d = doc(singleHtml(bt(1)))
    const sign = d.querySelector('.sign[data-tour-key="k1"]')!
    expect(sign.getAttribute('tabindex')).toBe('0')
    expect(sign.getAttribute('title')).toBe('Ziel 1 (Parkplatz), 1.0 km')
    expect(sign.textContent).toContain('Ziel 1')
    expect(sign.textContent).toContain('1.0 km')
    expect(sign.querySelector('svg')).not.toBeNull()
  })
  it('escapes the end point name', () => {
    expect(singleHtml(bt(1, '<b>&"'))).not.toContain('<b>')
    expect(escapeHtml('<&>"')).toBe('&lt;&amp;&gt;&quot;')
  })
})

describe('stackHtml', () => {
  it('has a body sign with the tour count, a backdrop and one board per tour', () => {
    const d = doc(stackHtml([bt(1), bt(2), bt(3)]))
    expect(d.querySelector('.sign')!.textContent).toBe('3')
    expect(d.querySelector('.spread-backdrop')).not.toBeNull()
    expect([...d.querySelectorAll('.board[data-tour-key]')].map((b) => b.getAttribute('data-tour-key'))).toEqual(['k1', 'k2', 'k3'])
    expect(d.querySelector('[data-overflow]')).toBeNull()
  })
  it('stacks boards on the pole in list order, first at the top', () => {
    const ups = [...doc(stackHtml([bt(1), bt(2), bt(3)])).querySelectorAll<HTMLElement>('.board')].map((b) => b.style.getPropertyValue('--up'))
    expect(ups).toEqual(['3', '2', '1'])
  })
  it('caps the spread and adds an overflow board with a title naming the total', () => {
    const tours = Array.from({ length: SPREAD_CAP + 4 }, (_, i) => bt(i))
    const d = doc(stackHtml(tours))
    expect(d.querySelectorAll('.board[data-tour-key]')).toHaveLength(SPREAD_CAP)
    const overflow = d.querySelector('.board.overflow[data-overflow]')!
    expect(overflow.textContent).toBe('+4')
    expect(overflow.getAttribute('title')).toBe('Alle 12 Touren in der Liste zeigen')
  })
  it('adds no overflow board at exactly the cap', () => {
    const d = doc(stackHtml(Array.from({ length: SPREAD_CAP }, (_, i) => bt(i))))
    expect(d.querySelector('[data-overflow]')).toBeNull()
  })
})

describe('clusterHtml', () => {
  it('is a two-arm sign with the summed count', () => {
    const d = doc(clusterHtml(214))
    expect(d.querySelector('.sign.cluster-sign')!.textContent).toBe('214')
    expect(d.querySelectorAll('.arm')).toHaveLength(2)
  })
})
```

- [ ] **Step 2: Run to verify failure**

Run: `npx vitest run src/features/map/signpostHtml.test.ts`
Expected: FAIL.

- [ ] **Step 3: Implement `signpostHtml.ts`**

```ts
import { startSymbolSvg } from './hutSymbol.js'
import type { TourBoardLabel } from './tourBoard.js'

/** A stack spreads into at most this many tour boards, plus one overflow board. */
export const SPREAD_CAP = 8

export interface BoardTour {
  key: string
  label: TourBoardLabel
}

export function escapeHtml(text: string): string {
  return text.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!)
}

function boardBody({ label }: BoardTour): string {
  return `<span class="sym">${startSymbolSvg(label.sourceType, 14)}</span><span class="txt">${escapeHtml(label.text)}</span><span class="km">${escapeHtml(label.distance)}</span>`
}

/** One start point, one tour: the tour board itself is the marker. */
export function singleHtml(tour: BoardTour): string {
  return `<div class="sign" tabindex="0" role="button" data-tour-key="${escapeHtml(tour.key)}" title="${escapeHtml(tour.label.title)}">${boardBody(tour)}</div>`
}

/** One start point, several tours: a count sign plus every board and a backdrop, hidden until the marker
 *  gets the `spread` class. Board `--up` is its distance above the sign in board pitches (first tour on top). */
export function stackHtml(tours: BoardTour[]): string {
  const shown = tours.slice(0, SPREAD_CAP)
  const hidden = tours.length - shown.length
  const slots = shown.length + (hidden > 0 ? 1 : 0)
  const boards = shown.map((t, i) =>
    `<div class="board" tabindex="0" role="button" style="--up:${slots - i}" data-tour-key="${escapeHtml(t.key)}" title="${escapeHtml(t.label.title)}">${boardBody(t)}</div>`)
  if (hidden > 0) {
    boards.push(`<div class="board overflow" tabindex="0" role="button" style="--up:1" data-overflow title="Alle ${tours.length} Touren in der Liste zeigen"><span class="txt">+${hidden}</span></div>`)
  }
  return `<div class="sign stack-sign" tabindex="0" role="button" aria-label="${tours.length} Touren">${tours.length}</div><div class="spread-backdrop"></div>${boards.join('')}`
}

/** Several start points: two arms pointing opposite ways, the top one carrying the summed count. */
export function clusterHtml(count: number): string {
  return `<div class="sign cluster-sign" tabindex="0" role="button" aria-label="${count} Touren an mehreren Startpunkten"><span class="arm right">${count}</span><span class="arm left"></span></div>`
}
```
`.sign.cluster-sign` textContent must be exactly the count: the empty left arm keeps that true.

- [ ] **Step 4: CSS**

In `map.css` replace the `.start-count-marker` selectors in the shared reset rule (`.hut-marker, .start-count-marker, .swap-marker`) with `.signpost-marker`, delete the `.start-count-marker …` rules, and add:
```css
/* Signpost markers. The marker element is 0x0 at the geographic point; signs and boards are absolutely
   positioned children, so the spread column can overflow it without resizing it. */
.signpost-marker {
  --board-h: 26px;
  --board-pitch: 30px;
}
.signpost-marker .sign,
.signpost-marker .board {
  position: absolute;
  display: flex;
  align-items: center;
  gap: 6px;
  box-sizing: border-box;
  height: var(--board-h);
  padding: 0 16px 0 8px;
  max-width: 220px;
  background: var(--color-ink);
  color: var(--color-ink);
  font: 600 0.8rem/1 'Barlow Semi Condensed', 'Barlow', sans-serif;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  cursor: pointer;
  clip-path: polygon(0 0, calc(100% - 10px) 0, 100% 50%, calc(100% - 10px) 100%, 0 100%);
}
/* Yellow face inset from the ink edge, clipped to the same arrow. */
.signpost-marker .sign::before,
.signpost-marker .board::before {
  content: '';
  position: absolute;
  inset: 2px;
  background: var(--color-signpost);
  clip-path: polygon(0 0, calc(100% - 9px) 0, 100% 50%, calc(100% - 9px) 100%, 0 100%);
}
.signpost-marker .sign > *,
.signpost-marker .board > * { position: relative; }
.signpost-marker .txt { overflow: hidden; text-overflow: ellipsis; min-width: 0; }
.signpost-marker .km { opacity: 0.75; }

/* Single tour: the board's left edge sits on the start point. */
.signpost-marker.single .sign { left: -8px; top: calc(var(--board-h) / -2); }
/* Stack and cluster: the count sign is centred on the point. */
.signpost-marker.stack .stack-sign,
.signpost-marker.cluster .cluster-sign {
  left: 0;
  top: calc(var(--board-h) / -2);
  min-width: 34px;
  justify-content: center;
  transform: translateX(-50%);
  font-size: 0.9rem;
  font-weight: 700;
}
.signpost-marker.cluster .cluster-sign { height: calc(var(--board-h) * 1.6); top: calc(var(--board-h) * -0.8); padding: 0; }
.signpost-marker .arm { position: absolute; left: 0; right: 0; height: 50%; display: flex; align-items: center; justify-content: center; }
.signpost-marker .arm.right { top: 0; }
.signpost-marker .arm.left { bottom: 0; transform: scaleX(-1); }

/* Spread: boards start folded onto the sign and hidden, and move up the pole. */
.signpost-marker .board {
  left: 0;
  top: calc(var(--board-h) / -2);
  opacity: 0;
  visibility: hidden;
  transform: translate(0, 0);
  transition: transform 160ms ease-out, opacity 160ms ease-out, visibility 0s linear 160ms;
}
.signpost-marker.spread .board {
  opacity: 1;
  visibility: visible;
  transform: translate(var(--dx, 0px), calc(var(--up) * var(--board-pitch) * -1));
  transition: transform 160ms ease-out, opacity 160ms ease-out;
}
.signpost-marker.to-right { --dx: 12px; }
.signpost-marker.to-left { --dx: calc(-100% - 12px); }
.signpost-marker.to-left .board { left: auto; right: 0; }
.signpost-marker.to-left .board,
.signpost-marker.to-left .board::before { clip-path: polygon(10px 0, 100% 0, 100% 100%, 10px 100%, 0 50%); }
.signpost-marker.to-left .board { padding: 0 8px 0 16px; }
/* Covers the gaps between boards so the pointer never leaves the marker while crossing them. */
.signpost-marker .spread-backdrop {
  position: absolute;
  left: -20px;
  right: -240px;
  top: calc(var(--board-pitch) * -9 - 10px);
  bottom: 10px;
  pointer-events: none;
}
.signpost-marker.spread .spread-backdrop { pointer-events: auto; }
.signpost-marker.to-left .spread-backdrop { left: -240px; right: -20px; }
.signpost-marker.spread { z-index: 1000; }

.signpost-marker .sign:focus-visible,
.signpost-marker .board:focus-visible { outline: 3px solid var(--color-alpine-blue); outline-offset: 2px; }
.signpost-marker:not(.dimmed):hover .sign,
.signpost-marker.highlighted .sign { filter: drop-shadow(0 2px 6px color-mix(in srgb, var(--color-ink) 55%, transparent)); z-index: 1; }
.signpost-marker .board:hover::before { background: #fff; }
.signpost-marker.dimmed .sign { opacity: 0.45; }

@media (prefers-reduced-motion: reduce) {
  .signpost-marker .board,
  .signpost-marker.spread .board { transition: none; }
}
```
`--dx` for `.to-left` uses `calc(-100% - 12px)`, and `translate()` percentages resolve against the element's own width, so this places the board left of the pole. Confirm it by reading the rule, not with a browser; if a visual issue appears the user will report it.

- [ ] **Step 5: Run tests, lint, commit**

Run: `npx vitest run src/features/map/signpostHtml.test.ts && npm run lint`
Expected: PASS.
```bash
git add -A src && git commit -m "feat(ui): signpost marker HTML and styles" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 8: SignpostMarker component (spread, hover intent, keyboard)

Wraps one react-leaflet `Marker`. The icon depends only on `kind` and `html`; `dimmed`, `highlighted`, `spread`, and the spread side are toggled as classes on the live icon element, so the DOM under the pointer is never replaced. Hover uses raw DOM `mouseover`/`mouseout` on the icon element (Leaflet's own marker `mouseover` does not fire when moving between children).

**Files:**
- Create: `huts/src/features/map/SignpostMarker.tsx`, `huts/src/features/map/SignpostMarker.test.tsx`

**Interfaces:**
- Consumes: DOM contract of Task 7.
- Produces:
  - `OPEN_DELAY_MS = 200`, `CLOSE_DELAY_MS = 250`
  - `type Activation = { kind: 'tour'; tourKey: string } | { kind: 'overflow' } | { kind: 'body' }`
  - `SignpostMarker({ position, kind, html, dimmed, highlighted, onHoverMarker, onHoverTour, onActivate })` with `position: [number, number]`, `kind: MarkerKind`, `html: string`, `dimmed: boolean`, `highlighted: boolean`, `onHoverMarker: (hovering: boolean) => void`, `onHoverTour: (key: string | null) => void`, `onActivate: (a: Activation) => void`

- [ ] **Step 1: Write the failing tests**

```tsx
// @vitest-environment jsdom
import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { render, cleanup, fireEvent, act } from '@testing-library/react'
import L from 'leaflet'
import { MapContainer, useMap } from 'react-leaflet'
import SignpostMarker, { CLOSE_DELAY_MS, OPEN_DELAY_MS } from './SignpostMarker.js'
import { stackHtml, singleHtml } from './signpostHtml.js'
import type { BoardTour } from './signpostHtml.js'

const bt = (i: number): BoardTour => ({ key: `k${i}`, label: { text: `Z${i}`, distance: '1.0 km', title: `t${i}`, sourceType: 1 } })
let map: L.Map
function CaptureMap() { map = useMap(); return null }

beforeEach(() => { vi.useFakeTimers() })
afterEach(() => { cleanup(); vi.useRealTimers() })

function setup(over: Partial<Parameters<typeof SignpostMarker>[0]> = {}) {
  const handlers = { onHoverMarker: vi.fn(), onHoverTour: vi.fn(), onActivate: vi.fn() }
  const utils = render(
    <MapContainer center={[47, 11]} zoom={13} style={{ height: 400, width: 400 }}>
      <CaptureMap />
      <SignpostMarker position={[47, 11]} kind="stack" html={stackHtml([bt(1), bt(2)])} dimmed={false} highlighted={false} {...handlers} {...over} />
    </MapContainer>,
  )
  const el = () => utils.container.querySelector('.signpost-marker') as HTMLElement
  return { ...utils, ...handlers, el }
}
const advance = (ms: number) => act(() => { vi.advanceTimersByTime(ms) })

describe('SignpostMarker spread', () => {
  it('does not spread before the open delay and spreads after it', () => {
    const { el } = setup()
    fireEvent.mouseOver(el().querySelector('.sign')!)
    advance(OPEN_DELAY_MS - 1)
    expect(el().classList.contains('spread')).toBe(false)
    advance(1)
    expect(el().classList.contains('spread')).toBe(true)
  })
  it('does not collapse inside the close delay, collapses after it', () => {
    const { el } = setup()
    fireEvent.mouseOver(el().querySelector('.sign')!)
    advance(OPEN_DELAY_MS)
    fireEvent.mouseOut(el().querySelector('.sign')!, { relatedTarget: document.body })
    advance(CLOSE_DELAY_MS - 1)
    expect(el().classList.contains('spread')).toBe(true)
    advance(1)
    expect(el().classList.contains('spread')).toBe(false)
  })
  it('stays open when the pointer crosses from one board to another', () => {
    const { el } = setup()
    fireEvent.mouseOver(el().querySelector('.sign')!)
    advance(OPEN_DELAY_MS)
    const [a, b] = el().querySelectorAll('.board')
    fireEvent.mouseOut(a, { relatedTarget: b })
    fireEvent.mouseOver(b)
    advance(CLOSE_DELAY_MS * 2)
    expect(el().classList.contains('spread')).toBe(true)
  })
  it('collapses at once on zoomstart and on dragstart', () => {
    const { el } = setup()
    for (const event of ['zoomstart', 'dragstart']) {
      fireEvent.mouseOver(el().querySelector('.sign')!)
      advance(OPEN_DELAY_MS)
      expect(el().classList.contains('spread')).toBe(true)
      act(() => { map.fire(event) })
      expect(el().classList.contains('spread')).toBe(false)
    }
  })
  it('raises a spread marker above its neighbours', () => {
    const { el } = setup()
    fireEvent.mouseOver(el().querySelector('.sign')!)
    advance(OPEN_DELAY_MS)
    expect(Number(el().style.zIndex)).toBeGreaterThan(5000)
  })
  it('does not spread a single or a cluster marker', () => {
    const { el } = setup({ kind: 'single', html: singleHtml(bt(1)) })
    fireEvent.mouseOver(el().querySelector('.sign')!)
    advance(OPEN_DELAY_MS * 2)
    expect(el().classList.contains('spread')).toBe(false)
  })
  it('keeps its spread state when the html changes while spread', () => {
    const { el, rerender } = setup()
    fireEvent.mouseOver(el().querySelector('.sign')!)
    advance(OPEN_DELAY_MS)
    rerender(
      <MapContainer center={[47, 11]} zoom={13} style={{ height: 400, width: 400 }}>
        <SignpostMarker position={[47, 11]} kind="stack" html={stackHtml([bt(1), bt(2), bt(3)])} dimmed={false} highlighted={false} onHoverMarker={() => {}} onHoverTour={() => {}} onActivate={() => {}} />
      </MapContainer>,
    )
    expect(el().classList.contains('spread')).toBe(true)
  })
  it('does not fire a pending timer after unmount', () => {
    const { el, unmount } = setup()
    fireEvent.mouseOver(el().querySelector('.sign')!)
    unmount()
    expect(() => advance(OPEN_DELAY_MS * 2)).not.toThrow()
  })
})

describe('SignpostMarker events', () => {
  it('reports the hovered board and clears it on leaving', () => {
    const { el, onHoverTour, onHoverMarker } = setup()
    fireEvent.mouseOver(el().querySelector('.sign')!)
    advance(OPEN_DELAY_MS)
    fireEvent.mouseOver(el().querySelector('.board[data-tour-key="k2"]')!)
    expect(onHoverTour).toHaveBeenLastCalledWith('k2')
    fireEvent.mouseOut(el().querySelector('.board[data-tour-key="k2"]')!, { relatedTarget: document.body })
    expect(onHoverTour).toHaveBeenLastCalledWith(null)
    expect(onHoverMarker).toHaveBeenLastCalledWith(false)
  })
  it('activates a board, the overflow board and the body sign from clicks', () => {
    const many = Array.from({ length: 10 }, (_, i) => bt(i))
    const { el, onActivate } = setup({ html: stackHtml(many) })
    fireEvent.click(el().querySelector('.board[data-tour-key="k3"]')!)
    expect(onActivate).toHaveBeenLastCalledWith({ kind: 'tour', tourKey: 'k3' })
    fireEvent.click(el().querySelector('[data-overflow]')!)
    expect(onActivate).toHaveBeenLastCalledWith({ kind: 'overflow' })
    fireEvent.click(el().querySelector('.stack-sign')!)
    expect(onActivate).toHaveBeenLastCalledWith({ kind: 'body' })
  })
  it('toggles dimmed and highlighted as classes', () => {
    const { el } = setup({ dimmed: true, highlighted: true })
    expect(el().classList.contains('dimmed')).toBe(true)
    expect(el().classList.contains('highlighted')).toBe(true)
  })
})

describe('SignpostMarker keyboard', () => {
  it('spreads on focus at once, activates a board with Enter, collapses with Escape', () => {
    const { el, onActivate } = setup()
    fireEvent.focusIn(el().querySelector('.sign')!)
    expect(el().classList.contains('spread')).toBe(true)
    fireEvent.keyDown(el().querySelector('.board[data-tour-key="k1"]')!, { key: 'Enter' })
    expect(onActivate).toHaveBeenLastCalledWith({ kind: 'tour', tourKey: 'k1' })
    fireEvent.keyDown(el().querySelector('.board[data-tour-key="k1"]')!, { key: 'Escape' })
    expect(el().classList.contains('spread')).toBe(false)
  })
  it('focusing a board highlights its tour', () => {
    const { el, onHoverTour } = setup()
    fireEvent.focusIn(el().querySelector('.board[data-tour-key="k2"]')!)
    expect(onHoverTour).toHaveBeenLastCalledWith('k2')
  })
})
```
Every interactive element in the HTML carries `tabindex="0"`, so keyboard access is by the HTML contract (asserted in Task 7).

- [ ] **Step 2: Run to verify failure**

Run: `npx vitest run src/features/map/SignpostMarker.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement**

```tsx
import { useEffect, useMemo, useRef, useState } from 'react'
import L from 'leaflet'
import { Marker, useMap, useMapEvents } from 'react-leaflet'
import type { MarkerKind } from './clusterStarts.js'

export const OPEN_DELAY_MS = 200
export const CLOSE_DELAY_MS = 250
/** Lifts a spread marker above every neighbour so the column is never covered. */
const SPREAD_Z_OFFSET = 10_000

export type Activation = { kind: 'tour'; tourKey: string } | { kind: 'overflow' } | { kind: 'body' }

function resolveTarget(target: EventTarget | null): Activation {
  const el = target instanceof Element ? target : null
  const board = el?.closest<HTMLElement>('[data-tour-key]')
  if (board) return { kind: 'tour', tourKey: board.dataset.tourKey! }
  if (el?.closest('[data-overflow]')) return { kind: 'overflow' }
  return { kind: 'body' }
}

const tourKeyOf = (target: EventTarget | null): string | null => {
  const a = resolveTarget(target)
  return a.kind === 'tour' ? a.tourKey : null
}

/** One signpost marker. The icon depends only on `kind` and `html`; dimmed, highlighted, spread and the
 *  spread side are classes toggled on the live icon element, so hovering never replaces the DOM under the
 *  pointer. Only a `stack` spreads. */
export default function SignpostMarker({ position, kind, html, dimmed, highlighted, onHoverMarker, onHoverTour, onActivate }: {
  position: [number, number]
  kind: MarkerKind
  html: string
  dimmed: boolean
  highlighted: boolean
  /** The pointer or focus entered (true) or left (false) the marker as a whole, spread boards included. */
  onHoverMarker: (hovering: boolean) => void
  /** The tour board under the pointer or focus; null when none. */
  onHoverTour: (key: string | null) => void
  onActivate: (a: Activation) => void
}) {
  const map = useMap()
  const markerRef = useRef<L.Marker>(null)
  const icon = useMemo(() => L.divIcon({ className: `signpost-marker ${kind}`, html, iconSize: [0, 0] }), [kind, html])
  const [spread, setSpread] = useState(false)
  const spreadRef = useRef(false)
  spreadRef.current = spread
  const timer = useRef<number | undefined>(undefined)
  const escaped = useRef(false)
  const callbacks = useRef({ onHoverMarker, onHoverTour, onActivate })
  callbacks.current = { onHoverMarker, onHoverTour, onActivate }
  const canSpread = kind === 'stack'

  const cancelTimer = () => window.clearTimeout(timer.current)
  const later = (fn: () => void, ms: number) => { cancelTimer(); timer.current = window.setTimeout(fn, ms) }
  const collapse = () => { cancelTimer(); setSpread(false) }
  useMapEvents({ zoomstart: collapse, dragstart: collapse })
  useEffect(() => cancelTimer, [])

  useEffect(() => {
    const el = markerRef.current?.getElement()
    if (!el) return
    el.classList.toggle('dimmed', dimmed)
    el.classList.toggle('highlighted', highlighted)
  }, [icon, dimmed, highlighted])

  useEffect(() => {
    const marker = markerRef.current
    const el = marker?.getElement()
    if (!marker || !el) return
    el.classList.toggle('spread', spread)
    marker.setZIndexOffset(spread ? SPREAD_Z_OFFSET : 0)
    if (spread) {
      const toLeft = map.latLngToContainerPoint(marker.getLatLng()).x > map.getSize().x / 2
      el.classList.toggle('to-left', toLeft)
      el.classList.toggle('to-right', !toLeft)
    }
  }, [icon, spread, map])

  useEffect(() => {
    const el = markerRef.current?.getElement()
    if (!el) return
    const inside = (t: EventTarget | null) => t instanceof Node && el.contains(t)
    const onOver = (e: MouseEvent) => {
      escaped.current = false
      cancelTimer()
      callbacks.current.onHoverMarker(true)
      callbacks.current.onHoverTour(tourKeyOf(e.target))
      if (canSpread && !spreadRef.current) later(() => setSpread(true), OPEN_DELAY_MS)
    }
    const onOut = (e: MouseEvent) => {
      if (inside(e.relatedTarget)) return
      callbacks.current.onHoverMarker(false)
      callbacks.current.onHoverTour(null)
      later(() => setSpread(false), CLOSE_DELAY_MS)
    }
    const onFocusIn = (e: FocusEvent) => {
      cancelTimer()
      callbacks.current.onHoverMarker(true)
      callbacks.current.onHoverTour(tourKeyOf(e.target))
      if (canSpread && !escaped.current) setSpread(true)
    }
    const onFocusOut = (e: FocusEvent) => {
      if (inside(e.relatedTarget)) return
      escaped.current = false
      callbacks.current.onHoverMarker(false)
      callbacks.current.onHoverTour(null)
      setSpread(false)
    }
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Enter') {
        e.preventDefault()
        callbacks.current.onActivate(resolveTarget(e.target))
      } else if (e.key === 'Escape' && spreadRef.current) {
        escaped.current = true
        el.querySelector<HTMLElement>('.sign')?.focus()
        setSpread(false)
      }
    }
    el.addEventListener('mouseover', onOver)
    el.addEventListener('mouseout', onOut)
    el.addEventListener('focusin', onFocusIn)
    el.addEventListener('focusout', onFocusOut)
    el.addEventListener('keydown', onKeyDown)
    return () => {
      el.removeEventListener('mouseover', onOver)
      el.removeEventListener('mouseout', onOut)
      el.removeEventListener('focusin', onFocusIn)
      el.removeEventListener('focusout', onFocusOut)
      el.removeEventListener('keydown', onKeyDown)
    }
  }, [icon, canSpread])

  return (
    <Marker
      ref={markerRef} position={position} icon={icon} keyboard={false}
      eventHandlers={{ click: (e) => callbacks.current.onActivate(resolveTarget(e.originalEvent.target)) }}
    />
  )
}
```
`later`/`cancelTimer`/`collapse` are recreated each render but only touch refs and the stable `setSpread`, so the listener effect capturing an older `later` is safe. If oxlint objects to assigning refs during render or to the exhaustive-deps shape, keep behavior and satisfy the linter with the smallest change (e.g. move the ref assignments into a `useEffect` without deps).

- [ ] **Step 4: Run tests, typecheck, lint, commit**

Run: `npx vitest run src/features/map/SignpostMarker.test.tsx && npm run typecheck && npm run lint`
Expected: PASS. The zIndex assertion reads `el.style.zIndex`: Leaflet sets it as `_zIndex = latitude-based + zIndexOffset`. If jsdom yields a value under 5000, compare against the value before spreading instead.
```bash
git add -A src && git commit -m "feat(ui): signpost marker with hover-intent spread and keyboard support" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 9: Focus as a tour set, set-valued hover, DiscoverLayer rewrite

One task because the `DiscoverLayer` prop contract, `useDiscover`, `PlannerPage` and `DiscoverMapLayers` change together and must compile together.

**Files:**
- Modify: `huts/src/features/discover/useDiscover.ts`, `huts/src/features/discover/useDiscover.test.tsx`
- Modify: `huts/src/features/map/DiscoverMapLayers.tsx`, `huts/src/features/map/DiscoverLayer.tsx`
- Modify: `huts/src/features/planner/PlannerPage.tsx` (and `PlannerPage.test.tsx`, `PlannerMap.test.tsx` if they reference the old props)
- Modify: `huts/src/features/map/clusterStarts.ts` + test (delete `markerRadius`)

**Interfaces:**
- Consumes: everything from Tasks 1–8.
- Produces:
  - `useDiscover` returns `focusTours: Set<string> | null`, `setFocusTours`, `hoveredTourKeys: ReadonlySet<string>`, `setHoveredTourKeys` (replacing `focusStarts`, `setFocusStarts`, `hoveredTourKey`, `setHoveredTourKey`; `hoveredStarts` stays).
  - `DiscoverLayer` props: `groups, startById, dimmed, allTours, routeCtx, hutNameById: Map<number, string>, hoveredTourKeys: ReadonlySet<string>, onHoverTours: (keys: ReadonlySet<string>) => void, onPickRoute, onNavigate?, focusTours?: ReadonlySet<string> | null, onFocusTours?: (keys: string[] | null) => void, onHoverStarts?, onViewChange?`.
  - `DiscoverMapMode` fields renamed the same way, plus `hutNameById`.

**Decision taken where the spec is silent:** clicking a leg or hut that belongs to exactly one visible tour picks that tour (as a route click does today); with two or more it focuses the list on them. The focus zoom for a leg/hut focus is the current zoom (no fly).

- [ ] **Step 1: Update `useDiscover` tests first**

In `useDiscover.test.tsx` rename usages (`focusStarts`→`focusTours`, `hoveredTourKey`→`hoveredTourKeys`) and add:
```tsx
it('limits viewTours to the focused tour keys and lifts the limit again', async () => {
  // render the hook as the existing tests do, wait for tours, then:
  const [first] = result.current.visibleTours
  act(() => result.current.setFocusTours(new Set([tourKey(first)])))
  expect(result.current.viewTours.map(tourKey)).toEqual([tourKey(first)])
  act(() => result.current.setFocusTours(null))
  expect(result.current.viewTours.length).toBeGreaterThan(0)
})
it('drops the focus when the form changes', () => {
  act(() => result.current.setFocusTours(new Set(['x'])))
  act(() => result.current.patchForm({ onlyAvailable: !result.current.form.onlyAvailable }))
  expect(result.current.focusTours).toBeNull()
})
```
Reuse the file's existing harness/fixtures for `result` and the wait; import `tourKey` from `@/tourSearch/tourKey.js`.

- [ ] **Step 2: Run to verify failure**

Run: `npx vitest run src/features/discover/useDiscover.test.tsx`
Expected: FAIL.

- [ ] **Step 3: `useDiscover.ts`**

```ts
import { NO_TOURS, tourKey } from '@/tourSearch/tourKey.js'
...
const [focusTours, setFocusTours] = useState<Set<string> | null>(null)
const [hoveredTourKeys, setHoveredTourKeys] = useState<ReadonlySet<string>>(NO_TOURS)
...
useEffect(() => { setFocusTours(null) }, [form, draft])
...
const viewTours = useMemo(() => {
  if (focusTours) return rankedTours.filter((t) => focusTours.has(tourKey(t)))
  ...
}, [rankedTours, mapView, data, focusTours])
...
focusTours, setFocusTours, hoveredTourKeys, setHoveredTourKeys, hoveredStarts, setHoveredStarts,
```
Remove the old four names.

- [ ] **Step 4: `DiscoverMapLayers.tsx`**

`DiscoverMapMode`: replace `hoveredTourKey`, `focusStarts`, `onFocusStarts`, `onHoverTour` with
```ts
hutNameById: Map<number, string>
hoveredTourKeys: ReadonlySet<string>
/** Tour keys the list and map are focused on; null when unfocused. */
focusTours: ReadonlySet<string> | null
onFocusTours: (keys: string[] | null) => void
onHoverTours: (keys: ReadonlySet<string>) => void
```
and pass them through in `DiscoverMapLayers`.

- [ ] **Step 5: `PlannerPage.tsx`**

- Destructure `focusTours, setFocusTours, hoveredTourKeys, setHoveredTourKeys` from `useDiscover`.
- `showAllTours`: `setFocusTours(null)`.
- `pick` and `confirmDiscard`: `setHoveredTourKeys(NO_TOURS)` (import `NO_TOURS, tourKey` from `@/tourSearch/tourKey.js`).
- Discover `mapMode`: `hutNameById: data.hutNameById, hoveredTourKeys, focusTours, onFocusTours: (keys) => setFocusTours(keys && new Set(keys)), onHoverTours: setHoveredTourKeys`.
- `mapCommands.onMapClick`: `setFocusTours(null)`.
- `ResultsList`: `isHighlighted={(t) => hoveredTourKeys.has(tourKey(t)) || (hoveredStarts?.has(t.startId) ?? false)}` and `onPreview={(t) => setHoveredTourKeys(t ? new Set([tourKey(t)]) : NO_TOURS)}`.
- Fix the `useMemo` dependency lists accordingly.

- [ ] **Step 6: Rewrite `DiscoverLayer.tsx`**

Full replacement:
```tsx
import { useEffect, useMemo, useRef, useState } from 'react'
import L from 'leaflet'
import { useMap, useMapEvents } from 'react-leaflet'
import type { StartGroup } from '@/tourSearch/groupByStart.js'
import { NO_TOURS, tourKey } from '@/tourSearch/tourKey.js'
import type { PlannerTour } from '@/tourSearch/plannerTour.js'
import type { StartPoint } from '@/data/types.js'
import { currentView, routeTouchesBbox } from '@/lib/viewport.js'
import type { View } from '@/lib/viewport.js'
import { tourToRoute } from './routes.js'
import type { RouteContext } from './routes.js'
import RouteLayer from './RouteLayer.js'
import WaypointLayer, { collectSymbols } from './WaypointLayer.js'
import HoverTooltip from './HoverTooltip.js'
import SignpostMarker from './SignpostMarker.js'
import type { Activation } from './SignpostMarker.js'
import { createStartClusterer, markerKind } from './clusterStarts.js'
import type { MapMarker } from './clusterStarts.js'
import { clusterHtml, escapeHtml, singleHtml, stackHtml } from './signpostHtml.js'
import { tourBoardLabel } from './tourBoard.js'
import { indexToursByHut, indexToursByLeg, legKey, tierOf } from './tourMatch.js'
import './map.css'

/** Below this zoom, routes stay hidden and only markers show — tuned lower than the
 *  clusterer's own maxZoom (14) so routes appear before markers finish separating one-per-start. */
export const ROUTE_REVEAL_ZOOM = 11

const toursText = (n: number) => `In ${n} Touren`

/** One signpost marker per start point with matching tours (a single tour board, or a stack of boards with
 *  the tour count) or per cluster of start points (a two-arm sign with the summed count), clustered by zoom.
 *  Panning and zooming only re-cluster, they never re-search. A single board and every board of a spread stack
 *  pick their tour on click; a stack or cluster click flies the map to the bounds of its tours, focuses the results list on them
 *  and draws them at the focused tier until the focus is dropped (show all tours, a map click, or zooming out
 *  past the zoom the click flew to); markers outside the focus fade like the search-running state.
 *  Past `ROUTE_REVEAL_ZOOM`, routes draw for every tour whose waypoints' bounding box overlaps the viewport,
 *  in three tiers (rest, focused, hovered); the focused and hovered tiers are display-only copies above the
 *  interactive rest lines, so mouseout always fires. Hovering a leg or hut hovers every visible tour containing
 *  it; clicking one focuses the list on those tours (a leg or hut in a single tour picks it). */
export default function DiscoverLayer({
  groups, startById, dimmed, allTours, routeCtx, hutNameById, hoveredTourKeys, onHoverTours, onPickRoute, onNavigate,
  focusTours, onFocusTours, onHoverStarts, onViewChange,
}: {
  groups: StartGroup<PlannerTour>[]
  startById: Map<number, StartPoint>
  dimmed: boolean
  allTours: PlannerTour[]
  routeCtx: RouteContext | null
  hutNameById: Map<number, string>
  /** Tours hovered anywhere (map or results list); drawn at the hovered tier. */
  hoveredTourKeys: ReadonlySet<string>
  onHoverTours: (keys: ReadonlySet<string>) => void
  onPickRoute: (tour: PlannerTour) => void
  onNavigate?: () => void
  /** Tour keys the results list is limited to and the map highlights; null when unfocused. */
  focusTours?: ReadonlySet<string> | null
  /** Sets the focus; null lifts it. */
  onFocusTours?: (keys: string[] | null) => void
  /** Start points of the marker under the pointer; null when none. */
  onHoverStarts?: (startIds: Set<number> | null) => void
  onViewChange?: (view: View) => void
}) {
  const map = useMap()
  /** Zoom the map settled on when the focus was set; zooming out below it drops the focus. */
  const focusZoom = useRef(0)
  const [view, setView] = useState<View>(() => currentView(map))
  useMapEvents({
    moveend: () => setView(currentView(map)),
    zoomend: () => {
      setView(currentView(map))
      if (focusTours && map.getZoom() < focusZoom.current) onFocusTours?.(null)
    },
  })
  useEffect(() => { onViewChange?.(view) }, [view, onViewChange])

  const clusterer = useMemo(() => createStartClusterer(groups.flatMap((g) => {
    const s = startById.get(g.startId)
    return s ? [{ startId: g.startId, count: g.tours.length, lat: s.lat, lng: s.lng }] : []
  })), [groups, startById])
  const groupOfStart = useMemo(() => new Map(groups.map((g) => [g.startId, g])), [groups])
  const tourByKey = useMemo(() => new Map(allTours.map((t) => [tourKey(t), t])), [allTours])
  const keysOfStarts = (startIds: number[]) => startIds.flatMap((id) => groupOfStart.get(id)?.tours.map(tourKey) ?? [])

  const routeReveal = view.zoom >= ROUTE_REVEAL_ZOOM
  const routedTours = useMemo(() => {
    if (!routeCtx || !routeReveal) return []
    return allTours.flatMap((tour) => {
      const route = tourToRoute(tour, routeCtx)
      return route && routeTouchesBbox(route.waypoints, view.bbox) ? [{ key: tourKey(tour), tour, route }] : []
    })
  }, [allTours, routeCtx, routeReveal, view.bbox])
  const toursByLeg = useMemo(() => indexToursByLeg(routedTours), [routedTours])
  const toursByHut = useMemo(() => indexToursByHut(routedTours), [routedTours])

  const [hoveredStartIds, setHoveredStartIds] = useState<ReadonlySet<number> | null>(null)
  const hoverStarts = (ids: Set<number> | null) => { setHoveredStartIds(ids); onHoverStarts?.(ids) }
  const tiered = useMemo(() => routedTours.map((r) => ({
    ...r, tier: tierOf({ key: r.key, startId: r.tour.startId }, { hoveredKeys: hoveredTourKeys, hoveredStarts: hoveredStartIds, focus: focusTours ?? null }),
  })), [routedTours, hoveredTourKeys, hoveredStartIds, focusTours])
  const symbols = useMemo(() => collectSymbols(tiered), [tiered])

  const [tip, setTip] = useState<{ at: L.LatLng; html: string } | null>(null)
  const hoverKeys = (keys: string[] | null, at: L.LatLng, title?: string) => {
    if (!keys) { onHoverTours(NO_TOURS); setTip(null); return }
    onHoverTours(new Set(keys))
    setTip({ at, html: `${title ? `<strong>${escapeHtml(title)}</strong><br>` : ''}${toursText(keys.length)}` })
  }
  /** A shared leg or hut: one tour is picked, several focus the list on them. */
  const clickKeys = (keys: string[]) => {
    onNavigate?.()
    if (keys.length === 1) {
      const tour = tourByKey.get(keys[0])
      if (tour) onPickRoute(tour)
      return
    }
    focusZoom.current = map.getZoom()
    onFocusTours?.(keys)
  }

  /** Bounds of every waypoint of every tour starting at one of the given start points. */
  const tourBounds = (startIds: number[]): L.LatLngBounds | null => {
    if (!routeCtx) return null
    const ids = new Set(startIds)
    const bounds = L.latLngBounds([])
    for (const g of groups) {
      if (!ids.has(g.startId)) continue
      for (const tour of g.tours) tourToRoute(tour, routeCtx)?.waypoints.forEach((p) => bounds.extend([p.lat, p.lng]))
    }
    return bounds.isValid() ? bounds : null
  }

  const startIdsOf = (m: MapMarker) => (m.kind === 'cluster' ? clusterer.startIdsOf(m.clusterId) : [m.startId])
  const markerKey = (m: MapMarker) => (m.kind === 'start' ? `s${m.startId}` : `c${m.clusterId}`)

  const markers = useMemo(() => clusterer.clustersFor(view.bbox, view.zoom), [clusterer, view])
  const htmlByMarker = useMemo(() => new Map(markers.map((m) => {
    const kind = markerKind(m)
    if (kind === 'cluster') return [markerKey(m), clusterHtml(m.count)] as const
    const boards = (groupOfStart.get((m as { startId: number }).startId)?.tours ?? [])
      .map((t) => ({ key: tourKey(t), label: tourBoardLabel(t, startById) }))
    return [markerKey(m), kind === 'single' && boards[0] ? singleHtml(boards[0]) : stackHtml(boards)] as const
  })), [markers, groupOfStart, startById])

  const highlightedStarts = useMemo(() => {
    const ids = new Set<number>()
    for (const key of hoveredTourKeys) { const t = tourByKey.get(key); if (t) ids.add(t.startId) }
    return ids
  }, [hoveredTourKeys, tourByKey])

  const activate = (m: MapMarker, a: Activation) => {
    onNavigate?.()
    if (a.kind === 'tour') {
      const tour = tourByKey.get(a.tourKey)
      if (tour) onPickRoute(tour)
      return
    }
    const startIds = startIdsOf(m)
    const only = m.kind === 'start' && m.count === 1 ? groupOfStart.get(m.startId)?.tours[0] : undefined
    if (only) { onPickRoute(only); return }
    onFocusTours?.(keysOfStarts(startIds))
    const bounds = tourBounds(startIds)
    if (bounds) {
      focusZoom.current = Math.min(map.getBoundsZoom(bounds, false, L.point(80, 80)), map.getMaxZoom())
      map.flyToBounds(bounds, { padding: [40, 40], duration: 0.6 })
    } else if (m.kind === 'cluster') {
      focusZoom.current = Math.min(clusterer.expansionZoom(m.clusterId), map.getMaxZoom())
      map.setView([m.lat, m.lng], focusZoom.current)
    }
  }

  return (
    <>
      {markers.map((m) => {
        const ids = startIdsOf(m)
        const outsideFocus = focusTours != null && !keysOfStarts(ids).some((k) => focusTours.has(k))
        return (
          <SignpostMarker
            key={markerKey(m)} position={[m.lat, m.lng]} kind={markerKind(m)} html={htmlByMarker.get(markerKey(m)) ?? ''}
            dimmed={dimmed || outsideFocus} highlighted={ids.some((id) => highlightedStarts.has(id))}
            onHoverMarker={(hovering) => hoverStarts(hovering ? new Set(ids) : null)}
            onHoverTour={(key) => onHoverTours(key ? new Set([key]) : NO_TOURS)}
            onActivate={(a) => activate(m, a)}
          />
        )
      })}
      {tiered.map(({ key, route }) => (
        <RouteLayer
          key={key} route={route} emphasis="rest" dots={false}
          onHover={(hovering, i, at) => {
            const lk = legKey(route.legs[i])
            hoverKeys(hovering ? (lk ? toursByLeg.get(lk) ?? [key] : [key]) : null, at)
          }}
          onClick={(i) => { const lk = legKey(route.legs[i]); clickKeys(lk ? toursByLeg.get(lk) ?? [key] : [key]) }}
        />
      ))}
      {/* The focused and hovered tiers are display-only copies above the rest tier; the interactive
          layers underneath never change, so their mouseout always fires. */}
      {tiered.filter((t) => t.tier === 'focused').map(({ key, route }) => <RouteLayer key={`f-${key}`} route={route} emphasis="focused" dots={false} interactive={false} />)}
      {tiered.filter((t) => t.tier === 'hovered').map(({ key, route }) => <RouteLayer key={`h-${key}`} route={route} emphasis="hovered" dots={false} interactive={false} />)}
      <WaypointLayer
        symbols={symbols}
        onHoverHut={(hutId, at) => hoverKeys(hutId === null ? null : toursByHut.get(hutId) ?? [], at, hutId === null ? undefined : hutNameById.get(hutId) ?? String(hutId))}
        onClickHut={(hutId) => clickKeys(toursByHut.get(hutId) ?? [])}
      />
      <HoverTooltip tip={tip} />
    </>
  )
}
```
A hut whose tour list is empty cannot occur (symbols come from visible routes), but `clickKeys([])` must be a no-op: add `if (keys.length === 0) return` first in `clickKeys`. Delete `markerRadius` from `clusterStarts.ts` and its describe block/import from `clusterStarts.test.ts` now that nothing uses it.

- [ ] **Step 7: Rewrite the affected `DiscoverLayer.test.tsx` tests**

- `renderLayer`/`renderFocused` props: replace `hoveredTourKey={null} onHoverTour={() => {}}` with `hutNameById={new Map()} hoveredTourKeys={NO_TOURS} onHoverTours={() => {}}`; add `hutClassByIndex: new Map([[10, { operator: 'av', serviced: true }], [11, { operator: 'sonstige', serviced: false }]])` to `routeCtx`/`routeCtx2`; `FocusedLayer` owns `focusTours` (`useState<Set<string> | null>`) and passes `focusTours={focus} onFocusTours={(keys) => setFocus(keys && new Set(keys))}`.
- Route line tests keep `path.leaflet-interactive` counts (rest layer is interactive).
- Replace the focus test's pane proxies with the new panes: focused = `.leaflet-route-focused-line-pane path`, faded = `.leaflet-route-rest-line-pane path`; marker selector `.signpost-marker`. Assert: focused count is 0 before the click and `> 0` after; the first marker lacks `dimmed`, the second has it.
- Zoom-out test: swap `.leaflet-route-dot-pane path` for `.leaflet-route-focused-line-pane path` and `.start-count-marker` for `.signpost-marker`.
- Add:
```tsx
it('hovering a shared leg hovers every tour containing it, with a count tooltip', () => {
  // two tours from start 1 over huts [10, 11] share edgeId 1 on the same layer
  const onHoverTours = vi.fn()
  const { container } = renderLayer({ allTours: [tour(1, [10, 11]), tour(1, [10, 11, 12])], onHoverTours, routeCtx: ctx3 }, 13)
  fireEvent.mouseOver(container.querySelector('.leaflet-route-rest-line-pane path.leaflet-interactive')!)
  expect([...onHoverTours.mock.calls.at(-1)![0]]).toHaveLength(2)
  expect(document.querySelector('.leaflet-tooltip')!.textContent).toBe('In 2 Touren')
})
it('a leg click focuses the matched tours and is not read as the map click that drops the focus', () => {
  const onFocusTours = vi.fn(); const onMapClick = vi.fn()
  // render with <MapClick onClick={onMapClick} /> (useMapEvents({ click })) next to the layer
  fireEvent.click(path)
  expect(onFocusTours).toHaveBeenCalledWith(expect.arrayContaining([tourKey(a), tourKey(b)]))
  expect(onMapClick).not.toHaveBeenCalled()
})
it('a leg in a single tour picks it on click', () => { /* onPickRoute called with the tour, onFocusTours not called */ })
it('hovering a hut hit target hovers every tour stopping there; the tooltip names the hut', () => {
  // hutNameById = new Map([[10, 'Hütte Eins']]); mouseOver `.leaflet-route-hit-pane .leaflet-marker-icon`
  // expect tooltip text 'Hütte EinsIn 2 Touren'
})
it('draws hovered tours at the hovered tier and leaves the rest layer interactive', () => {
  const { container } = renderLayer({ hoveredTourKeys: new Set([tourKey(theTour)]) }, 13)
  expect(container.querySelectorAll('.leaflet-route-hovered-line-pane path').length).toBeGreaterThan(0)
  expect(container.querySelectorAll('.leaflet-route-rest-line-pane path.leaflet-interactive').length).toBeGreaterThan(0)
})
it('draws focused tours thin at the focused tier and no dots on route lines', () => { /* focusTours set, no path in *-symbol panes */ })
```
Build `ctx3` with a hut 12 and matching `hutClassByIndex`; make the tours share `edgeId: 1` on layer `hut_edges` (the `tour()` helper already uses `edgeId: 1` for every leg; the middle leg is `hut_edges`). Fill the test bodies fully following the patterns above; each assertion listed must be present.

- [ ] **Step 8: Run tests, typecheck, lint**

Run: `npx vitest run src && npm run typecheck && npm run lint`
Expected: PASS, including `architecture.test.ts` (`features/discover` must not import `features/map`; `tourKey` now lives in `tourSearch/`). Fix `PlannerPage.test.tsx`/`PlannerMap.test.tsx` for the renamed props if they fail.

- [ ] **Step 9: Commit**

```bash
git add -A src && git commit -m "feat(ui): signpost markers, emphasis tiers and shared-leg/hut hover in Discover" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 10: Integration tests for stack spread through `DiscoverLayer`

**Files:**
- Modify: `huts/src/features/map/DiscoverLayer.test.tsx`

- [ ] **Step 1: Write the tests**

Add a `describe('DiscoverLayer signposts')` using `vi.useFakeTimers()` in `beforeEach` and `vi.useRealTimers()` in `afterEach`:
```tsx
it('renders a single tour as one board labelled end point and distance; click picks the tour', () => {
  // groups: one start, one tour with exit 2 named "Kaunertal", totalDistanceM 42300
  // expect .signpost-marker.single .sign text to contain 'Kaunertal' and '42.3 km'
  // fireEvent.click(sign) -> onPickRoute(theTour)
})
it('renders several tours from one start as a stack with the count', () => {
  // expect .signpost-marker.stack .stack-sign text '3'
})
it('spreads a stack on hover into one board per tour and picks a board\'s tour on click', () => {
  // mouseOver .sign, advance 200ms, expect 3 .board[data-tour-key]; click one -> onPickRoute(thatTour)
})
it('hovering a spread board hovers just that tour', () => {
  // mouseOver board -> onHoverTours called with new Set([tourKey(thatTour)])
})
it('caps a spread at 8 boards plus an overflow board whose click focuses that start\'s tours', () => {
  // 11 tours -> 8 .board[data-tour-key] + .board.overflow text '+3'; click overflow -> onFocusTours(11 keys), onPickRoute not called
})
it('renders a cluster as a two-arm sign with the summed count and never spreads it', () => {
  // two starts close together at a low zoom -> .signpost-marker.cluster text = summed count; hover 300ms -> no 'spread' class
})
it('highlights the marker of a start whose tour is hovered from the list', () => {
  // hoveredTourKeys = new Set([key]) -> that start's .signpost-marker has class 'highlighted'
})
```
Write each body fully with the file's existing fixtures (`tour`, `startById`, `routeCtx`, `renderLayer`); give the exit start a `name`. The cluster test renders at zoom 9 with two starts 0.01° apart so supercluster merges them.

- [ ] **Step 2: Run tests**

Run: `npx vitest run src/features/map/DiscoverLayer.test.tsx`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add -A src && git commit -m "test(ui): DiscoverLayer signpost marker behaviour" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 11: Docs and cleanup

**Files:**
- Modify: `CLAUDE.md` at `/home/superhellth/open-alps/.claude/CLAUDE.md` (App structure paragraph on `PlannerMap`/map layers)
- Modify: `docs/superpowers/STATUS.md`
- Delete: `docs/superpowers/plans/2026-09-25-discover-map-signposts.md` (only once the work has shipped, per the repo's plan rule)

- [ ] **Step 1: Update `.claude/CLAUDE.md`**

In the App structure section, extend the `PlannerMap` sentence to say Discover draws signpost markers (`SignpostMarker`: single board / stack that spreads on hover / cluster), waypoint symbols from `WaypointLayer`, and three emphasis tiers via `routePanes.ts`; and that Discover focus is a set of tour keys (`useDiscover`'s `focusTours`), hover a set of tour keys (`hoveredTourKeys`), with `tourKey` living in `tourSearch/tourKey.ts`. Keep it to the same density as the surrounding text.

- [ ] **Step 2: Full verification**

Run: `npx vitest run && npm run typecheck && npm run lint && npm run build`
Expected: all PASS.

- [ ] **Step 3: STATUS row and plan removal, commit**

Flip the spec's row in `docs/superpowers/STATUS.md` from `in progress` to `done`, delete this plan file, then:
```bash
cd /home/superhellth/open-alps
git add -A docs .claude huts && git commit -m "docs: discover map signposts shipped" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```
There is no `backlog.md` in the repo today; if the user adds one referencing this work, remove that item.

---

## Self-Review Notes

- **Spec coverage:** signpost kinds and tour boards (Tasks 2, 7, 9); spread, backdrop, hover intent, z-order, cap and overflow title, reduced motion, keyboard (Tasks 7, 8); waypoint symbols and unchanged trip/saved views (Tasks 4, 5, 6); tiers (Tasks 3, 5, 9); shared-leg and hut hover, tooltip, click focus, tour-set focus, no map-click drop (Tasks 3, 5, 6, 9); set-valued hover through list (Task 9); doc comment rewrite (Task 9); test list (Tasks 2, 3, 6, 8, 9, 10).
- **Spec deviations, on purpose:** leg identity is `layer:edgeId`, not `edgeId` alone (edge ids index per-layer tables); `tourKey` gains `exitStartId`; a leg/hut in exactly one tour picks it on click; the "selected" yellow fill applies to huts only (`startSymbolSvg` has no selected variant, as in `TripLayer`).
- **Not verified in a browser** (memory rule: no unrequested visual confirmation): spread column layout, arrow clip-paths, cluster two-arm look, board width and truncation. The CSS in Task 7 is a first pass for the user to tune.
