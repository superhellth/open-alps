# Tour Search Frontend Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this
> plan task-by-task, executing directly in this session on the current checkout. This repo's
> `.claude/CLAUDE.md` forbids git worktrees and forbids
> `superpowers:subagent-driven-development` (or any other worktree/subagent-spinning approach) —
> do **not** offer or use that option even though the writing-plans skill normally recommends it.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate `huts/` to strict TypeScript, fix two tour-search engine correctness bugs and one
exponential-blowup performance bug, and rebuild the UI on a unified MUI shell with a real results
pane and an in-page tour map — per the approved design spec.

**Architecture:** Bottom-up. Bootstrap TypeScript support first (Task 1), then port every
`tourSearch/*.js` leaf module to `.ts` in dependency order, folding in the two correctness fixes
and the dominance-pruning perf fix at their two existing chokepoints in `search.ts` (Tasks 12-13).
Then build the MUI shell (`theme.ts`, `AppShell.tsx`) and convert `App.jsx`/`GraphPage.jsx` to sit
under it unchanged behaviourally. Finally rebuild `TourSearchPage` in three passes — form, results
pane, map — since each is an independently reviewable deliverable, then add UI test infrastructure.

**Tech Stack:** TypeScript (strict), Vite + `@vitejs/plugin-react` (native `.ts`/`.tsx` support, no
build-tool change), `@mui/material` + `@emotion/react` + `@emotion/styled`, `vitest` +
`@testing-library/react` + `jsdom`, existing hash-based router (`main.tsx`), `react-leaflet`.

**Spec:** `docs/superpowers/specs/2026-08-26-tour-search-frontend-rewrite-design.md`

## Global Constraints

- `huts/tsconfig.json` has `"strict": true` — every new/converted file must typecheck under strict
  mode (no `any` unless truly unavoidable, no implicit any).
- Import specifiers keep their existing `.js` extension even after the target file is renamed to
  `.ts`/`.tsx` (e.g. `import { resolveVariant } from './resolveVariant.js'` continues to resolve to
  `resolveVariant.ts`). This is normal under `moduleResolution: "bundler"` — do not "fix" these to
  `.ts`.
- `SOURCE_TYPE_STATION = 1` / `SOURCE_TYPE_PARKING = 2` live in exactly one place:
  `huts/src/tourSearch/types.ts`. Every other file imports them from there — never redeclare.
- No engine change in Tasks 15-24 (UI work) — `findTours`/`loadTourSearchData`'s public shape is
  frozen after Task 14.
- No `pipeline/` changes anywhere in this plan (non-goal, see spec).
- German UI strings throughout (existing convention) — no i18n, no dark mode.
- Run `npm run typecheck`, `npm run lint`, and `npm test` (all from `huts/`) before every commit
  that touches `.ts`/`.tsx` files; a task is not done until all three are clean.

---

## Task 1: Bootstrap TypeScript — `tsconfig.json`, `typecheck` script, `types.ts`

**Files:**
- Create: `huts/tsconfig.json`
- Create: `huts/src/tourSearch/types.ts`
- Modify: `huts/package.json`

**Interfaces:**
- Produces: `SOURCE_TYPE_STATION`, `SOURCE_TYPE_PARKING`, `SourceType`, `ApproachRecord`,
  `HutEdgeRecord`, `LegBase`, `HutLeg`, `StartLeg`, `Leg`, `ChainState`, `LegSummary`, `TourResult`,
  `TourMode`, `Query`, `KillCounters`, `ReverseIndexEntry`, `HutEdgesData`, `ApproachesData`,
  `GraphData`, `SearchResult` — the canonical types every later task imports.

- [ ] **Step 1: Write `huts/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noEmit": true,
    "isolatedModules": true,
    "skipLibCheck": true,
    "resolveJsonModule": true,
    "esModuleInterop": true,
    "forceConsistentCasingInFileNames": true
  },
  "include": ["src"]
}
```

- [ ] **Step 2: Add `typescript` devDependency and `typecheck` script**

In `huts/package.json`, add to `"scripts"`:

```json
"typecheck": "tsc --noEmit",
```

Add to `"devDependencies"`:

```json
"typescript": "^5.7.3",
```

Run: `cd huts && npm install`

- [ ] **Step 3: Write `huts/src/tourSearch/types.ts`**

```typescript
export const SOURCE_TYPE_STATION = 1
export const SOURCE_TYPE_PARKING = 2

export type SourceType = typeof SOURCE_TYPE_STATION | typeof SOURCE_TYPE_PARKING

export interface ApproachRecord {
  hutIndex: number
  startId: number
  sourceType: SourceType
  accessUnknown: boolean
  distanceM: number
  ascentM: number
  descentM: number
  access: string | null
}

export interface HutEdgeRecord {
  fromIndex: number
  toIndex: number
  variant: number
  distanceM: number
  ascentM: number
  descentM: number
  maxEleM: number
  sacRank: number
  viaFerrata: boolean
  roadM: number
  ungradedM: number
  inferredM: number
  snapM: number
}

/** Fields legFilters.legPasses needs, present on every leg shape (hut-hut, approach, exit). */
export interface LegBase {
  distanceM: number
  ascentM: number
  descentM: number
  durationH: number
  maxEleM?: number
  viaFerrata?: boolean
}

export interface HutLeg extends LegBase {
  fromIndex: number
  toIndex: number
  variant: number
  maxEleM: number
  sacRank: number
  viaFerrata: boolean
  roadM: number
  ungradedM: number
  inferredM: number
  snapM: number
}

export interface StartLeg extends LegBase {
  startId: number
  sourceType: SourceType
  hutIndex?: number
  accessUnknown?: boolean
  access?: string | null
}

export type Leg = HutLeg | StartLeg

export interface ChainState {
  path: number[]
  startId: number
  totalDurationH: number
  totalAscentM: number
  totalDescentM: number
  totalDistanceM: number
}

/** One hop's numbers, in chain order: leg 0 is startId->huts[0], leg i (0<i<huts.length) is
 *  huts[i-1]->huts[i], and the last leg is huts[huts.length-1]->exitStartId. The UI derives
 *  from/to labels itself by zipping this array against [startId, ...huts, exitStartId] —
 *  the engine stays name-agnostic. */
export interface LegSummary {
  durationH: number
  ascentM: number
  descentM: number
  distanceM: number
}

export interface TourResult {
  huts: number[]
  startId: number
  exitStartId: number
  totalDurationH: number
  totalAscentM: number
  totalDescentM: number
  totalDistanceM: number
  legs: LegSummary[]
}

export type TourMode = 'car' | 'transit'

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
}

export interface KillCounters {
  maxLegTime: number
  minLegTime: number
  legAscentCap: number
  maxEleM: number
  viaFerrata: number
  revisit: number
}

export interface ReverseIndexEntry {
  hut_id: number
  start_id: number
  source_type: SourceType
  variant: number
  distance_m: number
  ascent_m: number
  descent_m: number
}

export interface HutEdgesData {
  hutIds: string[]
  variantNames: Record<string, string>
  records: HutEdgeRecord[]
}

export interface ApproachesData {
  records: ApproachRecord[]
  reverseIndex: {
    hut_to_starts: Record<string, ReverseIndexEntry[]>
    start_to_huts: Record<string, ReverseIndexEntry[]>
  }
}

export interface GraphData {
  hutEdges: HutEdgesData
  approaches: ApproachesData
}

export interface SearchResult {
  chains: TourResult[]
  killCounters: KillCounters
}
```

- [ ] **Step 4: Run typecheck**

Run: `cd huts && npm run typecheck`
Expected: PASS (no `.ts` files consume `types.ts` yet, but it must typecheck standalone).

- [ ] **Step 5: Commit**

```bash
git add huts/tsconfig.json huts/package.json huts/package-lock.json huts/src/tourSearch/types.ts
git commit -m "chore(huts): bootstrap TypeScript strict mode and canonical tourSearch types"
```

---

## Task 2: Port `binaryColumns.js` → `.ts`

**Files:**
- Modify (rename): `huts/src/tourSearch/binaryColumns.js` → `binaryColumns.ts`
- Modify (rename): `huts/src/tourSearch/binaryColumns.test.js` → `binaryColumns.test.ts`

**Interfaces:**
- Consumes: none (leaf module).
- Produces: `readColumns(buffer: ArrayBuffer, manifest: ColumnManifest): Record<string, number[]>`,
  `packColumns(columnDefs: Record<string, Dtype>, columnValues: Record<string, number[]>, rows: number): { manifest: ColumnManifest, buffer: ArrayBuffer }`,
  and the exported `Dtype`/`ColumnManifest` types other loaders import.

- [ ] **Step 1: Rename and type `binaryColumns.ts`**

```typescript
/**
 * Parses/builds the packed-column binary layout shared by hut-edge-payload.bin and
 * approaches.bin: each column is a contiguous run of `rows` values at its own dtype and
 * byte offset, NOT interleaved (docs/tour-suggestion-payload.md §1) — that layout is what
 * the pipeline's gzip-size measurements assume, so columns must be read independently.
 */
export type Dtype = 'u1' | 'i1' | 'u2' | 'u4' | 'u8' | 'f4'

export interface ColumnManifest {
  rows: number
  columns: Record<string, { dtype: Dtype; offset: number }>
  [key: string]: unknown
}

interface DtypeOps {
  bytes: number
  get: (v: DataView, o: number) => number
  set: (v: DataView, o: number, x: number) => void
}

const DTYPES: Record<Dtype, DtypeOps> = {
  u1: { bytes: 1, get: (v, o) => v.getUint8(o), set: (v, o, x) => v.setUint8(o, x) },
  i1: { bytes: 1, get: (v, o) => v.getInt8(o), set: (v, o, x) => v.setInt8(o, x) },
  u2: { bytes: 2, get: (v, o) => v.getUint16(o, true), set: (v, o, x) => v.setUint16(o, x, true) },
  u4: { bytes: 4, get: (v, o) => v.getUint32(o, true), set: (v, o, x) => v.setUint32(o, x, true) },
  u8: {
    bytes: 8,
    get: (v, o) => Number(v.getBigUint64(o, true)),
    set: (v, o, x) => v.setBigUint64(o, BigInt(x), true),
  },
  f4: { bytes: 4, get: (v, o) => v.getFloat32(o, true), set: (v, o, x) => v.setFloat32(o, x, true) },
}

export function readColumns(buffer: ArrayBuffer, manifest: ColumnManifest): Record<string, number[]> {
  const view = new DataView(buffer)
  const out: Record<string, number[]> = {}
  for (const [name, { dtype, offset }] of Object.entries(manifest.columns)) {
    const dt = DTYPES[dtype]
    if (!dt) throw new Error(`unsupported dtype "${dtype}" for column "${name}"`)
    const values = new Array<number>(manifest.rows)
    for (let i = 0; i < manifest.rows; i++) values[i] = dt.get(view, offset + i * dt.bytes)
    out[name] = values
  }
  return out
}

export function packColumns(
  columnDefs: Record<string, Dtype>,
  columnValues: Record<string, number[]>,
  rows: number,
): { manifest: ColumnManifest; buffer: ArrayBuffer } {
  let offset = 0
  const manifest: ColumnManifest = { rows, columns: {} }
  for (const [name, dtype] of Object.entries(columnDefs)) {
    manifest.columns[name] = { dtype, offset }
    offset += DTYPES[dtype].bytes * rows
  }
  const buffer = new ArrayBuffer(offset)
  const view = new DataView(buffer)
  for (const [name, dtype] of Object.entries(columnDefs)) {
    const dt = DTYPES[dtype]
    const colOffset = manifest.columns[name].offset
    const values = columnValues[name]
    for (let i = 0; i < rows; i++) dt.set(view, colOffset + i * dt.bytes, values[i])
  }
  return { manifest, buffer }
}
```

Run: `git -C huts mv src/tourSearch/binaryColumns.js src/tourSearch/binaryColumns.ts` then overwrite
with the content above.

- [ ] **Step 2: Rename `binaryColumns.test.ts` (content unchanged, only the `.js` imports become
  irrelevant since there are none — this file imports only from `./binaryColumns.js`, which still
  resolves)**

Run: `git -C huts mv src/tourSearch/binaryColumns.test.js src/tourSearch/binaryColumns.test.ts`

- [ ] **Step 3: Run tests and typecheck**

Run: `cd huts && npm test -- binaryColumns && npm run typecheck`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add huts/src/tourSearch/binaryColumns.ts huts/src/tourSearch/binaryColumns.test.ts
git commit -m "chore(huts): port binaryColumns to TypeScript"
```

---

## Task 3: Port `dinDuration.js` → `.ts`

**Files:**
- Modify (rename): `huts/src/tourSearch/dinDuration.js` → `dinDuration.ts`
- Modify (rename): `huts/src/tourSearch/dinDuration.test.js` → `dinDuration.test.ts`

**Interfaces:**
- Produces: `dinDurationH(distanceM: number, ascentM: number, descentM: number): number`

- [ ] **Step 1: Rename and type**

```typescript
/**
 * DIN 33466 hiking duration. Mirrors pipeline/lib/speed.py's din_duration_h() exactly —
 * this is the client-side half of a formula the pipeline deliberately does not ship a
 * precomputed value for (docs/tour-suggestion-payload.md §2).
 */
export function dinDurationH(distanceM: number, ascentM: number, descentM: number): number {
  const tHorizontal = distanceM / 4000
  const tVertical = ascentM / 300 + descentM / 500
  return Math.max(tHorizontal, tVertical) + Math.min(tHorizontal, tVertical) / 2
}
```

Run: `git -C huts mv src/tourSearch/dinDuration.js src/tourSearch/dinDuration.ts` then overwrite.

- [ ] **Step 2: Rename test file, content unchanged**

Run: `git -C huts mv src/tourSearch/dinDuration.test.js src/tourSearch/dinDuration.test.ts`

- [ ] **Step 3: Run tests and typecheck**

Run: `cd huts && npm test -- dinDuration && npm run typecheck`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add huts/src/tourSearch/dinDuration.ts huts/src/tourSearch/dinDuration.test.ts
git commit -m "chore(huts): port dinDuration to TypeScript"
```

---

## Task 4: Port `reverseLeg.js` → `.ts`

**Files:**
- Modify (rename): `huts/src/tourSearch/reverseLeg.js` → `reverseLeg.ts`
- Modify (rename): `huts/src/tourSearch/reverseLeg.test.js` → `reverseLeg.test.ts`

**Interfaces:**
- Consumes: `dinDurationH` from `./dinDuration.js`, `HutEdgeRecord`/`ApproachRecord` shapes from
  `./types.js`.
- Produces: `reverseHutLeg(record: HutEdgeRecord): HutLeg`, `forwardHutLeg(record: HutEdgeRecord): HutLeg`,
  `reverseStartLeg(record: ApproachRecord): StartLeg`, `forwardStartLeg(record: ApproachRecord): StartLeg`.

- [ ] **Step 1: Rename and type**

```typescript
import { dinDurationH } from './dinDuration.js'
import type { ApproachRecord, HutEdgeRecord, HutLeg, StartLeg } from './types.js'

function withDuration<T extends { distanceM: number; ascentM: number; descentM: number }>(
  leg: T,
): T & { durationH: number } {
  return { ...leg, durationH: dinDurationH(leg.distanceM, leg.ascentM, leg.descentM) }
}

/** Reverse-traversal contract (docs/tour-suggestion-payload.md §3): distance/road/sacRank/
 *  viaFerrata/maxEle/ungraded/inferred unchanged; ascent<->descent swapped; duration recomputed. */
export function reverseHutLeg(record: HutEdgeRecord): HutLeg {
  return withDuration({
    ...record,
    fromIndex: record.toIndex,
    toIndex: record.fromIndex,
    ascentM: record.descentM,
    descentM: record.ascentM,
  })
}

export function forwardHutLeg(record: HutEdgeRecord): HutLeg {
  return withDuration(record)
}

export function reverseStartLeg(record: ApproachRecord): StartLeg {
  return withDuration({ ...record, ascentM: record.descentM, descentM: record.ascentM })
}

export function forwardStartLeg(record: ApproachRecord): StartLeg {
  return withDuration(record)
}
```

Run: `git -C huts mv src/tourSearch/reverseLeg.js src/tourSearch/reverseLeg.ts` then overwrite.

- [ ] **Step 2: Rename test file, content unchanged**

Run: `git -C huts mv src/tourSearch/reverseLeg.test.js src/tourSearch/reverseLeg.test.ts`

- [ ] **Step 3: Run tests and typecheck**

Run: `cd huts && npm test -- reverseLeg && npm run typecheck`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add huts/src/tourSearch/reverseLeg.ts huts/src/tourSearch/reverseLeg.test.ts
git commit -m "chore(huts): port reverseLeg to TypeScript"
```

---

## Task 5: Port `resolveVariant.js` → `.ts`

**Files:**
- Modify (rename): `huts/src/tourSearch/resolveVariant.js` → `resolveVariant.ts`
- Modify (rename): `huts/src/tourSearch/resolveVariant.test.js` → `resolveVariant.test.ts`

**Interfaces:**
- Produces: `resolveVariant(query: { sacCeiling?: number | null; allowUngraded?: boolean }, variantNames: Record<string, string>): number`

- [ ] **Step 1: Rename and type**

```typescript
/**
 * Difficulty ceiling is a routing-relevant threshold, not a per-edge filter (spec Part 2's
 * filter/objective/variant table) — it resolves to exactly ONE variant row for the whole
 * query, never a per-edge sac_rank comparison. Filtering sac_rank on an unconstrained row
 * does not support the "every metre graded" claim (docs/tour-suggestion-payload.md §5).
 */
export function resolveVariant(
  { sacCeiling, allowUngraded = false }: { sacCeiling?: number | null; allowUngraded?: boolean } = {},
  variantNames: Record<string, string>,
): number {
  const idByName: Record<string, number> = {}
  for (const [id, name] of Object.entries(variantNames)) idByName[name] = Number(id)

  if (sacCeiling != null && sacCeiling <= 2) return idByName.FAST_T2
  if (sacCeiling != null && sacCeiling <= 3) return allowUngraded ? idByName.FAST_T3_UNGRADED : idByName.FAST_T3
  return idByName.FAST_ANY
}
```

Run: `git -C huts mv src/tourSearch/resolveVariant.js src/tourSearch/resolveVariant.ts` then overwrite.

- [ ] **Step 2: Rename test file, content unchanged**

Run: `git -C huts mv src/tourSearch/resolveVariant.test.js src/tourSearch/resolveVariant.test.ts`

- [ ] **Step 3: Run tests and typecheck**

Run: `cd huts && npm test -- resolveVariant && npm run typecheck`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add huts/src/tourSearch/resolveVariant.ts huts/src/tourSearch/resolveVariant.test.ts
git commit -m "chore(huts): port resolveVariant to TypeScript"
```

---

## Task 6: Port `legFilters.js` → `.ts`

**Files:**
- Modify (rename): `huts/src/tourSearch/legFilters.js` → `legFilters.ts`
- Modify (rename): `huts/src/tourSearch/legFilters.test.js` → `legFilters.test.ts`

**Interfaces:**
- Consumes: `LegBase`, `KillCounters` from `./types.js`.
- Produces: `createKillCounters(): KillCounters`, `legPasses(leg: LegBase, constraints: LegConstraints, killCounters: KillCounters): boolean`,
  and the exported `LegConstraints` type Task 12's `search.ts` reuses.

- [ ] **Step 1: Rename and type**

```typescript
import type { KillCounters, LegBase } from './types.js'

export interface LegConstraints {
  maxLegTimeH: number
  minLegTimeH: number
  legAscentCapM: number
  maxEleM: number | null
  allowViaFerrata: boolean
}

export function createKillCounters(): KillCounters {
  return { maxLegTime: 0, minLegTime: 0, legAscentCap: 0, maxEleM: 0, viaFerrata: 0, revisit: 0 }
}

/** No maxApproachTime: this predicate is applied identically to hut-hut, approach, and exit
 *  legs (root CLAUDE.md Global Constraints; spec Part 4). */
export function legPasses(leg: LegBase, constraints: LegConstraints, killCounters: KillCounters): boolean {
  const { maxLegTimeH, minLegTimeH, legAscentCapM, maxEleM, allowViaFerrata } = constraints

  if (leg.durationH > maxLegTimeH) { killCounters.maxLegTime++; return false }
  if (leg.durationH < minLegTimeH) { killCounters.minLegTime++; return false }
  if (leg.ascentM > legAscentCapM) { killCounters.legAscentCap++; return false }
  if (maxEleM != null && leg.maxEleM != null && leg.maxEleM > maxEleM) { killCounters.maxEleM++; return false }
  if (!allowViaFerrata && leg.viaFerrata) { killCounters.viaFerrata++; return false }
  return true
}
```

Run: `git -C huts mv src/tourSearch/legFilters.js src/tourSearch/legFilters.ts` then overwrite.

- [ ] **Step 2: Rename test file, content unchanged**

Run: `git -C huts mv src/tourSearch/legFilters.test.js src/tourSearch/legFilters.test.ts`

- [ ] **Step 3: Run tests and typecheck**

Run: `cd huts && npm test -- legFilters && npm run typecheck`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add huts/src/tourSearch/legFilters.ts huts/src/tourSearch/legFilters.test.ts
git commit -m "chore(huts): port legFilters to TypeScript"
```

---

## Task 7: Port `adjacency.js` → `.ts`

**Files:**
- Modify (rename): `huts/src/tourSearch/adjacency.js` → `adjacency.ts`
- Modify (rename): `huts/src/tourSearch/adjacency.test.js` → `adjacency.test.ts`

**Interfaces:**
- Consumes: `forwardHutLeg`, `reverseHutLeg` from `./reverseLeg.js`; `HutEdgesData`, `HutLeg` from `./types.js`.
- Produces: `buildAdjacency(hutEdgesData: HutEdgesData, variant: number): Map<number, HutLeg[]>`

- [ ] **Step 1: Rename and type**

```typescript
import { forwardHutLeg, reverseHutLeg } from './reverseLeg.js'
import type { HutEdgesData, HutLeg } from './types.js'

export function buildAdjacency(hutEdgesData: HutEdgesData, variant: number): Map<number, HutLeg[]> {
  const adjacency = new Map<number, HutLeg[]>()
  const push = (hutIndex: number, leg: HutLeg) => {
    if (!adjacency.has(hutIndex)) adjacency.set(hutIndex, [])
    adjacency.get(hutIndex)!.push(leg)
  }
  for (const record of hutEdgesData.records) {
    if (record.variant !== variant) continue
    push(record.fromIndex, forwardHutLeg(record))
    push(record.toIndex, reverseHutLeg(record))
  }
  return adjacency
}
```

Run: `git -C huts mv src/tourSearch/adjacency.js src/tourSearch/adjacency.ts` then overwrite.

- [ ] **Step 2: Rename test file, content unchanged**

Run: `git -C huts mv src/tourSearch/adjacency.test.js src/tourSearch/adjacency.test.ts`

- [ ] **Step 3: Run tests and typecheck**

Run: `cd huts && npm test -- adjacency && npm run typecheck`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add huts/src/tourSearch/adjacency.ts huts/src/tourSearch/adjacency.test.ts
git commit -m "chore(huts): port adjacency to TypeScript"
```

---

## Task 8: Port `approaches.js` → `.ts`

**Files:**
- Modify (rename): `huts/src/tourSearch/approaches.js` → `approaches.ts`
- Modify (rename): `huts/src/tourSearch/approaches.test.js` → `approaches.test.ts`

**Interfaces:**
- Consumes: `forwardStartLeg`, `reverseStartLeg` from `./reverseLeg.js`; `ApproachesData`, `StartLeg` from `./types.js`.
- Produces: `getApproachLegs(hutIndex: number, approachesData: ApproachesData): StartLeg[]`,
  `getExitLegs(hutIndex: number, variant: number, approachesData: ApproachesData): StartLeg[]`.

- [ ] **Step 1: Rename and type**

```typescript
import { forwardStartLeg, reverseStartLeg } from './reverseLeg.js'
import type { ApproachesData, StartLeg } from './types.js'

/** The curated k-best-per-hut table, FAST_ANY only (docs/tour-suggestion-payload.md §6):
 *  "an approach is a fastest, unconstrained leg to the hub, not a difficulty-graded one." */
export function getApproachLegs(hutIndex: number, approachesData: ApproachesData): StartLeg[] {
  return approachesData.records
    .filter((r) => r.hutIndex === hutIndex)
    .map((r) => forwardStartLeg(r))
}

/** Exits are the (all-variant) loop-closure reverse index, read backwards — a separate
 *  structure from the approach table on purpose (spec Part 4: "nothing extra is stored"). */
export function getExitLegs(hutIndex: number, variant: number, approachesData: ApproachesData): StartLeg[] {
  const entries = approachesData.reverseIndex.hut_to_starts[String(hutIndex)] || []
  return entries
    .filter((r) => r.variant === variant)
    .map((r) =>
      reverseStartLeg({
        hutIndex,
        startId: r.start_id,
        sourceType: r.source_type,
        accessUnknown: false,
        distanceM: r.distance_m,
        ascentM: r.ascent_m,
        descentM: r.descent_m,
        access: null,
      }),
    )
}
```

Run: `git -C huts mv src/tourSearch/approaches.js src/tourSearch/approaches.ts` then overwrite.

- [ ] **Step 2: Rename test file, content unchanged**

Run: `git -C huts mv src/tourSearch/approaches.test.js src/tourSearch/approaches.test.ts`

- [ ] **Step 3: Run tests and typecheck**

Run: `cd huts && npm test -- approaches && npm run typecheck`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add huts/src/tourSearch/approaches.ts huts/src/tourSearch/approaches.test.ts
git commit -m "chore(huts): port approaches to TypeScript"
```

---

## Task 9: Port `loadApproaches.js` → `.ts`

**Files:**
- Modify (rename): `huts/src/tourSearch/loadApproaches.js` → `loadApproaches.ts`
- Modify (rename): `huts/src/tourSearch/loadApproaches.test.js` → `loadApproaches.test.ts`

**Interfaces:**
- Consumes: `readColumns` from `./binaryColumns.js`; `ApproachesData`, `ApproachRecord` from `./types.js`.
- Produces: `loadApproachesData(baseUrl?: string): Promise<ApproachesData>`

- [ ] **Step 1: Rename and type**

```typescript
import { readColumns } from './binaryColumns.js'
import type { ApproachesData, ApproachRecord } from './types.js'

interface ApproachesManifest {
  rows: number
  columns: Record<string, { dtype: string; offset: number }>
  access_values?: (string | null)[]
  reverse_index: ApproachesData['reverseIndex']
}

export async function loadApproachesData(baseUrl = '/data'): Promise<ApproachesData> {
  const manifest: ApproachesManifest = await (await fetch(`${baseUrl}/approaches.json`)).json()
  const buffer = await (await fetch(`${baseUrl}/approaches.bin`)).arrayBuffer()
  const c = readColumns(buffer, manifest as unknown as Parameters<typeof readColumns>[1])

  const records = new Array<ApproachRecord>(manifest.rows)
  for (let i = 0; i < manifest.rows; i++) {
    records[i] = {
      hutIndex: c.hut_id[i], startId: c.start_id[i], sourceType: c.source_type[i] as ApproachRecord['sourceType'],
      accessUnknown: c.access_unknown[i] === 1, distanceM: c.distance_m[i],
      ascentM: c.ascent_m[i], descentM: c.descent_m[i],
      access: manifest.access_values ? manifest.access_values[i] : null,
    }
  }
  return { records, reverseIndex: manifest.reverse_index }
}
```

Run: `git -C huts mv src/tourSearch/loadApproaches.js src/tourSearch/loadApproaches.ts` then overwrite.

- [ ] **Step 2: Rename test file, content unchanged**

Run: `git -C huts mv src/tourSearch/loadApproaches.test.js src/tourSearch/loadApproaches.test.ts`

- [ ] **Step 3: Run tests and typecheck**

Run: `cd huts && npm test -- loadApproaches && npm run typecheck`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add huts/src/tourSearch/loadApproaches.ts huts/src/tourSearch/loadApproaches.test.ts
git commit -m "chore(huts): port loadApproaches to TypeScript"
```

---

## Task 10: Port `loadHutEdges.js` → `.ts`

**Files:**
- Modify (rename): `huts/src/tourSearch/loadHutEdges.js` → `loadHutEdges.ts`
- Modify (rename): `huts/src/tourSearch/loadHutEdges.test.js` → `loadHutEdges.test.ts`

**Interfaces:**
- Consumes: `readColumns` from `./binaryColumns.js`; `HutEdgesData`, `HutEdgeRecord` from `./types.js`.
- Produces: `loadHutEdgesData(baseUrl?: string): Promise<HutEdgesData>`

- [ ] **Step 1: Rename and type**

```typescript
import { readColumns } from './binaryColumns.js'
import type { HutEdgesData, HutEdgeRecord } from './types.js'

interface HutEdgesManifest {
  rows: number
  columns: Record<string, { dtype: string; offset: number }>
  hut_ids: string[]
  variants: Record<string, string>
}

export async function loadHutEdgesData(baseUrl = '/data'): Promise<HutEdgesData> {
  const manifest: HutEdgesManifest = await (await fetch(`${baseUrl}/hut-edge-payload.json`)).json()
  const buffer = await (await fetch(`${baseUrl}/hut-edge-payload.bin`)).arrayBuffer()
  const c = readColumns(buffer, manifest as unknown as Parameters<typeof readColumns>[1])

  const records = new Array<HutEdgeRecord>(manifest.rows)
  for (let i = 0; i < manifest.rows; i++) {
    records[i] = {
      fromIndex: c.from_id[i], toIndex: c.to_id[i], variant: c.variant[i],
      distanceM: c.distance_m[i], ascentM: c.ascent_m[i], descentM: c.descent_m[i],
      maxEleM: c.max_ele_m[i], sacRank: c.sac_rank[i], viaFerrata: c.via_ferrata[i] === 1,
      roadM: c.road_m[i], ungradedM: c.ungraded_m[i], inferredM: c.inferred_m[i], snapM: c.snap_m[i],
    }
  }
  return { hutIds: manifest.hut_ids, variantNames: manifest.variants, records }
}
```

Run: `git -C huts mv src/tourSearch/loadHutEdges.js src/tourSearch/loadHutEdges.ts` then overwrite.

- [ ] **Step 2: Rename test file, content unchanged**

Run: `git -C huts mv src/tourSearch/loadHutEdges.test.js src/tourSearch/loadHutEdges.test.ts`

- [ ] **Step 3: Run tests and typecheck**

Run: `cd huts && npm test -- loadHutEdges && npm run typecheck`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add huts/src/tourSearch/loadHutEdges.ts huts/src/tourSearch/loadHutEdges.test.ts
git commit -m "chore(huts): port loadHutEdges to TypeScript"
```

---

## Task 11: Port `diversity.js` → `.ts`

**Files:**
- Modify (rename): `huts/src/tourSearch/diversity.js` → `diversity.ts`
- Modify (rename): `huts/src/tourSearch/diversity.test.js` → `diversity.test.ts`

**Interfaces:**
- Consumes: nothing from `./types.js` directly — both functions are generic over the minimal
  shape they actually use, so the *existing* test fixtures (which build partial chain objects
  missing `exitStartId`/`legs`) keep typechecking unchanged, while production call sites (which
  pass real `TourResult[]`) also satisfy the bound.
- Produces: `dedupeReversePairs<T extends { huts: number[]; totalDurationH: number }>(chains: T[]): T[]`,
  `suppressSimilar<T extends { huts: number[]; startId: number; totalDurationH: number }>(chains: T[], overlapThreshold: number): T[]`.

- [ ] **Step 1: Rename and type**

```typescript
/**
 * Two separate diversity steps with two separate keys (spec Part 6, "Result diversity") —
 * this file must never merge them. Step 1: exact-duplicate removal on the ORDERED hut
 * sequence — a chain and its reverse are one tour walked two ways, and this step has no
 * threshold. Step 2: similarity suppression on the UNORDERED hut set.
 *
 * Generic over the minimal shape each function needs (not the full TourResult) so synthetic
 * test fixtures don't have to carry every TourResult field just to exercise this file.
 */
export function dedupeReversePairs<T extends { huts: number[]; totalDurationH: number }>(chains: T[]): T[] {
  const bestBySignature = new Map<string, T>()
  for (const chain of chains) {
    const forwardKey = chain.huts.join('>')
    const reverseKey = [...chain.huts].reverse().join('>')
    const canonicalKey = forwardKey < reverseKey ? forwardKey : reverseKey
    const existing = bestBySignature.get(canonicalKey)
    if (!existing || chain.totalDurationH < existing.totalDurationH) {
      bestBySignature.set(canonicalKey, chain)
    }
  }
  return [...bestBySignature.values()]
}

function hutOverlapFraction(a: { huts: number[] }, b: { huts: number[] }): number {
  const setA = new Set(a.huts)
  const setB = new Set(b.huts)
  let shared = 0
  for (const h of setA) if (setB.has(h)) shared++
  return shared / Math.min(setA.size, setB.size)
}

export function suppressSimilar<T extends { huts: number[]; startId: number; totalDurationH: number }>(
  chains: T[],
  overlapThreshold: number,
): T[] {
  const accepted: T[] = []
  for (const candidate of chains) {
    const tooSimilar = accepted.some(
      (a) => a.startId === candidate.startId || hutOverlapFraction(a, candidate) > overlapThreshold,
    )
    if (!tooSimilar) accepted.push(candidate)
  }
  return accepted
}
```

Run: `git -C huts mv src/tourSearch/diversity.js src/tourSearch/diversity.ts` then overwrite.

- [ ] **Step 2: Rename test file, content unchanged**

Run: `git -C huts mv src/tourSearch/diversity.test.js src/tourSearch/diversity.test.ts`

- [ ] **Step 3: Run tests and typecheck**

Run: `cd huts && npm test -- diversity && npm run typecheck`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add huts/src/tourSearch/diversity.ts huts/src/tourSearch/diversity.test.ts
git commit -m "chore(huts): port diversity to TypeScript"
```

---

## Task 12: Port `search.js` → `.ts` + Section A correctness fixes (mode-gated source types)

**Files:**
- Modify (rename): `huts/src/tourSearch/search.js` → `search.ts`
- Modify (rename): `huts/src/tourSearch/search.test.js` → `search.test.ts`

**Interfaces:**
- Consumes: `resolveVariant` from `./resolveVariant.js`, `buildAdjacency` from `./adjacency.js`,
  `getApproachLegs`/`getExitLegs` from `./approaches.js`, `legPasses`/`createKillCounters` from
  `./legFilters.js`, `SOURCE_TYPE_STATION`/`SOURCE_TYPE_PARKING`/`Query`/`GraphData`/`SearchResult`/
  `ChainState`/`TourResult` from `./types.js`.
- Produces: `searchChains(query: Query, graphData: GraphData): SearchResult` — same signature as
  before; behavior changes only in which chains are accepted.

This task fixes both bugs from spec section A at their two existing chokepoints:

1. **Seed step**: `getApproachLegs` results are filtered to `sourceType === SOURCE_TYPE_STATION`
   when `mode === 'transit'`, or `sourceType === SOURCE_TYPE_PARKING` when `mode === 'car'`.
2. **Finish step**: `getExitLegs` results get the same source-type filter, **in addition to** the
   existing `mode === 'car' → exitLeg.startId === s.startId` check (both must hold for car).

Dominance pruning (Section B) is **not** in this task — that's Task 13, on top of this file.

- [ ] **Step 1: Write the new mode-gating tests (append to the existing ported test file)**

First rename: `git -C huts mv src/tourSearch/search.js src/tourSearch/search.ts` (content
overwritten in Step 3) and `git -C huts mv src/tourSearch/search.test.js src/tourSearch/search.test.ts`.

Then edit `search.test.ts`: keep every existing `describe`/`it` block from the original file
verbatim (they still pass — the existing fixtures already use `sourceType: 2`, i.e. parking, for
both the approach and the reverse-index exit, so the parking-mode tests are unaffected by the new
gating), and append:

```typescript
import { SOURCE_TYPE_PARKING, SOURCE_TYPE_STATION } from './types.js'

describe('mode-gated source types (Section A fixes)', () => {
  const stationGraphData = {
    ...graphData,
    approaches: {
      records: [{ ...graphData.approaches.records[0], sourceType: SOURCE_TYPE_STATION }],
      reverseIndex: {
        hut_to_starts: {
          2: [{ ...graphData.approaches.reverseIndex.hut_to_starts[2][0], source_type: SOURCE_TYPE_STATION }],
        },
        start_to_huts: {},
      },
    },
  }

  it('transit mode seeds only from station-type approaches, rejecting a parking-only approach', () => {
    const { chains } = searchChains(
      { mode: 'transit', legCountMin: 3, legCountMax: 4, ...generousConstraints },
      graphData, // fixture approach is sourceType: 2 (parking)
    )
    expect(chains.some((c) => c.huts.length === 3)).toBe(false)
  })

  it('transit mode finds the chain once approach and exit are both station-type', () => {
    const { chains } = searchChains(
      { mode: 'transit', legCountMin: 3, legCountMax: 4, ...generousConstraints },
      stationGraphData,
    )
    const full = chains.find((c) => c.huts.length === 3)
    expect(full).toBeDefined()
    expect(full?.startId).toBe(100)
    expect(full?.exitStartId).toBe(200)
    // legs = [start->A, A->B, B->C, C->exit] = 4 entries for a 3-hut chain.
    expect(full?.legs).toHaveLength(4)
    const summedDuration = full!.legs.reduce((sum, l) => sum + l.durationH, 0)
    expect(summedDuration).toBeCloseTo(full!.totalDurationH, 6)
  })

  it('car mode rejects a loop closure at a station even when the start id matches the entry', () => {
    const loopStationGraphData = {
      ...stationGraphData,
      approaches: {
        ...stationGraphData.approaches,
        reverseIndex: {
          hut_to_starts: {
            2: [{ hut_id: 2, start_id: 100, source_type: SOURCE_TYPE_STATION, variant: 0, distance_m: 2000, ascent_m: 50, descent_m: 100 }],
          },
          start_to_huts: {},
        },
      },
    }
    const { chains } = searchChains(
      { mode: 'car', legCountMin: 3, legCountMax: 4, ...generousConstraints },
      loopStationGraphData,
    )
    // start ids match (100 == 100) but both are SOURCE_TYPE_STATION, not SOURCE_TYPE_PARKING —
    // car must still reject.
    expect(chains.some((c) => c.huts.length === 3)).toBe(false)
  })
})
```

(`SOURCE_TYPE_PARKING` import above is unused if you only add the three tests as written — drop it
from the import if your linter flags unused imports, or use it in an assertion comment; keep
`SOURCE_TYPE_STATION` either way.)

- [ ] **Step 2: Run the new tests to verify they fail against the old (pre-fix) behavior**

Run: `cd huts && npm test -- search.test`
Expected: FAIL on the three new tests (old code has no source-type gating at all, so the
"transit... rejecting a parking-only approach" and "car mode rejects a loop closure at a station"
tests fail; the middle test may pass or fail depending on old code's more permissive matching —
the exact pre-fix failure isn't asserted, only that at least the two rejection tests fail).

- [ ] **Step 3: Implement the TypeScript port with both correctness fixes**

Overwrite `huts/src/tourSearch/search.ts`:

```typescript
/**
 * The layered (hut, leg[, start_id]) exact DFS from spec Part 6, with dominance pruning by
 * visited-set (Task 13 adds this on top) and mode-gated source types (this task): transit
 * tours must start and finish at a station; car tours must start and finish at the same
 * parking lot.
 */
import { resolveVariant } from './resolveVariant.js'
import { buildAdjacency } from './adjacency.js'
import { getApproachLegs, getExitLegs } from './approaches.js'
import { legPasses, createKillCounters } from './legFilters.js'
import { SOURCE_TYPE_PARKING, SOURCE_TYPE_STATION } from './types.js'
import type { GraphData, LegSummary, Query, SearchResult, SourceType, TourResult } from './types.js'

function requiredSourceType(mode: Query['mode']): SourceType | null {
  if (mode === 'transit') return SOURCE_TYPE_STATION
  if (mode === 'car') return SOURCE_TYPE_PARKING
  return null
}

export function searchChains(query: Query, graphData: GraphData): SearchResult {
  const {
    mode, legCountMin, legCountMax, sacCeiling, allowUngraded = false,
    maxLegTimeH, minLegTimeH = 0, legAscentCapM = Infinity, maxEleM = null, allowViaFerrata = true,
  } = query
  const constraints = { maxLegTimeH, minLegTimeH, legAscentCapM, maxEleM, allowViaFerrata }
  const killCounters = createKillCounters()
  const gateSourceType = requiredSourceType(mode)

  const variant = resolveVariant({ sacCeiling, allowUngraded }, graphData.hutEdges.variantNames)
  const adjacency = buildAdjacency(graphData.hutEdges, variant)

  const nightsMin = legCountMin - 1
  const nightsMax = legCountMax - 1

  // layer: Map<hutIndex, State[]>, State = { path, startId, totalDurationH, totalAscentM, totalDescentM, totalDistanceM, legs }
  interface State {
    path: number[]
    startId: number
    totalDurationH: number
    totalAscentM: number
    totalDescentM: number
    totalDistanceM: number
    legs: LegSummary[]
  }
  function legSummary(leg: { durationH: number; ascentM: number; descentM: number; distanceM: number }): LegSummary {
    return { durationH: leg.durationH, ascentM: leg.ascentM, descentM: leg.descentM, distanceM: leg.distanceM }
  }
  let layer = new Map<number, State[]>()
  for (let h = 0; h < graphData.hutEdges.hutIds.length; h++) {
    for (const approachLeg of getApproachLegs(h, graphData.approaches)) {
      if (gateSourceType != null && approachLeg.sourceType !== gateSourceType) continue
      if (!legPasses(approachLeg, constraints, killCounters)) continue
      const state: State = {
        path: [h], startId: approachLeg.startId,
        totalDurationH: approachLeg.durationH, totalAscentM: approachLeg.ascentM,
        totalDescentM: approachLeg.descentM, totalDistanceM: approachLeg.distanceM,
        legs: [legSummary(approachLeg)],
      }
      if (!layer.has(h)) layer.set(h, [])
      layer.get(h)!.push(state)
    }
  }

  const finished: TourResult[] = []
  const collectFinished = (n: number) => {
    if (n < nightsMin) return
    for (const [h, states] of layer) {
      const exitLegs = getExitLegs(h, variant, graphData.approaches)
      for (const s of states) {
        for (const exitLeg of exitLegs) {
          if (mode === 'car' && exitLeg.startId !== s.startId) continue
          if (gateSourceType != null && exitLeg.sourceType !== gateSourceType) continue
          if (!legPasses(exitLeg, constraints, killCounters)) continue
          finished.push({
            huts: [...s.path], startId: s.startId, exitStartId: exitLeg.startId,
            totalDurationH: s.totalDurationH + exitLeg.durationH,
            totalAscentM: s.totalAscentM + exitLeg.ascentM,
            totalDescentM: s.totalDescentM + exitLeg.descentM,
            totalDistanceM: s.totalDistanceM + exitLeg.distanceM,
            legs: [...s.legs, legSummary(exitLeg)],
          })
        }
      }
    }
  }

  collectFinished(1)
  for (let n = 1; n < nightsMax; n++) {
    const nextLayer = new Map<number, State[]>()
    for (const [h, states] of layer) {
      const legs = adjacency.get(h) || []
      for (const s of states) {
        for (const leg of legs) {
          const h2 = leg.toIndex
          if (s.path.includes(h2)) { killCounters.revisit++; continue }
          if (!legPasses(leg, constraints, killCounters)) continue
          const next: State = {
            path: [...s.path, h2], startId: s.startId,
            totalDurationH: s.totalDurationH + leg.durationH,
            totalAscentM: s.totalAscentM + leg.ascentM,
            totalDescentM: s.totalDescentM + leg.descentM,
            totalDistanceM: s.totalDistanceM + leg.distanceM,
            legs: [...s.legs, legSummary(leg)],
          }
          if (!nextLayer.has(h2)) nextLayer.set(h2, [])
          nextLayer.get(h2)!.push(next)
        }
      }
    }
    layer = nextLayer
    collectFinished(n + 1)
  }

  finished.sort((a, b) => a.totalDurationH - b.totalDurationH)
  return { chains: finished, killCounters }
}
```

- [ ] **Step 4: Run tests and typecheck**

Run: `cd huts && npm test -- search.test && npm run typecheck`
Expected: PASS — all ported tests plus all three new mode-gating tests.

- [ ] **Step 5: Commit**

```bash
git add huts/src/tourSearch/search.ts huts/src/tourSearch/search.test.ts
git commit -m "fix(tour-search): gate approach/exit legs by source type per mode (TS port)"
```

---

## Task 13: Dominance pruning by visited-set (Section B performance fix)

**Files:**
- Modify: `huts/src/tourSearch/search.ts`
- Modify: `huts/src/tourSearch/search.test.ts`
- Modify: `huts/src/tourSearch/realData.smoke.test.js` → rename to `realData.smoke.test.ts`

**Interfaces:**
- Consumes: same as Task 12, plus `ChainState` shape extended internally with a `visitedKey: bigint`
  field (internal to `search.ts` — not exported, not part of `SearchResult`).
- Produces: same `searchChains(query, graphData): SearchResult` signature — only internal state
  storage and the resulting *number* of finished chains before diversity changes (never the set of
  distinct final results after diversity, per the spec's exactness argument).

**Key fact this relies on (from the spec):** a state's future expansion possibilities depend only
on `(currentHut, startId, visitedSet)`. Two states sharing that triple are functionally
interchangeable going forward — only the lower-`totalDurationH` one needs to survive.

- [ ] **Step 1: Write the exactness test in `search.test.ts` (append)**

This test compares the production (pruned) engine against a brute-force reference copy of the
pre-pruning algorithm — kept only in this test file — on a small synthetic "diamond" graph
specifically built so two different hut orderings reach the same hut with the same visited set
(`A→B→C→D` and `A→C→B→D` both end at `D` having visited `{A,B,C,D}`), which is exactly the case
dominance pruning collapses. It asserts that after normalizing away internal ordering (unordered
hut set + start/exit ids, keeping only the best duration per group — this normalization mirrors
what `suppressSimilar` already effectively does before either function fabricates or drops a
distinct final result), pruned and unpruned engines agree.

Append to `search.test.ts`:

```typescript
import type { GraphData, LegSummary, Query, TourResult } from './types.js'

/**
 * Pre-pruning reference implementation (Task 12's fixed mode-gating, no dominance collapsing) —
 * exists ONLY in this test file, to prove Task 13's pruning never drops a distinct final result.
 * Do not import this into production code.
 */
function bruteForceSearchChains(query: Query, graphData: GraphData) {
  const {
    mode, legCountMin, legCountMax, sacCeiling, allowUngraded = false,
    maxLegTimeH, minLegTimeH = 0, legAscentCapM = Infinity, maxEleM = null, allowViaFerrata = true,
  } = query
  const constraints = { maxLegTimeH, minLegTimeH, legAscentCapM, maxEleM, allowViaFerrata }
  const killCounters = createKillCounters()
  const gateSourceType = mode === 'transit' ? SOURCE_TYPE_STATION : mode === 'car' ? SOURCE_TYPE_PARKING : null

  const variant = resolveVariant({ sacCeiling, allowUngraded }, graphData.hutEdges.variantNames)
  const adjacency = buildAdjacency(graphData.hutEdges, variant)
  const nightsMin = legCountMin - 1
  const nightsMax = legCountMax - 1

  interface State { path: number[]; startId: number; totalDurationH: number; totalAscentM: number; totalDescentM: number; totalDistanceM: number; legs: LegSummary[] }
  function legSummary(leg: { durationH: number; ascentM: number; descentM: number; distanceM: number }): LegSummary {
    return { durationH: leg.durationH, ascentM: leg.ascentM, descentM: leg.descentM, distanceM: leg.distanceM }
  }
  let layer = new Map<number, State[]>()
  for (let h = 0; h < graphData.hutEdges.hutIds.length; h++) {
    for (const approachLeg of getApproachLegs(h, graphData.approaches)) {
      if (gateSourceType != null && approachLeg.sourceType !== gateSourceType) continue
      if (!legPasses(approachLeg, constraints, killCounters)) continue
      const state: State = { path: [h], startId: approachLeg.startId, totalDurationH: approachLeg.durationH, totalAscentM: approachLeg.ascentM, totalDescentM: approachLeg.descentM, totalDistanceM: approachLeg.distanceM, legs: [legSummary(approachLeg)] }
      if (!layer.has(h)) layer.set(h, [])
      layer.get(h)!.push(state)
    }
  }

  const finished: TourResult[] = []
  const collectFinished = (n: number) => {
    if (n < nightsMin) return
    for (const [h, states] of layer) {
      const exitLegs = getExitLegs(h, variant, graphData.approaches)
      for (const s of states) {
        for (const exitLeg of exitLegs) {
          if (mode === 'car' && exitLeg.startId !== s.startId) continue
          if (gateSourceType != null && exitLeg.sourceType !== gateSourceType) continue
          if (!legPasses(exitLeg, constraints, killCounters)) continue
          finished.push({ huts: [...s.path], startId: s.startId, exitStartId: exitLeg.startId, totalDurationH: s.totalDurationH + exitLeg.durationH, totalAscentM: s.totalAscentM + exitLeg.ascentM, totalDescentM: s.totalDescentM + exitLeg.descentM, totalDistanceM: s.totalDistanceM + exitLeg.distanceM, legs: [...s.legs, legSummary(exitLeg)] })
        }
      }
    }
  }

  collectFinished(1)
  for (let n = 1; n < nightsMax; n++) {
    const nextLayer = new Map<number, State[]>()
    for (const [h, states] of layer) {
      const legs = adjacency.get(h) || []
      for (const s of states) {
        for (const leg of legs) {
          const h2 = leg.toIndex
          if (s.path.includes(h2)) { killCounters.revisit++; continue }
          if (!legPasses(leg, constraints, killCounters)) continue
          const next: State = { path: [...s.path, h2], startId: s.startId, totalDurationH: s.totalDurationH + leg.durationH, totalAscentM: s.totalAscentM + leg.ascentM, totalDescentM: s.totalDescentM + leg.descentM, totalDistanceM: s.totalDistanceM + leg.distanceM, legs: [...s.legs, legSummary(leg)] }
          if (!nextLayer.has(h2)) nextLayer.set(h2, [])
          nextLayer.get(h2)!.push(next)
        }
      }
    }
    layer = nextLayer
    collectFinished(n + 1)
  }

  finished.sort((a, b) => a.totalDurationH - b.totalDurationH)
  return { chains: finished, killCounters }
}

function normalizeForComparison(chains: TourResult[]): string[] {
  const best = new Map<string, number>()
  for (const c of chains) {
    const key = `${[...c.huts].sort((a, b) => a - b).join(',')}|${c.startId}|${c.exitStartId}`
    const prev = best.get(key)
    if (prev === undefined || c.totalDurationH < prev) best.set(key, c.totalDurationH)
  }
  return [...best.entries()].map(([k, d]) => `${k}=${d.toFixed(4)}`).sort()
}

describe('dominance pruning (Section B) is exact', () => {
  // Diamond graph: A(seed)->B, A->C, B->C, B->D, C->D, all variant 0. A->B->C->D and A->C->B->D
  // both visit {A,B,C,D} and finish at D - exactly the case dominance pruning collapses.
  function edge(fromIndex: number, toIndex: number, distanceM: number) {
    return { fromIndex, toIndex, variant: 0, distanceM, ascentM: 100, descentM: 100, maxEleM: 2000, sacRank: 1, viaFerrata: false, roadM: 0, ungradedM: 0, inferredM: 0, snapM: 0 }
  }
  const diamondGraph: GraphData = {
    hutEdges: {
      hutIds: ['A', 'B', 'C', 'D'],
      variantNames: { 0: 'FAST_ANY' },
      records: [edge(0, 1, 3000), edge(0, 2, 4000), edge(1, 2, 2000), edge(1, 3, 3500), edge(2, 3, 3000)],
    },
    approaches: {
      records: [{ hutIndex: 0, startId: 100, sourceType: SOURCE_TYPE_STATION, accessUnknown: false, distanceM: 1000, ascentM: 50, descentM: 20, access: null }],
      reverseIndex: {
        hut_to_starts: {
          3: [{ hut_id: 3, start_id: 200, source_type: SOURCE_TYPE_STATION, variant: 0, distance_m: 1000, ascent_m: 20, descent_m: 50 }],
        },
        start_to_huts: {},
      },
    },
  }
  const query: Query = { mode: 'transit', legCountMin: 1, legCountMax: 6, maxLegTimeH: 10, minLegTimeH: 0, legAscentCapM: 9999, maxEleM: null, allowViaFerrata: true }

  it('produces the same normalized (hut-set, start, exit, best-duration) results as an unpruned reference', () => {
    const pruned = searchChains(query, diamondGraph)
    const unpruned = bruteForceSearchChains(query, diamondGraph)
    expect(normalizeForComparison(pruned.chains)).toEqual(normalizeForComparison(unpruned.chains))
  })
})
```

- [ ] **Step 2: Run to verify the new test passes against Task 12's un-pruned implementation**

Run: `cd huts && npm test -- search.test`
Expected: PASS (pruning isn't implemented yet, so pruned === unpruned trivially — this establishes
the baseline before Step 3 changes the implementation; re-run after Step 3 to confirm it still
passes with real pruning active).

- [ ] **Step 3: Implement dominance pruning in `search.ts`**

Replace the `State`/layer section of `huts/src/tourSearch/search.ts` (the `interface State` block
through the final `for (let n = 1; ...)` loop) with:

```typescript
  interface State {
    path: number[]
    startId: number
    totalDurationH: number
    totalAscentM: number
    totalDescentM: number
    totalDistanceM: number
    legs: LegSummary[]
    visitedKey: bigint
  }
  function legSummary(leg: { durationH: number; ascentM: number; descentM: number; distanceM: number }): LegSummary {
    return { durationH: leg.durationH, ascentM: leg.ascentM, descentM: leg.descentM, distanceM: leg.distanceM }
  }

  function insertDominant(bucket: Map<string, State>, key: string, state: State) {
    const existing = bucket.get(key)
    if (!existing || state.totalDurationH < existing.totalDurationH) bucket.set(key, state)
  }

  // layer: Map<hutIndex, Map<"startId|visitedKey", State>> — the inner map is the dominance
  // structure: at most one surviving state per (hutIndex, startId, visitedSet), the one with
  // the lower totalDurationH. hutIndex stays the outer key (unchanged from before) purely so
  // getExitLegs/adjacency.get(h) are still looked up once per hut, not once per state.
  let layer = new Map<number, Map<string, State>>()
  for (let h = 0; h < graphData.hutEdges.hutIds.length; h++) {
    for (const approachLeg of getApproachLegs(h, graphData.approaches)) {
      if (gateSourceType != null && approachLeg.sourceType !== gateSourceType) continue
      if (!legPasses(approachLeg, constraints, killCounters)) continue
      const visitedKey = 1n << BigInt(h)
      const state: State = {
        path: [h], startId: approachLeg.startId,
        totalDurationH: approachLeg.durationH, totalAscentM: approachLeg.ascentM,
        totalDescentM: approachLeg.descentM, totalDistanceM: approachLeg.distanceM,
        legs: [legSummary(approachLeg)],
        visitedKey,
      }
      if (!layer.has(h)) layer.set(h, new Map())
      insertDominant(layer.get(h)!, `${state.startId}|${visitedKey}`, state)
    }
  }

  const finished: TourResult[] = []
  const collectFinished = (n: number) => {
    if (n < nightsMin) return
    for (const [h, states] of layer) {
      const exitLegs = getExitLegs(h, variant, graphData.approaches)
      for (const s of states.values()) {
        for (const exitLeg of exitLegs) {
          if (mode === 'car' && exitLeg.startId !== s.startId) continue
          if (gateSourceType != null && exitLeg.sourceType !== gateSourceType) continue
          if (!legPasses(exitLeg, constraints, killCounters)) continue
          finished.push({
            huts: [...s.path], startId: s.startId, exitStartId: exitLeg.startId,
            totalDurationH: s.totalDurationH + exitLeg.durationH,
            totalAscentM: s.totalAscentM + exitLeg.ascentM,
            totalDescentM: s.totalDescentM + exitLeg.descentM,
            totalDistanceM: s.totalDistanceM + exitLeg.distanceM,
            legs: [...s.legs, legSummary(exitLeg)],
          })
        }
      }
    }
  }

  collectFinished(1)
  for (let n = 1; n < nightsMax; n++) {
    const nextLayer = new Map<number, Map<string, State>>()
    for (const [h, states] of layer) {
      const legs = adjacency.get(h) || []
      for (const s of states.values()) {
        for (const leg of legs) {
          const h2 = leg.toIndex
          if (s.path.includes(h2)) { killCounters.revisit++; continue }
          if (!legPasses(leg, constraints, killCounters)) continue
          const nextVisitedKey = s.visitedKey | (1n << BigInt(h2))
          const next: State = {
            path: [...s.path, h2], startId: s.startId,
            totalDurationH: s.totalDurationH + leg.durationH,
            totalAscentM: s.totalAscentM + leg.ascentM,
            totalDescentM: s.totalDescentM + leg.descentM,
            totalDistanceM: s.totalDistanceM + leg.distanceM,
            legs: [...s.legs, legSummary(leg)],
            visitedKey: nextVisitedKey,
          }
          if (!nextLayer.has(h2)) nextLayer.set(h2, new Map())
          insertDominant(nextLayer.get(h2)!, `${next.startId}|${nextVisitedKey}`, next)
        }
      }
    }
    layer = nextLayer
    collectFinished(n + 1)
  }
```

Note the local `legs` variable name in the expansion loop (`const legs = adjacency.get(h) || []`, the per-hut adjacency list) shadows the imported `LegSummary`-typed `legs` field on `State` — this shadowing already exists in the original pre-TS code and is harmless (different scopes), but keep it in mind when reading the diff.

The revisit check (`s.path.includes(h2)`) and the final `finished.sort(...)`/`return` are
unchanged — only the layer's storage type and the two insertion points (seed, expansion) change.

- [ ] **Step 4: Run tests and typecheck**

Run: `cd huts && npm test -- search.test && npm run typecheck`
Expected: PASS — including the exactness test from Step 1, now exercising real pruning.

- [ ] **Step 5: Extend the real-data smoke test to `legCountMax` up to 14**

Rename: `git -C huts mv src/tourSearch/realData.smoke.test.js src/tourSearch/realData.smoke.test.ts`.
This file already typechecks with only import-resolution changes (no `.js`→`.ts` content changes
needed beyond what strict mode requires — add explicit return types if `tsc` flags the two
`loadHutEdgesFromDisk`/`loadApproachesFromDisk` helpers; they should already infer correctly against
`HutEdgesData`/`ApproachesData` since Tasks 9-10 shaped those functions' return values identically).

Append a new test:

```typescript
it('an unanchored transit search stays usable up to legCountMax 14 (Section B target)', () => {
  const start = performance.now()
  const { chains } = findTours(
    {
      mode: 'transit', legCountMin: 2, legCountMax: 14,
      maxLegTimeH: 8, minLegTimeH: 0, legAscentCapM: 2000, allowViaFerrata: true,
      sacCeiling: 3, allowUngraded: true,
    },
    graphData,
  )
  const elapsedMs = performance.now() - start
  // No fixed wall-clock assertion (spec: "no fixed ms target was set") - this is a manual
  // benchmark during implementation. Print it so a human reviewing test output sees the number.
  console.log(`legCountMax=14 search took ${elapsedMs.toFixed(0)}ms, ${chains.length} chains`)
  for (const chain of chains) {
    expect(new Set(chain.huts).size).toBe(chain.huts.length)
  }
})
```

- [ ] **Step 6: Run the smoke test and record the manual benchmark**

Run: `cd huts && npm test -- realData.smoke`
Expected: PASS, completing in a reasonable time (seconds, not minutes — if it hangs or takes
minutes, that's a signal the pruning implementation has a bug, e.g. the dominance key is missing a
component; stop and debug before proceeding, don't just raise a timeout).

- [ ] **Step 7: Commit**

```bash
git add huts/src/tourSearch/search.ts huts/src/tourSearch/search.test.ts huts/src/tourSearch/realData.smoke.test.ts
git commit -m "perf(tour-search): dominance-prune search states by (hut, start, visited-set)"
```

---

## Task 14: Port `index.js` → `.ts`

**Files:**
- Modify (rename): `huts/src/tourSearch/index.js` → `index.ts`
- Modify (rename): `huts/src/tourSearch/index.test.js` → `index.test.ts`

**Interfaces:**
- Consumes: `loadHutEdgesData`, `loadApproachesData`, `searchChains`, `dedupeReversePairs`,
  `suppressSimilar`, `GraphData`, `Query`, `SearchResult` from their respective `./*.js` modules.
- Produces (public API, unchanged shape from the pre-TS version):
  `loadTourSearchData(baseUrl?: string): Promise<GraphData>`,
  `findTours(query: Query, graphData: GraphData, options?: { overlapThreshold?: number }): SearchResult`.

- [ ] **Step 1: Rename and type**

```typescript
import { loadHutEdgesData } from './loadHutEdges.js'
import { loadApproachesData } from './loadApproaches.js'
import { searchChains } from './search.js'
import { dedupeReversePairs, suppressSimilar } from './diversity.js'
import type { GraphData, Query, SearchResult } from './types.js'

export async function loadTourSearchData(baseUrl = '/data'): Promise<GraphData> {
  const [hutEdges, approaches] = await Promise.all([
    loadHutEdgesData(baseUrl),
    loadApproachesData(baseUrl),
  ])
  return { hutEdges, approaches }
}

export function findTours(
  query: Query,
  graphData: GraphData,
  { overlapThreshold = 0.5 }: { overlapThreshold?: number } = {},
): SearchResult {
  const { chains, killCounters } = searchChains(query, graphData)
  const deduped = dedupeReversePairs(chains)
  const diverse = suppressSimilar(deduped, overlapThreshold)
  return { chains: diverse, killCounters }
}
```

Run: `git -C huts mv src/tourSearch/index.js src/tourSearch/index.ts` then overwrite.

- [ ] **Step 2: Rename test file, content unchanged**

Run: `git -C huts mv src/tourSearch/index.test.js src/tourSearch/index.test.ts`

- [ ] **Step 3: Run tests and typecheck**

Run: `cd huts && npm test -- index.test && npm run typecheck`
Expected: PASS

- [ ] **Step 4: Full engine test suite + typecheck sanity pass**

Run: `cd huts && npm test && npm run typecheck && npm run lint`
Expected: PASS — this is the checkpoint confirming Sections A, B and the entire engine TS port
(Tasks 2-14) are done and green before UI work starts.

- [ ] **Step 5: Commit**

```bash
git add huts/src/tourSearch/index.ts huts/src/tourSearch/index.test.ts
git commit -m "chore(huts): port tourSearch index (public API) to TypeScript"
```

---

## Task 15: Add MUI dependencies + `theme.ts`

**Files:**
- Create: `huts/src/theme.ts`
- Modify: `huts/package.json`

**Interfaces:**
- Produces: `theme` (default export), a `Theme` from `createTheme()`.

- [ ] **Step 1: Add MUI dependencies**

Run: `cd huts && npm install @mui/material @emotion/react @emotion/styled`

- [ ] **Step 2: Write `huts/src/theme.ts`**

```typescript
import { createTheme } from '@mui/material/styles'

// Single source of truth for palette/spacing/typography (spec D). No dark-mode requirement
// today, but nothing here precludes adding a dark palette variant later.
const theme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: '#1b5e20' }, // matches the existing map header green
    secondary: { main: '#e65100' }, // matches GraphPage's edge-orange accent
  },
  typography: {
    fontFamily: 'system-ui, sans-serif',
  },
})

export default theme
```

- [ ] **Step 3: Typecheck**

Run: `cd huts && npm run typecheck`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add huts/package.json huts/package-lock.json huts/src/theme.ts
git commit -m "chore(huts): add MUI dependencies and shared theme"
```

---

## Task 16: `AppShell.tsx` — unified header/nav

**Files:**
- Create: `huts/src/AppShell.tsx`

**Interfaces:**
- Consumes: MUI `AppBar`/`Toolbar`/`Tabs`/`Tab`/`Box`.
- Produces: `AppShell({ title, status, children }: AppShellProps): JSX.Element` (default export),
  replacing the copy-pasted `<header>`/`.nav-link` block each page currently rolls on its own.

- [ ] **Step 1: Write `huts/src/AppShell.tsx`**

```tsx
import type { ReactNode } from 'react'
import { AppBar, Box, Tab, Tabs, Toolbar, Typography } from '@mui/material'

const TABS = [
  { hash: '', label: 'Karte' },
  { hash: '#graph', label: 'Trail-Graph' },
  { hash: '#tours', label: 'Tourensuche' },
] as const

interface AppShellProps {
  title: string
  status?: ReactNode
  children: ReactNode
}

function activeTabIndex(): number {
  const hash = window.location.hash
  const index = TABS.findIndex((t) => t.hash === hash)
  return index === -1 ? 0 : index
}

function AppShell({ title, status, children }: AppShellProps) {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <AppBar position="static" color="primary">
        <Toolbar sx={{ gap: 2, flexWrap: 'wrap' }}>
          <Typography variant="h6" component="h1" sx={{ fontSize: '1.1rem' }}>
            {title}
          </Typography>
          <Tabs
            value={activeTabIndex()}
            textColor="inherit"
            indicatorColor="secondary"
            sx={{ minHeight: 0 }}
          >
            {TABS.map((tab) => (
              <Tab
                key={tab.hash}
                label={tab.label}
                href={tab.hash || '#'}
                component="a"
                sx={{ minHeight: 0, color: 'inherit' }}
              />
            ))}
          </Tabs>
          <Box sx={{ marginLeft: 'auto', fontSize: '0.85rem', opacity: 0.85 }}>{status}</Box>
        </Toolbar>
      </AppBar>
      <Box sx={{ flex: 1, minHeight: 0, display: 'flex' }}>{children}</Box>
    </Box>
  )
}

export default AppShell
```

The active tab is recomputed from `window.location.hash` on every render; `main.tsx`'s
`useSyncExternalStore`-based router already re-renders its child (and therefore `AppShell`) on
`hashchange`, so no separate subscription is needed here.

- [ ] **Step 2: Typecheck**

Run: `cd huts && npm run typecheck`
Expected: PASS (nothing imports `AppShell` yet — this only checks the file standalone).

- [ ] **Step 3: Commit**

```bash
git add huts/src/AppShell.tsx
git commit -m "feat(huts): add MUI AppShell for unified header/nav"
```

---

## Task 17: `main.tsx` — TS port + `ThemeProvider`

**Files:**
- Modify (rename): `huts/src/main.jsx` → `main.tsx`

**Interfaces:**
- Consumes: `theme` from `./theme.js`, `App` from `./App.js` (post-Task-18 `.tsx`), `GraphPage`
  from `./GraphPage.js` (post-Task-19 `.tsx`), `TourSearchPage` from `./TourSearchPage.js`
  (post-Task-20+ `.tsx`).
- Produces: nothing exported — this is the app entry point.

Note: this task's import specifiers (`./App.jsx`, `./GraphPage.jsx`, `./TourSearchPage.jsx`) still
point at the *not-yet-renamed* files at this point in the plan; Tasks 18-20 update them in place
when those files move to `.tsx`. To keep every task independently green, do this task's rename now
but leave the extensions as `.jsx` in the import specifiers until Task 18 changes them (a `.jsx`
specifier resolves to a same-named `.tsx` file exactly like `.js` resolves to `.ts`, so this isn't
a temporary breakage — either extension resolves correctly on either side).

- [ ] **Step 1: Rename and type**

```tsx
import { StrictMode, useSyncExternalStore } from 'react'
import { createRoot } from 'react-dom/client'
import { ThemeProvider } from '@mui/material/styles'
import CssBaseline from '@mui/material/CssBaseline'
import './index.css'
import theme from './theme.js'
import App from './App.jsx'
import GraphPage from './GraphPage.jsx'
import TourSearchPage from './TourSearchPage.jsx'

function subscribeHash(callback: () => void) {
  window.addEventListener('hashchange', callback)
  return () => window.removeEventListener('hashchange', callback)
}

function Router() {
  const hash = useSyncExternalStore(subscribeHash, () => window.location.hash)
  if (hash === '#graph') return <GraphPage />
  if (hash === '#tours') return <TourSearchPage />
  return <App />
}

const rootElement = document.getElementById('root')
if (!rootElement) throw new Error('#root element not found')

createRoot(rootElement).render(
  <StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Router />
    </ThemeProvider>
  </StrictMode>,
)
```

Run: `git -C huts mv src/main.jsx src/main.tsx` then overwrite.

- [ ] **Step 2: Update `huts/index.html`'s script tag if it references `main.jsx` explicitly**

Run: `grep -n "main.jsx" huts/index.html`

If it references `/src/main.jsx`, update it to `/src/main.tsx` via Edit.

- [ ] **Step 3: Typecheck (expected partial failure until Tasks 18-20 land)**

Run: `cd huts && npm run typecheck`
Expected: this may report errors on the `App.jsx`/`GraphPage.jsx`/`TourSearchPage.jsx` imports if
`tsc` can't resolve a `.jsx` specifier to a same-named `.tsx` file under this project's exact
`moduleResolution` behavior in a mixed `.jsx`+`.tsx` tree. If so, don't fight it — jump straight to
updating the three import specifiers to `./App.js`, `./GraphPage.js`, `./TourSearchPage.js` now
(these still resolve correctly once Tasks 18-20 rename the targets to `.tsx`, per the Global
Constraints rule) instead of leaving them as `.jsx`. Re-run typecheck; it's expected to still show
errors here until Task 18 actually creates `App.tsx` — that's fine, this task's own deliverable is
the entry point content and wiring, not a fully green build (Task 18's own typecheck step is the
first one that must be clean end-to-end for `App`).

- [ ] **Step 4: Commit**

```bash
git add huts/src/main.tsx huts/index.html
git commit -m "chore(huts): port main entry point to TypeScript, wrap in MUI ThemeProvider"
```

---

## Task 18: `App.tsx` — TS port + AppShell integration

**Files:**
- Modify (rename): `huts/src/App.jsx` → `App.tsx`
- Modify: `huts/src/main.tsx` (import specifier, if Task 17 left it as `.jsx`)

**Interfaces:**
- Consumes: `AppShell` from `./AppShell.js`.
- Produces: `App(): JSX.Element` (default export) — same rendering behavior as before (all ~1173
  hut markers, station/parking toggles), restyled to sit under `AppShell` instead of rolling its
  own `<header>`.

- [ ] **Step 1: Rename and convert**

```tsx
import { useEffect, useState } from 'react'
import { MapContainer, TileLayer, CircleMarker, Tooltip } from 'react-leaflet'
import { Box, FormControlLabel, Switch } from '@mui/material'
import 'leaflet/dist/leaflet.css'
import AppShell from './AppShell.js'

const QUERY_URL =
  'https://services1.arcgis.com/PHS4LHADrqt5glC9/ArcGIS/rest/services/' +
  'AVT_GEO_CAA_HUETTEN_View_P/FeatureServer/0/query' +
  '?f=json&where=1%3D1&outFields=*&outSR=4326&returnGeometry=true' +
  '&resultRecordCount=8000&orderByFields=OBJECTID%20ASC'

const STATIONS_URL = '/data/stations.geojson'
const PARKING_URL = '/data/parking.geojson'

interface Hut {
  id: number
  name: string
  elevation: number | null
  category: string | null
  club: string | null
  lat: number
  lng: number
}

interface GeoPoint {
  id: number
  name: string | null
  lat: number
  lng: number
  [key: string]: unknown
}

interface ArcGisFeature {
  geometry?: { x: number; y: number }
  attributes: { OBJECTID: number; name: string; meereshoehe: number | null; kategorie: string | null; verein_name: string | null }
}

function pointsFromGeojson(fc: GeoJSON.FeatureCollection): GeoPoint[] {
  return fc.features.map((f, i) => ({
    id: i,
    name: (f.properties as Record<string, unknown> | null)?.name as string | null ?? null,
    ...(f.properties ?? {}),
    lat: (f.geometry as GeoJSON.Point).coordinates[1],
    lng: (f.geometry as GeoJSON.Point).coordinates[0],
  }))
}

function App() {
  const [huts, setHuts] = useState<Hut[]>([])
  const [stations, setStations] = useState<GeoPoint[]>([])
  const [parking, setParking] = useState<GeoPoint[]>([])
  const [showStations, setShowStations] = useState(false)
  const [showParking, setShowParking] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch(QUERY_URL)
      .then((r) => r.json())
      .then((data: { error?: { message: string }; features: ArcGisFeature[] }) => {
        if (data.error) throw new Error(data.error.message)
        setHuts(
          data.features
            .filter((f) => f.geometry)
            .map((f) => ({
              id: f.attributes.OBJECTID,
              name: f.attributes.name,
              elevation: f.attributes.meereshoehe,
              category: f.attributes.kategorie,
              club: f.attributes.verein_name,
              lat: f.geometry!.y,
              lng: f.geometry!.x,
            })),
        )
      })
      .catch((e: Error) => setError(e.message))

    fetch(STATIONS_URL)
      .then((r) => r.json())
      .then((fc: GeoJSON.FeatureCollection) => setStations(pointsFromGeojson(fc)))
      .catch((e: Error) => setError(e.message))

    fetch(PARKING_URL)
      .then((r) => r.json())
      .then((fc: GeoJSON.FeatureCollection) => setParking(pointsFromGeojson(fc)))
      .catch((e: Error) => setError(e.message))
  }, [])

  return (
    <AppShell
      title="Alpenvereinshütten"
      status={
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <span>{error ? `Fehler: ${error}` : `${huts.length} Hütten`}</span>
          <FormControlLabel
            control={<Switch size="small" checked={showStations} onChange={(e) => setShowStations(e.target.checked)} />}
            label="Bahnhöfe"
            sx={{ color: 'inherit', m: 0 }}
          />
          <FormControlLabel
            control={<Switch size="small" checked={showParking} onChange={(e) => setShowParking(e.target.checked)} />}
            label="Parkplätze"
            sx={{ color: 'inherit', m: 0 }}
          />
        </Box>
      }
    >
      <MapContainer center={[47.3, 12.0]} zoom={7} style={{ flex: 1 }}>
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> | Hüttendaten: Alpenverein / ArcGIS'
        />
        {huts.map((hut) => (
          <CircleMarker
            key={hut.id}
            center={[hut.lat, hut.lng]}
            radius={5}
            pathOptions={{ color: '#1b5e20', fillColor: '#43a047', fillOpacity: 0.9, weight: 1 }}
          >
            <Tooltip direction="top" offset={[0, -6]}>
              <strong>{hut.name}</strong>
              {hut.elevation ? <div>{hut.elevation} m</div> : null}
              {hut.category ? <div>{hut.category}</div> : null}
              {hut.club ? <div>{hut.club}</div> : null}
            </Tooltip>
          </CircleMarker>
        ))}
        {showParking &&
          parking.map((p) => (
            <CircleMarker
              key={`parking-${p.id}`}
              center={[p.lat, p.lng]}
              radius={3}
              pathOptions={{ color: '#0d47a1', fillColor: '#42a5f5', fillOpacity: 0.9, weight: 1 }}
            >
              <Tooltip direction="top" offset={[0, -6]}>
                <strong>{(p.name as string) || 'Parkplatz'}</strong>
                {p.capacity ? <div>{String(p.capacity)} Plätze</div> : null}
                {p.fee ? <div>Gebühr: {String(p.fee)}</div> : null}
              </Tooltip>
            </CircleMarker>
          ))}
        {showStations &&
          stations.map((s) => (
            <CircleMarker
              key={`station-${s.id}`}
              center={[s.lat, s.lng]}
              radius={4}
              pathOptions={{ color: '#e65100', fillColor: '#ff9800', fillOpacity: 0.9, weight: 1 }}
            >
              <Tooltip direction="top" offset={[0, -6]}>
                <strong>{(s.name as string) || 'Bahnhof'}</strong>
                {s.operator ? <div>{String(s.operator)}</div> : null}
              </Tooltip>
            </CircleMarker>
          ))}
      </MapContainer>
    </AppShell>
  )
}

export default App
```

`App.css`'s `.app`/`header`/`.nav-link`/`.layer-toggle` rules are now dead (AppShell replaces that
markup) — leave `App.css` in place for now since `GraphPage`/`TourSearchPage` still import it for
`.map`, `.edge-hover-panel` etc until Tasks 19-22 finish; a cleanup pass to drop the now-unused
header rules is optional and not required for this task's deliverable.

Run: `git -C huts mv src/App.jsx src/App.tsx` then overwrite.

- [ ] **Step 2: Fix `main.tsx`'s import if still `.jsx`**

If Task 17 left `import App from './App.jsx'`, change it to `import App from './App.js'` (Edit
`huts/src/main.tsx`).

- [ ] **Step 3: Typecheck**

Run: `cd huts && npm run typecheck`
Expected: PASS for `App.tsx` and `main.tsx`'s `App` import (may still show errors for the not-yet-
converted `GraphPage`/`TourSearchPage` imports — that's expected until Tasks 19-20 land).

- [ ] **Step 4: Manual smoke check**

Run: `cd huts && npm run dev` (background), open the app, confirm the map renders with the AppBar/
Tabs shell, hut markers, and both toggle switches working, then stop the dev server.

- [ ] **Step 5: Commit**

```bash
git add huts/src/App.tsx huts/src/main.tsx
git commit -m "feat(huts): port App to TypeScript, integrate AppShell"
```

---

## Task 19: `GraphPage.tsx` — TS port + AppShell integration

**Files:**
- Modify (rename): `huts/src/GraphPage.jsx` → `GraphPage.tsx`
- Modify: `huts/src/main.tsx` (import specifier, if still `.jsx`)

**Interfaces:**
- Consumes: `AppShell` from `./AppShell.js`.
- Produces: `GraphPage(): JSX.Element` (default export) — same rendering behavior (PMTiles trail/
  hut-edge layers, hover inspector, elevation sparklines), restyled to sit under `AppShell`.

- [ ] **Step 1: Rename and convert**

Port `huts/src/GraphPage.jsx` to `GraphPage.tsx` following the same pattern as Task 18: add
explicit types to every `useState`, every helper function's parameters/return, and every `Feature`/
`FeatureCollection` shape (use the `GeoJSON.FeatureCollection`/`GeoJSON.Feature` global types the
`@types/geojson` transitive dependency of `react-leaflet`/`leaflet` already provides — no new
dependency needed; verify with `grep -r geojson huts/node_modules/.package-lock.json` if `tsc`
complains the global isn't found, and add `"@types/geojson"` as an explicit devDependency only if
that grep comes up empty).

Concretely:
- `distToSegmentPx(p: L.Point, a: L.Point, b: L.Point): number`
- `distToPolylinePx(map: L.Map, cursorPt: L.Point, positions: L.LatLngExpression[]): number`
- `degreesPerPixel(map: L.Map, cursorPt: L.Point): number`
- `HoverInspector({ edges, onHover }: { edges: Edge[]; onHover: (hover: Hover | null) => void })`
  where `Edge` and `Hover` are new local interfaces:
  ```typescript
  interface Edge {
    fromId: number
    toId: number
    distanceM: number
    roadM: number
    ascentM: number | null
    descentM: number | null
    elevationProfile: number[] | null
    sacScale: string | null
    viaFerrata: boolean
    positions: L.LatLngExpression[]
    bounds: L.LatLngBounds
  }
  interface Hover { x: number; y: number; indices: number[] }
  ```
- `TrailTilesLayer({ visible }: { visible: boolean })`, `HutEdgeTilesLayer()` — no param types
  beyond the one prop each already has.
- `ElevationSparkline({ values }: { values: number[] | null | undefined })`
- `GraphPage()` — replace the `<div className="app"><header>...</header><MapContainer>` shell with
  `<AppShell title="Hütten-Trail-Graph" status={...}>` the same way Task 18 did for `App.tsx`, moving
  the hut/edge count `<span>` and the "OSM-Wege (roh)" toggle into the `status` slot (use MUI
  `FormControlLabel`/`Switch` for the toggle, matching Task 18's pattern). The `<MapContainer>`
  and the `hover`-panel `<div>` become `AppShell`'s children, kept exactly as before (the hover
  panel's inline `left`/`top` positioning and `edge-hover-panel`/`edge-hover-row`/
  `elevation-sparkline`/`edge-difficulty-badges`/`difficulty-badge`/`via-ferrata-badge` CSS classes
  from `App.css` are unchanged — this task doesn't touch that styling).

Run: `git -C huts mv src/GraphPage.jsx src/GraphPage.tsx` then apply the typed rewrite described
above (mechanical: add the interfaces and parameter/return types listed to the existing function
bodies from the pre-conversion file — no logic changes).

- [ ] **Step 2: Fix `main.tsx`'s import if still `.jsx`**

Change `import GraphPage from './GraphPage.jsx'` to `import GraphPage from './GraphPage.js'` if
needed.

- [ ] **Step 3: Typecheck**

Run: `cd huts && npm run typecheck`
Expected: PASS for `GraphPage.tsx` (may still show an error for `TourSearchPage`'s import until
Task 20 lands).

- [ ] **Step 4: Manual smoke check**

Run: `cd huts && npm run dev` (background), navigate to `#graph`, confirm the trail-graph map,
hover panel, and OSM-Wege toggle still work, then stop the dev server.

- [ ] **Step 5: Commit**

```bash
git add huts/src/GraphPage.tsx huts/src/main.tsx
git commit -m "feat(huts): port GraphPage to TypeScript, integrate AppShell"
```

---

## Task 20: `TourSearchPage.tsx` — MUI form (Sections D, D2)

**Files:**
- Create: `huts/src/TourSearchPage.tsx` (replaces `huts/src/TourSearchPage.jsx`)
- Delete: `huts/src/TourSearchPage.jsx`
- Modify: `huts/src/main.tsx` (import specifier, if still `.jsx`)

**Interfaces:**
- Consumes: `loadTourSearchData`, `findTours` from `./tourSearch/index.js`; `SOURCE_TYPE_STATION`,
  `SOURCE_TYPE_PARKING`, `Query`, `GraphData`, `SearchResult`, `TourMode` from
  `./tourSearch/types.js`; `AppShell` from `./AppShell.js`.
- Produces: `TourSearchPage(): JSX.Element` (default export). This task builds the form half only;
  Task 21 replaces the plain results `<ul>` with the full results pane, Task 22 adds the map. Wire
  a minimal placeholder results render (`{result && <pre>{JSON.stringify(result, null, 2)}</pre>}`)
  so the page is testable end-to-end after this task, to be replaced in Task 21.

This is the first of three passes over `TourSearchPage.tsx` (form → results → map) — each is
independently reviewable, matching spec sections D/D2, D1, and E respectively.

- [ ] **Step 1: Write the form-only `TourSearchPage.tsx`**

```tsx
import { useEffect, useMemo, useState } from 'react'
import {
  Alert, Box, Button, Checkbox, CircularProgress, FormControlLabel, MenuItem, Select,
  Slider, TextField, Typography,
} from '@mui/material'
import type { SelectChangeEvent } from '@mui/material'
import { loadTourSearchData, findTours } from './tourSearch/index.js'
import { SOURCE_TYPE_PARKING, SOURCE_TYPE_STATION } from './tourSearch/types.js'
import type { GraphData, Query, SearchResult, TourMode } from './tourSearch/types.js'
import AppShell from './AppShell.js'

const HUTS_URL = '/data/huts.geojson'
const PARKING_URL = '/data/parking.geojson'
const STATIONS_URL = '/data/stations.geojson'

const SOURCE_TYPE_LABEL: Record<number, string> = {
  [SOURCE_TYPE_STATION]: 'Bahnhof',
  [SOURCE_TYPE_PARKING]: 'Parkplatz',
}

// legCountMax above this is flagged as potentially slow in the UI (spec D2: "guard the
// expensive end of the range" - no Worker, no cancel, so an unexpected blowup freezes the tab).
const LEG_COUNT_SLOW_WARNING_THRESHOLD = 8

interface FormState {
  mode: TourMode
  legCountRange: [number, number]
  sacCeiling: number | 'any'
  allowUngraded: boolean
  legTimeRange: [number, number]
  legAscentCapM: string
  maxEleM: string
  allowViaFerrata: boolean
  overlapVariety: 'wenig' | 'mittel' | 'viel'
}

const DEFAULT_FORM: FormState = {
  mode: 'car',
  legCountRange: [2, 4],
  sacCeiling: 3,
  allowUngraded: true,
  legTimeRange: [0, 8],
  legAscentCapM: '',
  maxEleM: '',
  allowViaFerrata: true,
  overlapVariety: 'mittel',
}

const OVERLAP_THRESHOLD_BY_VARIETY: Record<FormState['overlapVariety'], number> = {
  wenig: 0.3,
  mittel: 0.5,
  viel: 0.8,
}

export interface StartPoint {
  name: string | null
  sourceType: number
  lat: number
  lng: number
}

// OSM feature ids in parking.geojson/stations.geojson are prefixed ("n123") - approaches.startId
// is the bare numeric OSM node id, so this strips the prefix to join the two.
function idFromOsmFeatureId(featureId: string | number): number | null {
  const n = Number(String(featureId).replace(/^\D+/, ''))
  return Number.isFinite(n) ? n : null
}

function toNumberOrDefault(value: string, fallback: number): number {
  if (value === '') return fallback
  const n = Number(value)
  return Number.isFinite(n) ? n : fallback
}

function buildQuery(form: FormState): Query {
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
  }
}

function TourSearchPage() {
  const [graphData, setGraphData] = useState<GraphData | null>(null)
  const [hutNameById, setHutNameById] = useState<Map<number, string>>(new Map())
  const [startById, setStartById] = useState<Map<number, StartPoint>>(new Map())
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState<FormState>(DEFAULT_FORM)
  const [result, setResult] = useState<SearchResult | null>(null)
  const [searching, setSearching] = useState(false)

  useEffect(() => {
    Promise.all([
      loadTourSearchData(),
      fetch(HUTS_URL).then((r) => r.json()) as Promise<GeoJSON.FeatureCollection>,
      fetch(PARKING_URL).then((r) => r.json()) as Promise<GeoJSON.FeatureCollection>,
      fetch(STATIONS_URL).then((r) => r.json()) as Promise<GeoJSON.FeatureCollection>,
    ])
      .then(([tourSearchData, hutsFc, parkingFc, stationsFc]) => {
        setGraphData(tourSearchData)
        setHutNameById(
          new Map(
            hutsFc.features.map((f) => [
              (f.properties as { id: number }).id,
              (f.properties as { name: string }).name,
            ]),
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
      .catch((e: Error) => setError(e.message))
  }, [])

  const startLabel = useMemo(
    () => (startId: number) => {
      const start = startById.get(startId)
      if (!start) return `Startpunkt ${startId}`
      const kind = SOURCE_TYPE_LABEL[start.sourceType] ?? 'Startpunkt'
      return start.name ? `${start.name} (${kind})` : kind
    },
    [startById],
  )

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!graphData) return
    setSearching(true)
    setResult(null)
    // Defer the heavy synchronous findTours call a tick so React can paint the spinner first
    // (spec D: no Web Worker in this spec's scope).
    setTimeout(() => {
      const query = buildQuery(form)
      const overlapThreshold = OVERLAP_THRESHOLD_BY_VARIETY[form.overlapVariety]
      setResult(findTours(query, graphData, { overlapThreshold }))
      setSearching(false)
    }, 0)
  }

  function handleReset() {
    setForm(DEFAULT_FORM)
    setResult(null)
  }

  const legCountTooHigh = form.legCountRange[1] > LEG_COUNT_SLOW_WARNING_THRESHOLD

  return (
    <AppShell
      title="Tourensuche"
      status={error ? `Fehler: ${error}` : graphData ? 'Daten geladen' : 'Lade Daten…'}
    >
      <Box sx={{ display: 'flex', flex: 1, minHeight: 0 }}>
        <Box
          component="form"
          onSubmit={handleSubmit}
          sx={{ display: 'flex', flexDirection: 'column', gap: 2, width: 320, flexShrink: 0, p: 2, overflowY: 'auto', borderRight: '1px solid #e0e0e0' }}
        >
          <Box>
            <Typography variant="subtitle2">Modus</Typography>
            <Select
              fullWidth
              size="small"
              value={form.mode}
              onChange={(e: SelectChangeEvent) => setForm((f) => ({ ...f, mode: e.target.value as TourMode }))}
            >
              <MenuItem value="car">Auto (Rundtour zum Ausgangspunkt)</MenuItem>
              <MenuItem value="transit">ÖPNV (offene Strecke)</MenuItem>
            </Select>
          </Box>

          <Box>
            <Typography variant="subtitle2">
              Etappen: {form.legCountRange[0]}–{form.legCountRange[1]}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {form.legCountRange[1]} Etappen = {form.legCountRange[1] - 1} Hütten ={' '}
              {form.legCountRange[1] - 1} Übernachtungen
            </Typography>
            <Slider
              value={form.legCountRange}
              onChange={(_e, value) => setForm((f) => ({ ...f, legCountRange: value as [number, number] }))}
              min={1}
              max={14}
              step={1}
              marks
              valueLabelDisplay="auto"
            />
            {legCountTooHigh && (
              <Alert severity="warning" sx={{ mt: 1 }}>
                Hohe Etappenzahl kann die Suche spürbar verlangsamen.
              </Alert>
            )}
          </Box>

          <Box>
            <Typography variant="subtitle2">Schwierigkeit (max. SAC-Skala)</Typography>
            <Select
              fullWidth
              size="small"
              value={form.sacCeiling}
              onChange={(e: SelectChangeEvent<number | 'any'>) =>
                setForm((f) => ({ ...f, sacCeiling: e.target.value === 'any' ? 'any' : Number(e.target.value) }))
              }
            >
              <MenuItem value={1}>T1 Wandern</MenuItem>
              <MenuItem value={2}>T2 Bergwandern</MenuItem>
              <MenuItem value={3}>T3 anspruchsvolles Bergwandern</MenuItem>
              <MenuItem value="any">beliebig</MenuItem>
            </Select>
          </Box>

          <FormControlLabel
            control={<Checkbox checked={form.allowUngraded} onChange={(e) => setForm((f) => ({ ...f, allowUngraded: e.target.checked }))} />}
            label="auch ungeratete Wege erlauben"
          />

          <Box>
            <Typography variant="subtitle2">Gehzeit pro Etappe (Stunden)</Typography>
            <Box sx={{ display: 'flex', gap: 1 }}>
              <TextField
                size="small"
                type="number"
                label="min"
                inputProps={{ min: 0, step: 0.5 }}
                value={form.legTimeRange[0]}
                onChange={(e) => setForm((f) => ({ ...f, legTimeRange: [Number(e.target.value), f.legTimeRange[1]] }))}
              />
              <TextField
                size="small"
                type="number"
                label="max"
                inputProps={{ min: 0, step: 0.5 }}
                value={form.legTimeRange[1]}
                onChange={(e) => setForm((f) => ({ ...f, legTimeRange: [f.legTimeRange[0], Number(e.target.value)] }))}
              />
            </Box>
          </Box>

          <TextField
            size="small"
            type="number"
            label="Anstiegslimit pro Etappe (m, leer = unbegrenzt)"
            inputProps={{ min: 0 }}
            value={form.legAscentCapM}
            onChange={(e) => setForm((f) => ({ ...f, legAscentCapM: e.target.value }))}
          />

          <TextField
            size="small"
            type="number"
            label="Maximalhöhe (m, leer = unbegrenzt)"
            value={form.maxEleM}
            onChange={(e) => setForm((f) => ({ ...f, maxEleM: e.target.value }))}
          />

          <FormControlLabel
            control={<Checkbox checked={form.allowViaFerrata} onChange={(e) => setForm((f) => ({ ...f, allowViaFerrata: e.target.checked }))} />}
            label="Klettersteige erlauben"
          />

          <Box>
            <Typography variant="subtitle2">Variantenvielfalt</Typography>
            <Select
              fullWidth
              size="small"
              value={form.overlapVariety}
              onChange={(e: SelectChangeEvent) => setForm((f) => ({ ...f, overlapVariety: e.target.value as FormState['overlapVariety'] }))}
            >
              <MenuItem value="wenig">wenig (ähnliche Touren zusammenfassen)</MenuItem>
              <MenuItem value="mittel">mittel</MenuItem>
              <MenuItem value="viel">viel (auch ähnliche Touren zeigen)</MenuItem>
            </Select>
          </Box>

          <Box sx={{ display: 'flex', gap: 1, mt: 1 }}>
            <Button type="submit" variant="contained" disabled={!graphData || searching} startIcon={searching ? <CircularProgress size={16} color="inherit" /> : undefined}>
              Touren suchen
            </Button>
            <Button type="button" variant="outlined" onClick={handleReset}>
              Zurücksetzen
            </Button>
          </Box>
        </Box>

        <Box sx={{ flex: 1, overflowY: 'auto', p: 2 }}>
          {result && <pre>{JSON.stringify(result, (k, v) => (typeof v === 'bigint' ? v.toString() : v), 2)}</pre>}
        </Box>
      </Box>
    </AppShell>
  )
}

export default TourSearchPage
```

Delete the old file: `git -C huts rm src/TourSearchPage.jsx` (the new `.tsx` file above replaces
it; this isn't a `git mv` because the content is a substantial rewrite, not a mechanical port).

- [ ] **Step 2: Fix `main.tsx`'s import if still `.jsx`**

Change `import TourSearchPage from './TourSearchPage.jsx'` to `import TourSearchPage from './TourSearchPage.js'`.

- [ ] **Step 3: Typecheck**

Run: `cd huts && npm run typecheck`
Expected: PASS — this is the first fully-green typecheck across the whole `src/` tree since Task 1.

- [ ] **Step 4: Manual smoke check**

Run: `cd huts && npm run dev` (background), navigate to `#tours`, fill the form (try both modes,
adjust the leg-count slider past 8 to confirm the warning appears, T1 in the SAC select), submit,
confirm the spinner shows briefly and the raw JSON result renders, click "Zurücksetzen" and confirm
the form returns to defaults. Stop the dev server.

- [ ] **Step 5: Commit**

```bash
git add huts/src/TourSearchPage.tsx huts/src/main.tsx
git rm huts/src/TourSearchPage.jsx 2>/dev/null || true
git commit -m "feat(huts): rebuild TourSearchPage form on MUI (Sections D, D2)"
```

---

## Task 21: `TourSearchPage.tsx` — results pane (Section D1)

**Files:**
- Modify: `huts/src/TourSearchPage.tsx`

**Interfaces:**
- Consumes: `TourResult`, `KillCounters` from `./tourSearch/types.js`; the `startById`/
  `hutNameById`/`startLabel` state and helper already present from Task 20.
- Produces: extends `TourSearchPage` with a real results pane — sort, pagination, region filter,
  per-leg breakdown, translated `killCounters`. No change to the component's exported shape (still
  the page's default export).

This task replaces the `<pre>{JSON.stringify(result...)}</pre>` placeholder from Task 20 with the
full presentation designed in spec D1.

- [ ] **Step 1: Add sort/pagination/region-filter state and derived data**

In `huts/src/TourSearchPage.tsx`, add near the top (after the existing constants):

```tsx
const PAGE_SIZE = 25

type SortKey = 'duration' | 'ascent' | 'distance' | 'legCount'

const SORT_COMPARATORS: Record<SortKey, (a: TourResult, b: TourResult) => number> = {
  duration: (a, b) => a.totalDurationH - b.totalDurationH,
  ascent: (a, b) => a.totalAscentM - b.totalAscentM,
  distance: (a, b) => a.totalDistanceM - b.totalDistanceM,
  legCount: (a, b) => a.huts.length - b.huts.length,
}

const SORT_LABEL: Record<SortKey, string> = {
  duration: 'Gesamtdauer',
  ascent: 'Anstieg',
  distance: 'Distanz',
  legCount: 'Etappenzahl',
}

// Translates raw kill-counter keys into actionable German guidance (spec D1: killCounters must
// not be rendered raw). Shown only in the empty-results state.
const KILL_COUNTER_GUIDANCE: Record<string, (n: number) => string> = {
  maxLegTime: (n) => `${n} Etappen waren zu lang — maximale Gehzeit erhöhen`,
  minLegTime: (n) => `${n} Etappen waren zu kurz — minimale Gehzeit senken`,
  legAscentCap: (n) => `${n} Etappen hatten zu viel Anstieg — Anstiegslimit erhöhen`,
  maxEleM: (n) => `${n} Etappen lagen über der Maximalhöhe — Maximalhöhe erhöhen`,
  viaFerrata: (n) => `${n} Etappen enthielten Klettersteige — "Klettersteige erlauben" aktivieren`,
  revisit: () => '', // internal search bookkeeping, not user-actionable
}

function killCounterGuidance(killCounters: SearchResult['killCounters']): string[] {
  return Object.entries(killCounters)
    .filter(([key, n]) => n > 0 && KILL_COUNTER_GUIDANCE[key]?.(n))
    .map(([key, n]) => KILL_COUNTER_GUIDANCE[key](n))
}

// Zips chain.legs (engine-side, name-agnostic) against the point sequence [start, ...huts, exit]
// to produce one "from → to" label per leg, without the engine ever knowing about hut/start names.
function legWaypointLabels(
  chain: TourResult,
  startLabel: (startId: number) => string,
  hutNameById: Map<number, string>,
): string[] {
  const pointLabels = [
    startLabel(chain.startId),
    ...chain.huts.map((h) => hutNameById.get(h) ?? String(h)),
    startLabel(chain.exitStartId),
  ]
  const labels: string[] = []
  for (let i = 0; i < pointLabels.length - 1; i++) labels.push(`${pointLabels[i]} → ${pointLabels[i + 1]}`)
  return labels
}

function haversineKm(a: { lat: number; lng: number }, b: { lat: number; lng: number }): number {
  const R = 6371
  const dLat = ((b.lat - a.lat) * Math.PI) / 180
  const dLng = ((b.lng - a.lng) * Math.PI) / 180
  const sinLat = Math.sin(dLat / 2)
  const sinLng = Math.sin(dLng / 2)
  const h = sinLat * sinLat + Math.cos((a.lat * Math.PI) / 180) * Math.cos((b.lat * Math.PI) / 180) * sinLng * sinLng
  return 2 * R * Math.asin(Math.sqrt(h))
}
```

Add `TourResult`, `SearchResult` to the existing `import type { GraphData, Query, SearchResult, TourMode } from './tourSearch/types.js'` line (change to
`import type { GraphData, Query, SearchResult, TourMode, TourResult } from './tourSearch/types.js'`).

Inside the `TourSearchPage` component, add state:

```tsx
const [sortKey, setSortKey] = useState<SortKey>('duration')
const [page, setPage] = useState(1)
const [regionCenterId, setRegionCenterId] = useState<number | 'all'>('all')
const [regionRadiusKm, setRegionRadiusKm] = useState('50')
const [expandedChain, setExpandedChain] = useState<number | null>(null)
```

- [ ] **Step 2: Derive the filtered/sorted/paginated chain list**

Add, after the `startLabel` `useMemo`:

```tsx
const displayedChains = useMemo(() => {
  if (!result) return []
  let chains = [...result.chains]
  if (regionCenterId !== 'all') {
    const center = startById.get(regionCenterId)
    const radiusKm = toNumberOrDefault(regionRadiusKm, Infinity)
    if (center) {
      chains = chains.filter((c) => {
        const start = startById.get(c.startId)
        const end = startById.get(c.exitStartId)
        return (
          (start && haversineKm(center, start) <= radiusKm) ||
          (end && haversineKm(center, end) <= radiusKm)
        )
      })
    }
  }
  chains.sort(SORT_COMPARATORS[sortKey])
  return chains
}, [result, sortKey, regionCenterId, regionRadiusKm, startById])

const pageCount = Math.max(1, Math.ceil(displayedChains.length / PAGE_SIZE))
const pageChains = displayedChains.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
```

Reset `page` to 1 whenever `result` changes — add to `handleSubmit`, right after `setResult(...)`:
`setPage(1)`.

- [ ] **Step 3: Replace the placeholder results `<Box>` with the full pane**

Replace:

```tsx
<Box sx={{ flex: 1, overflowY: 'auto', p: 2 }}>
  {result && <pre>{JSON.stringify(result, (k, v) => (typeof v === 'bigint' ? v.toString() : v), 2)}</pre>}
</Box>
```

with:

```tsx
<Box sx={{ flex: 1, overflowY: 'auto', p: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
  {result && (
    <>
      <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', alignItems: 'center' }}>
        <Typography color="text.secondary">
          {displayedChains.length} Tour{displayedChains.length === 1 ? '' : 'en'} gefunden
        </Typography>
        <Select size="small" value={sortKey} onChange={(e: SelectChangeEvent) => setSortKey(e.target.value as SortKey)}>
          {(Object.keys(SORT_LABEL) as SortKey[]).map((key) => (
            <MenuItem key={key} value={key}>
              Sortieren: {SORT_LABEL[key]}
            </MenuItem>
          ))}
        </Select>
        <Select
          size="small"
          value={regionCenterId}
          onChange={(e: SelectChangeEvent) => setRegionCenterId(e.target.value === 'all' ? 'all' : Number(e.target.value))}
        >
          <MenuItem value="all">Alle Regionen</MenuItem>
          {[...startById.entries()].map(([id, start]) => (
            <MenuItem key={id} value={id}>
              Nahe: {start.name ?? SOURCE_TYPE_LABEL[start.sourceType]}
            </MenuItem>
          ))}
        </Select>
        {regionCenterId !== 'all' && (
          <TextField
            size="small"
            type="number"
            label="Radius (km)"
            value={regionRadiusKm}
            onChange={(e) => setRegionRadiusKm(e.target.value)}
            sx={{ width: 120 }}
          />
        )}
      </Box>

      {displayedChains.length === 0 && (
        <Box>
          <Typography>Keine Touren gefunden. Filter lockern und erneut versuchen.</Typography>
          {killCounterGuidance(result.killCounters).map((msg, i) => (
            <Alert key={i} severity="info" sx={{ mt: 1 }}>
              {msg}
            </Alert>
          ))}
        </Box>
      )}

      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        {pageChains.map((chain, i) => {
          const chainIndex = (page - 1) * PAGE_SIZE + i
          const isExpanded = expandedChain === chainIndex
          return (
            <Card key={chainIndex} variant="outlined">
              <CardActionArea onClick={() => setExpandedChain(isExpanded ? null : chainIndex)}>
                <CardContent>
                  <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                    {startLabel(chain.startId)} → … → {startLabel(chain.exitStartId)}
                  </Typography>
                  <Typography color="text.secondary" variant="body2">
                    {chain.totalDurationH.toFixed(1)} h · ↑{Math.round(chain.totalAscentM)}m ↓
                    {Math.round(chain.totalDescentM)}m · {(chain.totalDistanceM / 1000).toFixed(1)} km ·{' '}
                    {chain.huts.length} Etappen
                  </Typography>
                </CardContent>
              </CardActionArea>
              {isExpanded && (
                <CardContent sx={{ pt: 0 }}>
                  <Typography variant="body2" sx={{ mb: 1 }}>
                    {startLabel(chain.startId)}
                    {chain.huts.map((h) => ` → ${hutNameById.get(h) ?? h}`).join('')}
                    {' → '}
                    {startLabel(chain.exitStartId)}
                  </Typography>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Etappe</TableCell>
                        <TableCell align="right">Dauer</TableCell>
                        <TableCell align="right">↑</TableCell>
                        <TableCell align="right">↓</TableCell>
                        <TableCell align="right">Distanz</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {legWaypointLabels(chain, startLabel, hutNameById).map((label, legIndex) => {
                        const leg = chain.legs[legIndex]
                        return (
                          <TableRow key={legIndex}>
                            <TableCell>{label}</TableCell>
                            <TableCell align="right">{leg.durationH.toFixed(1)} h</TableCell>
                            <TableCell align="right">{Math.round(leg.ascentM)}m</TableCell>
                            <TableCell align="right">{Math.round(leg.descentM)}m</TableCell>
                            <TableCell align="right">{(leg.distanceM / 1000).toFixed(1)} km</TableCell>
                          </TableRow>
                        )
                      })}
                    </TableBody>
                  </Table>
                </CardContent>
              )}
            </Card>
          )
        })}
      </Box>

      {pageCount > 1 && (
        <Pagination count={pageCount} page={page} onChange={(_e, p) => setPage(p)} sx={{ alignSelf: 'center' }} />
      )}
    </>
  )}
</Box>
```

Add `Card`, `CardActionArea`, `CardContent`, `Pagination`, `Table`, `TableBody`, `TableCell`,
`TableHead`, `TableRow` to the existing MUI import line at the top of the file, and add
`TourResult` to the `import type { GraphData, Query, SearchResult, TourMode, TourResult } from
'./tourSearch/types.js'` line if Step 1 hadn't already added it.

**Per-leg breakdown data source:** Task 12/13's `search.ts` now populates `TourResult.legs:
LegSummary[]` (one entry per hop: `startId→huts[0]`, each `huts[i-1]→huts[i]`, and
`huts[last]→exitStartId`, in that order — see `types.ts`'s `LegSummary` doc comment). This table
zips that array against the point-name sequence via `legWaypointLabels` above, so the engine never
has to know about hut/start names — only the UI resolves labels.

- [ ] **Step 4: Typecheck**

Run: `cd huts && npm run typecheck`
Expected: PASS

- [ ] **Step 5: Manual smoke check**

Run: `cd huts && npm run dev` (background), search with broad filters to get 25+ results, confirm
pagination appears and pages correctly, change the sort selector and confirm order changes, pick a
region filter and confirm the count shrinks, click a card to expand/collapse its route detail, then
run a search guaranteed to return zero chains (e.g. `maxLegTimeH` near 0) and confirm translated
guidance appears instead of raw counter keys. Stop the dev server.

- [ ] **Step 6: Commit**

```bash
git add huts/src/TourSearchPage.tsx
git commit -m "feat(huts): add sort/pagination/region-filter results pane (Section D1)"
```

---

## Task 22: `TourSearchPage.tsx` — selected-tour map (Section E)

**Files:**
- Modify: `huts/src/TourSearchPage.tsx`

**Interfaces:**
- Consumes: `huts.geojson` (hut coordinates, fetched fresh in this task — Task 20/21 only fetched
  it for `hutNameById`), `startById` (already has `lat`/`lng` from Task 20).
- Produces: extends `TourSearchPage` with its own small `react-leaflet` `MapContainer` in the
  results pane, drawing the selected chain as a dashed schematic polyline.

- [ ] **Step 1: Fetch and store hut coordinates alongside hut names**

In the `useEffect` from Task 20, `hutsFc.features` is currently mapped only into
`hutNameById`. Add a second map built from the same fetch, `hutCoordsById`:

```tsx
const [hutCoordsById, setHutCoordsById] = useState<Map<number, { lat: number; lng: number }>>(new Map())
```

In the `.then(([tourSearchData, hutsFc, parkingFc, stationsFc]) => { ... })` block, alongside the
existing `setHutNameById(...)` call, add:

```tsx
setHutCoordsById(
  new Map(
    hutsFc.features.map((f) => {
      const [lng, lat] = (f.geometry as GeoJSON.Point).coordinates
      return [(f.properties as { id: number }).id, { lat, lng }]
    }),
  ),
)
```

- [ ] **Step 2: Add selected-chain state and the map component**

Add state near the other `TourSearchPage` state:

```tsx
const [selectedChain, setSelectedChain] = useState<TourResult | null>(null)
```

Set it on card click — in the `CardActionArea onClick` from Task 21, change:
```tsx
onClick={() => setExpandedChain(isExpanded ? null : chainIndex)}
```
to:
```tsx
onClick={() => {
  setExpandedChain(isExpanded ? null : chainIndex)
  setSelectedChain(chain)
}}
```

Add, above the `TourSearchPage` function (module scope):

```tsx
function SelectedTourMap({
  chain, hutCoordsById, startById,
}: {
  chain: TourResult
  hutCoordsById: Map<number, { lat: number; lng: number }>
  startById: Map<number, StartPoint>
}) {
  const startPoint = startById.get(chain.startId)
  const endPoint = startById.get(chain.exitStartId)
  const hutPoints = chain.huts.map((h) => hutCoordsById.get(h)).filter((p): p is { lat: number; lng: number } => !!p)
  const positions: [number, number][] = [
    ...(startPoint ? [[startPoint.lat, startPoint.lng] as [number, number]] : []),
    ...hutPoints.map((p): [number, number] => [p.lat, p.lng]),
    ...(endPoint ? [[endPoint.lat, endPoint.lng] as [number, number]] : []),
  ]
  if (positions.length < 2) return null

  const center = positions[Math.floor(positions.length / 2)]

  return (
    <Box>
      <MapContainer center={center} zoom={11} style={{ height: 260, width: '100%' }}>
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        />
        <Polyline positions={positions} pathOptions={{ color: '#e65100', weight: 3, dashArray: '6 8' }} />
        {startPoint && (
          <CircleMarker center={[startPoint.lat, startPoint.lng]} radius={6} pathOptions={{ color: '#1b5e20', fillColor: '#43a047', fillOpacity: 1 }} />
        )}
        {endPoint && (
          <CircleMarker center={[endPoint.lat, endPoint.lng]} radius={6} pathOptions={{ color: '#1b5e20', fillColor: '#43a047', fillOpacity: 1 }} />
        )}
      </MapContainer>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
        Schematische Verbindung, nicht der reale Wegverlauf.
      </Typography>
    </Box>
  )
}
```

Add `Polyline` to the `react-leaflet` import line at the top of the file (it currently imports
`MapContainer, TileLayer, CircleMarker, Tooltip` — extend to include `Polyline`; also add the
`MapContainer, TileLayer, CircleMarker` imports themselves, since Task 20/21 didn't need
`react-leaflet` yet — add `import { MapContainer, TileLayer, CircleMarker, Polyline } from 'react-leaflet'`
and `import 'leaflet/dist/leaflet.css'` near the top of the file, matching `App.tsx`'s pattern).

- [ ] **Step 3: Render `SelectedTourMap` in the expanded card**

In the `isExpanded && (<CardContent>...)` block from Task 21, after the route `<Typography>`, add:

```tsx
<Box sx={{ mt: 1 }}>
  <SelectedTourMap chain={chain} hutCoordsById={hutCoordsById} startById={startById} />
</Box>
```

- [ ] **Step 4: Typecheck**

Run: `cd huts && npm run typecheck`
Expected: PASS

- [ ] **Step 5: Manual smoke check**

Run: `cd huts && npm run dev` (background), search, expand a result card, confirm a small map
appears with a dashed orange polyline through the tour's huts, start/end markers, and the
"schematische Verbindung" caption below it. Stop the dev server.

- [ ] **Step 6: Commit**

```bash
git add huts/src/TourSearchPage.tsx
git commit -m "feat(huts): draw selected tour as a schematic polyline (Section E)"
```

---

## Task 23: UI test infrastructure + `TourSearchPage` flow test (Section F)

**Files:**
- Create: `huts/src/TourSearchPage.test.tsx`
- Modify: `huts/package.json`

**Interfaces:**
- Consumes: `@testing-library/react`'s `render`, `screen`, `fireEvent`/`userEvent`; mocked
  `loadTourSearchData`/`findTours` from `./tourSearch/index.js`.
- Produces: nothing new exported — this is a test-only task.

- [ ] **Step 1: Add jsdom + RTL devDependencies**

Run: `cd huts && npm install --save-dev jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event`

- [ ] **Step 2: Write `huts/src/TourSearchPage.test.tsx` with a per-file jsdom environment**

The project's `vitest.config.js` defaults to `environment: 'node'` (fast, correct for the engine
tests). Rather than switching the whole project to `jsdom` (which would slow down every existing
engine test), scope `jsdom` to this one file via vitest's per-file docblock:

```tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import '@testing-library/jest-dom/vitest'
import TourSearchPage from './TourSearchPage.js'
import * as tourSearchIndex from './tourSearch/index.js'
import { SOURCE_TYPE_PARKING } from './tourSearch/types.js'
import type { GraphData, SearchResult } from './tourSearch/types.js'

const graphDataFixture: GraphData = {
  hutEdges: { hutIds: ['HutA'], variantNames: { 0: 'FAST_ANY' }, records: [] },
  approaches: { records: [], reverseIndex: { hut_to_starts: {}, start_to_huts: {} } },
}

const searchResultFixture: SearchResult = {
  chains: [
    {
      huts: [0], startId: 100, exitStartId: 100,
      totalDurationH: 5, totalAscentM: 500, totalDescentM: 500, totalDistanceM: 8000,
      legs: [
        { durationH: 2.5, ascentM: 250, descentM: 250, distanceM: 4000 },
        { durationH: 2.5, ascentM: 250, descentM: 250, distanceM: 4000 },
      ],
    },
  ],
  killCounters: { maxLegTime: 0, minLegTime: 0, legAscentCap: 0, maxEleM: 0, viaFerrata: 0, revisit: 0 },
}

function fetchJsonMock(body: unknown) {
  return Promise.resolve({ json: () => Promise.resolve(body) } as Response)
}

beforeEach(() => {
  vi.spyOn(tourSearchIndex, 'loadTourSearchData').mockResolvedValue(graphDataFixture)
  vi.spyOn(tourSearchIndex, 'findTours').mockReturnValue(searchResultFixture)
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      if (url.includes('huts.geojson')) {
        return fetchJsonMock({ type: 'FeatureCollection', features: [{ properties: { id: 0, name: 'HutA' }, geometry: { type: 'Point', coordinates: [11.0, 47.0] } }] })
      }
      if (url.includes('parking.geojson')) {
        return fetchJsonMock({
          type: 'FeatureCollection',
          features: [{ id: 'n100', properties: { name: 'Parkplatz Test' }, geometry: { type: 'Point', coordinates: [11.1, 47.1] } }],
        })
      }
      if (url.includes('stations.geojson')) {
        return fetchJsonMock({ type: 'FeatureCollection', features: [] })
      }
      throw new Error(`unexpected fetch ${url}`)
    }),
  )
})

describe('TourSearchPage', () => {
  it('loads data, submits the form, renders a result, and expanding it shows the route', async () => {
    render(<TourSearchPage />)

    await waitFor(() => expect(screen.getByText('Daten geladen')).toBeInTheDocument())

    await userEvent.click(screen.getByRole('button', { name: 'Touren suchen' }))

    await waitFor(() => expect(tourSearchIndex.findTours).toHaveBeenCalled())
    await waitFor(() => expect(screen.getByText(/1 Tour gefunden/)).toBeInTheDocument())

    await userEvent.click(screen.getByText(/Parkplatz Test/))
    await waitFor(() => expect(screen.getByText('Schematische Verbindung, nicht der reale Wegverlauf.')).toBeInTheDocument())
  })
})
```

`react-leaflet`'s `MapContainer`/`TileLayer`/`Polyline`/`CircleMarker` render real (mocked-DOM)
Leaflet instances under jsdom without a browser — this is standard for RTL + react-leaflet and
needs no additional mocking for a smoke-level assertion like the one above (asserting the caption
text renders is sufficient per spec F: "assert on component state/props/rendered marker count, not
on actual Leaflet DOM/tile behavior" — this test doesn't inspect Leaflet's internal DOM at all).

- [ ] **Step 3: Run the new test**

Run: `cd huts && npm test -- TourSearchPage.test`
Expected: PASS. If `MapContainer` throws in jsdom due to missing `ResizeObserver` (a known jsdom
gap), add a minimal stub at the top of the test file before the `describe` block:

```tsx
if (!('ResizeObserver' in globalThis)) {
  // @ts-expect-error jsdom does not implement ResizeObserver
  globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
}
```

- [ ] **Step 4: Full suite + typecheck + lint**

Run: `cd huts && npm test && npm run typecheck && npm run lint`
Expected: PASS across the whole project.

- [ ] **Step 5: Commit**

```bash
git add huts/package.json huts/package-lock.json huts/src/TourSearchPage.test.tsx
git commit -m "test(huts): add TourSearchPage RTL flow test with per-file jsdom environment"
```

---

## Task 24: Update `CLAUDE.md`, final verification pass

**Files:**
- Modify: `.claude/CLAUDE.md`

**Interfaces:** none — documentation-only task.

- [ ] **Step 1: Correct the stale "No test setup exists yet" line**

In `.claude/CLAUDE.md`, find:

```
No test setup exists yet.
```

Replace with:

```
`huts/` has a vitest test suite (`npm test`, `npm run typecheck`, `npm run lint` from `huts/`) —
engine tests run under the default `node` environment, UI tests opt into `jsdom` per-file via a
`// @vitest-environment jsdom` docblock (see `huts/src/TourSearchPage.test.tsx`). No CI pipeline
runs these automatically yet.
```

- [ ] **Step 2: Run the complete verification suite one more time**

Run: `cd huts && npm run typecheck && npm run lint && npm test`
Expected: PASS, zero errors, zero warnings treated as failures.

- [ ] **Step 3: Manual full-app smoke pass**

Run: `cd huts && npm run dev` (background). Visit `#` (Karte), `#graph` (Trail-Graph), and `#tours`
(Tourensuche) in turn; confirm the AppBar/Tabs shell is consistent across all three, the map/graph
pages render as before, and a tour search end-to-end (submit → paginated results → sort → region
filter → expand a card → see the schematic map) works. Stop the dev server.

- [ ] **Step 4: Commit**

```bash
git add .claude/CLAUDE.md
git commit -m "docs: correct stale 'no test setup' note in CLAUDE.md"
```

---

## Deferred (per spec, not part of this plan)

- Shareable/restorable search state in the URL hash.
- Web Worker offload for `findTours` (revisit only if Task 13's pruning doesn't bring perceived
  latency down enough in practice).
- Real per-leg duration/ascent/descent data on `TourResult` (see Task 21's flagged discrepancy) —
  decide with the user before Task 21 if the richer per-leg breakdown is wanted now or deferred.
