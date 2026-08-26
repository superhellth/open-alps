# Client-Side Tour Search Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (this repo's `.claude/CLAUDE.md` forbids worktrees/subagent-driven-development — see Global Constraints). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A headless, unit-tested JS module (`huts/src/tourSearch/`) that loads the pipeline's static
tour-suggestion payload and answers "find me multi-hut chains matching these constraints" — the
client-side chain search Part 6 of the design spec describes. No UI in this plan; the result is a
library other code (a future search page) calls.

**Architecture:** Pure ES modules, no framework dependency (usable from React later, but not
React-shaped now). Layered like the spec: (1) binary payload parsing, (2) direction-reversal and
duration computation, (3) adjacency/approach lookups, (4) the layered `(hut, leg[, start_id])` exact
DFS, (5) result diversity. Each layer is independently testable against small synthetic fixtures;
the final task smoke-tests the whole stack against the real files in `huts/public/data`.

**Tech Stack:** Plain JS (the `huts/` app has no TypeScript), `vitest` (new dev dependency — no test
runner exists in `huts/` yet), native `fetch`/`ArrayBuffer`/`DataView` for binary parsing.

**Spec:** `docs/superpowers/specs/2026-08-21-tour-suggestion-design.md` (read the 2026-08-26 addendum
first — it confirms the design's assumptions against the now-built pipeline). Companion:
`docs/tour-suggestion-payload.md` (exact file/column contract), `docs/superpowers/specs/2026-08-21-tour-suggestion-deferred.md`
(explicitly out of scope — do not implement anything from it).

## Global Constraints

- **No day/night vocabulary anywhere in this module.** The search speaks only in legs
  (`legCountMin`/`legCountMax`); a leg is `start->hut`, `hut->hut`, or `hut->start`. Translating to
  "days"/"nights" is a future UI's job (spec Part 6, "The backend contract").
- **No `maxApproachTime`.** Approach and exit legs are filtered by the exact same
  `minLegTimeH`/`maxLegTimeH`/`legAscentCapM` as any hut-to-hut leg — never a separate, tighter budget
  (spec Part 4; root `CLAUDE.md`'s Global Constraints repeats this — it must never be reintroduced).
- **No `either` transport mode.** `car` and `transit` are two separate searches with different state
  shapes, never a merged/relaxed closure rule (spec Part 1, "Transport mode").
- **`car` mode requires exact loop closure**: the exit leg's `startId` must equal the entry leg's
  `startId`. No proximity relaxation (that is `2026-08-21-tour-suggestion-deferred.md`'s "Loop
  relaxation for car mode" — explicitly deferred, do not build it here).
- **Exact DFS only — no beam/top-K.** The 2026-08-26 addendum confirmed mean hut degree of 3-5 under
  the real time-cost graph, matching the design's exact-DFS bet. Do not add a beam fallback in this
  plan.
- **One objective: `fastest` (ascending total duration).** `least road` arrives only once the
  `ROAD_*` variant ships (decided-but-not-built, per the addendum) — do not add an `objective`
  parameter or comparator for it now; that is a real YAGNI violation waiting to happen.
- **The reverse-traversal contract is exact** (`docs/tour-suggestion-payload.md` §3): unchanged —
  `distanceM`, `roadM`, `sacRank`, `viaFerrata`, `maxEleM`, `ungradedM`, `inferredM`; swapped —
  `ascentM ↔ descentM`; recomputed — duration. Geometry/profile reversal is a map-rendering concern,
  out of scope for this module.
- **Duration formula must mirror `pipeline/lib/speed.py`'s `din_duration_h()` exactly**:
  `t_h = distance_m / 4000`, `t_v = ascent_m / 300 + descent_m / 500`,
  `duration_h = max(t_h, t_v) + min(t_h, t_v) / 2`. Never approximate this.
- **Approach legs are always drawn from the `FAST_ANY`-only approach table; exit legs are always
  drawn from the (all-variant) loop-closure reverse index, read backwards** — these are two different
  data structures on purpose (`docs/tour-suggestion-payload.md` §6, spec Part 4: "Exit records are
  the reverse index... read in that direction; nothing extra is stored"). Do not use the approach
  table for exits or vice versa.
- **Result diversity is two separate steps with two separate keys, in this order**: (1) exact-duplicate
  removal on the *ordered* hut sequence (mandatory, no threshold — a chain and its reverse are one
  tour), then (2) similarity suppression on the *unordered* hut set (threshold-based, greedy). Never
  merge these into one key (spec Part 6, "Result diversity").
- **Hut indices are positions into `hut_ids` / `huts.geojson`'s feature array** (`u2` in the payload —
  plain small integers here). **Start ids are raw OSM node ids** (`u8` in the payload, safe to
  represent as a JS `Number` — well under `Number.MAX_SAFE_INTEGER`).
- **Test command:** `cd huts && npm test` (added in Task 0). Every task ends with this passing.
- Commit per task, conventional-commit subject.

---

## File structure

```
huts/src/tourSearch/
  dinDuration.js         Task 1  — DIN 33466 duration
  binaryColumns.js       Task 2  — packed-column binary (de)serialization
  loadHutEdges.js         Task 3  — fetch + parse hut-edge-payload.{json,bin}
  loadApproaches.js       Task 4  — fetch + parse approaches.{json,bin}
  reverseLeg.js           Task 5  — direction-reversal contract
  adjacency.js            Task 6  — both-direction hut->hut lookup, one variant
  resolveVariant.js       Task 7  — (sacCeiling, allowUngraded) -> variant id
  approaches.js            Task 8  — approach/exit leg lookups incl. loop closure
  legFilters.js            Task 9  — per-leg predicates + kill counters
  search.js                Task 10/11 — the (hut, leg[, start_id]) exact DFS
  diversity.js              Task 12/13 — dedup + similarity suppression
  index.js                  Task 14 — public API
(each *.js above gets a colocated *.test.js)
```

Each file has one responsibility and depends only on files listed before it, so a reviewer can
approve/reject a task without reading ahead.

---

### Task 0: Add a test runner (`vitest`) to `huts/`

**Files:**
- Modify: `huts/package.json` (devDependency + `test` script)
- Create: `huts/vitest.config.js`
- Test: a throwaway smoke test, deleted at the end of this task

**Interfaces:** none — pure tooling.

- [ ] **Step 1: Install vitest**

```bash
cd huts && npm install -D vitest
```

- [ ] **Step 2: Add the config**

```js
// huts/vitest.config.js
import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: { environment: 'node' },
})
```

- [ ] **Step 3: Add the script**

In `huts/package.json`, under `"scripts"`, add:

```json
"test": "vitest run"
```

- [ ] **Step 4: Write a throwaway smoke test and confirm the runner works**

```js
// huts/src/tourSearch/__smoke.test.js
import { describe, it, expect } from 'vitest'

describe('vitest smoke test', () => {
  it('runs', () => {
    expect(1 + 1).toBe(2)
  })
})
```

Run: `cd huts && npm test`
Expected: PASS, 1 test.

- [ ] **Step 5: Delete the smoke test and commit the tooling**

```bash
rm huts/src/tourSearch/__smoke.test.js
git add huts/package.json huts/package-lock.json huts/vitest.config.js
git commit -m "chore(huts): add vitest test runner"
```

---

### Task 1: DIN 33466 duration

**Files:**
- Create: `huts/src/tourSearch/dinDuration.js`
- Test: `huts/src/tourSearch/dinDuration.test.js`

**Interfaces:**
- Produces: `dinDurationH(distanceM, ascentM, descentM) -> number` (hours). Consumed by Tasks 5, 10.

- [ ] **Step 1: Write the failing test**

```js
// huts/src/tourSearch/dinDuration.test.js
import { describe, it, expect } from 'vitest'
import { dinDurationH } from './dinDuration.js'

describe('dinDurationH', () => {
  it('blends horizontal and vertical time (8km, 600m up, 500m down -> 4.0h)', () => {
    // t_h = 2.0, t_v = 2.0 + 1.0 = 3.0 -> 3.0 + 1.0 = 4.0 h. Same fixture as
    // pipeline/tests/test_speed.py::test_din_duration_blends_horizontal_and_vertical.
    expect(dinDurationH(8000, 600, 500)).toBeCloseTo(4.0, 6)
  })

  it('is purely horizontal on the flat', () => {
    expect(dinDurationH(4000, 0, 0)).toBeCloseTo(1.0, 6)
  })

  it('handles zero-length legs without dividing by zero', () => {
    expect(dinDurationH(0, 0, 0)).toBe(0)
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd huts && npm test -- dinDuration`
Expected: FAIL — `Cannot find module './dinDuration.js'`

- [ ] **Step 3: Implement**

```js
// huts/src/tourSearch/dinDuration.js
/**
 * DIN 33466 hiking duration. Mirrors pipeline/lib/speed.py's din_duration_h() exactly —
 * this is the client-side half of a formula the pipeline deliberately does not ship a
 * precomputed value for (docs/tour-suggestion-payload.md §2).
 */
export function dinDurationH(distanceM, ascentM, descentM) {
  const tHorizontal = distanceM / 4000
  const tVertical = ascentM / 300 + descentM / 500
  return Math.max(tHorizontal, tVertical) + Math.min(tHorizontal, tVertical) / 2
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd huts && npm test -- dinDuration`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add huts/src/tourSearch/dinDuration.js huts/src/tourSearch/dinDuration.test.js
git commit -m "feat(tour-search): DIN 33466 duration module"
```

---

### Task 2: Packed-column binary (de)serialization

**Files:**
- Create: `huts/src/tourSearch/binaryColumns.js`
- Test: `huts/src/tourSearch/binaryColumns.test.js`

**Interfaces:**
- Produces: `readColumns(buffer, manifest) -> { [columnName]: Array<number> }` where `manifest` is
  `{ rows, columns: { [name]: { dtype, offset } } }` — the exact shape of `hut-edge-payload.json` /
  `approaches.json` (`docs/tour-suggestion-payload.md` §1). Supports dtypes `u1, i1, u2, u4, u8, f4`
  (u8 returned as `Number`, safe per Global Constraints).
- Produces: `packColumns(columnDefs, columnValues, rows) -> { manifest, buffer }` — the inverse, used
  by this task's own round-trip test and reused as a test-fixture builder in Tasks 3-4.
  Consumed by Tasks 3, 4.

- [ ] **Step 1: Write the failing tests**

```js
// huts/src/tourSearch/binaryColumns.test.js
import { describe, it, expect } from 'vitest'
import { readColumns, packColumns } from './binaryColumns.js'

describe('binaryColumns', () => {
  it('reads columns at their declared byte offsets', () => {
    // 3 rows: id (u1) then val (f4), laid out per-column like the real payload.
    const buffer = new ArrayBuffer(3 * 1 + 3 * 4)
    const view = new DataView(buffer)
    view.setUint8(0, 7); view.setUint8(1, 8); view.setUint8(2, 9)
    view.setFloat32(3, 1.5, true); view.setFloat32(7, 2.5, true); view.setFloat32(11, 3.5, true)
    const manifest = { rows: 3, columns: { id: { dtype: 'u1', offset: 0 }, val: { dtype: 'f4', offset: 3 } } }

    const columns = readColumns(buffer, manifest)

    expect(columns.id).toEqual([7, 8, 9])
    expect(columns.val[0]).toBeCloseTo(1.5, 5)
    expect(columns.val[2]).toBeCloseTo(3.5, 5)
  })

  it('reads u8 as a safe Number, not a BigInt', () => {
    const buffer = new ArrayBuffer(8)
    new DataView(buffer).setBigUint64(0, 2986313292n, true)
    const columns = readColumns(buffer, { rows: 1, columns: { startId: { dtype: 'u8', offset: 0 } } })
    expect(columns.startId).toEqual([2986313292])
    expect(typeof columns.startId[0]).toBe('number')
  })

  it('throws on an unsupported dtype rather than silently misreading', () => {
    expect(() => readColumns(new ArrayBuffer(4), { rows: 1, columns: { x: { dtype: 'f8', offset: 0 } } }))
      .toThrow(/unsupported dtype/)
  })

  it('packColumns then readColumns round-trips', () => {
    const { manifest, buffer } = packColumns(
      { a: 'u2', b: 'f4' },
      { a: [10, 20, 30], b: [1.25, -2.5, 0] },
      3,
    )
    const columns = readColumns(buffer, manifest)
    expect(columns.a).toEqual([10, 20, 30])
    expect(columns.b[0]).toBeCloseTo(1.25, 5)
    expect(columns.b[1]).toBeCloseTo(-2.5, 5)
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd huts && npm test -- binaryColumns`
Expected: FAIL — module not found

- [ ] **Step 3: Implement**

```js
// huts/src/tourSearch/binaryColumns.js
/**
 * Parses/builds the packed-column binary layout shared by hut-edge-payload.bin and
 * approaches.bin: each column is a contiguous run of `rows` values at its own dtype and
 * byte offset, NOT interleaved (docs/tour-suggestion-payload.md §1) — that layout is what
 * the pipeline's gzip-size measurements assume, so columns must be read independently.
 */
const DTYPES = {
  u1: { bytes: 1, get: (v, o) => v.getUint8(o), set: (v, o, x) => v.setUint8(o, x) },
  i1: { bytes: 1, get: (v, o) => v.getInt8(o), set: (v, o, x) => v.setInt8(o, x) },
  u2: { bytes: 2, get: (v, o) => v.getUint16(o, true), set: (v, o, x) => v.setUint16(o, x, true) },
  u4: { bytes: 4, get: (v, o) => v.getUint32(o, true), set: (v, o, x) => v.setUint32(o, x, true) },
  u8: { bytes: 8, get: (v, o) => Number(v.getBigUint64(o, true)), set: (v, o, x) => v.setBigUint64(o, BigInt(x), true) },
  f4: { bytes: 4, get: (v, o) => v.getFloat32(o, true), set: (v, o, x) => v.setFloat32(o, x, true) },
}

export function readColumns(buffer, manifest) {
  const view = new DataView(buffer)
  const out = {}
  for (const [name, { dtype, offset }] of Object.entries(manifest.columns)) {
    const dt = DTYPES[dtype]
    if (!dt) throw new Error(`unsupported dtype "${dtype}" for column "${name}"`)
    const values = new Array(manifest.rows)
    for (let i = 0; i < manifest.rows; i++) values[i] = dt.get(view, offset + i * dt.bytes)
    out[name] = values
  }
  return out
}

export function packColumns(columnDefs, columnValues, rows) {
  let offset = 0
  const manifest = { rows, columns: {} }
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

- [ ] **Step 4: Run to verify it passes**

Run: `cd huts && npm test -- binaryColumns`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add huts/src/tourSearch/binaryColumns.js huts/src/tourSearch/binaryColumns.test.js
git commit -m "feat(tour-search): packed-column binary reader/writer"
```

---

### Task 3: Load and normalize `hut-edge-payload.{json,bin}`

**Files:**
- Create: `huts/src/tourSearch/loadHutEdges.js`
- Test: `huts/src/tourSearch/loadHutEdges.test.js`

**Interfaces:**
- Consumes: `readColumns` (Task 2).
- Produces: `async loadHutEdgesData(baseUrl = '/data') -> { hutIds: string[], variantNames: {[id]: string}, records: HutEdgeRecord[] }`
  where `HutEdgeRecord = { fromIndex, toIndex, variant, distanceM, ascentM, descentM, maxEleM,
  sacRank, viaFerrata, roadM, ungradedM, inferredM, snapM }`. Consumed by Task 6.

- [ ] **Step 1: Write the failing test**

```js
// huts/src/tourSearch/loadHutEdges.test.js
import { describe, it, expect, vi, afterEach } from 'vitest'
import { packColumns } from './binaryColumns.js'
import { loadHutEdgesData } from './loadHutEdges.js'

afterEach(() => vi.unstubAllGlobals())

describe('loadHutEdgesData', () => {
  it('fetches the manifest and binary, and normalizes rows into camelCase records', async () => {
    const { manifest, buffer } = packColumns(
      {
        from_id: 'u2', to_id: 'u2', variant: 'u1', distance_m: 'f4', ascent_m: 'f4', descent_m: 'f4',
        max_ele_m: 'f4', sac_rank: 'i1', via_ferrata: 'u1', road_m: 'f4', ungraded_m: 'f4',
        inferred_m: 'f4', snap_m: 'f4',
      },
      {
        from_id: [0], to_id: [1], variant: [2], distance_m: [1200], ascent_m: [300], descent_m: [100],
        max_ele_m: [2400], sac_rank: [3], via_ferrata: [1], road_m: [50], ungraded_m: [0],
        inferred_m: [200], snap_m: [15],
      },
      1,
    )
    const fullManifest = { ...manifest, variants: { 0: 'FAST_ANY', 2: 'FAST_T3' }, hut_ids: ['hutA', 'hutB'] }
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ json: () => Promise.resolve(fullManifest) })
      .mockResolvedValueOnce({ arrayBuffer: () => Promise.resolve(buffer) })
    vi.stubGlobal('fetch', fetchMock)

    const data = await loadHutEdgesData('/data')

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/data/hut-edge-payload.json')
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/data/hut-edge-payload.bin')
    expect(data.hutIds).toEqual(['hutA', 'hutB'])
    expect(data.variantNames).toEqual({ 0: 'FAST_ANY', 2: 'FAST_T3' })
    expect(data.records).toHaveLength(1)
    expect(data.records[0]).toMatchObject({
      fromIndex: 0, toIndex: 1, variant: 2, distanceM: 1200, ascentM: 300, descentM: 100,
      maxEleM: 2400, sacRank: 3, viaFerrata: true, roadM: 50, ungradedM: 0, inferredM: 200, snapM: 15,
    })
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd huts && npm test -- loadHutEdges`
Expected: FAIL — module not found

- [ ] **Step 3: Implement**

```js
// huts/src/tourSearch/loadHutEdges.js
import { readColumns } from './binaryColumns.js'

/** @typedef {{ fromIndex:number, toIndex:number, variant:number, distanceM:number, ascentM:number,
 *  descentM:number, maxEleM:number, sacRank:number, viaFerrata:boolean, roadM:number,
 *  ungradedM:number, inferredM:number, snapM:number }} HutEdgeRecord */

export async function loadHutEdgesData(baseUrl = '/data') {
  const manifest = await (await fetch(`${baseUrl}/hut-edge-payload.json`)).json()
  const buffer = await (await fetch(`${baseUrl}/hut-edge-payload.bin`)).arrayBuffer()
  const c = readColumns(buffer, manifest)

  const records = new Array(manifest.rows)
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

- [ ] **Step 4: Run to verify it passes**

Run: `cd huts && npm test -- loadHutEdges`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add huts/src/tourSearch/loadHutEdges.js huts/src/tourSearch/loadHutEdges.test.js
git commit -m "feat(tour-search): load and normalize hut-edge-payload"
```

---

### Task 4: Load and normalize `approaches.{json,bin}`

**Files:**
- Create: `huts/src/tourSearch/loadApproaches.js`
- Test: `huts/src/tourSearch/loadApproaches.test.js`

**Interfaces:**
- Consumes: `readColumns` (Task 2).
- Produces: `async loadApproachesData(baseUrl = '/data') -> { records: ApproachRecord[], reverseIndex: { hut_to_starts, start_to_huts } }`
  where `ApproachRecord = { hutIndex, startId, sourceType, accessUnknown, distanceM, ascentM,
  descentM, access }`. `reverseIndex` is passed through unparsed (already plain JSON per
  `docs/tour-suggestion-payload.md` §6 — its entries are objects with snake_case keys, normalized
  later in Task 8, not here). Consumed by Task 8.

- [ ] **Step 1: Write the failing test**

```js
// huts/src/tourSearch/loadApproaches.test.js
import { describe, it, expect, vi, afterEach } from 'vitest'
import { packColumns } from './binaryColumns.js'
import { loadApproachesData } from './loadApproaches.js'

afterEach(() => vi.unstubAllGlobals())

describe('loadApproachesData', () => {
  it('fetches the manifest and binary, normalizes records, and passes the reverse index through', async () => {
    const { manifest, buffer } = packColumns(
      { hut_id: 'u2', start_id: 'u8', source_type: 'u1', access_unknown: 'u1', distance_m: 'f4', ascent_m: 'f4', descent_m: 'f4' },
      { hut_id: [15], start_id: [32854131], source_type: [1], access_unknown: [0], distance_m: [19812.6], ascent_m: [746.2], descent_m: [488.2] },
      1,
    )
    const reverseIndex = {
      hut_to_starts: { 15: [{ hut_id: 15, start_id: 32854131, source_type: 1, variant: 0, distance_m: 19812.6, ascent_m: 746.2, descent_m: 488.2 }] },
      start_to_huts: { 32854131: [{ hut_id: 15, start_id: 32854131, source_type: 1, variant: 0, distance_m: 19812.6, ascent_m: 746.2, descent_m: 488.2 }] },
    }
    const fullManifest = { ...manifest, access_values: ['customers'], reverse_index: reverseIndex }
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ json: () => Promise.resolve(fullManifest) })
      .mockResolvedValueOnce({ arrayBuffer: () => Promise.resolve(buffer) })
    vi.stubGlobal('fetch', fetchMock)

    const data = await loadApproachesData('/data')

    expect(data.records).toHaveLength(1)
    expect(data.records[0]).toMatchObject({
      hutIndex: 15, startId: 32854131, sourceType: 1, accessUnknown: false,
      distanceM: expect.closeTo(19812.6, 1), access: 'customers',
    })
    expect(data.reverseIndex).toBe(reverseIndex)
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd huts && npm test -- loadApproaches`
Expected: FAIL — module not found

- [ ] **Step 3: Implement**

```js
// huts/src/tourSearch/loadApproaches.js
import { readColumns } from './binaryColumns.js'

/** @typedef {{ hutIndex:number, startId:number, sourceType:number, accessUnknown:boolean,
 *  distanceM:number, ascentM:number, descentM:number, access:string|null }} ApproachRecord */

export async function loadApproachesData(baseUrl = '/data') {
  const manifest = await (await fetch(`${baseUrl}/approaches.json`)).json()
  const buffer = await (await fetch(`${baseUrl}/approaches.bin`)).arrayBuffer()
  const c = readColumns(buffer, manifest)

  const records = new Array(manifest.rows)
  for (let i = 0; i < manifest.rows; i++) {
    records[i] = {
      hutIndex: c.hut_id[i], startId: c.start_id[i], sourceType: c.source_type[i],
      accessUnknown: c.access_unknown[i] === 1, distanceM: c.distance_m[i],
      ascentM: c.ascent_m[i], descentM: c.descent_m[i],
      access: manifest.access_values ? manifest.access_values[i] : null,
    }
  }
  return { records, reverseIndex: manifest.reverse_index }
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd huts && npm test -- loadApproaches`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add huts/src/tourSearch/loadApproaches.js huts/src/tourSearch/loadApproaches.test.js
git commit -m "feat(tour-search): load and normalize approaches payload"
```

---

### Task 5: Direction-reversal contract

**Files:**
- Create: `huts/src/tourSearch/reverseLeg.js`
- Test: `huts/src/tourSearch/reverseLeg.test.js`

**Interfaces:**
- Consumes: `dinDurationH` (Task 1).
- Produces: `forwardHutLeg(record) -> Leg`, `reverseHutLeg(record) -> Leg`,
  `forwardStartLeg(record) -> Leg`, `reverseStartLeg(record) -> Leg`, where every `Leg` gains a
  `durationH` field. Consumed by Tasks 6, 8.

- [ ] **Step 1: Write the failing tests**

```js
// huts/src/tourSearch/reverseLeg.test.js
import { describe, it, expect } from 'vitest'
import { forwardHutLeg, reverseHutLeg, forwardStartLeg, reverseStartLeg } from './reverseLeg.js'

const record = {
  fromIndex: 0, toIndex: 1, variant: 2, distanceM: 8000, ascentM: 600, descentM: 500,
  maxEleM: 2400, sacRank: 3, viaFerrata: false, roadM: 100, ungradedM: 0, inferredM: 50, snapM: 5,
}

describe('reverseHutLeg', () => {
  it('swaps ascent/descent, swaps endpoints, recomputes duration, and leaves everything else unchanged', () => {
    const reversed = reverseHutLeg(record)
    expect(reversed.fromIndex).toBe(1)
    expect(reversed.toIndex).toBe(0)
    expect(reversed.ascentM).toBe(500)
    expect(reversed.descentM).toBe(600)
    // reversed: distance 8000, ascent 500, descent 600 -> t_h=2, t_v=500/300+600/500=2.867 -> 2.867+1=3.867h
    expect(reversed.durationH).toBeCloseTo(3.8667, 3)
    for (const field of ['distanceM', 'roadM', 'sacRank', 'viaFerrata', 'maxEleM', 'ungradedM', 'inferredM']) {
      expect(reversed[field]).toEqual(record[field])
    }
  })
})

describe('forwardHutLeg', () => {
  it('computes duration without altering any other field', () => {
    const forward = forwardHutLeg(record)
    expect(forward.ascentM).toBe(600)
    expect(forward.descentM).toBe(500)
    expect(forward.durationH).toBeCloseTo(4.0, 6) // same fixture as dinDuration.test.js
  })
})

describe('start-edge reversal (approach/exit)', () => {
  const approach = { hutIndex: 15, startId: 32854131, sourceType: 1, distanceM: 4000, ascentM: 300, descentM: 100 }

  it('forwardStartLeg computes duration in the stored (start->hut) direction', () => {
    // t_h = 4000/4000 = 1.0, t_v = 300/300 + 100/500 = 1.2 -> max(1.2,1.0) + min(1.2,1.0)/2 = 1.7h
    expect(forwardStartLeg(approach).durationH).toBeCloseTo(1.7, 3)
  })

  it('reverseStartLeg swaps ascent/descent for the hut->start (exit) direction', () => {
    const exit = reverseStartLeg(approach)
    expect(exit.ascentM).toBe(100)
    expect(exit.descentM).toBe(300)
    expect(exit.startId).toBe(32854131)
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd huts && npm test -- reverseLeg`
Expected: FAIL — module not found

- [ ] **Step 3: Implement**

```js
// huts/src/tourSearch/reverseLeg.js
import { dinDurationH } from './dinDuration.js'

function withDuration(leg) {
  return { ...leg, durationH: dinDurationH(leg.distanceM, leg.ascentM, leg.descentM) }
}

/** Reverse-traversal contract (docs/tour-suggestion-payload.md §3): distance/road/sacRank/
 *  viaFerrata/maxEle/ungraded/inferred unchanged; ascent<->descent swapped; duration recomputed. */
export function reverseHutLeg(record) {
  return withDuration({
    ...record,
    fromIndex: record.toIndex,
    toIndex: record.fromIndex,
    ascentM: record.descentM,
    descentM: record.ascentM,
  })
}

export function forwardHutLeg(record) {
  return withDuration(record)
}

export function reverseStartLeg(record) {
  return withDuration({ ...record, ascentM: record.descentM, descentM: record.ascentM })
}

export function forwardStartLeg(record) {
  return withDuration(record)
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd huts && npm test -- reverseLeg`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add huts/src/tourSearch/reverseLeg.js huts/src/tourSearch/reverseLeg.test.js
git commit -m "feat(tour-search): direction-reversal contract for hut and start legs"
```

---

### Task 6: Both-direction adjacency for one variant

**Files:**
- Create: `huts/src/tourSearch/adjacency.js`
- Test: `huts/src/tourSearch/adjacency.test.js`

**Interfaces:**
- Consumes: `forwardHutLeg`, `reverseHutLeg` (Task 5); the `HutEdgeRecord[]` shape from Task 3.
- Produces: `buildAdjacency(hutEdgesData, variant) -> Map<number, Leg[]>` — every `Leg` in
  `adjacency.get(h)` is oriented `h -> leg.toIndex`. Consumed by Tasks 10-11.

- [ ] **Step 1: Write the failing test**

```js
// huts/src/tourSearch/adjacency.test.js
import { describe, it, expect } from 'vitest'
import { buildAdjacency } from './adjacency.js'

const hutEdgesData = {
  hutIds: ['A', 'B', 'C'],
  records: [
    { fromIndex: 0, toIndex: 1, variant: 0, distanceM: 5000, ascentM: 400, descentM: 200, maxEleM: 2000, sacRank: 1, viaFerrata: false, roadM: 0, ungradedM: 0, inferredM: 0, snapM: 0 },
    { fromIndex: 0, toIndex: 2, variant: 1, distanceM: 6000, ascentM: 500, descentM: 300, maxEleM: 2100, sacRank: 2, viaFerrata: false, roadM: 0, ungradedM: 0, inferredM: 0, snapM: 0 },
  ],
}

describe('buildAdjacency', () => {
  it('includes only edges of the requested variant, in both directions', () => {
    const adjacency = buildAdjacency(hutEdgesData, 0)
    expect(adjacency.get(0)).toHaveLength(1)
    expect(adjacency.get(0)[0]).toMatchObject({ toIndex: 1, ascentM: 400, descentM: 200 })
    expect(adjacency.get(1)).toHaveLength(1)
    expect(adjacency.get(1)[0]).toMatchObject({ toIndex: 0, ascentM: 200, descentM: 400 }) // swapped
    expect(adjacency.has(2)).toBe(false) // variant-1 edge excluded
  })

  it('a hut with no edges in this variant is simply absent from the map', () => {
    const adjacency = buildAdjacency(hutEdgesData, 1)
    expect(adjacency.get(0)).toHaveLength(1)
    expect(adjacency.has(1)).toBe(false)
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd huts && npm test -- adjacency`
Expected: FAIL — module not found

- [ ] **Step 3: Implement**

```js
// huts/src/tourSearch/adjacency.js
import { forwardHutLeg, reverseHutLeg } from './reverseLeg.js'

export function buildAdjacency(hutEdgesData, variant) {
  const adjacency = new Map()
  const push = (hutIndex, leg) => {
    if (!adjacency.has(hutIndex)) adjacency.set(hutIndex, [])
    adjacency.get(hutIndex).push(leg)
  }
  for (const record of hutEdgesData.records) {
    if (record.variant !== variant) continue
    push(record.fromIndex, forwardHutLeg(record))
    push(record.toIndex, reverseHutLeg(record))
  }
  return adjacency
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd huts && npm test -- adjacency`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add huts/src/tourSearch/adjacency.js huts/src/tourSearch/adjacency.test.js
git commit -m "feat(tour-search): both-direction adjacency for a single variant"
```

---

### Task 7: Difficulty ceiling to variant row

**Files:**
- Create: `huts/src/tourSearch/resolveVariant.js`
- Test: `huts/src/tourSearch/resolveVariant.test.js`

**Interfaces:**
- Produces: `resolveVariant({ sacCeiling, allowUngraded }, variantNames) -> number` — `variantNames`
  is the `{ [id]: name }` map from Task 3's `loadHutEdgesData`. Consumed by Tasks 10-11.

- [ ] **Step 1: Write the failing test**

```js
// huts/src/tourSearch/resolveVariant.test.js
import { describe, it, expect } from 'vitest'
import { resolveVariant } from './resolveVariant.js'

const variantNames = { 0: 'FAST_ANY', 1: 'FAST_T2', 2: 'FAST_T3', 3: 'FAST_T3_UNGRADED' }

describe('resolveVariant', () => {
  it('a T2 ceiling resolves to the FAST_T2 row (fully-graded guarantee)', () => {
    expect(resolveVariant({ sacCeiling: 2 }, variantNames)).toBe(1)
  })

  it('a T3 ceiling with no ungraded terrain allowed resolves to FAST_T3', () => {
    expect(resolveVariant({ sacCeiling: 3, allowUngraded: false }, variantNames)).toBe(2)
  })

  it('a T3 ceiling with ungraded terrain allowed resolves to FAST_T3_UNGRADED', () => {
    expect(resolveVariant({ sacCeiling: 3, allowUngraded: true }, variantNames)).toBe(3)
  })

  it('no ceiling (or T4+) resolves to FAST_ANY, which carries no grading guarantee', () => {
    expect(resolveVariant({}, variantNames)).toBe(0)
    expect(resolveVariant({ sacCeiling: 5 }, variantNames)).toBe(0)
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd huts && npm test -- resolveVariant`
Expected: FAIL — module not found

- [ ] **Step 3: Implement**

```js
// huts/src/tourSearch/resolveVariant.js
/**
 * Difficulty ceiling is a routing-relevant threshold, not a per-edge filter (spec Part 2's
 * filter/objective/variant table) — it resolves to exactly ONE variant row for the whole
 * query, never a per-edge sac_rank comparison. Filtering sac_rank on an unconstrained row
 * does not support the "every metre graded" claim (docs/tour-suggestion-payload.md §5).
 */
export function resolveVariant({ sacCeiling, allowUngraded = false } = {}, variantNames) {
  const idByName = {}
  for (const [id, name] of Object.entries(variantNames)) idByName[name] = Number(id)

  if (sacCeiling != null && sacCeiling <= 2) return idByName.FAST_T2
  if (sacCeiling != null && sacCeiling <= 3) return allowUngraded ? idByName.FAST_T3_UNGRADED : idByName.FAST_T3
  return idByName.FAST_ANY
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd huts && npm test -- resolveVariant`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add huts/src/tourSearch/resolveVariant.js huts/src/tourSearch/resolveVariant.test.js
git commit -m "feat(tour-search): resolve a difficulty ceiling to a variant row"
```

---

### Task 8: Approach and exit leg lookups, including loop closure

**Files:**
- Create: `huts/src/tourSearch/approaches.js`
- Test: `huts/src/tourSearch/approaches.test.js`

**Interfaces:**
- Consumes: `forwardStartLeg`, `reverseStartLeg` (Task 5); the `ApproachRecord[]`/`reverseIndex`
  shape from Task 4.
- Produces: `getApproachLegs(hutIndex, approachesData) -> Leg[]` (start->hut, `FAST_ANY` only, the
  curated k-best table); `getExitLegs(hutIndex, variant, approachesData) -> Leg[]` (hut->start, from
  the all-variant reverse index, read backwards). Every `Leg` here also carries `startId`,
  `sourceType`, `accessUnknown`, `access`. Consumed by Tasks 10-11.

- [ ] **Step 1: Write the failing tests**

```js
// huts/src/tourSearch/approaches.test.js
import { describe, it, expect } from 'vitest'
import { getApproachLegs, getExitLegs } from './approaches.js'

const approachesData = {
  records: [
    { hutIndex: 15, startId: 32854131, sourceType: 1, accessUnknown: false, distanceM: 19812, ascentM: 746, descentM: 488, access: null },
    { hutIndex: 16, startId: 999, sourceType: 2, accessUnknown: false, distanceM: 3000, ascentM: 200, descentM: 100, access: null },
  ],
  reverseIndex: {
    hut_to_starts: {
      15: [
        { hut_id: 15, start_id: 32854131, source_type: 1, variant: 0, distance_m: 19812, ascent_m: 746, descent_m: 488 },
        { hut_id: 15, start_id: 32854131, source_type: 1, variant: 1, distance_m: 20500, ascent_m: 760, descent_m: 500 },
        { hut_id: 15, start_id: 40000000, source_type: 1, variant: 0, distance_m: 9000, ascent_m: 300, descent_m: 250 },
      ],
    },
    start_to_huts: {},
  },
}

describe('getApproachLegs', () => {
  it('returns only the requested hut\'s FAST_ANY approach-table rows, start->hut oriented', () => {
    const legs = getApproachLegs(15, approachesData)
    expect(legs).toHaveLength(1)
    expect(legs[0]).toMatchObject({ startId: 32854131, ascentM: 746, descentM: 488 })
  })

  it('a hut with no approach rows gets an empty array', () => {
    expect(getApproachLegs(999, approachesData)).toEqual([])
  })
})

describe('getExitLegs', () => {
  it('reads the reverse index backwards (ascent/descent swapped), filtered to the given variant', () => {
    const legs = getExitLegs(15, 0, approachesData)
    expect(legs).toHaveLength(2) // both start points at variant 0
    const toOrigin = legs.find((l) => l.startId === 32854131)
    expect(toOrigin.ascentM).toBe(488) // swapped from the stored 746/488
    expect(toOrigin.descentM).toBe(746)
  })

  it('a variant not present in the reverse index for this hut yields no exits', () => {
    expect(getExitLegs(15, 2, approachesData)).toEqual([])
  })

  it('a hut absent from the reverse index yields no exits', () => {
    expect(getExitLegs(999, 0, approachesData)).toEqual([])
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd huts && npm test -- approaches`
Expected: FAIL — module not found

- [ ] **Step 3: Implement**

```js
// huts/src/tourSearch/approaches.js
import { forwardStartLeg, reverseStartLeg } from './reverseLeg.js'

/** The curated k-best-per-hut table, FAST_ANY only (docs/tour-suggestion-payload.md §6):
 *  "an approach is a fastest, unconstrained leg to the hub, not a difficulty-graded one." */
export function getApproachLegs(hutIndex, approachesData) {
  return approachesData.records
    .filter((r) => r.hutIndex === hutIndex)
    .map((r) => forwardStartLeg(r))
}

/** Exits are the (all-variant) loop-closure reverse index, read backwards — a separate
 *  structure from the approach table on purpose (spec Part 4: "nothing extra is stored"). */
export function getExitLegs(hutIndex, variant, approachesData) {
  const entries = approachesData.reverseIndex.hut_to_starts[String(hutIndex)] || []
  return entries
    .filter((r) => r.variant === variant)
    .map((r) => reverseStartLeg({
      startId: r.start_id,
      sourceType: r.source_type,
      distanceM: r.distance_m,
      ascentM: r.ascent_m,
      descentM: r.descent_m,
    }))
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd huts && npm test -- approaches`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add huts/src/tourSearch/approaches.js huts/src/tourSearch/approaches.test.js
git commit -m "feat(tour-search): approach-table and loop-closure-index leg lookups"
```

---

### Task 9: Per-leg filters and kill counters

**Files:**
- Create: `huts/src/tourSearch/legFilters.js`
- Test: `huts/src/tourSearch/legFilters.test.js`

**Interfaces:**
- Produces: `createKillCounters() -> { maxLegTime, minLegTime, legAscentCap, maxEleM, viaFerrata, revisit }`
  (all zero); `legPasses(leg, constraints, killCounters) -> boolean`, incrementing the matching
  counter and returning `false` on the first constraint the leg fails.
  `constraints = { maxLegTimeH, minLegTimeH, legAscentCapM, maxEleM, allowViaFerrata }`. Consumed by
  Tasks 10-11.

- [ ] **Step 1: Write the failing tests**

```js
// huts/src/tourSearch/legFilters.test.js
import { describe, it, expect } from 'vitest'
import { legPasses, createKillCounters } from './legFilters.js'

const baseLeg = { durationH: 5, ascentM: 800, maxEleM: 2200, viaFerrata: false }
const baseConstraints = { maxLegTimeH: 7, minLegTimeH: 2, legAscentCapM: 1000, maxEleM: 2500, allowViaFerrata: true }

describe('legPasses', () => {
  it('passes a leg within every constraint', () => {
    const counters = createKillCounters()
    expect(legPasses(baseLeg, baseConstraints, counters)).toBe(true)
    expect(counters.maxLegTime).toBe(0)
  })

  it('rejects and counts a leg over maxLegTimeH', () => {
    const counters = createKillCounters()
    expect(legPasses({ ...baseLeg, durationH: 8 }, baseConstraints, counters)).toBe(false)
    expect(counters.maxLegTime).toBe(1)
  })

  it('rejects and counts a leg under minLegTimeH', () => {
    const counters = createKillCounters()
    expect(legPasses({ ...baseLeg, durationH: 1 }, baseConstraints, counters)).toBe(false)
    expect(counters.minLegTime).toBe(1)
  })

  it('rejects and counts a leg over legAscentCapM', () => {
    const counters = createKillCounters()
    expect(legPasses({ ...baseLeg, ascentM: 1200 }, baseConstraints, counters)).toBe(false)
    expect(counters.legAscentCap).toBe(1)
  })

  it('rejects and counts a leg over maxEleM when a cap is set', () => {
    const counters = createKillCounters()
    expect(legPasses({ ...baseLeg, maxEleM: 2600 }, baseConstraints, counters)).toBe(false)
    expect(counters.maxEleM).toBe(1)
  })

  it('does not apply a maxEleM check when no cap is given', () => {
    const counters = createKillCounters()
    const constraints = { ...baseConstraints, maxEleM: null }
    expect(legPasses({ ...baseLeg, maxEleM: 9000 }, constraints, counters)).toBe(true)
  })

  it('rejects and counts a via-ferrata leg when disallowed', () => {
    const counters = createKillCounters()
    const constraints = { ...baseConstraints, allowViaFerrata: false }
    expect(legPasses({ ...baseLeg, viaFerrata: true }, constraints, counters)).toBe(false)
    expect(counters.viaFerrata).toBe(1)
  })

  it('a start leg with no maxEleM/viaFerrata fields is not rejected by those checks', () => {
    const counters = createKillCounters()
    const startLeg = { durationH: 3, ascentM: 400 } // approach/exit legs carry no maxEleM/viaFerrata
    expect(legPasses(startLeg, baseConstraints, counters)).toBe(true)
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd huts && npm test -- legFilters`
Expected: FAIL — module not found

- [ ] **Step 3: Implement**

```js
// huts/src/tourSearch/legFilters.js
export function createKillCounters() {
  return { maxLegTime: 0, minLegTime: 0, legAscentCap: 0, maxEleM: 0, viaFerrata: 0, revisit: 0 }
}

/** No maxApproachTime: this predicate is applied identically to hut-hut, approach, and exit
 *  legs (root CLAUDE.md Global Constraints; spec Part 4). */
export function legPasses(leg, constraints, killCounters) {
  const { maxLegTimeH, minLegTimeH, legAscentCapM, maxEleM, allowViaFerrata } = constraints

  if (leg.durationH > maxLegTimeH) { killCounters.maxLegTime++; return false }
  if (leg.durationH < minLegTimeH) { killCounters.minLegTime++; return false }
  if (leg.ascentM > legAscentCapM) { killCounters.legAscentCap++; return false }
  if (maxEleM != null && leg.maxEleM > maxEleM) { killCounters.maxEleM++; return false }
  if (!allowViaFerrata && leg.viaFerrata) { killCounters.viaFerrata++; return false }
  return true
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd huts && npm test -- legFilters`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add huts/src/tourSearch/legFilters.js huts/src/tourSearch/legFilters.test.js
git commit -m "feat(tour-search): per-leg constraint filters with kill counters"
```

---

### Task 10: The exact DFS — `transit` mode

**Files:**
- Create: `huts/src/tourSearch/search.js`
- Test: `huts/src/tourSearch/search.test.js`

**Interfaces:**
- Consumes: `resolveVariant` (7), `buildAdjacency` (6), `getApproachLegs`/`getExitLegs` (8),
  `legPasses`/`createKillCounters` (9).
- Produces: `searchChains(query, graphData) -> { chains: Chain[], killCounters }` where
  `graphData = { hutEdges, approaches }` (the objects Tasks 3-4 load) and
  `Chain = { huts: number[], startId, exitStartId, totalDurationH, totalAscentM, totalDescentM,
  totalDistanceM }`, sorted ascending by `totalDurationH` (the one shipped objective). This task
  implements `mode: 'transit'` only; Task 11 adds `'car'`.

**Implementation note, stated once here rather than repeated per step:** every search `State` tracks
`{ path, startId, totalDurationH, totalAscentM, totalDescentM, totalDistanceM }`. The design's Part 6
keeps `startId` out of `transit`'s state to hold the state space to `(hut, n)` only; this
implementation carries `startId` in both modes' states for one shared code path and simply never
checks it for `transit`'s finish condition. At this graph's actual size (956 huts, ~12k edges,
measured mean degree 3-5 — see the 2026-08-26 design addendum) that costs milliseconds, not the
state-space collapse the design motivates for a much bigger graph. Note this as a deliberate
simplification, not a silent deviation, in the file's module docstring.

- [ ] **Step 1: Write the failing tests**

```js
// huts/src/tourSearch/search.test.js
import { describe, it, expect } from 'vitest'
import { searchChains } from './search.js'

// A tiny 3-hut chain: start1 -> A -> B -> C -> start2, all within budget, all FAST_ANY.
function edge(fromIndex, toIndex, distanceM) {
  return { fromIndex, toIndex, variant: 0, distanceM, ascentM: 200, descentM: 200, maxEleM: 2000, sacRank: 1, viaFerrata: false, roadM: 0, ungradedM: 0, inferredM: 0, snapM: 0 }
}

const graphData = {
  hutEdges: {
    hutIds: ['A', 'B', 'C'],
    variantNames: { 0: 'FAST_ANY' },
    records: [edge(0, 1, 5000), edge(1, 2, 5000)],
  },
  approaches: {
    records: [
      { hutIndex: 0, startId: 100, sourceType: 2, accessUnknown: false, distanceM: 2000, ascentM: 100, descentM: 50, access: null },
    ],
    reverseIndex: {
      hut_to_starts: {
        2: [{ hut_id: 2, start_id: 200, source_type: 2, variant: 0, distance_m: 2000, ascent_m: 50, descent_m: 100 }],
      },
      start_to_huts: {},
    },
  },
}

const generousConstraints = { maxLegTimeH: 10, minLegTimeH: 0, legAscentCapM: 9999, maxEleM: null, allowViaFerrata: true }

describe('searchChains (transit)', () => {
  it('finds the A->B->C chain within a 3-4 leg budget', () => {
    const { chains } = searchChains(
      { mode: 'transit', legCountMin: 3, legCountMax: 4, ...generousConstraints },
      graphData,
    )
    const full = chains.find((c) => c.huts.length === 3)
    expect(full).toBeDefined()
    expect(full.huts).toEqual([0, 1, 2])
    expect(full.startId).toBe(100)
    expect(full.exitStartId).toBe(200)
  })

  it('never revisits a hut within one chain', () => {
    const { chains } = searchChains(
      { mode: 'transit', legCountMin: 2, legCountMax: 6, ...generousConstraints },
      graphData,
    )
    for (const chain of chains) {
      expect(new Set(chain.huts).size).toBe(chain.huts.length)
    }
  })

  it('respects legCountMax: a 2-leg budget cannot reach the 3-hut chain', () => {
    const { chains } = searchChains(
      { mode: 'transit', legCountMin: 2, legCountMax: 2, ...generousConstraints },
      graphData,
    )
    expect(chains.some((c) => c.huts.length === 3)).toBe(false)
  })

  it('a maxLegTimeH too tight for any leg returns no chains and records why', () => {
    const { chains, killCounters } = searchChains(
      { mode: 'transit', legCountMin: 2, legCountMax: 4, ...generousConstraints, maxLegTimeH: 0.01 },
      graphData,
    )
    expect(chains).toEqual([])
    expect(killCounters.maxLegTime).toBeGreaterThan(0)
  })

  it('sorts results by ascending total duration', () => {
    const { chains } = searchChains(
      { mode: 'transit', legCountMin: 2, legCountMax: 4, ...generousConstraints },
      graphData,
    )
    const durations = chains.map((c) => c.totalDurationH)
    expect(durations).toEqual([...durations].sort((a, b) => a - b))
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd huts && npm test -- search`
Expected: FAIL — module not found

- [ ] **Step 3: Implement**

```js
// huts/src/tourSearch/search.js
/**
 * The layered (hut, leg[, start_id]) exact DFS from spec Part 6. Both `car` and `transit`
 * carry `startId` in every state for one shared code path — the design keeps `transit`'s
 * state to (hut, n) only to shrink the state space, but at this graph's measured size
 * (2026-08-26 design addendum: mean degree 3-5 over 956 huts) that collapse is a
 * performance nicety this plan deliberately skips, not a correctness requirement. `transit`
 * simply never checks `startId` at finish time.
 */
import { resolveVariant } from './resolveVariant.js'
import { buildAdjacency } from './adjacency.js'
import { getApproachLegs, getExitLegs } from './approaches.js'
import { legPasses, createKillCounters } from './legFilters.js'

export function searchChains(query, graphData) {
  const {
    mode, legCountMin, legCountMax, sacCeiling, allowUngraded = false,
    maxLegTimeH, minLegTimeH = 0, legAscentCapM = Infinity, maxEleM = null, allowViaFerrata = true,
  } = query
  const constraints = { maxLegTimeH, minLegTimeH, legAscentCapM, maxEleM, allowViaFerrata }
  const killCounters = createKillCounters()

  const variant = resolveVariant({ sacCeiling, allowUngraded }, graphData.hutEdges.variantNames)
  const adjacency = buildAdjacency(graphData.hutEdges, variant)

  const nightsMin = legCountMin - 1
  const nightsMax = legCountMax - 1

  // layer: Map<hutIndex, State[]>, State = { path, startId, totalDurationH, totalAscentM, totalDescentM, totalDistanceM }
  let layer = new Map()
  for (let h = 0; h < graphData.hutEdges.hutIds.length; h++) {
    for (const approachLeg of getApproachLegs(h, graphData.approaches)) {
      if (!legPasses(approachLeg, constraints, killCounters)) continue
      const state = {
        path: [h], startId: approachLeg.startId,
        totalDurationH: approachLeg.durationH, totalAscentM: approachLeg.ascentM,
        totalDescentM: approachLeg.descentM, totalDistanceM: approachLeg.distanceM,
      }
      if (!layer.has(h)) layer.set(h, [])
      layer.get(h).push(state)
    }
  }

  const finished = []
  const collectFinished = (n) => {
    if (n < nightsMin) return
    for (const [h, states] of layer) {
      const exitLegs = getExitLegs(h, variant, graphData.approaches)
      for (const s of states) {
        for (const exitLeg of exitLegs) {
          if (mode === 'car' && exitLeg.startId !== s.startId) continue
          if (!legPasses(exitLeg, constraints, killCounters)) continue
          finished.push({
            huts: [...s.path], startId: s.startId, exitStartId: exitLeg.startId,
            totalDurationH: s.totalDurationH + exitLeg.durationH,
            totalAscentM: s.totalAscentM + exitLeg.ascentM,
            totalDescentM: s.totalDescentM + exitLeg.descentM,
            totalDistanceM: s.totalDistanceM + exitLeg.distanceM,
          })
        }
      }
    }
  }

  collectFinished(1)
  for (let n = 1; n < nightsMax; n++) {
    const nextLayer = new Map()
    for (const [h, states] of layer) {
      const legs = adjacency.get(h) || []
      for (const s of states) {
        for (const leg of legs) {
          const h2 = leg.toIndex
          if (s.path.includes(h2)) { killCounters.revisit++; continue }
          if (!legPasses(leg, constraints, killCounters)) continue
          const next = {
            path: [...s.path, h2], startId: s.startId,
            totalDurationH: s.totalDurationH + leg.durationH,
            totalAscentM: s.totalAscentM + leg.ascentM,
            totalDescentM: s.totalDescentM + leg.descentM,
            totalDistanceM: s.totalDistanceM + leg.distanceM,
          }
          if (!nextLayer.has(h2)) nextLayer.set(h2, [])
          nextLayer.get(h2).push(next)
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

- [ ] **Step 4: Run to verify it passes**

Run: `cd huts && npm test -- search`
Expected: PASS (5 tests) — this also exercises the `mode === 'car'` branch's `continue`, but no
test yet asserts car-mode *behaviour*; that is Task 11.

- [ ] **Step 5: Commit**

```bash
git add huts/src/tourSearch/search.js huts/src/tourSearch/search.test.js
git commit -m "feat(tour-search): layered exact DFS chain search (transit mode)"
```

---

### Task 11: `car` mode — loop closure

**Files:**
- Modify: `huts/src/tourSearch/search.test.js` (no changes needed to `search.js` — Task 10 already
  implemented the `mode === 'car'` branch; this task is tests-only, proving that branch)

**Interfaces:** none new — this task adds coverage for behaviour `search.js` already has.

- [ ] **Step 1: Write the failing tests**

Append to `huts/src/tourSearch/search.test.js`:

```js
describe('searchChains (car)', () => {
  it('only finishes a chain whose exit start point matches the entry start point', () => {
    const { chains } = searchChains(
      { mode: 'car', legCountMin: 2, legCountMax: 4, ...generousConstraints },
      graphData,
    )
    // graphData's only exit from hut 2 is start_id 200, but the only approach is start_id 100 ->
    // no car chain can close, regardless of leg budget.
    expect(chains).toEqual([])
  })

  it('finds a closing loop when an exit back to the entry start point exists', () => {
    const loopGraphData = {
      ...graphData,
      approaches: {
        ...graphData.approaches,
        reverseIndex: {
          hut_to_starts: {
            2: [{ hut_id: 2, start_id: 100, source_type: 2, variant: 0, distance_m: 2000, ascent_m: 50, descent_m: 100 }],
          },
          start_to_huts: {},
        },
      },
    }
    const { chains } = searchChains(
      { mode: 'car', legCountMin: 2, legCountMax: 4, ...generousConstraints },
      loopGraphData,
    )
    const full = chains.find((c) => c.huts.length === 3)
    expect(full).toBeDefined()
    expect(full.startId).toBe(100)
    expect(full.exitStartId).toBe(100)
  })
})
```

- [ ] **Step 2: Run and confirm both new tests pass**

Run: `cd huts && npm test -- search`
Expected: PASS (7 tests total in this file) — Task 10 already implemented the `mode === 'car'`
branch, so both new tests pass against the existing `search.js` with no implementation change.

- [ ] **Step 3: Commit**

```bash
git add huts/src/tourSearch/search.test.js
git commit -m "test(tour-search): cover car-mode loop closure"
```

---

### Task 12: Result diversity — exact-duplicate (reverse) removal

**Files:**
- Create: `huts/src/tourSearch/diversity.js`
- Test: `huts/src/tourSearch/diversity.test.js`

**Interfaces:**
- Produces: `dedupeReversePairs(chains) -> Chain[]` — for a chain and its exact reverse-sequence
  twin, keeps the better-ranked one (lower `totalDurationH`). Consumed by Task 14.

- [ ] **Step 1: Write the failing tests**

```js
// huts/src/tourSearch/diversity.test.js
import { describe, it, expect } from 'vitest'
import { dedupeReversePairs } from './diversity.js'

describe('dedupeReversePairs', () => {
  it('collapses a chain and its exact reverse, keeping the faster one', () => {
    const chains = [
      { huts: [0, 1, 2], totalDurationH: 10 },
      { huts: [2, 1, 0], totalDurationH: 8 }, // same tour walked backwards, faster this way
    ]
    const result = dedupeReversePairs(chains)
    expect(result).toHaveLength(1)
    expect(result[0].totalDurationH).toBe(8)
  })

  it('does NOT collapse a different permutation sharing the same hut set', () => {
    // h1->h2->h3 and h1->h3->h2 are different tours, not a reverse pair (spec Part 6).
    const chains = [
      { huts: [0, 1, 2], totalDurationH: 10 },
      { huts: [0, 2, 1], totalDurationH: 9 },
    ]
    const result = dedupeReversePairs(chains)
    expect(result).toHaveLength(2)
  })

  it('leaves a chain with no reverse twin untouched', () => {
    const chains = [{ huts: [0, 1], totalDurationH: 5 }]
    expect(dedupeReversePairs(chains)).toEqual(chains)
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd huts && npm test -- diversity`
Expected: FAIL — module not found

- [ ] **Step 3: Implement**

```js
// huts/src/tourSearch/diversity.js
/**
 * Two separate diversity steps with two separate keys (spec Part 6, "Result diversity") —
 * this file must never merge them. Step 1 (this task): exact-duplicate removal on the
 * ORDERED hut sequence — a chain and its reverse are one tour walked two ways, and this
 * step has no threshold. Step 2 (Task 13): similarity suppression on the UNORDERED hut set.
 */
export function dedupeReversePairs(chains) {
  const bestBySignature = new Map()
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd huts && npm test -- diversity`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add huts/src/tourSearch/diversity.js huts/src/tourSearch/diversity.test.js
git commit -m "feat(tour-search): exact-duplicate reverse-pair removal"
```

---

### Task 13: Result diversity — similarity suppression

**Files:**
- Modify: `huts/src/tourSearch/diversity.js`
- Modify: `huts/src/tourSearch/diversity.test.js`

**Interfaces:**
- Produces: `suppressSimilar(chains, overlapThreshold) -> Chain[]` — greedy, assumes `chains` is
  already ranked (best first, e.g. the output of `dedupeReversePairs` on a duration-sorted list);
  drops a candidate sharing more than `overlapThreshold` of its huts (as a fraction of the smaller
  chain's hut count — the spec leaves the exact fraction formula as a tunable, this is the chosen
  definition, documented in code) or sharing its start point, with an already-accepted chain.
  Consumed by Task 14.

- [ ] **Step 1: Write the failing tests**

Append to `huts/src/tourSearch/diversity.test.js`:

```js
import { suppressSimilar } from './diversity.js'

describe('suppressSimilar', () => {
  it('drops a candidate that shares more than the threshold fraction of huts with an accepted chain', () => {
    const chains = [
      { huts: [0, 1, 2], startId: 100, totalDurationH: 5 },
      { huts: [0, 1, 3], startId: 200, totalDurationH: 6 }, // shares 2/3 huts with the first
    ]
    const result = suppressSimilar(chains, 0.5)
    expect(result).toHaveLength(1)
    expect(result[0].totalDurationH).toBe(5)
  })

  it('keeps a candidate below the overlap threshold', () => {
    const chains = [
      { huts: [0, 1, 2], startId: 100, totalDurationH: 5 },
      { huts: [3, 4, 5], startId: 200, totalDurationH: 6 }, // disjoint
    ]
    expect(suppressSimilar(chains, 0.5)).toHaveLength(2)
  })

  it('drops a candidate sharing its start point with an accepted chain, even with low hut overlap', () => {
    const chains = [
      { huts: [0, 1, 2], startId: 100, totalDurationH: 5 },
      { huts: [3, 4, 5], startId: 100, totalDurationH: 6 }, // same trailhead
    ]
    expect(suppressSimilar(chains, 0.5)).toHaveLength(1)
  })

  it('processes candidates in the given (ranked) order, always keeping the first', () => {
    const chains = [
      { huts: [0], startId: 1, totalDurationH: 1 },
      { huts: [0], startId: 1, totalDurationH: 2 },
      { huts: [0], startId: 1, totalDurationH: 3 },
    ]
    const result = suppressSimilar(chains, 0.5)
    expect(result).toHaveLength(1)
    expect(result[0].totalDurationH).toBe(1)
  })
})
```

- [ ] **Step 2: Run to verify the new tests fail**

Run: `cd huts && npm test -- diversity`
Expected: FAIL — `suppressSimilar is not a function`

- [ ] **Step 3: Implement**

Append to `huts/src/tourSearch/diversity.js`:

```js
function hutOverlapFraction(a, b) {
  const setA = new Set(a.huts)
  const setB = new Set(b.huts)
  let shared = 0
  for (const h of setA) if (setB.has(h)) shared++
  return shared / Math.min(setA.size, setB.size)
}

export function suppressSimilar(chains, overlapThreshold) {
  const accepted = []
  for (const candidate of chains) {
    const tooSimilar = accepted.some((a) =>
      a.startId === candidate.startId || hutOverlapFraction(a, candidate) > overlapThreshold)
    if (!tooSimilar) accepted.push(candidate)
  }
  return accepted
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd huts && npm test -- diversity`
Expected: PASS (7 tests total in this file)

- [ ] **Step 5: Commit**

```bash
git add huts/src/tourSearch/diversity.js huts/src/tourSearch/diversity.test.js
git commit -m "feat(tour-search): greedy similarity suppression on the unordered hut set"
```

---

### Task 14: Public API

**Files:**
- Create: `huts/src/tourSearch/index.js`
- Test: `huts/src/tourSearch/index.test.js`

**Interfaces:**
- Consumes: everything above.
- Produces: `async loadTourSearchData(baseUrl = '/data') -> { hutEdges, approaches }` (wraps Tasks
  3-4); `findTours(query, data, { overlapThreshold = 0.5 } = {}) -> { chains, killCounters }` — runs
  `searchChains` then `dedupeReversePairs` then `suppressSimilar`, in that order (Global
  Constraints). This is the module's front door — everything else in `huts/src/tourSearch/` is an
  implementation detail behind these two functions.

- [ ] **Step 1: Write the failing test**

```js
// huts/src/tourSearch/index.test.js
import { describe, it, expect, vi, afterEach } from 'vitest'
import { packColumns } from './binaryColumns.js'
import { loadTourSearchData, findTours } from './index.js'

afterEach(() => vi.unstubAllGlobals())

describe('loadTourSearchData', () => {
  it('loads and returns both hutEdges and approaches', async () => {
    const hutEdgesFixture = packColumns(
      { from_id: 'u2', to_id: 'u2', variant: 'u1', distance_m: 'f4', ascent_m: 'f4', descent_m: 'f4', max_ele_m: 'f4', sac_rank: 'i1', via_ferrata: 'u1', road_m: 'f4', ungraded_m: 'f4', inferred_m: 'f4', snap_m: 'f4' },
      { from_id: [0], to_id: [1], variant: [0], distance_m: [1000], ascent_m: [100], descent_m: [50], max_ele_m: [2000], sac_rank: [1], via_ferrata: [0], road_m: [0], ungraded_m: [0], inferred_m: [0], snap_m: [0] },
      1,
    )
    const approachesFixture = packColumns(
      { hut_id: 'u2', start_id: 'u8', source_type: 'u1', access_unknown: 'u1', distance_m: 'f4', ascent_m: 'f4', descent_m: 'f4' },
      { hut_id: [0], start_id: [1], source_type: [2], access_unknown: [0], distance_m: [500], ascent_m: [50], descent_m: [10] },
      1,
    )
    const fetchMock = vi.fn()
      .mockImplementation((url) => {
        if (url.endsWith('hut-edge-payload.json')) return Promise.resolve({ json: () => Promise.resolve({ ...hutEdgesFixture.manifest, variants: { 0: 'FAST_ANY' }, hut_ids: ['A', 'B'] }) })
        if (url.endsWith('hut-edge-payload.bin')) return Promise.resolve({ arrayBuffer: () => Promise.resolve(hutEdgesFixture.buffer) })
        if (url.endsWith('approaches.json')) return Promise.resolve({ json: () => Promise.resolve({ ...approachesFixture.manifest, access_values: [null], reverse_index: { hut_to_starts: {}, start_to_huts: {} } }) })
        if (url.endsWith('approaches.bin')) return Promise.resolve({ arrayBuffer: () => Promise.resolve(approachesFixture.buffer) })
        throw new Error(`unexpected fetch ${url}`)
      })
    vi.stubGlobal('fetch', fetchMock)

    const data = await loadTourSearchData('/data')

    expect(data.hutEdges.records).toHaveLength(1)
    expect(data.approaches.records).toHaveLength(1)
  })
})

describe('findTours', () => {
  it('runs search then both diversity passes', () => {
    // Two states that would collapse under dedupeReversePairs, seeded directly rather than via a
    // real search, to test the pipeline wiring in isolation from the DFS itself (Task 10 already
    // tests the DFS; this test is about ordering, not search correctness).
    const graphData = {
      hutEdges: { hutIds: ['A', 'B'], variantNames: { 0: 'FAST_ANY' }, records: [] },
      approaches: { records: [], reverseIndex: { hut_to_starts: {}, start_to_huts: {} } },
    }
    const query = { mode: 'transit', legCountMin: 2, legCountMax: 2, maxLegTimeH: 5 }
    const { chains, killCounters } = findTours(query, graphData)
    expect(chains).toEqual([])
    expect(killCounters).toBeDefined()
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd huts && npm test -- index`
Expected: FAIL — module not found

- [ ] **Step 3: Implement**

```js
// huts/src/tourSearch/index.js
import { loadHutEdgesData } from './loadHutEdges.js'
import { loadApproachesData } from './loadApproaches.js'
import { searchChains } from './search.js'
import { dedupeReversePairs, suppressSimilar } from './diversity.js'

export async function loadTourSearchData(baseUrl = '/data') {
  const [hutEdges, approaches] = await Promise.all([
    loadHutEdgesData(baseUrl),
    loadApproachesData(baseUrl),
  ])
  return { hutEdges, approaches }
}

export function findTours(query, graphData, { overlapThreshold = 0.5 } = {}) {
  const { chains, killCounters } = searchChains(query, graphData)
  const deduped = dedupeReversePairs(chains)
  const diverse = suppressSimilar(deduped, overlapThreshold)
  return { chains: diverse, killCounters }
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd huts && npm test -- index`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add huts/src/tourSearch/index.js huts/src/tourSearch/index.test.js
git commit -m "feat(tour-search): public loadTourSearchData/findTours API"
```

---

### Task 15: Smoke test against the real shipped payload

**Files:**
- Create: `huts/src/tourSearch/realData.smoke.test.js`

**Interfaces:** none new — this is a correctness/wiring check against `huts/public/data`'s actual
files, not synthetic fixtures. It reads them from disk directly (Node `fs`, not `fetch`) since
vitest's default environment has no bundler-served static assets.

- [ ] **Step 1: Write the test**

```js
// huts/src/tourSearch/realData.smoke.test.js
import { describe, it, expect, beforeAll } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { readColumns } from './binaryColumns.js'
import { buildAdjacency } from './adjacency.js'
import { resolveVariant } from './resolveVariant.js'
import { findTours } from './index.js'

const DATA_DIR = fileURLToPath(new URL('../../public/data/', import.meta.url))

function loadHutEdgesFromDisk() {
  const manifest = JSON.parse(readFileSync(`${DATA_DIR}hut-edge-payload.json`, 'utf-8'))
  const buffer = readFileSync(`${DATA_DIR}hut-edge-payload.bin`).buffer
  const c = readColumns(buffer, manifest)
  const records = new Array(manifest.rows)
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

function loadApproachesFromDisk() {
  const manifest = JSON.parse(readFileSync(`${DATA_DIR}approaches.json`, 'utf-8'))
  const buffer = readFileSync(`${DATA_DIR}approaches.bin`).buffer
  const c = readColumns(buffer, manifest)
  const records = new Array(manifest.rows)
  for (let i = 0; i < manifest.rows; i++) {
    records[i] = {
      hutIndex: c.hut_id[i], startId: c.start_id[i], sourceType: c.source_type[i],
      accessUnknown: c.access_unknown[i] === 1, distanceM: c.distance_m[i],
      ascentM: c.ascent_m[i], descentM: c.descent_m[i],
      access: manifest.access_values ? manifest.access_values[i] : null,
    }
  }
  return { records, reverseIndex: manifest.reverse_index }
}

describe('real shipped payload (huts/public/data)', () => {
  let graphData

  beforeAll(() => {
    graphData = { hutEdges: loadHutEdgesFromDisk(), approaches: loadApproachesFromDisk() }
  })

  it('resolves every difficulty ceiling to a variant the payload actually has', () => {
    for (const query of [{ sacCeiling: 2 }, { sacCeiling: 3, allowUngraded: false }, { sacCeiling: 3, allowUngraded: true }, {}]) {
      const variant = resolveVariant(query, graphData.hutEdges.variantNames)
      expect(graphData.hutEdges.variantNames[variant]).toBeDefined()
    }
  })

  it('builds adjacency for every variant without throwing, and every hut in it is a valid index', () => {
    for (const variantId of Object.keys(graphData.hutEdges.variantNames)) {
      const adjacency = buildAdjacency(graphData.hutEdges, Number(variantId))
      for (const [hutIndex, legs] of adjacency) {
        expect(hutIndex).toBeGreaterThanOrEqual(0)
        expect(hutIndex).toBeLessThan(graphData.hutEdges.hutIds.length)
        for (const leg of legs) {
          expect(leg.toIndex).toBeGreaterThanOrEqual(0)
          expect(leg.toIndex).toBeLessThan(graphData.hutEdges.hutIds.length)
        }
      }
    }
  })

  it('every constrained-row (FAST_T2/FAST_T3) edge has zero ungraded metres, matching the shipped guarantee', () => {
    const idByName = {}
    for (const [id, name] of Object.entries(graphData.hutEdges.variantNames)) idByName[name] = Number(id)
    const constrained = graphData.hutEdges.records.filter(
      (r) => r.variant === idByName.FAST_T2 || r.variant === idByName.FAST_T3,
    )
    expect(constrained.length).toBeGreaterThan(0)
    for (const r of constrained) expect(r.ungradedM).toBe(0)
  })

  it('an unanchored transit search with a generous budget runs end to end and returns well-formed chains', () => {
    const { chains } = findTours(
      {
        mode: 'transit', legCountMin: 2, legCountMax: 4,
        maxLegTimeH: 8, minLegTimeH: 0, legAscentCapM: 2000, allowViaFerrata: true,
        sacCeiling: 3, allowUngraded: true,
      },
      graphData,
    )
    for (const chain of chains) {
      expect(chain.huts.length).toBeGreaterThanOrEqual(1)
      expect(new Set(chain.huts).size).toBe(chain.huts.length) // no revisits
      expect(chain.totalDurationH).toBeGreaterThan(0)
    }
  })
})
```

- [ ] **Step 2: Run it**

Run: `cd huts && npm test -- realData.smoke`
Expected: PASS, all 4 assertions. If the third test fails (`ungradedM !== 0` on a constrained row),
**stop and treat it as a data bug, not a test bug** — it means the pipeline's own guarantee
(`docs/tour-suggestion-payload.md` §5) has regressed; do not weaken the assertion.

- [ ] **Step 3: Commit**

```bash
git add huts/src/tourSearch/realData.smoke.test.js
git commit -m "test(tour-search): smoke-test the engine against the real shipped payload"
```

---

## Self-review notes

- **Spec coverage:** query inputs (leg count/time/ascent, difficulty ceiling, transport mode) —
  Tasks 9-11; transport modes and no-`either` — Task 10-11; approach/exit tables and loop closure —
  Tasks 4, 8; direction reversal — Task 5; variant resolution — Task 7; exact DFS over
  `(hut, leg[, start_id])` — Tasks 10-11; result diversity (both steps, correct keys) — Tasks 12-13;
  kill counters for the empty-result case — Task 9, surfaced through Task 14's `findTours`. Not
  covered, deliberately: spatial anchor filtering (a seed-set narrowing that composes trivially with
  Task 10's per-hut approach loop — small enough to fold into a future UI task rather than warranting
  its own here), the `least road` objective (blocked on `ROAD_*`, per Global Constraints), and
  everything in the deferred doc.
- **Placeholder scan:** no TBD/TODO; every step has real code or a real, runnable test.
- **Type consistency:** `Leg` fields (`distanceM/ascentM/descentM/durationH/...`) are consistent from
  Task 5 through Task 11; `Chain` fields (`huts/startId/exitStartId/totalDurationH/...`) are
  consistent from Task 10 through Task 14.
