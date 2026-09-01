# Hut-availability-based routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user pick a start date + party size in the tour-search form and see, per hut in
each candidate tour, whether it has free beds that night — either as a hard filter or as
badges — sourced live from the Alpenverein/OHRS bed-availability API.

**Architecture:** A small additive pipeline change ships `ohrsHutId`/`tenantCode` on every hut
feature in `huts.geojson`. A new, `tourSearch`-independent `huts/src/availability/` client module
wraps the two OHRS endpoints (bulk map-wide `collectAll`, per-hut detail) with in-memory caching.
`tourSearch/search.ts` gains one more pruning check, structurally identical to the existing
`allowedHutIndices` hut-identity check, gated behind an optional `Query.availability` field so
omitting it reproduces today's behavior exactly. The form/list/detail UI in `tourSearchPage/`
wires the two together: badges are always computed from one shared fetch, filtering is opt-in via
a checkbox.

**Tech Stack:** Python (pipeline, pytest via `pixi run test`), TypeScript/React/MUI (`huts/`,
vitest via `npm test --`).

**Spec:** `docs/superpowers/specs/2026-09-01-hut-availability-routing-design.md`

## Global Constraints

- Dates sent to OHRS are always `DD.MM.YYYY` (spec §2, §5 of `docs/alpenverein-api.md`).
- The per-hut endpoint (OHRS 2b / `fetchHutDetail`) is called at most once per hut in one already-
  expanded tour's detail panel — **never** looped over the full hut list or the full result list
  (root `CLAUDE.md`, spec §2/§4).
- The bulk endpoint (OHRS 2a / `fetchAvailabilityByOffset`) fires exactly one `collectAll` POST
  per night-offset (`1..maxOffsetDays`), in parallel — never per hut (spec §2).
- No booking/reservation flow: the app only reads OHRS and links out to
  `hut-reservation.org/reservation/book-hut/...` (spec "Non-goals").
- One leg = one night, no per-leg custom dates (spec "Non-goals", §3 date model).
- `Query.availability` is optional; when absent, `searchChains` output must be byte-for-byte
  identical to before this plan (spec §3).
- Root-layer rule (`CLAUDE.md`): the `ohrsHutId`/`tenantCode` data-contract change belongs in
  `pipeline/`; UI/interaction concerns (badges, checkbox, detail panel) belong in `huts/`.
- **Never run any `pipeline/` doit task** as part of this plan — Task 1 only edits
  `fetch_huts.py`/its test, it does not need to run `doit fetch_huts` to be verified (the unit
  tests exercise `classify_hut`/`split_features` directly, in-process, without touching the
  network or `data/`).

---

### Task 1: Pipeline — ship `ohrsHutId`/`tenantCode` in `huts.geojson`

**Files:**
- Modify: `pipeline/phases/downloads/fetch_huts.py`
- Test: `pipeline/tests/test_fetch_huts.py`

**Interfaces:**
- Produces: every hut feature in `huts.geojson` gains `properties.ohrsHutId: string | null` and
  `properties.tenantCode: int | null`. `partner_betriebe.geojson` features are unaffected (still
  just `{id, name}`). Consumed by Task 9 (`TourSearchPage.tsx`'s data-loading effect) and, via that,
  by every later task that reads hut availability.

- [ ] **Step 1: Write the failing tests**

Open `pipeline/tests/test_fetch_huts.py`. Update the existing
`test_split_features_routes_partner_to_second_list_with_minimal_properties` test (it currently
asserts an exact `properties` dict that will gain two new keys) and add three new tests:

```python
def test_split_features_routes_partner_to_second_list_with_minimal_properties():
    features = [
        {"attributes": {"id": "{GUID-1}", "OBJECTID": 501, "name": "Bielefelder Hütte",
                         "kategorie_nr": 40, "verein_nr": 5, "meereshoehe": 2112,
                         "ohrs_hut_id": "179"},
         "geometry": {"x": 10.9, "y": 47.2}},
        {"attributes": {"id": "{GUID-2}", "OBJECTID": 502, "name": "Gasthof Alpenrose",
                         "kategorie_nr": 100, "verein_nr": 19, "meereshoehe": 1150,
                         "ohrs_hut_id": None},
         "geometry": {"x": 11.5, "y": 47.3}},
    ]

    huts, partners = split_features(features)

    assert len(huts) == 1 and len(partners) == 1
    assert huts[0]["properties"] == {
        "id": "{GUID-1}", "name": "Bielefelder Hütte", "hutType": "av",
        "serviced": True, "elevation": 2112, "ohrsHutId": "179", "tenantCode": 5,
    }
    assert partners[0]["properties"] == {"id": 502, "name": "Gasthof Alpenrose"}
    assert partners[0]["geometry"] == {"type": "Point", "coordinates": [11.5, 47.3]}


def test_split_features_hut_with_no_ohrs_id_gets_null_ohrs_hut_id():
    # Direct-booking-only hut: the ArcGIS layer returns ohrs_hut_id: null for these (spec §1).
    features = [
        {"attributes": {"id": "{GUID-3}", "OBJECTID": 503, "name": "Almhütte Privat",
                         "kategorie_nr": 30, "verein_nr": 14, "meereshoehe": 1600,
                         "ohrs_hut_id": None},
         "geometry": {"x": 11.0, "y": 47.4}},
    ]

    huts, _ = split_features(features)

    assert huts[0]["properties"]["ohrsHutId"] is None
    assert huts[0]["properties"]["tenantCode"] == 14


def test_split_features_hut_missing_ohrs_hut_id_field_entirely_gets_null():
    # Defensive: a record missing the key outright (not just null-valued) must not KeyError.
    features = [
        {"attributes": {"id": "{GUID-4}", "OBJECTID": 504, "name": "Alte Hütte",
                         "kategorie_nr": 30, "verein_nr": 8, "meereshoehe": 1900},
         "geometry": {"x": 11.2, "y": 47.5}},
    ]

    huts, _ = split_features(features)

    assert huts[0]["properties"]["ohrsHutId"] is None
    assert huts[0]["properties"]["tenantCode"] == 8


def test_out_fields_requests_ohrs_hut_id():
    from downloads.fetch_huts import OUT_FIELDS
    assert "ohrs_hut_id" in OUT_FIELDS.split(",")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd pipeline && pixi run test tests/test_fetch_huts.py -v`
Expected: the three new tests fail — the first two with a `KeyError`-free but wrong `assert
huts[0]["properties"] == {...}` (missing `ohrsHutId`/`tenantCode` keys), the third with
`ImportError: cannot import name 'OUT_FIELDS'`.

- [ ] **Step 3: Implement**

In `pipeline/phases/downloads/fetch_huts.py`:

1. Extract the `outFields` list to a module-level constant (so it's importable/testable without
   executing the `if __name__ == "__main__":` block, which would hit the network) and add
   `ohrs_hut_id`:

```python
OUT_FIELDS = "OBJECTID,id,name,kategorie_nr,verein_nr,meereshoehe,ohrs_hut_id"
```

2. In `split_features()`, add `ohrsHutId`/`tenantCode` to the hut-feature properties dict (the
   `else` branch — partner features are untouched):

```python
        else:
            huts.append({
                "type": "Feature",
                "properties": {
                    "id": a["id"], "name": a["name"], "hutType": hut_type,
                    "serviced": serviced, "elevation": a.get("meereshoehe"),
                    "ohrsHutId": a.get("ohrs_hut_id"), "tenantCode": a.get("verein_nr"),
                },
                "geometry": geometry,
            })
```

3. Update the docstring of `split_features()` to mention the two new properties, and update the
   `url = (...)` construction in `if __name__ == "__main__":` to build from `OUT_FIELDS`:

```python
    url = (
        "https://services1.arcgis.com/PHS4LHADrqt5glC9/arcgis/rest/services/"
        "AVT_GEO_CAA_HUETTEN_View_P/FeatureServer/0/query"
        f"?where=1%3D1&outFields={OUT_FIELDS}"
        "&returnGeometry=true&outSR=4326&resultRecordCount=8000&f=json"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd pipeline && pixi run test tests/test_fetch_huts.py -v`
Expected: all tests (existing + new) PASS.

- [ ] **Step 5: Run the full pipeline test suite to check for regressions**

Run: `cd pipeline && pixi run test`
Expected: all tests PASS (no other module reads `fetch_huts.py`'s hut-feature property shape, so
no other test file should be affected — confirm this is actually true rather than assuming it).

- [ ] **Step 6: Commit**

```bash
git add pipeline/phases/downloads/fetch_huts.py pipeline/tests/test_fetch_huts.py
git commit -m "$(cat <<'EOF'
feat(pipeline): ship ohrsHutId/tenantCode on huts.geojson features

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PSiy9D7gGYdGCoorzewPVZ
EOF
)"
```

---

### Task 2: `tourSearch` types — `Query.availability` + `KillCounters.availability`

**Files:**
- Modify: `huts/src/tourSearch/types.ts`
- Modify: `huts/src/tourSearch/legFilters.ts`
- Test: `huts/src/tourSearch/legFilters.test.ts`
- Modify (to keep the app type-checking — no new behavior): `huts/src/tourSearchPage/helpers.test.ts`,
  `huts/src/tourSearchPage/TourList.test.tsx`, `huts/src/tourSearchPage/TourSearchPage.test.tsx`

**Interfaces:**
- Produces: `Query['availability']` — `{ ohrsIdByHutIndex: Map<number, string | null>,
  freeByOffset: Map<number, Set<string> | 'unknown'> } | undefined`, consumed by Task 3
  (`search.ts`) and Task 7 (`formState.ts`'s `buildQuery`). `KillCounters.availability: number`,
  consumed by Task 3 and rendered nowhere yet (kept unguided in `helpers.ts`'s
  `KILL_COUNTER_GUIDANCE`, same as the existing `revisit`/`trackOverlap` internal counters — no
  user-facing message needed for it).

- [ ] **Step 1: Write the failing test**

In `huts/src/tourSearch/legFilters.test.ts`, add:

```ts
  it('createKillCounters starts availability at 0', () => {
    expect(createKillCounters().availability).toBe(0)
  })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd huts && npm test -- run src/tourSearch/legFilters.test.ts`
Expected: FAIL — `expect(undefined).toBe(0)`.

- [ ] **Step 3: Implement the type + counter changes**

In `huts/src/tourSearch/types.ts`, add to `Query`:

```ts
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
  availability?: {
    ohrsIdByHutIndex: Map<number, string | null>
    freeByOffset: Map<number, Set<string> | 'unknown'>
  }
}
```

Add to `KillCounters`:

```ts
export interface KillCounters {
  maxLegTime: number
  minLegTime: number
  legAscentCap: number
  maxEleM: number
  viaFerrata: number
  revisit: number
  hutFiltered: number
  trackOverlap: number
  availability: number
}
```

In `huts/src/tourSearch/legFilters.ts`, update `createKillCounters`:

```ts
export function createKillCounters(): KillCounters {
  return {
    maxLegTime: 0, minLegTime: 0, legAscentCap: 0, maxEleM: 0, viaFerrata: 0, revisit: 0,
    hutFiltered: 0, trackOverlap: 0, availability: 0,
  }
}
```

- [ ] **Step 4: Fix the other `KillCounters` literals so the app still type-checks**

`KillCounters` is now missing a required field in three test fixtures. Update each:

`huts/src/tourSearchPage/helpers.test.ts`, in the `killCounterGuidance hutFiltered` test:

```ts
    const msgs = killCounterGuidance({
      maxLegTime: 0, minLegTime: 0, legAscentCap: 0, maxEleM: 0, viaFerrata: 0, revisit: 0,
      hutFiltered: 7, trackOverlap: 0, availability: 0,
    })
```

`huts/src/tourSearchPage/TourList.test.tsx`:

```ts
const result: SearchResult = { chains: [chain], killCounters: { maxLegTime: 0, minLegTime: 0, legAscentCap: 0, maxEleM: 0, viaFerrata: 0, revisit: 0, hutFiltered: 0, trackOverlap: 0, availability: 0 } }
```

`huts/src/tourSearchPage/TourSearchPage.test.tsx`, both `killCounters: {...}` occurrences (the
top-level `searchResultFixture` and the one inside the GUID-ids test):

```ts
  killCounters: { maxLegTime: 0, minLegTime: 0, legAscentCap: 0, maxEleM: 0, viaFerrata: 0, revisit: 0, hutFiltered: 0, trackOverlap: 0, availability: 0 },
```

- [ ] **Step 5: Run tests + typecheck**

Run: `cd huts && npm test -- run src/tourSearch/legFilters.test.ts src/tourSearchPage/helpers.test.ts src/tourSearchPage/TourList.test.tsx src/tourSearchPage/TourSearchPage.test.tsx`
Expected: all PASS.

Run: `cd huts && npm run typecheck`
Expected: no errors (this is the check that catches any other `KillCounters`/`Query` literal this
grep-based sweep missed — if it fails on a file not listed above, fix that literal too before
moving on).

- [ ] **Step 6: Commit**

```bash
git add huts/src/tourSearch/types.ts huts/src/tourSearch/legFilters.ts huts/src/tourSearch/legFilters.test.ts huts/src/tourSearchPage/helpers.test.ts huts/src/tourSearchPage/TourList.test.tsx huts/src/tourSearchPage/TourSearchPage.test.tsx
git commit -m "$(cat <<'EOF'
feat(tourSearch): add Query.availability and KillCounters.availability types

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PSiy9D7gGYdGCoorzewPVZ
EOF
)"
```

---

### Task 3: `search.ts` — wire the availability pruning check

**Files:**
- Modify: `huts/src/tourSearch/search.ts`
- Test: `huts/src/tourSearch/search.test.ts`

**Interfaces:**
- Consumes: `Query['availability']`, `KillCounters.availability` from Task 2.
- Produces: `searchChains` now prunes a hut from a chain the moment its `Query.availability`-
  resolved offset shows no free beds; no change to `SearchResult`'s shape.

- [ ] **Step 1: Write the failing tests**

Add a new `describe` block to `huts/src/tourSearch/search.test.ts` (reusing the file's existing
3-hut `graphData` fixture — hut 0 = A, approach start 100 into A on offset/night 1; hut edge A→B is
night 2; hut edge B→C is night 3; hut 2 = C exits to start 200):

```ts
describe('searchChains availability pruning', () => {
  const availability = (ohrsIdByHutIndex: Map<number, string | null>, freeByOffset: Map<number, Set<string> | 'unknown'>) =>
    ({ ohrsIdByHutIndex, freeByOffset })

  it('rejects the whole chain when the seed hut has no free beds on night 1', () => {
    const { chains, killCounters } = searchChains(
      {
        mode: 'transit', legCountMin: 2, legCountMax: 4, ...generousConstraints,
        availability: availability(new Map([[0, 'ohrsA']]), new Map([[1, new Set<string>()]])),
      },
      graphData,
    )
    expect(chains).toHaveLength(0)
    expect(killCounters.availability).toBeGreaterThan(0)
  })

  it('a hut with ohrsHutId null (direct-booking-only) always passes, regardless of freeByOffset', () => {
    const { chains } = searchChains(
      {
        mode: 'transit', legCountMin: 3, legCountMax: 4, ...generousConstraints,
        availability: availability(new Map([[0, null]]), new Map([[1, new Set<string>()]])),
      },
      graphData,
    )
    expect(chains.some((c) => c.huts.length === 3)).toBe(true)
  })

  it("an 'unknown' offset always passes", () => {
    const { chains } = searchChains(
      {
        mode: 'transit', legCountMin: 3, legCountMax: 4, ...generousConstraints,
        availability: availability(new Map([[0, 'ohrsA']]), new Map<number, Set<string> | 'unknown'>([[1, 'unknown']])),
      },
      graphData,
    )
    expect(chains.some((c) => c.huts.length === 3)).toBe(true)
  })

  it('rejects an expansion hut with no free beds on its own night, without killing earlier huts', () => {
    const { chains, killCounters } = searchChains(
      {
        mode: 'transit', legCountMin: 2, legCountMax: 4, ...generousConstraints,
        availability: availability(
          new Map([[0, 'ohrsA'], [1, 'ohrsB']]),
          new Map<number, Set<string> | 'unknown'>([[1, new Set(['ohrsA'])], [2, new Set<string>()]]),
        ),
      },
      graphData,
    )
    expect(chains.some((c) => c.huts.includes(1))).toBe(false)
    expect(chains.some((c) => c.huts.length === 3)).toBe(false)
    expect(killCounters.availability).toBeGreaterThan(0)
  })

  it('is byte-for-byte identical to an unconstrained search when availability is absent', () => {
    const withoutAvailability = searchChains({ mode: 'transit', legCountMin: 2, legCountMax: 4, ...generousConstraints }, graphData)
    const withUndefinedAvailability = searchChains({ mode: 'transit', legCountMin: 2, legCountMax: 4, ...generousConstraints, availability: undefined }, graphData)
    expect(withUndefinedAvailability.chains).toEqual(withoutAvailability.chains)
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd huts && npm test -- run src/tourSearch/search.test.ts`
Expected: the four new behavioral tests FAIL (availability is not yet read anywhere, so every hut
passes regardless of `freeByOffset`/`ohrsIdByHutIndex` — the "rejects the whole chain" and "rejects
an expansion hut" tests fail because chains that should be pruned still appear; the last test
passes trivially already and is there to lock in the no-regression guarantee going forward).

- [ ] **Step 3: Implement**

In `huts/src/tourSearch/search.ts`, add the helper above `export function searchChains` and thread
`availability` through:

```ts
function hutAvailable(h: number, offsetDays: number, availability: Query['availability']): boolean {
  if (!availability) return true
  const ohrsId = availability.ohrsIdByHutIndex.get(h)
  if (ohrsId == null) return true // no OHRS id (direct-booking-only) or huts.geojson lacked it: pass/unknown
  const free = availability.freeByOffset.get(offsetDays)
  if (free === 'unknown' || free === undefined) return true // fetch failed for this night: pass/unknown
  return free.has(ohrsId)
}
```

Update the destructuring at the top of `searchChains`:

```ts
  const {
    mode, legCountMin, legCountMax, sacCeiling, allowUngraded = false,
    maxLegTimeH, minLegTimeH = 0, legAscentCapM = Infinity, maxEleM = null, allowViaFerrata = true,
    allowedHutIndices, availability,
  } = query
```

In the seed loop, add the check right after the existing `allowedHutIndices` check (once per `h`,
before the `for (const approachLeg ...)` loop — offset is always 1 for a seed hut):

```ts
  for (let h = 0; h < graphData.hutEdges.hutIds.length; h++) {
    if (allowedHutIndices && !allowedHutIndices.has(h)) { killCounters.hutFiltered++; continue }
    if (!hutAvailable(h, 1, availability)) { killCounters.availability++; continue }
    for (const approachLeg of getApproachLegs(h, graphData.approaches)) {
```

In the expansion loop, add the check after the existing `allowedHutIndices`/revisit checks, before
`legPasses`:

```ts
          const h2 = leg.toIndex
          if (allowedHutIndices && !allowedHutIndices.has(h2)) { killCounters.hutFiltered++; continue }
          if (s.path.includes(h2)) { killCounters.revisit++; continue }
          if (!hutAvailable(h2, s.path.length + 1, availability)) { killCounters.availability++; continue }
          if (!legPasses(leg, constraints, killCounters)) continue
```

`collectFinished`'s exit-leg loop is untouched — the exit leg goes to a parking lot/station/village
point, not a hut, so there is no night there to check.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd huts && npm test -- run src/tourSearch/search.test.ts`
Expected: all PASS, including every pre-existing test in the file (confirms the byte-for-byte
no-`availability` guarantee holds for the file's other fixtures too, not just the new one).

- [ ] **Step 5: Run the full frontend test suite + typecheck**

Run: `cd huts && npm test -- run && npm run typecheck`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add huts/src/tourSearch/search.ts huts/src/tourSearch/search.test.ts
git commit -m "$(cat <<'EOF'
feat(tourSearch): prune chains by hut-availability during search

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PSiy9D7gGYdGCoorzewPVZ
EOF
)"
```

---

### Task 4: `huts/src/availability/` — types + date formatting

**Files:**
- Create: `huts/src/availability/types.ts`
- Create: `huts/src/availability/formatDate.ts`
- Test: `huts/src/availability/formatDate.test.ts`

**Interfaces:**
- Produces: `BedCategory`, `CalendarDay`, `HutDetail`, `FreeByOffset` types; `formatOhrsDate(date:
  Date, offsetDays?: number): string` — `DD.MM.YYYY`, UTC-safe. Consumed by every later task in
  this module and by Task 11 (`AvailabilityDetailPanel.tsx`).

- [ ] **Step 1: Write the failing test**

Create `huts/src/availability/formatDate.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { formatOhrsDate } from './formatDate.js'

describe('formatOhrsDate', () => {
  it('formats a Date as DD.MM.YYYY with zero-padding', () => {
    expect(formatOhrsDate(new Date(Date.UTC(2026, 7, 5)))).toBe('05.08.2026')
  })

  it('adds offsetDays before formatting', () => {
    expect(formatOhrsDate(new Date(Date.UTC(2026, 7, 30)), 3)).toBe('02.09.2026')
  })

  it('offsetDays defaults to 0', () => {
    expect(formatOhrsDate(new Date(Date.UTC(2026, 0, 1)))).toBe('01.01.2026')
  })

  it('crosses a year boundary correctly', () => {
    expect(formatOhrsDate(new Date(Date.UTC(2026, 11, 31)), 1)).toBe('01.01.2027')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd huts && npm test -- run src/availability/formatDate.test.ts`
Expected: FAIL — `Cannot find module './formatDate.js'`.

- [ ] **Step 3: Implement**

Create `huts/src/availability/types.ts`:

```ts
export interface BedCategory {
  totalPlaces: number
  occupation: string
  totalFreePlaces: number
  label: string
}

export interface CalendarDay {
  day: string
  reservationMode: string
  status: string
  bedCategoriesData: BedCategory[]
}

export interface HutDetail {
  hutId: number
  hutName: string
  calendarDays: CalendarDay[]
}

/** offsetDays (1..maxOffsetDays) -> the set of ohrsHutIds with free beds that night, or
 *  'unknown' if that offset's collectAll request failed. */
export type FreeByOffset = Map<number, Set<string> | 'unknown'>
```

Create `huts/src/availability/formatDate.ts`:

```ts
/** DD.MM.YYYY, the date format every OHRS endpoint expects (docs/alpenverein-api.md).
 *  UTC-safe: adds offsetDays via Date.UTC arithmetic rather than local-time setDate, so a
 *  native <input type="date"> value (parsed as UTC midnight) never drifts a day from DST. */
export function formatOhrsDate(date: Date, offsetDays = 0): string {
  const d = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate() + offsetDays))
  const dd = String(d.getUTCDate()).padStart(2, '0')
  const mm = String(d.getUTCMonth() + 1).padStart(2, '0')
  return `${dd}.${mm}.${d.getUTCFullYear()}`
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd huts && npm test -- run src/availability/formatDate.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add huts/src/availability/types.ts huts/src/availability/formatDate.ts huts/src/availability/formatDate.test.ts
git commit -m "$(cat <<'EOF'
feat(availability): add types and OHRS date formatting

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PSiy9D7gGYdGCoorzewPVZ
EOF
)"
```

---

### Task 5: `fetchAvailabilityByOffset` (OHRS 2a, bulk map-wide)

**Files:**
- Create: `huts/src/availability/fetchAvailability.ts`
- Test: `huts/src/availability/fetchAvailability.test.ts`

**Interfaces:**
- Consumes: `formatOhrsDate` (Task 4), `FreeByOffset` (Task 4).
- Produces: `fetchAvailabilityByOffset(startDate: Date, numOfPeople: number, maxOffsetDays:
  number): Promise<FreeByOffset>`. Consumed by Task 9 (`TourSearchPage.tsx`).

- [ ] **Step 1: Write the failing test**

Create `huts/src/availability/fetchAvailability.test.ts`:

```ts
import { describe, it, expect, vi, afterEach } from 'vitest'
import { fetchAvailabilityByOffset } from './fetchAvailability.js'

afterEach(() => vi.unstubAllGlobals())

function jsonResponse(body: unknown, ok = true) {
  return Promise.resolve({ ok, json: () => Promise.resolve(body) } as Response)
}

describe('fetchAvailabilityByOffset', () => {
  it('fires one POST per offset day, in parallel, with the right body', async () => {
    const fetchMock = vi.fn().mockImplementation((_url: string, init: RequestInit) => {
      const body = JSON.parse(init.body as string) as { startDate: string; numOfPeople: number; collectAll: boolean }
      if (body.startDate === '21.08.2026') return jsonResponse([1, 2])
      if (body.startDate === '22.08.2026') return jsonResponse([2, 3])
      throw new Error(`unexpected startDate ${body.startDate}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchAvailabilityByOffset(new Date(Date.UTC(2026, 7, 20)), 2, 2)

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(fetchMock.mock.calls[0][0]).toBe('https://caa.alpenverein.at/service/server/callOHRS_REST.php')
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).numOfPeople).toBe(2)
    expect(result.get(1)).toEqual(new Set(['1', '2']))
    expect(result.get(2)).toEqual(new Set(['2', '3']))
  })

  it("marks an offset 'unknown' when its request fails, without affecting other offsets", async () => {
    const fetchMock = vi.fn().mockImplementation((_url: string, init: RequestInit) => {
      const body = JSON.parse(init.body as string) as { startDate: string }
      if (body.startDate === '21.08.2026') return Promise.reject(new Error('network error'))
      return jsonResponse([5])
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchAvailabilityByOffset(new Date(Date.UTC(2026, 7, 20)), 1, 2)

    expect(result.get(1)).toBe('unknown')
    expect(result.get(2)).toEqual(new Set(['5']))
  })

  it("marks an offset 'unknown' on a non-ok HTTP response", async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, json: () => Promise.resolve([]) } as Response))

    const result = await fetchAvailabilityByOffset(new Date(Date.UTC(2026, 7, 20)), 1, 1)

    expect(result.get(1)).toBe('unknown')
  })

  it('caches by (date, numOfPeople): a second call for the same night+party size does not refetch', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([9]) } as Response)
    vi.stubGlobal('fetch', fetchMock)

    await fetchAvailabilityByOffset(new Date(Date.UTC(2026, 7, 20)), 2, 1)
    await fetchAvailabilityByOffset(new Date(Date.UTC(2026, 7, 20)), 2, 1)

    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd huts && npm test -- run src/availability/fetchAvailability.test.ts`
Expected: FAIL — `Cannot find module './fetchAvailability.js'`.

- [ ] **Step 3: Implement**

Create `huts/src/availability/fetchAvailability.ts`:

```ts
import { formatOhrsDate } from './formatDate.js'
import type { FreeByOffset } from './types.js'

const OHRS_URL = 'https://caa.alpenverein.at/service/server/callOHRS_REST.php'

// Keyed by the resolved date string (not the raw offset) + numOfPeople: two calls with the same
// offsetDays but different startDate resolve to different real-world nights and must not share a
// cache entry. Caches the in-flight Promise, not just the resolved value, so two concurrent
// fetchAvailabilityByOffset calls for the same night+party size still only fire one request.
const cache = new Map<string, Promise<Set<string> | 'unknown'>>()

async function fetchOneOffset(dateStr: string, numOfPeople: number): Promise<Set<string> | 'unknown'> {
  try {
    const res = await fetch(OHRS_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ startDate: dateStr, numOfPeople, collectAll: true }),
    })
    if (!res.ok) return 'unknown'
    const ids: unknown = await res.json()
    if (!Array.isArray(ids)) return 'unknown'
    return new Set(ids.map((id) => String(id)))
  } catch {
    return 'unknown'
  }
}

export async function fetchAvailabilityByOffset(
  startDate: Date,
  numOfPeople: number,
  maxOffsetDays: number,
): Promise<FreeByOffset> {
  const offsets = Array.from({ length: maxOffsetDays }, (_, i) => i + 1)
  const entries = await Promise.all(
    offsets.map(async (offset) => {
      const dateStr = formatOhrsDate(startDate, offset)
      const cacheKey = `${dateStr}|${numOfPeople}`
      if (!cache.has(cacheKey)) cache.set(cacheKey, fetchOneOffset(dateStr, numOfPeople))
      return [offset, await cache.get(cacheKey)!] as const
    }),
  )
  return new Map(entries)
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd huts && npm test -- run src/availability/fetchAvailability.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add huts/src/availability/fetchAvailability.ts huts/src/availability/fetchAvailability.test.ts
git commit -m "$(cat <<'EOF'
feat(availability): add fetchAvailabilityByOffset (OHRS bulk collectAll)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PSiy9D7gGYdGCoorzewPVZ
EOF
)"
```

---

### Task 6: `fetchHutDetail` (OHRS 2b, per-hut) + booking deep link

**Files:**
- Create: `huts/src/availability/bookingLink.ts`
- Create: `huts/src/availability/fetchHutDetail.ts`
- Test: `huts/src/availability/bookingLink.test.ts`
- Test: `huts/src/availability/fetchHutDetail.test.ts`

**Interfaces:**
- Consumes: `formatOhrsDate`, `HutDetail`/`BedCategory`/`CalendarDay` (Task 4).
- Produces: `buildBookingLink(ohrsHutId: string, date: Date): string`;
  `fetchHutDetail(ohrsHutId: string, tenantCode: number, date: Date, numOfPeople: number):
  Promise<HutDetail>`. Both consumed by Task 11 (`AvailabilityDetailPanel.tsx`).

- [ ] **Step 1: Write the failing tests**

Create `huts/src/availability/bookingLink.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { buildBookingLink } from './bookingLink.js'

describe('buildBookingLink', () => {
  it('builds a one-night dateFrom/dateTo deep link to hut-reservation.org', () => {
    const link = buildBookingLink('179', new Date(Date.UTC(2026, 7, 20)))
    expect(link).toBe('https://www.hut-reservation.org/reservation/book-hut/179/wizard?dateFrom=20.08.2026&dateTo=21.08.2026')
  })
})
```

Create `huts/src/availability/fetchHutDetail.test.ts`:

```ts
import { describe, it, expect, vi, afterEach } from 'vitest'
import { fetchHutDetail } from './fetchHutDetail.js'

afterEach(() => vi.unstubAllGlobals())

const RAW_RESPONSE = [{
  page: 0, resultsPerPage: 1, totalPages: 1,
  hutsAvailability: [{
    hutID: 179, hutName: 'Pfeis-Hütte',
    calendarDays: [{
      day: '20.08.2026', reservationMode: 'SERVICED', status: 'RESERVATION_NOT_POSSIBLE',
      bedCategoriesData: [{
        totalPlaces: 37, occupation: 'HIGH', totalFreePlaces: 0,
        hutBedCategoryLanguagesData: [{ language: 'DE_DE', label: 'Matratzenlager', shortLabel: 'ML' }],
      }],
    }],
  }],
}]

describe('fetchHutDetail', () => {
  it('parses the OHRS per-hut response into HutDetail, picking the DE_DE label', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(RAW_RESPONSE) } as Response)
    vi.stubGlobal('fetch', fetchMock)

    const detail = await fetchHutDetail('179', 8, new Date(Date.UTC(2026, 7, 20)), 2)

    expect(fetchMock).toHaveBeenCalledWith('https://caa.alpenverein.at/service/server/callOHRS_REST.php', expect.objectContaining({ method: 'POST' }))
    const body = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(body).toMatchObject({ startDate: '20.08.2026', endDate: '21.08.2026', huts: ['179'], numOfPeople: '2', tenantCode: 8 })
    expect(detail.hutId).toBe(179)
    expect(detail.hutName).toBe('Pfeis-Hütte')
    expect(detail.calendarDays[0]).toMatchObject({ day: '20.08.2026', status: 'RESERVATION_NOT_POSSIBLE' })
    expect(detail.calendarDays[0].bedCategoriesData[0]).toEqual({
      totalPlaces: 37, occupation: 'HIGH', totalFreePlaces: 0, label: 'Matratzenlager',
    })
  })

  it("falls back to a TECHNICAL_ERROR HutDetail on a failed request", async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network error')))

    const detail = await fetchHutDetail('179', 8, new Date(Date.UTC(2026, 7, 20)), 2)

    expect(detail.calendarDays).toEqual([{ day: '20.08.2026', reservationMode: '', status: 'TECHNICAL_ERROR', bedCategoriesData: [] }])
  })

  it("falls back to TECHNICAL_ERROR when tenantCode is wrong (OHRS 400)", async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false, json: () => Promise.resolve({ messageId: 302, description: 'Tenant code not found', statusCode: 400 }),
    } as Response))

    const detail = await fetchHutDetail('179', 999, new Date(Date.UTC(2026, 7, 20)), 2)

    expect(detail.calendarDays[0].status).toBe('TECHNICAL_ERROR')
  })

  it('caches by (ohrsHutId, date, numOfPeople): a repeated call does not refetch', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(RAW_RESPONSE) } as Response)
    vi.stubGlobal('fetch', fetchMock)

    await fetchHutDetail('179', 8, new Date(Date.UTC(2026, 7, 20)), 2)
    await fetchHutDetail('179', 8, new Date(Date.UTC(2026, 7, 20)), 2)

    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd huts && npm test -- run src/availability/bookingLink.test.ts src/availability/fetchHutDetail.test.ts`
Expected: FAIL — modules don't exist yet.

- [ ] **Step 3: Implement**

Create `huts/src/availability/bookingLink.ts`:

```ts
import { formatOhrsDate } from './formatDate.js'

/** German is the app's only UI language, matching hut-reservation.org's default (no lang= param
 *  needed — docs/alpenverein-api.md's "Booking deep link" section). */
export function buildBookingLink(ohrsHutId: string, date: Date): string {
  const dateFrom = formatOhrsDate(date, 0)
  const dateTo = formatOhrsDate(date, 1)
  return `https://www.hut-reservation.org/reservation/book-hut/${ohrsHutId}/wizard?dateFrom=${dateFrom}&dateTo=${dateTo}`
}
```

Create `huts/src/availability/fetchHutDetail.ts`:

```ts
import { formatOhrsDate } from './formatDate.js'
import type { HutDetail } from './types.js'

const OHRS_URL = 'https://caa.alpenverein.at/service/server/callOHRS_REST.php'

interface OhrsBedCategoryLanguageRaw {
  language: string
  label: string
  shortLabel: string
}

interface OhrsBedCategoryRaw {
  totalPlaces: number
  occupation: string
  totalFreePlaces: number
  hutBedCategoryLanguagesData: OhrsBedCategoryLanguageRaw[]
}

interface OhrsCalendarDayRaw {
  day: string
  reservationMode: string
  status: string
  bedCategoriesData: OhrsBedCategoryRaw[]
}

interface OhrsHutAvailabilityRaw {
  hutID: number
  hutName: string
  calendarDays: OhrsCalendarDayRaw[]
}

interface OhrsDetailResponseRaw {
  hutsAvailability: OhrsHutAvailabilityRaw[]
}

const cache = new Map<string, Promise<HutDetail>>()

function technicalErrorDetail(ohrsHutId: string, dateStr: string): HutDetail {
  return {
    hutId: Number(ohrsHutId), hutName: '',
    calendarDays: [{ day: dateStr, reservationMode: '', status: 'TECHNICAL_ERROR', bedCategoriesData: [] }],
  }
}

function toHutDetail(raw: OhrsHutAvailabilityRaw): HutDetail {
  return {
    hutId: raw.hutID,
    hutName: raw.hutName,
    calendarDays: raw.calendarDays.map((day) => ({
      day: day.day,
      reservationMode: day.reservationMode,
      status: day.status,
      bedCategoriesData: day.bedCategoriesData.map((bc) => ({
        totalPlaces: bc.totalPlaces,
        occupation: bc.occupation,
        totalFreePlaces: bc.totalFreePlaces,
        label: bc.hutBedCategoryLanguagesData.find((l) => l.language === 'DE_DE')?.label ?? '',
      })),
    })),
  }
}

async function fetchOneDetail(
  ohrsHutId: string, tenantCode: number, dateStr: string, endDateStr: string, numOfPeople: number,
): Promise<HutDetail> {
  try {
    const res = await fetch(OHRS_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        startDate: dateStr, endDate: endDateStr, huts: [ohrsHutId],
        numOfPeople: String(numOfPeople), onlyAvailablePlaces: false, page: 0, tenantCode,
      }),
    })
    if (!res.ok) return technicalErrorDetail(ohrsHutId, dateStr)
    const data: OhrsDetailResponseRaw[] = await res.json()
    const raw = data[0]?.hutsAvailability?.[0]
    if (!raw) return technicalErrorDetail(ohrsHutId, dateStr)
    return toHutDetail(raw)
  } catch {
    return technicalErrorDetail(ohrsHutId, dateStr)
  }
}

/** One night = startDate/endDate = date/date+1, matching this app's one-leg-one-night model
 *  (docs/superpowers/specs/2026-09-01-hut-availability-routing-design.md §3). Never call this in
 *  a loop over more than one already-expanded tour's huts — one request per hut, per night. */
export function fetchHutDetail(
  ohrsHutId: string, tenantCode: number, date: Date, numOfPeople: number,
): Promise<HutDetail> {
  const dateStr = formatOhrsDate(date, 0)
  const endDateStr = formatOhrsDate(date, 1)
  const cacheKey = `${ohrsHutId}|${dateStr}|${numOfPeople}`
  if (!cache.has(cacheKey)) cache.set(cacheKey, fetchOneDetail(ohrsHutId, tenantCode, dateStr, endDateStr, numOfPeople))
  return cache.get(cacheKey)!
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd huts && npm test -- run src/availability/bookingLink.test.ts src/availability/fetchHutDetail.test.ts`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add huts/src/availability/bookingLink.ts huts/src/availability/fetchHutDetail.ts huts/src/availability/bookingLink.test.ts huts/src/availability/fetchHutDetail.test.ts
git commit -m "$(cat <<'EOF'
feat(availability): add fetchHutDetail (OHRS per-hut) and booking deep link

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PSiy9D7gGYdGCoorzewPVZ
EOF
)"
```

---

### Task 7: `formState.ts` — date/party-size/checkbox fields

**Files:**
- Modify: `huts/src/tourSearchPage/formState.ts`
- Test: `huts/src/tourSearchPage/formState.test.ts`

**Interfaces:**
- Consumes: `Query['availability']` (Task 2).
- Produces: `FormState.startDate: string` (`''` = unset, else a native `<input type="date">`
  value, `YYYY-MM-DD`), `FormState.numOfPeople: number`, `FormState.onlyAvailable: boolean`;
  `buildQuery(form, hutsByIndex, availability?: Query['availability']): Query` now attaches
  `availability` to the built `Query` only when `form.onlyAvailable` is true. Consumed by Task 9
  (`TourSearchPage.tsx`).

- [ ] **Step 1: Write the failing tests**

Add to `huts/src/tourSearchPage/formState.test.ts`:

```ts
describe('buildQuery availability wiring', () => {
  const availability = { ohrsIdByHutIndex: new Map([[0, 'ohrsA']]), freeByOffset: new Map([[1, new Set(['ohrsA'])]]) }

  it('attaches availability when onlyAvailable is checked', () => {
    const form = { ...DEFAULT_FORM, startDate: '2026-08-20', onlyAvailable: true }
    const q = buildQuery(form, hutsByIndex, availability)
    expect(q.availability).toBe(availability)
  })

  it('omits availability when onlyAvailable is unchecked, even if data was fetched', () => {
    const form = { ...DEFAULT_FORM, startDate: '2026-08-20', onlyAvailable: false }
    const q = buildQuery(form, hutsByIndex, availability)
    expect(q.availability).toBeUndefined()
  })

  it('omits availability when no data was fetched, even if onlyAvailable is checked', () => {
    const form = { ...DEFAULT_FORM, startDate: '', onlyAvailable: true }
    const q = buildQuery(form, hutsByIndex)
    expect(q.availability).toBeUndefined()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd huts && npm test -- run src/tourSearchPage/formState.test.ts`
Expected: FAIL — `buildQuery` doesn't accept a third argument yet / `FormState` has no
`onlyAvailable`/`startDate` fields (TS error surfaces as a test-file compile failure).

- [ ] **Step 3: Implement**

In `huts/src/tourSearchPage/formState.ts`, extend `FormState` and `DEFAULT_FORM`:

```ts
export interface FormState {
  mode: TourMode
  legCountRange: [number, number]
  sacCeiling: number | 'any'
  allowUngraded: boolean
  legTimeRange: [number, number]
  legAscentCapM: string
  maxEleM: string
  allowViaFerrata: boolean
  allowedOperators: Set<HutOperator>
  allowServiced: boolean
  allowSelfService: boolean
  startDate: string
  numOfPeople: number
  onlyAvailable: boolean
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
  allowedOperators: new Set(['av', 'sonstige']),
  allowServiced: true,
  allowSelfService: false,
  startDate: '',
  numOfPeople: 1,
  onlyAvailable: false,
}
```

Update `buildQuery`:

```ts
export function buildQuery(
  form: FormState,
  hutsByIndex: (HutClass | null)[],
  availability?: Query['availability'],
): Query {
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
    availability: form.onlyAvailable ? availability : undefined,
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd huts && npm test -- run src/tourSearchPage/formState.test.ts`
Expected: all PASS (existing + new).

- [ ] **Step 5: Run typecheck**

Run: `cd huts && npm run typecheck`
Expected: no errors. `TourSearchPage.tsx`'s existing `buildQuery(form, hutsByIndex)` two-argument
calls still compile (the third parameter is optional).

- [ ] **Step 6: Commit**

```bash
git add huts/src/tourSearchPage/formState.ts huts/src/tourSearchPage/formState.test.ts
git commit -m "$(cat <<'EOF'
feat(tourSearchPage): add start date/party size/onlyAvailable to FormState

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PSiy9D7gGYdGCoorzewPVZ
EOF
)"
```

---

### Task 8: `helpers.ts` — availability badge state

**Files:**
- Modify: `huts/src/tourSearchPage/helpers.ts`
- Test: `huts/src/tourSearchPage/helpers.test.ts`

**Interfaces:**
- Consumes: `FreeByOffset` (Task 4).
- Produces: `type AvailabilityBadge = 'free' | 'unavailable' | 'direct' | 'unknown' | null`;
  `hutAvailabilityBadge(hutIndex, offsetDays, ohrsIdByHutIndex, freeByOffset):
  AvailabilityBadge`; `AVAILABILITY_BADGE_LABEL`/`AVAILABILITY_BADGE_COLOR` records. Consumed by
  Task 10 (`TourList.tsx`).

- [ ] **Step 1: Write the failing tests**

Add to `huts/src/tourSearchPage/helpers.test.ts`:

```ts
import { hutAvailabilityBadge } from './helpers.js'

describe('hutAvailabilityBadge', () => {
  const ohrsIdByHutIndex = new Map<number, string | null>([[0, 'ohrsA'], [1, null]])

  it('returns null when no availability data was fetched (badges-off state)', () => {
    expect(hutAvailabilityBadge(0, 1, null, null)).toBeNull()
  })

  it('returns "direct" for a hut with no ohrsHutId, regardless of freeByOffset', () => {
    const freeByOffset = new Map<number, Set<string> | 'unknown'>([[1, new Set<string>()]])
    expect(hutAvailabilityBadge(1, 1, ohrsIdByHutIndex, freeByOffset)).toBe('direct')
  })

  it('returns "unknown" when the offset fetch failed', () => {
    const freeByOffset = new Map<number, Set<string> | 'unknown'>([[1, 'unknown']])
    expect(hutAvailabilityBadge(0, 1, ohrsIdByHutIndex, freeByOffset)).toBe('unknown')
  })

  it('returns "free" when the hut\'s ohrsHutId is in that offset\'s free set', () => {
    const freeByOffset = new Map<number, Set<string> | 'unknown'>([[1, new Set(['ohrsA'])]])
    expect(hutAvailabilityBadge(0, 1, ohrsIdByHutIndex, freeByOffset)).toBe('free')
  })

  it('returns "unavailable" when the hut\'s ohrsHutId is missing from that offset\'s free set', () => {
    const freeByOffset = new Map<number, Set<string> | 'unknown'>([[1, new Set(['someoneElse'])]])
    expect(hutAvailabilityBadge(0, 1, ohrsIdByHutIndex, freeByOffset)).toBe('unavailable')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd huts && npm test -- run src/tourSearchPage/helpers.test.ts`
Expected: FAIL — `hutAvailabilityBadge` is not exported.

- [ ] **Step 3: Implement**

Add to `huts/src/tourSearchPage/helpers.ts`:

```ts
import type { FreeByOffset } from '../availability/types.js'

export type AvailabilityBadge = 'free' | 'unavailable' | 'direct' | 'unknown' | null

/** Mirrors search.ts's hutAvailable() classification (spec §3), but returns which of the four UI
 *  states applies instead of a pass/fail boolean — used for badges-only mode, where every hut in
 *  an already-found chain is labeled independently of whether the search itself was constrained. */
export function hutAvailabilityBadge(
  hutIndex: number,
  offsetDays: number,
  ohrsIdByHutIndex: Map<number, string | null> | null,
  freeByOffset: FreeByOffset | null,
): AvailabilityBadge {
  if (!ohrsIdByHutIndex || !freeByOffset) return null
  const ohrsId = ohrsIdByHutIndex.get(hutIndex)
  if (ohrsId == null) return 'direct'
  const free = freeByOffset.get(offsetDays)
  if (free === 'unknown' || free === undefined) return 'unknown'
  return free.has(ohrsId) ? 'free' : 'unavailable'
}

export const AVAILABILITY_BADGE_LABEL: Record<Exclude<AvailabilityBadge, null>, string> = {
  free: 'frei',
  unavailable: 'ausgebucht/geschlossen',
  direct: 'Direktbuchung',
  unknown: 'unbekannt',
}

export const AVAILABILITY_BADGE_COLOR: Record<Exclude<AvailabilityBadge, null>, string> = {
  free: '#2e7d32',
  unavailable: '#c62828',
  direct: '#616161',
  unknown: '#9e9e9e',
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd huts && npm test -- run src/tourSearchPage/helpers.test.ts`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add huts/src/tourSearchPage/helpers.ts huts/src/tourSearchPage/helpers.test.ts
git commit -m "$(cat <<'EOF'
feat(tourSearchPage): add hutAvailabilityBadge classification helper

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PSiy9D7gGYdGCoorzewPVZ
EOF
)"
```

---

### Task 9: `TourSearchPage.tsx` — form fields + data loading + submit flow

**Files:**
- Modify: `huts/src/tourSearchPage/TourSearchPage.tsx`
- Test: `huts/src/tourSearchPage/TourSearchPage.test.tsx`

**Interfaces:**
- Consumes: `fetchAvailabilityByOffset` (Task 5), `FreeByOffset` (Task 4), `buildQuery` with its
  third `availability` argument (Task 7), `ohrsHutId`/`tenantCode` properties on `huts.geojson`
  features (Task 1).
- Produces: new state `hutOhrsByIndex: Map<number, { ohrsHutId: string | null; tenantCode: number
  | null }>`, `ohrsIdByHutIndex` (derived), `freeByOffset: FreeByOffset | null`. New props passed
  to `TourList`: `freeByOffset`, `ohrsIdByHutIndex`, `hutOhrsByIndex`, `startDate: Date | null`,
  `numOfPeople: number` — consumed by Task 10.

- [ ] **Step 1: Write the failing test**

Add to `huts/src/tourSearchPage/TourSearchPage.test.tsx`. First extend the shared `beforeEach`
fetch mock's `huts.geojson` fixture to carry `ohrsHutId`/`tenantCode` (existing tests must keep
passing with these new, unused-by-them fields present):

```ts
      if (url.includes('huts.geojson')) {
        return fetchJsonMock({
          type: 'FeatureCollection',
          features: [{ properties: { id: 0, name: 'HutA', hutType: 'av', serviced: true, ohrsHutId: '179', tenantCode: 8 }, geometry: { type: 'Point', coordinates: [11.0, 47.0] } }],
        })
      }
```

Then add a new test:

```ts
  it('fetches availability when a start date is set and shows a free-bed badge on the result hut', async () => {
    vi.spyOn(availability, 'fetchAvailabilityByOffset').mockResolvedValue(new Map([[1, new Set(['179'])]]))

    render(<TourSearchPage />)
    await waitFor(() => expect(screen.getByText('Daten geladen')).toBeInTheDocument())

    await userEvent.type(screen.getByLabelText(/Startdatum/), '2026-08-20')
    await userEvent.click(screen.getByRole('button', { name: 'Touren suchen' }))

    await waitFor(() => expect(availability.fetchAvailabilityByOffset).toHaveBeenCalledWith(new Date('2026-08-20'), 1, 3))
    await waitFor(() => expect(screen.getByText(/1 Tour gefunden/)).toBeInTheDocument())

    await userEvent.click(screen.getByText(/Parkplatz Test/))
    await waitFor(() => expect(screen.getByText('frei')).toBeInTheDocument())
  })

  it('the "nur Touren mit Verfügbarkeit" checkbox is hidden until a start date is picked', async () => {
    render(<TourSearchPage />)
    await waitFor(() => expect(screen.getByText('Daten geladen')).toBeInTheDocument())
    expect(screen.queryByLabelText(/nur Touren mit Verfügbarkeit/)).not.toBeInTheDocument()

    await userEvent.type(screen.getByLabelText(/Startdatum/), '2026-08-20')
    expect(screen.getByLabelText(/nur Touren mit Verfügbarkeit/)).toBeInTheDocument()
  })
```

Add the import at the top of the test file:

```ts
import * as availability from '../availability/fetchAvailability.js'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd huts && npm test -- run src/tourSearchPage/TourSearchPage.test.tsx`
Expected: FAIL — no "Startdatum" label exists yet, `fetchAvailabilityByOffset` is never called.

- [ ] **Step 3: Implement**

In `huts/src/tourSearchPage/TourSearchPage.tsx`:

Add imports:

```ts
import { fetchAvailabilityByOffset } from '../availability/fetchAvailability.js'
import type { FreeByOffset } from '../availability/types.js'
```

Add state (alongside the existing `hutsByIndex` state):

```ts
  const [hutOhrsByIndex, setHutOhrsByIndex] = useState<Map<number, { ohrsHutId: string | null; tenantCode: number | null }>>(new Map())
  const [freeByOffset, setFreeByOffset] = useState<FreeByOffset | null>(null)
```

In the data-loading `useEffect`, right after the existing `setHutsByIndex(...)` call (which reads
`hutsByIdx` — the array of `huts.geojson` features indexed by hut index, already computed there),
add:

```ts
        setHutOhrsByIndex(
          new Map(
            hutsByIdx
              .map((f, i) => {
                if (!f) return null
                const props = f.properties as { ohrsHutId?: string | null; tenantCode?: number | null }
                return [i, { ohrsHutId: props.ohrsHutId ?? null, tenantCode: props.tenantCode ?? null }] as const
              })
              .filter((entry): entry is readonly [number, { ohrsHutId: string | null; tenantCode: number | null }] => entry != null),
          ),
        )
```

Add a derived `ohrsIdByHutIndex` (used by `Query.availability`, which only needs the id, not the
tenant code):

```ts
  const ohrsIdByHutIndex = useMemo(
    () => new Map([...hutOhrsByIndex].map(([i, v]) => [i, v.ohrsHutId] as const)),
    [hutOhrsByIndex],
  )
```

Replace `handleSubmit` with an async version that fetches availability first when a date is set:

```ts
  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!graphData) return
    setSearching(true)
    setResult(null)
    setExpandedChain(null)

    let fetchedAvailability: FreeByOffset | null = null
    if (form.startDate) {
      fetchedAvailability = await fetchAvailabilityByOffset(new Date(form.startDate), form.numOfPeople, form.legCountRange[1] - 1)
    }
    setFreeByOffset(fetchedAvailability)

    // Defer the heavy synchronous findTours call a tick so React can paint the spinner first
    // (spec D: no Web Worker in this spec's scope).
    setTimeout(() => {
      const query = buildQuery(
        form, hutsByIndex,
        fetchedAvailability ? { ohrsIdByHutIndex, freeByOffset: fetchedAvailability } : undefined,
      )
      setResult(findTours(query, graphData))
      setPage(1)
      setSearching(false)
    }, 0)
  }
```

Update `handleReset` to also clear `freeByOffset`:

```ts
  function handleReset() {
    setForm(DEFAULT_FORM)
    setResult(null)
    setExpandedChain(null)
    setFreeByOffset(null)
  }
```

Add the new form fields — a new `Box` next to the existing "Modus"/leg-count/leg-time boxes:

```tsx
          <Box sx={{ width: 220 }}>
            <Typography variant="subtitle2">Startdatum (optional)</Typography>
            <TextField
              fullWidth
              size="small"
              type="date"
              label="Startdatum"
              InputLabelProps={{ shrink: true }}
              value={form.startDate}
              onChange={(e) => setForm((f) => ({ ...f, startDate: e.target.value }))}
            />
            {form.startDate && (
              <>
                <TextField
                  fullWidth
                  size="small"
                  type="number"
                  label="Personenzahl"
                  sx={{ mt: 1 }}
                  slotProps={{ htmlInput: { min: 1, max: 9 } }}
                  value={form.numOfPeople}
                  onChange={(e) => setForm((f) => ({ ...f, numOfPeople: Number(e.target.value) || 1 }))}
                />
                <FormControlLabel
                  sx={{ display: 'block' }}
                  control={<Checkbox checked={form.onlyAvailable} onChange={(e) => setForm((f) => ({ ...f, onlyAvailable: e.target.checked }))} />}
                  label="nur Touren mit Verfügbarkeit"
                />
              </>
            )}
          </Box>
```

Pass the new props to `TourList`:

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
              mode={form.mode}
              freeByOffset={freeByOffset}
              ohrsIdByHutIndex={ohrsIdByHutIndex}
              hutOhrsByIndex={hutOhrsByIndex}
              startDate={form.startDate ? new Date(form.startDate) : null}
              numOfPeople={form.numOfPeople}
            />
```

(`TourList`'s prop type won't accept these five new props yet — that's Task 10, done next; running
this task's tests before Task 10 will show a TS error on this JSX, which is expected and resolved
by the next task. If executing tasks strictly one-at-a-time with a full typecheck gate per task,
do Task 9 and Task 10 as one combined commit instead — see the note at Step 5 below.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd huts && npm test -- run src/tourSearchPage/TourSearchPage.test.tsx`
Expected: PASS. (Vitest transpiles per-file and doesn't type-check, so the test suite passes even
though `tsc` would flag the extra `TourList` props — Step 5 confirms).

- [ ] **Step 5: Run typecheck — expect a known, temporary failure**

Run: `cd huts && npm run typecheck`
Expected: **fails**, reporting that `TourList` doesn't accept `freeByOffset`/`ohrsIdByHutIndex`/
`hutOhrsByIndex`/`startDate`/`numOfPeople`. This is expected at this point in the plan — Task 10
adds those props to `TourList`. Do not attempt to fix it here; proceed to Task 10 and run
typecheck again at the end of that task's steps instead of committing Task 9 in isolation.

- [ ] **Step 6: Commit (staged only — actual commit happens at the end of Task 10)**

```bash
git add huts/src/tourSearchPage/TourSearchPage.tsx huts/src/tourSearchPage/TourSearchPage.test.tsx
```

Do not run `git commit` yet — carry these staged changes into Task 10 and commit both together
once `npm run typecheck` passes clean.

---

### Task 10: `TourList.tsx` — availability badges + detail-panel trigger

**Files:**
- Modify: `huts/src/tourSearchPage/TourList.tsx`
- Modify: `huts/src/tourSearchPage/TourList.test.tsx`

**Interfaces:**
- Consumes: `hutAvailabilityBadge`, `AVAILABILITY_BADGE_LABEL`, `AVAILABILITY_BADGE_COLOR` (Task
  8); `FreeByOffset` (Task 4); new props from Task 9 (`freeByOffset`, `ohrsIdByHutIndex`,
  `hutOhrsByIndex`, `startDate`, `numOfPeople`).
- Produces: renders an availability badge next to each hut in an expanded chain's hut-name
  sentence, and, when `startDate` is set, renders `AvailabilityDetailPanel` (Task 11) below the
  expanded chain's leg table.

- [ ] **Step 1: Write the failing test**

Add to `huts/src/tourSearchPage/TourList.test.tsx`:

```ts
const ohrsIdByHutIndex = new Map<number, string | null>([[0, '179']])

it('shows an availability badge next to the hut name when freeByOffset data is present', () => {
  const freeByOffset = new Map<number, Set<string> | 'unknown'>([[1, new Set(['179'])]])
  render(
    <TourList
      result={result} displayedChains={[chain]} pageChains={[chain]} page={1} pageCount={1}
      setPage={() => {}} sortKey="duration" setSortKey={() => {}} hutNameById={hutNameById}
      hutClassByIndex={hutClassByIndex} startLabel={() => 'Start'}
      expandedChain={0} setExpandedChain={() => {}} mode="transit"
      freeByOffset={freeByOffset} ohrsIdByHutIndex={ohrsIdByHutIndex}
      hutOhrsByIndex={new Map()} startDate={null} numOfPeople={1}
    />,
  )
  expect(screen.getByText('frei')).toBeInTheDocument()
})

it('shows no availability badge when freeByOffset is null (badges-off state)', () => {
  render(
    <TourList
      result={result} displayedChains={[chain]} pageChains={[chain]} page={1} pageCount={1}
      setPage={() => {}} sortKey="duration" setSortKey={() => {}} hutNameById={hutNameById}
      hutClassByIndex={hutClassByIndex} startLabel={() => 'Start'}
      expandedChain={0} setExpandedChain={() => {}} mode="transit"
      freeByOffset={null} ohrsIdByHutIndex={ohrsIdByHutIndex}
      hutOhrsByIndex={new Map()} startDate={null} numOfPeople={1}
    />,
  )
  expect(screen.queryByText('frei')).not.toBeInTheDocument()
})
```

Update the file's existing test (the one asserting the `AV·SV` hut-class badge) to also pass the
five new required props — `freeByOffset={null} ohrsIdByHutIndex={new Map()}
hutOhrsByIndex={new Map()} startDate={null} numOfPeople={1}` — so it keeps compiling.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd huts && npm test -- run src/tourSearchPage/TourList.test.tsx`
Expected: FAIL — TS compile error, `TourList` doesn't accept the new props yet.

- [ ] **Step 3: Implement**

In `huts/src/tourSearchPage/TourList.tsx`:

Add imports:

```ts
import { hutAvailabilityBadge, AVAILABILITY_BADGE_LABEL, AVAILABILITY_BADGE_COLOR, PAGE_SIZE, SORT_LABEL, VILLAGE_EMPTY_STATE_HINT, killCounterGuidance, legWaypointLabels, type SortKey } from './helpers.js'
import type { FreeByOffset } from '../availability/types.js'
import AvailabilityDetailPanel from './AvailabilityDetailPanel.js'
```

(remove the old `helpers.js` import line it's merging into; keep every existing named import from
that module).

Extend the props type:

```ts
  result, displayedChains, pageChains, page, pageCount, setPage,
  sortKey, setSortKey, hutNameById, hutClassByIndex, startLabel, expandedChain, setExpandedChain, mode,
  freeByOffset, ohrsIdByHutIndex, hutOhrsByIndex, startDate, numOfPeople,
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
  mode: TourMode
  freeByOffset: FreeByOffset | null
  ohrsIdByHutIndex: Map<number, string | null>
  hutOhrsByIndex: Map<number, { ohrsHutId: string | null; tenantCode: number | null }>
  startDate: Date | null
  numOfPeople: number
```

Change the hut-name `.map((h) => (` in the expanded-chain sentence to also carry the index, and
add the availability badge next to the existing hut-class badge:

```tsx
                    {chain.huts.map((h, idx) => {
                      const badge = hutAvailabilityBadge(h, idx + 1, ohrsIdByHutIndex, freeByOffset)
                      return (
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
                          {badge && (
                            <span
                              style={{
                                marginLeft: 4, padding: '0 4px', borderRadius: 3, fontSize: '0.7rem',
                                color: '#fff', backgroundColor: AVAILABILITY_BADGE_COLOR[badge],
                              }}
                            >
                              {AVAILABILITY_BADGE_LABEL[badge]}
                            </span>
                          )}
                        </span>
                      )
                    })}
```

After the closing `</Table>` inside the `isExpanded && (<CardContent ...>...)` block, add the
detail panel (only rendered once a start date is picked):

```tsx
                  {startDate && (
                    <AvailabilityDetailPanel
                      chain={chain}
                      hutNameById={hutNameById}
                      hutOhrsByIndex={hutOhrsByIndex}
                      startDate={startDate}
                      numOfPeople={numOfPeople}
                    />
                  )}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd huts && npm test -- run src/tourSearchPage/TourList.test.tsx`
Expected: still FAILS at this point — `AvailabilityDetailPanel.js` doesn't exist yet (Task 11). Do
not try to make it pass here; proceed directly to Task 11, which creates that module. Re-run this
exact command at the end of Task 11's Step 4 and confirm it passes there.

- [ ] **Step 5: Stage (do not commit yet)**

```bash
git add huts/src/tourSearchPage/TourList.tsx huts/src/tourSearchPage/TourList.test.tsx
```

Carry these staged changes into Task 11.

---

### Task 11: `AvailabilityDetailPanel.tsx` — per-tour bed-category detail

**Files:**
- Create: `huts/src/tourSearchPage/AvailabilityDetailPanel.tsx`
- Test: `huts/src/tourSearchPage/AvailabilityDetailPanel.test.tsx`

**Interfaces:**
- Consumes: `fetchHutDetail` (Task 6), `buildBookingLink` (Task 6), `HutDetail` (Task 4),
  `TourResult` (existing).
- Produces: default-exported `AvailabilityDetailPanel` component, consumed by `TourList.tsx`
  (Task 10, already wired in).

This is the last task of the availability chain — completing it also unblocks Task 9's and Task
10's typecheck/test gates, so this task's final steps re-run those two files' tests and the
project-wide typecheck before the combined commit.

- [ ] **Step 1: Write the failing test**

Create `huts/src/tourSearchPage/AvailabilityDetailPanel.test.tsx`:

```tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, waitFor, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import AvailabilityDetailPanel from './AvailabilityDetailPanel.js'
import * as fetchHutDetailModule from '../availability/fetchHutDetail.js'
import type { TourResult } from '../tourSearch/types.js'
import type { HutDetail } from '../availability/types.js'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

const chain: TourResult = {
  huts: [0], startId: 100, exitStartId: 100,
  totalDurationH: 5, totalAscentM: 500, totalDescentM: 500, totalDistanceM: 8000,
  legs: [
    { durationH: 2.5, ascentM: 250, descentM: 250, distanceM: 4000, edgeId: 0, reversed: false },
    { durationH: 2.5, ascentM: 250, descentM: 250, distanceM: 4000, edgeId: 1, reversed: true },
  ],
}
const hutNameById = new Map([[0, 'Pfeis-Hütte']])
const hutOhrsByIndex = new Map([[0, { ohrsHutId: '179', tenantCode: 8 }]])

it('fetches detail for each hut with an ohrsHutId and renders its bed categories', async () => {
  const detail: HutDetail = {
    hutId: 179, hutName: 'Pfeis-Hütte',
    calendarDays: [{
      day: '20.08.2026', reservationMode: 'SERVICED', status: 'RESERVATION_POSSIBLE',
      bedCategoriesData: [{ totalPlaces: 37, occupation: 'MEDIUM', totalFreePlaces: 5, label: 'Matratzenlager' }],
    }],
  }
  vi.spyOn(fetchHutDetailModule, 'fetchHutDetail').mockResolvedValue(detail)

  render(
    <AvailabilityDetailPanel
      chain={chain} hutNameById={hutNameById} hutOhrsByIndex={hutOhrsByIndex}
      startDate={new Date(Date.UTC(2026, 7, 20))} numOfPeople={2}
    />,
  )

  expect(fetchHutDetailModule.fetchHutDetail).toHaveBeenCalledWith('179', 8, new Date(Date.UTC(2026, 7, 20)), 2)
  await waitFor(() => expect(screen.getByText('Matratzenlager')).toBeInTheDocument())
  expect(screen.getByText('5')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /hut-reservation.org/ })).toHaveAttribute(
    'href', 'https://www.hut-reservation.org/reservation/book-hut/179/wizard?dateFrom=20.08.2026&dateTo=21.08.2026',
  )
})

it('shows the German reason text for a closed-for-season hut', async () => {
  const detail: HutDetail = {
    hutId: 520, hutName: 'Würgauer Haus',
    calendarDays: [{ day: '20.08.2026', reservationMode: 'CLOSED', status: 'HUT_CLOSED_TO_PUBLIC', bedCategoriesData: [] }],
  }
  vi.spyOn(fetchHutDetailModule, 'fetchHutDetail').mockResolvedValue(detail)

  render(
    <AvailabilityDetailPanel
      chain={chain} hutNameById={hutNameById} hutOhrsByIndex={hutOhrsByIndex}
      startDate={new Date(Date.UTC(2026, 7, 20))} numOfPeople={2}
    />,
  )

  await waitFor(() => expect(screen.getByText('Hütte geschlossen (Saison)')).toBeInTheDocument())
})

it('renders nothing for a hut with no ohrsHutId (direct-booking-only)', () => {
  render(
    <AvailabilityDetailPanel
      chain={chain} hutNameById={hutNameById} hutOhrsByIndex={new Map([[0, { ohrsHutId: null, tenantCode: null }]])}
      startDate={new Date(Date.UTC(2026, 7, 20))} numOfPeople={2}
    />,
  )
  expect(screen.queryByText('Pfeis-Hütte')).not.toBeInTheDocument()
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd huts && npm test -- run src/tourSearchPage/AvailabilityDetailPanel.test.tsx`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement**

Create `huts/src/tourSearchPage/AvailabilityDetailPanel.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { Box, Link, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material'
import { fetchHutDetail } from '../availability/fetchHutDetail.js'
import { buildBookingLink } from '../availability/bookingLink.js'
import type { HutDetail } from '../availability/types.js'
import type { TourResult } from '../tourSearch/types.js'

const STATUS_REASON: Record<string, string> = {
  HUT_CLOSED_TO_PUBLIC: 'Hütte geschlossen (Saison)',
  RESERVATION_NOT_POSSIBLE: 'ausgebucht',
  TECHNICAL_ERROR: 'dzt. nicht möglich',
}

type DetailState = 'loading' | HutDetail | 'error'

function addDays(date: Date, days: number): Date {
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate() + days))
}

// One request per hut, per already-expanded chain (root CLAUDE.md / spec §2, §4) — never looped
// over more than the single chain a user opened this panel for.
function AvailabilityDetailPanel({
  chain, hutNameById, hutOhrsByIndex, startDate, numOfPeople,
}: {
  chain: TourResult
  hutNameById: Map<number, string>
  hutOhrsByIndex: Map<number, { ohrsHutId: string | null; tenantCode: number | null }>
  startDate: Date
  numOfPeople: number
}) {
  const [details, setDetails] = useState<Map<number, DetailState>>(new Map())

  useEffect(() => {
    let cancelled = false
    const bookableHuts = chain.huts
      .map((h, idx) => ({ h, idx, ohrs: hutOhrsByIndex.get(h) }))
      .filter((entry): entry is { h: number; idx: number; ohrs: { ohrsHutId: string; tenantCode: number } } =>
        entry.ohrs?.ohrsHutId != null && entry.ohrs?.tenantCode != null)

    setDetails(new Map(bookableHuts.map(({ h }) => [h, 'loading'] as const)))

    for (const { h, idx, ohrs } of bookableHuts) {
      fetchHutDetail(ohrs.ohrsHutId, ohrs.tenantCode, addDays(startDate, idx), numOfPeople)
        .then((detail) => { if (!cancelled) setDetails((prev) => new Map(prev).set(h, detail)) })
        .catch(() => { if (!cancelled) setDetails((prev) => new Map(prev).set(h, 'error')) })
    }
    return () => { cancelled = true }
  }, [chain, hutOhrsByIndex, startDate, numOfPeople])

  const bookableHuts = chain.huts
    .map((h, idx) => ({ h, idx, ohrs: hutOhrsByIndex.get(h) }))
    .filter((entry): entry is { h: number; idx: number; ohrs: { ohrsHutId: string; tenantCode: number } } =>
      entry.ohrs?.ohrsHutId != null && entry.ohrs?.tenantCode != null)

  if (bookableHuts.length === 0) return null

  return (
    <Box sx={{ mt: 2 }}>
      <Typography variant="subtitle2">Verfügbarkeit im Detail</Typography>
      {bookableHuts.map(({ h, idx, ohrs }) => {
        const state = details.get(h)
        const nightDate = addDays(startDate, idx)
        return (
          <Box key={h} sx={{ mb: 1 }}>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              {hutNameById.get(h) ?? h}
            </Typography>
            {state === 'loading' && <Typography variant="caption">lädt…</Typography>}
            {state === 'error' && <Typography variant="caption" color="error">Details nicht verfügbar.</Typography>}
            {state && state !== 'loading' && state !== 'error' && (
              <>
                {state.calendarDays.map((day) => (
                  <Box key={day.day}>
                    {day.bedCategoriesData.length > 0 ? (
                      <Table size="small">
                        <TableHead>
                          <TableRow>
                            <TableCell>Kategorie</TableCell>
                            <TableCell align="right">frei</TableCell>
                            <TableCell align="right">gesamt</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {day.bedCategoriesData.map((bc, i) => (
                            <TableRow key={i}>
                              <TableCell>{bc.label}</TableCell>
                              <TableCell align="right">{bc.totalFreePlaces}</TableCell>
                              <TableCell align="right">{bc.totalPlaces}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    ) : (
                      <Typography variant="caption">{STATUS_REASON[day.status] ?? day.status}</Typography>
                    )}
                  </Box>
                ))}
                <Link href={buildBookingLink(ohrs.ohrsHutId, nightDate)} target="_blank" rel="noreferrer" variant="caption">
                  Auf hut-reservation.org buchen
                </Link>
              </>
            )}
          </Box>
        )
      })}
    </Box>
  )
}

export default AvailabilityDetailPanel
```

- [ ] **Step 4: Run all four affected test files**

Run: `cd huts && npm test -- run src/tourSearchPage/AvailabilityDetailPanel.test.tsx src/tourSearchPage/TourList.test.tsx src/tourSearchPage/TourSearchPage.test.tsx`
Expected: all PASS now that `AvailabilityDetailPanel` exists.

- [ ] **Step 5: Run the full frontend test suite + typecheck**

Run: `cd huts && npm test -- run && npm run typecheck`
Expected: all PASS with no TS errors — this is the gate that was deferred from Task 9/Task 10.

- [ ] **Step 6: Run lint**

Run: `cd huts && npm run lint`
Expected: no errors.

- [ ] **Step 7: Commit everything staged since Task 9 together with this task's new files**

```bash
git add huts/src/tourSearchPage/TourSearchPage.tsx huts/src/tourSearchPage/TourSearchPage.test.tsx \
        huts/src/tourSearchPage/TourList.tsx huts/src/tourSearchPage/TourList.test.tsx \
        huts/src/tourSearchPage/AvailabilityDetailPanel.tsx huts/src/tourSearchPage/AvailabilityDetailPanel.test.tsx
git commit -m "$(cat <<'EOF'
feat(tourSearchPage): wire hut-availability into the search form, result badges, and a per-tour detail panel

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PSiy9D7gGYdGCoorzewPVZ
EOF
)"
```

---

## Final verification (after all 11 tasks)

- [ ] Run the full backend suite: `cd pipeline && pixi run test` — expect all PASS.
- [ ] Run the full frontend suite: `cd huts && npm test -- run` — expect all PASS.
- [ ] Run `cd huts && npm run typecheck` — expect no errors.
- [ ] Run `cd huts && npm run lint` — expect no errors.
- [ ] Re-read `docs/superpowers/specs/2026-09-01-hut-availability-routing-design.md` section by
  section and confirm each numbered section (1–5 + Testing plan) is covered by a task above.
- [ ] Manual smoke test is explicitly out of scope per the spec's Testing plan and root
  `CLAUDE.md` ("no dev-server verification unless asked") — do not start the dev server unless the
  user asks for it.
