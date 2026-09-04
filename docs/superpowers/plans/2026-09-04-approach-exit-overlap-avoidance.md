# Extend Overlap Avoidance to Approach/Exit Legs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do **not** use
> superpowers:subagent-driven-development or any worktree-spinning approach — this repo's root
> `CLAUDE.md` forbids git worktrees and subagent-driven execution here; execute every task directly,
> in-session, on the current checkout.

**Goal:** make the "avoid overlapping tracks" search-time check (currently hut-hut legs only) also
cover approach legs (start → first hut) and exit legs (last hut → start), so a suggested tour can no
longer walk in or out over ground another leg in the same chain already used.

**Architecture:** flip on an already-built-but-dormant pipeline code path (`write_edge_ids` for
`start_edges`, whose prerequisite reordering was already done in the 2026-09-02 hub-edge-scaling
work) to ship a `start-edge-ids.bin`/`.json` sidecar shaped identically to the existing
`hut-edge-ids.bin`/`.json`. On the client, generalize `search.ts`'s existing hut-edge overlap
bookkeeping (which already generalizes cleanly, since approach/exit records share the exact same
storage convention as hut-hut records) to also track approach/exit legs, and add the exit-leg
overlap check `collectFinished` has never had.

**Tech Stack:** Python 3 / numpy (pipeline, `pixi` env), TypeScript / Vitest (client, `huts/`).

**Spec:** `docs/superpowers/specs/2026-09-04-approach-exit-overlap-avoidance-design.md`

## Global Constraints

- No pipeline task (`doit <task>` or a bare `doit`) may be run without the user's explicit
  confirmation first, per the root `CLAUDE.md` — this plan's pipeline tasks (1, 2) are code +
  pipeline-level `pytest` changes only; no `doit` invocation is part of any step below.
- No UI toggle for this feature — matches the original 2026-08-29 design's decision, unchanged here.
- No git worktrees, no subagent-driven-development, in this repo, for any reason.

---

### Task 1: Pipeline — turn on `write_edge_ids` for `start_edges`

**Files:**
- Modify: `pipeline/phases/graph_building/build_access_edges.py:263`
- Modify: `pipeline/lib/binfmt.py:124`
- Test: `pipeline/tests/test_build_access_edges.py`

**Interfaces:**
- Consumes: `lib.edge_output.write_edge_records(records, out_dir, write_edge_ids: bool)` (unchanged
  signature, already generic over `hut_edges`/`start_edges` — see
  `pipeline/tests/test_edge_output.py`'s existing `test_write_edge_output_writes_sorted_edge_ids_and_prefix_suffix`
  which already covers this function's `write_edge_ids=True` path against an arbitrary `out_dir`, so
  no change is needed there).
- Produces: `data/osm/start_edges/edge_ids.npy` and populated
  `edge_id_offset`/`edge_id_count`/`prefix_ids`/`prefix_count`/`suffix_ids`/`suffix_count` columns on
  `data/osm/start_edges/records.npy` (once a pipeline run actually happens — out of scope for this
  plan per the brainstorming decision to land code only).

- [ ] **Step 1: Write the failing test — `base_edge_ids` reversal, with a multi-edge path**

The existing `test_build_access_edges.py` fixture (`_line_subgraph`) has only one edge, so reversing
its `base_edge_ids` is a no-op and can't prove ordering. Add a two-edge fixture and a test that
proves the router's hut→access traversal order gets reversed into the access→hut storage order
`write_edge_records` (and therefore the new `edge_ids.npy`/`prefix_ids`/`suffix_ids` columns) expect.

Add to `pipeline/tests/test_build_access_edges.py`, alongside the existing `_line_subgraph()`:

```python
def _two_edge_line_subgraph():
    nodes = np.zeros(3, dtype=binfmt.NODE_DTYPE)
    nodes[0] = (0.0, 0.0, 0)
    nodes[1] = (0.0045, 0.0, 0)
    nodes[2] = (0.009, 0.0, 0)
    edges = np.zeros(2, dtype=binfmt.EDGE_DTYPE)
    edges[0] = (0, 1, 500.0, 0.0, 0.0, 0.0, 500.0, binfmt.UNSET, binfmt.UNSET, -1, False, True,
                0, 0, 0)
    edges[1] = (1, 2, 500.0, 0.0, 0.0, 0.0, 500.0, binfmt.UNSET, binfmt.UNSET, -1, False, True,
                0, 0, 1)
    interior = np.zeros(0, dtype=binfmt.COORD_DTYPE)
    return LocalSubgraph(
        global_node_ids=np.array([100, 101, 102]), local_nodes=nodes, local_edges=edges,
        interior=interior,
        local_node_ele=np.zeros(len(nodes), dtype=np.float32),
        interior_ele=np.zeros(len(interior), dtype=np.float32),
    )


def test_base_edge_ids_are_reversed_into_access_to_hut_traversal_order():
    subgraph = _two_edge_line_subgraph()
    hut = {"id": 1, "type": binfmt.TYPE_HUT, "lon": 0.0089, "lat": 0.0}
    station = {"id": 2, "type": binfmt.TYPE_STATION, "lon": 0.0001, "lat": 0.0}
    snaps = snap_hubs_for_cell(subgraph, [hut], [hut, station], max_snap_m=50.0)
    selected_targets_by_hut = {1: [station]}

    records, unreachable_skipped = route_selected_pairs_for_cell(
        subgraph, [hut], selected_targets_by_hut, snaps, variants=FAST_ANY_ONLY, max_edge_km=5.0,
    )

    assert unreachable_skipped == 0
    assert len(records) == 1
    # The router walks hut -> access (edge_id 1, near the hut at node 2, then edge_id 0, near the
    # access point at node 0). A3 (2026-09-02 spec) reverses this into the access -> hut storage
    # order every start_edges consumer expects - access-nearest edge first, hut-nearest edge last -
    # which is what makes turning write_edge_ids on for start_edges safe.
    assert records[0]["base_edge_ids"] == [0, 1]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd pipeline && pixi run pytest tests/test_build_access_edges.py::test_base_edge_ids_are_reversed_into_access_to_hut_traversal_order -v`
Expected: currently this should actually PASS already, since `build_access_edges.py`'s A3 reversal
is already implemented (`build_access_edges.py:131,151`) — this step is here to confirm the test is
correctly written and exercising real code, not a tautology. If it fails, the reversal logic itself
is broken and must be fixed before continuing (do not proceed to Step 3 in that case — this would be
a pre-existing bug outside this plan's stated scope, so stop and flag it rather than silently
"fixing" unrelated code).

- [ ] **Step 3: Flip `write_edge_ids` and bump the schema version**

In `pipeline/phases/graph_building/build_access_edges.py:263`, change:

```python
    write_edge_records(access_records, out_dir / "start_edges", write_edge_ids=False)
```

to:

```python
    write_edge_records(access_records, out_dir / "start_edges", write_edge_ids=True)
```

In `pipeline/lib/binfmt.py:124`, change:

```python
RECORD_SCHEMA_VERSION = 3  # bumped: RECORD_DTYPE gained edge_id_offset/count + prefix/suffix ids
```

to:

```python
RECORD_SCHEMA_VERSION = 4  # bumped: start_edges records now populate edge_id/prefix/suffix cols too
```

- [ ] **Step 4: Run the full pipeline unit test suite for the touched modules**

Run: `cd pipeline && pixi run pytest tests/test_build_access_edges.py tests/test_edge_output.py tests/test_dodo_wiring.py -v`
Expected: all PASS. (`test_dodo_wiring.py`'s schema-version tests assert which *parameter names*
each task tracks, not the version's numeric value, so the bump doesn't change their outcome —
confirm this by reading their assertions if any fail unexpectedly.)

- [ ] **Step 5: Commit**

```bash
cd /home/superhellth/open-alps
git add pipeline/phases/graph_building/build_access_edges.py pipeline/lib/binfmt.py pipeline/tests/test_build_access_edges.py
git commit -m "$(cat <<'EOF'
feat(pipeline): materialize edge-ids for start_edges too

build_access_edges.py already reverses base_edge_ids into the access->hut
storage order (2026-09-02 hub-edge-scaling spec's A3), specifically so
write_edge_ids could be turned on later without a correctness regression.
Turn it on, and bump RECORD_SCHEMA_VERSION so the pipeline reruns
build_hub_edges/build_access_edges with the new column populated.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TScTEg46Qwae85AttDMav1
EOF
)"
```

---

### Task 2: Pipeline — ship `start-edge-ids.bin`/`.json`

**Files:**
- Modify: `pipeline/dag/postprocessing.py`
- Modify: `pipeline/dodo.py`
- Test: `pipeline/tests/test_dodo_wiring.py`

**Interfaces:**
- Consumes: `pipeline/phases/postprocessing/build_edge_ids.py` (unmodified — already generic over
  `--edges-dir`/`--out-bin`/`--out-manifest`), `pipeline_task()`/`rel()` from
  `pipeline/lib/doit_support.py` (unmodified).
- Produces: `dodo.task_build_start_edge_ids()` — a doit task dict with
  `targets=["../data/osm/start-edge-ids.bin", "../data/osm/start-edge-ids.json"]` (exact string via
  `rel()`), consumed by `copy_public_data` through `PUBLIC_FILES`.

- [ ] **Step 1: Write the failing tests**

Add to `pipeline/tests/test_dodo_wiring.py`, near the existing `test_build_edge_ids_task_depends_on_hut_edges_records_and_ids`/`test_public_files_includes_hut_edge_ids`:

```python
def test_build_start_edge_ids_task_depends_on_start_edges_records_and_ids():
    task = dodo.task_build_start_edge_ids()
    file_deps = set(task["file_dep"])
    assert any("start_edges/records.npy" in p for p in file_deps)
    assert any("start_edges/edge_ids.npy" in p for p in file_deps)
    targets = set(task["targets"])
    assert any(p.endswith("start-edge-ids.bin") for p in targets)
    assert any(p.endswith("start-edge-ids.json") for p in targets)


def test_public_files_includes_start_edge_ids():
    assert "start-edge-ids.bin" in dodo.PUBLIC_FILES
    assert "start-edge-ids.json" in dodo.PUBLIC_FILES


def test_build_start_edge_ids_sits_after_build_access_edges():
    ordered = dodo.DOIT_CONFIG["default_tasks"]
    assert ordered.index("build_access_edges") < ordered.index("build_start_edge_ids")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd pipeline && pixi run pytest tests/test_dodo_wiring.py -k start_edge_ids -v`
Expected: FAIL with `AttributeError: module 'dodo' has no attribute 'task_build_start_edge_ids'` (or
similar) for the first two, and a `ValueError`/`KeyError` (task name not in `default_tasks`) for the
third.

- [ ] **Step 3: Add the DAG task**

In `pipeline/dag/postprocessing.py`, immediately after the existing `task_build_edge_ids` function
(`postprocessing.py:185-196`), add:

```python
def task_build_start_edge_ids():
    # Sibling of task_build_edge_ids, pointed at start_edges/ - build_edge_ids.py is already
    # generic over --edges-dir, no script change needed (docs/superpowers/specs/
    # 2026-09-04-approach-exit-overlap-avoidance-design.md §2).
    return pipeline_task(
        "phases/postprocessing/build_edge_ids.py",
        args=[
            f"--edges-dir {OSM_DIR / 'start_edges'}",
            f"--out-bin {OSM_DIR / 'start-edge-ids.bin'}",
            f"--out-manifest {OSM_DIR / 'start-edge-ids.json'}",
        ],
        task_dep=["build_access_edges"],
        file_dep=[OSM_DIR / "start_edges" / "records.npy", OSM_DIR / "start_edges" / "edge_ids.npy"],
        targets=[OSM_DIR / "start-edge-ids.bin", OSM_DIR / "start-edge-ids.json"],
    )
```

(Use a literal `§` character, not the escaped form above — the escape here is only to survive this
plan document's own formatting.)

- [ ] **Step 4: Wire `dodo.py`**

In `pipeline/dodo.py`, add the import (next to the existing `task_build_edge_ids` import — check the
exact existing import line first, e.g. around line 45, and add `task_build_start_edge_ids` to the
same `from dag.postprocessing import (...)` statement).

In `DOIT_CONFIG["default_tasks"]`, change:

```python
        "build_approach_table", "build_edge_payload", "build_edge_ids", "build_tour_edge_payload",
```

to:

```python
        "build_approach_table", "build_edge_payload", "build_edge_ids", "build_start_edge_ids",
        "build_tour_edge_payload",
```

In `PUBLIC_FILES`, change:

```python
    "hut-edge-ids.bin",
    "hut-edge-ids.json",
```

to:

```python
    "hut-edge-ids.bin",
    "hut-edge-ids.json",
    "start-edge-ids.bin",
    "start-edge-ids.json",
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd pipeline && pixi run pytest tests/test_dodo_wiring.py -v`
Expected: all PASS, including the three new ones and every pre-existing one (no regressions from the
import/list edits).

- [ ] **Step 6: Commit**

```bash
cd /home/superhellth/open-alps
git add pipeline/dag/postprocessing.py pipeline/dodo.py pipeline/tests/test_dodo_wiring.py
git commit -m "$(cat <<'EOF'
feat(pipeline): add build_start_edge_ids task, ship start-edge-ids.bin/.json

Mirrors the existing build_edge_ids task (hut_edges) - build_edge_ids.py
is already generic over --edges-dir, so this is DAG wiring only.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TScTEg46Qwae85AttDMav1
EOF
)"
```

---

### Task 3: Client — load `start-edge-ids.bin`/`.json`, wire into `GraphData`

**Files:**
- Modify: `huts/src/tourSearch/types.ts`
- Modify: `huts/src/tourSearch/loadHutEdgeIds.ts`
- Modify: `huts/src/tourSearch/index.ts`
- Modify: `huts/src/tourSearch/search.test.ts`
- Modify: `huts/src/tourSearch/index.test.ts`
- Modify: `huts/src/tourSearch/realData.smoke.test.ts`
- Test: `huts/src/tourSearch/loadHutEdgeIds.test.ts`

**Interfaces:**
- Consumes: nothing new from other tasks (this task is self-contained plumbing).
- Produces: `GraphData.startEdgeIds: HutEdgeIdsData` (same shape as `GraphData.hutEdgeIds`),
  `loadStartEdgeIdsData(baseUrl?: string): Promise<HutEdgeIdsData>` — both consumed by Tasks 5/6.

- [ ] **Step 1: Add the field to `GraphData`**

In `huts/src/tourSearch/types.ts`, change:

```ts
export interface GraphData {
  hutEdges: HutEdgesData
  approaches: ApproachesData
  hutEdgeIds: HutEdgeIdsData
}
```

to:

```ts
export interface GraphData {
  hutEdges: HutEdgesData
  approaches: ApproachesData
  hutEdgeIds: HutEdgeIdsData
  startEdgeIds: HutEdgeIdsData
}
```

(`HutEdgeIdsData`'s three methods are already leg-agnostic in shape — no rename needed; it's the
same manifest/binary layout for both `hut-edge-ids.*` and `start-edge-ids.*`.)

- [ ] **Step 2: Write the failing loader test**

In `huts/src/tourSearch/loadHutEdgeIds.test.ts`, add (reusing the file's existing
`buildFixtureBuffer()`):

```ts
import { loadStartEdgeIdsData } from './loadHutEdgeIds.js'

// ... inside a new describe block, after the existing loadHutEdgeIdsData one:

describe('loadStartEdgeIdsData', () => {
  const { buffer, manifest } = buildFixtureBuffer()
  let requestedUrls: string[] = []

  beforeEach(() => {
    requestedUrls = []
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      requestedUrls.push(url)
      if (url.endsWith('.json')) return { json: async () => manifest } as Response
      return { arrayBuffer: async () => buffer } as Response
    }))
  })
  afterEach(() => vi.unstubAllGlobals())

  it('fetches start-edge-ids.bin/.json, not the hut-edge-ids files', async () => {
    await loadStartEdgeIdsData('/data')
    expect(requestedUrls).toContain('/data/start-edge-ids.json')
    expect(requestedUrls).toContain('/data/start-edge-ids.bin')
    expect(requestedUrls.some((u) => u.includes('hut-edge-ids'))).toBe(false)
  })

  it('parses the same manifest/binary shape as loadHutEdgeIdsData', async () => {
    const data = await loadStartEdgeIdsData('/data')
    expect(Array.from(data.getSortedIds(0))).toEqual([10, 20, 30])
    expect(Array.from(data.getPrefixIds(1))).toEqual([40])
  })
})
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd huts && npx vitest run src/tourSearch/loadHutEdgeIds.test.ts`
Expected: FAIL — `loadStartEdgeIdsData` is not exported yet.

- [ ] **Step 4: Generalize the loader**

In `huts/src/tourSearch/loadHutEdgeIds.ts`, change the whole file to:

```ts
import type { HutEdgeIdsData } from './types.js'

interface HutEdgeIdsManifest {
  rows: number
  k: number
  edge_id_count: number[]
  prefix_count: number[]
  suffix_count: number[]
  sorted_bytes: number
  prefix_bytes: number
  suffix_bytes: number
}

/** Loads a <basename>.bin/.json pair built by pipeline/phases/postprocessing/build_edge_ids.py -
 *  the trail-segment identity the "avoid overlapping tracks" search-time check needs (spec §2 of
 *  docs/superpowers/specs/2026-08-29-avoid-overlapping-tracks-design.md, extended to start_edges
 *  by docs/superpowers/specs/2026-09-04-approach-exit-overlap-avoidance-design.md §2). Fetched
 *  wholesale, not lazily per-leg like geometry: the overlap check runs during search, before any
 *  tour is chosen. edgeId indexes into this exactly like it indexes into hut-edge-payload.bin /
 *  approaches.bin (same row order). build_edge_ids.py is generic over its --edges-dir, so the same
 *  manifest/binary shape serves both hut_edges and start_edges - hence one implementation here. */
async function loadEdgeIdsData(baseUrl: string, binName: string, jsonName: string): Promise<HutEdgeIdsData> {
  const manifest: HutEdgeIdsManifest = await (await fetch(`${baseUrl}/${jsonName}`)).json()
  const buffer = await (await fetch(`${baseUrl}/${binName}`)).arrayBuffer()

  const sortedOffsets = new Array<number>(manifest.rows + 1)
  sortedOffsets[0] = 0
  for (let i = 0; i < manifest.rows; i++) {
    sortedOffsets[i + 1] = sortedOffsets[i] + manifest.edge_id_count[i]
  }

  const k = manifest.k
  const sortedStart = 0
  const prefixStart = manifest.sorted_bytes
  const suffixStart = prefixStart + manifest.prefix_bytes

  const sortedView = new Int32Array(buffer, sortedStart, manifest.sorted_bytes / 4)
  const prefixView = new Int32Array(buffer, prefixStart, manifest.prefix_bytes / 4)
  const suffixView = new Int32Array(buffer, suffixStart, manifest.suffix_bytes / 4)

  return {
    getSortedIds(edgeId: number): Int32Array {
      return sortedView.subarray(sortedOffsets[edgeId], sortedOffsets[edgeId + 1])
    },
    getPrefixIds(edgeId: number): Int32Array {
      return prefixView.subarray(edgeId * k, edgeId * k + manifest.prefix_count[edgeId])
    },
    getSuffixIds(edgeId: number): Int32Array {
      return suffixView.subarray(edgeId * k, edgeId * k + manifest.suffix_count[edgeId])
    },
  }
}

export function loadHutEdgeIdsData(baseUrl = '/data'): Promise<HutEdgeIdsData> {
  return loadEdgeIdsData(baseUrl, 'hut-edge-ids.bin', 'hut-edge-ids.json')
}

export function loadStartEdgeIdsData(baseUrl = '/data'): Promise<HutEdgeIdsData> {
  return loadEdgeIdsData(baseUrl, 'start-edge-ids.bin', 'start-edge-ids.json')
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd huts && npx vitest run src/tourSearch/loadHutEdgeIds.test.ts`
Expected: all PASS (both the pre-existing `loadHutEdgeIdsData` tests, unchanged, and the two new
`loadStartEdgeIdsData` ones).

- [ ] **Step 6: Wire `loadTourSearchData`**

In `huts/src/tourSearch/index.ts`, change:

```ts
import { loadHutEdgesData } from './loadHutEdges.js'
import { loadApproachesData } from './loadApproaches.js'
import { loadHutEdgeIdsData } from './loadHutEdgeIds.js'
import { searchChains } from './search.js'
import { dedupeReversePairs, suppressSimilar } from './diversity.js'
import type { GraphData, Query, SearchResult } from './types.js'

export async function loadTourSearchData(baseUrl = '/data'): Promise<GraphData> {
  const [hutEdges, approaches, hutEdgeIds] = await Promise.all([
    loadHutEdgesData(baseUrl),
    loadApproachesData(baseUrl),
    loadHutEdgeIdsData(baseUrl),
  ])
  return { hutEdges, approaches, hutEdgeIds }
}
```

to:

```ts
import { loadHutEdgesData } from './loadHutEdges.js'
import { loadApproachesData } from './loadApproaches.js'
import { loadHutEdgeIdsData, loadStartEdgeIdsData } from './loadHutEdgeIds.js'
import { searchChains } from './search.js'
import { dedupeReversePairs, suppressSimilar } from './diversity.js'
import type { GraphData, Query, SearchResult } from './types.js'

export async function loadTourSearchData(baseUrl = '/data'): Promise<GraphData> {
  const [hutEdges, approaches, hutEdgeIds, startEdgeIds] = await Promise.all([
    loadHutEdgesData(baseUrl),
    loadApproachesData(baseUrl),
    loadHutEdgeIdsData(baseUrl),
    loadStartEdgeIdsData(baseUrl),
  ])
  return { hutEdges, approaches, hutEdgeIds, startEdgeIds }
}
```

- [ ] **Step 7: Fix every existing `GraphData` literal so the project typechecks again**

In `huts/src/tourSearch/index.test.ts`:

- In the `loadTourSearchData` test's `fetchMock`, add two more URL branches reusing the existing
  `hutEdgeIdsManifest`/`hutEdgeIdsBuffer` fixtures (the manifest/binary shape is identical, per Step
  4's `loadEdgeIdsData`):

```ts
        if (url.endsWith('start-edge-ids.json')) return Promise.resolve({ json: () => Promise.resolve(hutEdgeIdsManifest) })
        if (url.endsWith('start-edge-ids.bin')) return Promise.resolve({ arrayBuffer: () => Promise.resolve(hutEdgeIdsBuffer) })
```

  (add these two lines immediately after the existing `hut-edge-ids.bin` branch, before the `throw`)

- In the `findTours` describe block's `graphData` literal, add a `startEdgeIds` field identical in
  shape to the existing `hutEdgeIds` stub:

```ts
      startEdgeIds: {
        getSortedIds: () => new Int32Array(0),
        getPrefixIds: () => new Int32Array(0),
        getSuffixIds: () => new Int32Array(0),
      },
```

In `huts/src/tourSearch/search.test.ts`:

- On the `emptyHutEdgeIdsStub()` helper (line 15-21), no change needed — its return type
  `GraphData['hutEdgeIds']` is structurally identical to `GraphData['startEdgeIds']`, so the same
  function can populate either field.
- In the base `graphData` literal (line 26), add `startEdgeIds: emptyHutEdgeIdsStub(),` alongside
  the existing `hutEdgeIds: emptyHutEdgeIdsStub(),`.
- In `overlapGraphData` (line 147), add `startEdgeIds: emptyHutEdgeIdsStub(),` (this describe block
  only exercises hut-hut overlap, so a stub is correct here — the new approach/exit overlap tests
  get their own fixtures in Tasks 5/6).
- In `diamondGraph` (line 345), add `startEdgeIds: emptyHutEdgeIdsStub(),` alongside its existing
  `hutEdgeIds: emptyHutEdgeIdsStub(),`.
- `loopGraphData`, `parkingGraphData`, `loopStationGraphData`, `villageGraphData` all spread
  `...graphData` and don't override `hutEdgeIds`/`startEdgeIds`, so they inherit the field
  automatically — no change needed for those four.

In `huts/src/tourSearch/realData.smoke.test.ts`, change:

```ts
    graphData = {
      hutEdges: loadHutEdgesFromDisk(), approaches: loadApproachesFromDisk(),
      hutEdgeIds: {
        getSortedIds: () => new Int32Array(0),
        getPrefixIds: () => new Int32Array(0),
        getSuffixIds: () => new Int32Array(0),
      },
    }
```

to:

```ts
    graphData = {
      hutEdges: loadHutEdgesFromDisk(), approaches: loadApproachesFromDisk(),
      // hutEdgeIds/startEdgeIds are stubs until a confirmed pipeline run regenerates
      // huts/public/data/{hut,start}-edge-ids.* (docs/superpowers/plans/
      // 2026-09-04-approach-exit-overlap-avoidance.md) and this wires real
      // loadHutEdgeIdsFromDisk()/loadStartEdgeIdsFromDisk() readers here.
      hutEdgeIds: {
        getSortedIds: () => new Int32Array(0),
        getPrefixIds: () => new Int32Array(0),
        getSuffixIds: () => new Int32Array(0),
      },
      startEdgeIds: {
        getSortedIds: () => new Int32Array(0),
        getPrefixIds: () => new Int32Array(0),
        getSuffixIds: () => new Int32Array(0),
      },
    }
```

- [ ] **Step 8: Run the full client test suite and typecheck**

Run: `cd huts && npm run typecheck && npm test`
Expected: both PASS, with zero TypeScript errors and no test regressions. If `tsc` reports a missing
`startEdgeIds` anywhere not listed above, that's a literal this plan missed — add it the same way
(prefer `emptyHutEdgeIdsStub()`/an equivalent empty stub unless the surrounding test specifically
needs real overlap data).

- [ ] **Step 9: Commit**

```bash
cd /home/superhellth/open-alps
git add huts/src/tourSearch/types.ts huts/src/tourSearch/loadHutEdgeIds.ts huts/src/tourSearch/loadHutEdgeIds.test.ts huts/src/tourSearch/index.ts huts/src/tourSearch/index.test.ts huts/src/tourSearch/search.test.ts huts/src/tourSearch/realData.smoke.test.ts
git commit -m "$(cat <<'EOF'
feat(frontend): load start-edge-ids.bin/.json into GraphData

Generalizes the existing hut-edge-ids loader (same manifest/binary shape)
rather than duplicating it. No behavior change yet - Tasks 5/6 wire this
into the overlap check.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TScTEg46Qwae85AttDMav1
EOF
)"
```

---

### Task 4: Client — `nearHubIds` dispatch helper in `overlap.ts`

**Files:**
- Modify: `huts/src/tourSearch/overlap.ts`
- Test: `huts/src/tourSearch/overlap.test.ts`

**Interfaces:**
- Consumes: `HutEdgeIdsData` (from `./types.js`, unchanged).
- Produces: `export type EdgeKind = 'hut' | 'start'`, `export interface EdgeIdTables { hut:
  HutEdgeIdsData; start: HutEdgeIdsData }`, `export function nearHubIds(tables: EdgeIdTables, leg: {
  edgeId: number; reversed: boolean; kind: EdgeKind }, role: 'arriving' | 'departing'): Int32Array` —
  consumed by Tasks 5/6 in `search.ts`.

- [ ] **Step 1: Write the failing tests**

Add to `huts/src/tourSearch/overlap.test.ts`:

```ts
import { trimSharedHubIds, hasOverlap, nearHubIds } from './overlap.js'

// ... after the existing describe blocks:

describe('nearHubIds', () => {
  const tables = {
    hut: {
      getSortedIds: () => new Int32Array(0),
      getPrefixIds: (id: number) => Int32Array.from([100 + id]),
      getSuffixIds: (id: number) => Int32Array.from([200 + id]),
    },
    start: {
      getSortedIds: () => new Int32Array(0),
      getPrefixIds: (id: number) => Int32Array.from([300 + id]),
      getSuffixIds: (id: number) => Int32Array.from([400 + id]),
    },
  }

  it('an arriving, non-reversed hut leg reads the suffix (near its arrival end)', () => {
    expect(Array.from(nearHubIds(tables, { edgeId: 1, reversed: false, kind: 'hut' }, 'arriving'))).toEqual([201])
  })

  it('an arriving, reversed hut leg reads the prefix', () => {
    expect(Array.from(nearHubIds(tables, { edgeId: 1, reversed: true, kind: 'hut' }, 'arriving'))).toEqual([101])
  })

  it('a departing, non-reversed hut leg reads the prefix', () => {
    expect(Array.from(nearHubIds(tables, { edgeId: 1, reversed: false, kind: 'hut' }, 'departing'))).toEqual([101])
  })

  it('a departing, reversed hut leg reads the suffix', () => {
    expect(Array.from(nearHubIds(tables, { edgeId: 1, reversed: true, kind: 'hut' }, 'departing'))).toEqual([201])
  })

  it('dispatches to the start table for kind "start"', () => {
    expect(Array.from(nearHubIds(tables, { edgeId: 1, reversed: false, kind: 'start' }, 'arriving'))).toEqual([401])
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd huts && npx vitest run src/tourSearch/overlap.test.ts`
Expected: FAIL — `nearHubIds` is not exported yet.

- [ ] **Step 3: Implement `nearHubIds`**

In `huts/src/tourSearch/overlap.ts`, add at the top (after the existing file header comment) and at
the bottom of the file respectively:

```ts
import type { HutEdgeIdsData } from './types.js'

export type EdgeKind = 'hut' | 'start'

export interface EdgeIdTables {
  hut: HutEdgeIdsData
  start: HutEdgeIdsData
}
```

and, after the existing `hasOverlap` function:

```ts
/** Picks the id array "near" a leg's shared endpoint, dispatching to the hut- or start-edge-ids
 *  table by the leg's kind (hut-hut vs approach/exit both share the same from->to, prefix-near-
 *  from/suffix-near-to storage convention - spec §4 of docs/superpowers/specs/
 *  2026-08-29-avoid-overlapping-tracks-design.md, extended to start-legs by §4 of
 *  docs/superpowers/specs/2026-09-04-approach-exit-overlap-avoidance-design.md). role:
 *  'arriving' means the leg arrives at the shared point (its near-end is prefix if reversed, else
 *  suffix); 'departing' means it departs from the shared point (near-end is suffix if reversed,
 *  else prefix). */
export function nearHubIds(
  tables: EdgeIdTables,
  leg: { edgeId: number; reversed: boolean; kind: EdgeKind },
  role: 'arriving' | 'departing',
): Int32Array {
  const table = leg.kind === 'hut' ? tables.hut : tables.start
  const wantSuffix = role === 'arriving' ? !leg.reversed : leg.reversed
  return wantSuffix ? table.getSuffixIds(leg.edgeId) : table.getPrefixIds(leg.edgeId)
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd huts && npx vitest run src/tourSearch/overlap.test.ts`
Expected: all PASS, including the pre-existing `trimSharedHubIds`/`hasOverlap` tests (unchanged).

- [ ] **Step 5: Commit**

```bash
cd /home/superhellth/open-alps
git add huts/src/tourSearch/overlap.ts huts/src/tourSearch/overlap.test.ts
git commit -m "$(cat <<'EOF'
feat(frontend): add nearHubIds helper for hut/start-leg overlap dispatch

Approach/exit records share hut-edge records' exact from->to, prefix-
near-from/suffix-near-to storage convention, so the existing arrival/
departure formula generalizes unchanged - this just picks which table
to read from by leg kind.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TScTEg46Qwae85AttDMav1
EOF
)"
```

---

### Task 5: Client — track the approach leg's ids through the expansion loop

**Files:**
- Modify: `huts/src/tourSearch/search.ts`
- Modify: `huts/src/tourSearch/search.test.ts`

**Interfaces:**
- Consumes: `nearHubIds`, `EdgeKind`, `EdgeIdTables` (Task 4); `GraphData.startEdgeIds` (Task 3).
- Produces: `State.prevLeg: { edgeId: number; reversed: boolean; kind: EdgeKind } | null` (renamed
  from `prevHutLeg`, generalized), `State.approachEdgeId: number` — consumed by Task 6.

- [ ] **Step 1: Write the failing tests**

Add to `huts/src/tourSearch/search.test.ts`, as a new describe block after the existing
`'searchChains (overlap avoidance)'` block:

```ts
describe('searchChains (approach-leg overlap avoidance)', () => {
  // Chain A -[e01]-> B -[e12]-> C. Approach (start 500 -> A, edgeId 700) shares base-edge id 200
  // with e01 ONLY in the run leaving their common hut A - should be exempted, same rule as two
  // adjacent hut-hut legs. Approach also carries id 999, which e12 independently carries too, with
  // NO hut in common with the approach (e12 connects B and C, the approach touches only A) - a
  // genuine overlap that must exclude any chain using both.
  const approachOverlapEdge = (fromIndex: number, toIndex: number, edgeId: number) => ({
    fromIndex, toIndex, variant: 0, distanceM: 5000, ascentM: 200, descentM: 200, maxEleM: 2000,
    sacRank: 1, viaFerrata: false, roadM: 0, ungradedM: 0, inferredM: 0, snapM: 0, edgeId,
  })

  const SORTED_HUT: Record<number, number[]> = { 1: [100, 200], 2: [100, 300, 999] }
  const PREFIX_HUT: Record<number, number[]> = { 1: [200], 2: [100] } // near from_id
  const SUFFIX_HUT: Record<number, number[]> = { 1: [100], 2: [300] } // near to_id
  const SORTED_START: Record<number, number[]> = { 700: [200, 999] }
  const SUFFIX_START: Record<number, number[]> = { 700: [200] } // near hut A (the approach's arrival end)

  const approachOverlapGraphData: GraphData = {
    hutEdges: {
      hutIds: ['A', 'B', 'C'],
      variantNames: { 0: 'FAST_ANY' },
      records: [approachOverlapEdge(0, 1, 1), approachOverlapEdge(1, 2, 2)],
    },
    approaches: {
      records: [
        { hutIndex: 0, startId: 500, sourceType: SOURCE_TYPE_STATION, variant: 0, accessUnknown: false, distanceM: 2000, ascentM: 100, descentM: 50, access: null, edgeId: 700 },
      ],
      reverseIndex: {
        hut_to_starts: {
          1: [{ hut_id: 1, start_id: 601, source_type: SOURCE_TYPE_STATION, variant: 0, distance_m: 2000, ascent_m: 50, descent_m: 100, edge_id: 800 }],
          2: [{ hut_id: 2, start_id: 602, source_type: SOURCE_TYPE_STATION, variant: 0, distance_m: 2000, ascent_m: 50, descent_m: 100, edge_id: 801 }],
        },
        start_to_huts: {},
      },
    },
    hutEdgeIds: {
      getSortedIds: (edgeId) => Int32Array.from(SORTED_HUT[edgeId] ?? []),
      getPrefixIds: (edgeId) => Int32Array.from(PREFIX_HUT[edgeId] ?? []),
      getSuffixIds: (edgeId) => Int32Array.from(SUFFIX_HUT[edgeId] ?? []),
    },
    startEdgeIds: {
      getSortedIds: (edgeId) => Int32Array.from(SORTED_START[edgeId] ?? []),
      getPrefixIds: () => new Int32Array(0),
      getSuffixIds: (edgeId) => Int32Array.from(SUFFIX_START[edgeId] ?? []),
    },
  }

  it('excludes a chain whose approach leg overlaps a later, non-adjacent hut-hut leg', () => {
    const { chains, killCounters } = searchChains(
      { mode: 'transit', legCountMin: 2, legCountMax: 6, ...generousConstraints },
      approachOverlapGraphData,
    )
    expect(chains.some((c) => c.huts.length >= 3)).toBe(false)
    expect(killCounters.trackOverlap).toBeGreaterThan(0)
  })

  it('keeps a chain whose approach and first hut-hut leg only share the run out of their common hut', () => {
    const { chains } = searchChains(
      { mode: 'transit', legCountMin: 3, legCountMax: 3, ...generousConstraints },
      approachOverlapGraphData,
    )
    const kept = chains.find((c) => c.huts.length === 2)
    expect(kept).toBeDefined()
    expect(kept!.huts).toEqual([0, 1])
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd huts && npx vitest run src/tourSearch/search.test.ts -t "approach-leg overlap"`
Expected: FAIL. The first test currently fails because the approach leg's ids are never tracked at
all (today's `usedEdgeIds` starts empty and `prevHutLeg` starts `null`), so nothing currently
excludes the id-999 collision — `chains.some((c) => c.huts.length >= 3)` will be `true`. The second
test may already incidentally pass (there's nothing today making it fail), which is fine — Step 2's
job is to confirm the *first* test fails for the *right* reason; if the second already passes, that
is not a problem, just note it and continue to Step 3, which will make it pass for the *right*
reason too.

- [ ] **Step 3: Generalize `search.ts`'s `State.prevHutLeg` into `State.prevLeg`, seed it from the approach leg**

In `huts/src/tourSearch/search.ts`, change the import line:

```ts
import { trimSharedHubIds, hasOverlap } from './overlap.js'
```

to:

```ts
import { trimSharedHubIds, hasOverlap, nearHubIds } from './overlap.js'
import type { EdgeKind } from './overlap.js'
```

Change:

```ts
  const variant = resolveVariant({ sacCeiling, allowUngraded }, graphData.hutEdges.variantNames)
  const adjacency = buildAdjacency(graphData.hutEdges, variant)
```

to:

```ts
  const variant = resolveVariant({ sacCeiling, allowUngraded }, graphData.hutEdges.variantNames)
  const adjacency = buildAdjacency(graphData.hutEdges, variant)
  const edgeIdTables = { hut: graphData.hutEdgeIds, start: graphData.startEdgeIds }
```

(Declared once here, at function scope, so both the expansion loop below and `collectFinished`
(Task 6) share the same object instead of each rebuilding it.)

Change the `State` interface:

```ts
  interface State {
    path: number[]
    startId: number
    totalDurationH: number
    totalAscentM: number
    totalDescentM: number
    totalDistanceM: number
    legs: LegSummary[]
    visitedKey: bigint
    usedEdgeIds: Set<number>
    prevHutLeg: { edgeId: number; reversed: boolean } | null
  }
```

to:

```ts
  interface State {
    path: number[]
    startId: number
    totalDurationH: number
    totalAscentM: number
    totalDescentM: number
    totalDistanceM: number
    legs: LegSummary[]
    visitedKey: bigint
    usedEdgeIds: Set<number>
    prevLeg: { edgeId: number; reversed: boolean; kind: EdgeKind } | null
    approachEdgeId: number
  }
```

Change the initial-state construction (inside the `for (const approachLeg of getApproachLegs(h, graphData.approaches))` loop):

```ts
      const visitedKey = 1n << BigInt(h)
      const state: State = {
        path: [h], startId: approachLeg.startId,
        totalDurationH: approachLeg.durationH, totalAscentM: approachLeg.ascentM,
        totalDescentM: approachLeg.descentM, totalDistanceM: approachLeg.distanceM,
        legs: [legSummary(approachLeg)],
        visitedKey,
        usedEdgeIds: EMPTY_EDGE_IDS,
        prevHutLeg: null,
      }
```

to:

```ts
      const visitedKey = 1n << BigInt(h)
      const approachSortedIds = graphData.startEdgeIds.getSortedIds(approachLeg.edgeId)
      const state: State = {
        path: [h], startId: approachLeg.startId,
        totalDurationH: approachLeg.durationH, totalAscentM: approachLeg.ascentM,
        totalDescentM: approachLeg.descentM, totalDistanceM: approachLeg.distanceM,
        legs: [legSummary(approachLeg)],
        visitedKey,
        usedEdgeIds: new Set(approachSortedIds),
        prevLeg: { edgeId: approachLeg.edgeId, reversed: approachLeg.reversed, kind: 'start' },
        approachEdgeId: approachLeg.edgeId,
      }
```

Change the expansion loop's overlap check:

```ts
          const sortedIdsNew = graphData.hutEdgeIds.getSortedIds(leg.edgeId)
          let exempt: Set<number> = EMPTY_EDGE_IDS
          if (s.prevHutLeg) {
            // leg.fromIndex === h always (adjacency.ts's invariant: legs is adjacency.get(h)) -
            // the shared hut is h, so "near h" for the new leg is its prefix (reversed=false,
            // record's from_id === h) or suffix (reversed=true, record's to_id === h). Same logic
            // for the previous leg, using its own reversed flag against its own arrival hut h.
            const prevNear = s.prevHutLeg.reversed
              ? graphData.hutEdgeIds.getPrefixIds(s.prevHutLeg.edgeId)
              : graphData.hutEdgeIds.getSuffixIds(s.prevHutLeg.edgeId)
            const newNear = leg.reversed
              ? graphData.hutEdgeIds.getSuffixIds(leg.edgeId)
              : graphData.hutEdgeIds.getPrefixIds(leg.edgeId)
            exempt = trimSharedHubIds(prevNear, newNear)
          }
          if (hasOverlap(sortedIdsNew, exempt, s.usedEdgeIds)) { killCounters.trackOverlap++; continue }
```

to:

```ts
          const sortedIdsNew = graphData.hutEdgeIds.getSortedIds(leg.edgeId)
          let exempt: Set<number> = EMPTY_EDGE_IDS
          if (s.prevLeg) {
            // leg.fromIndex === h always (adjacency.ts's invariant: legs is adjacency.get(h)) - the
            // shared hut is h. s.prevLeg is whatever leg most recently arrived at h (a hut-hut leg,
            // or - for the very first hop - the approach leg itself, kind 'start'); nearHubIds
            // dispatches to the right id table by kind, so this works unchanged for both.
            const prevNear = nearHubIds(edgeIdTables, s.prevLeg, 'arriving')
            const newNear = nearHubIds(edgeIdTables, { edgeId: leg.edgeId, reversed: leg.reversed, kind: 'hut' }, 'departing')
            exempt = trimSharedHubIds(prevNear, newNear)
          }
          if (hasOverlap(sortedIdsNew, exempt, s.usedEdgeIds)) { killCounters.trackOverlap++; continue }
```

Change the next-state construction:

```ts
          const next: State = {
            path: [...s.path, h2], startId: s.startId,
            totalDurationH: s.totalDurationH + leg.durationH,
            totalAscentM: s.totalAscentM + leg.ascentM,
            totalDescentM: s.totalDescentM + leg.descentM,
            totalDistanceM: s.totalDistanceM + leg.distanceM,
            legs: [...s.legs, legSummary(leg)],
            visitedKey: nextVisitedKey,
            usedEdgeIds: nextUsedEdgeIds,
            prevHutLeg: { edgeId: leg.edgeId, reversed: leg.reversed },
          }
```

to:

```ts
          const next: State = {
            path: [...s.path, h2], startId: s.startId,
            totalDurationH: s.totalDurationH + leg.durationH,
            totalAscentM: s.totalAscentM + leg.ascentM,
            totalDescentM: s.totalDescentM + leg.descentM,
            totalDistanceM: s.totalDistanceM + leg.distanceM,
            legs: [...s.legs, legSummary(leg)],
            visitedKey: nextVisitedKey,
            usedEdgeIds: nextUsedEdgeIds,
            prevLeg: { edgeId: leg.edgeId, reversed: leg.reversed, kind: 'hut' },
            approachEdgeId: s.approachEdgeId,
          }
```

Note: `collectFinished` still references `s.path`/`s.startId`/etc. only, so it does not need to
change in this task — Task 6 changes it. Leave it as-is for now; the exit-leg overlap check does not
exist yet, so these two new tests pass purely from the expansion-loop change.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd huts && npx vitest run src/tourSearch/search.test.ts`
Expected: all PASS, including every pre-existing test in the file (the `EMPTY_EDGE_IDS`-seeded stub
fixtures used elsewhere in the file return an empty array from `getSortedIds` regardless of edgeId,
so seeding `usedEdgeIds` from the approach leg is a no-op for those and changes no existing
behavior).

- [ ] **Step 5: Run the full client test suite and typecheck**

Run: `cd huts && npm run typecheck && npm test`
Expected: both PASS.

- [ ] **Step 6: Commit**

```bash
cd /home/superhellth/open-alps
git add huts/src/tourSearch/search.ts huts/src/tourSearch/search.test.ts
git commit -m "$(cat <<'EOF'
feat(frontend): track the approach leg's ids through the expansion loop

State.prevHutLeg generalizes to prevLeg (adds a hut/start kind
discriminator) and seeds from the approach leg instead of null/empty, so
the existing per-expansion overlap check now also protects the approach
leg's ground against reuse anywhere later in the chain - for free, since
it's the same usedEdgeIds accumulation every hut-hut leg already used.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TScTEg46Qwae85AttDMav1
EOF
)"
```

---

### Task 6: Client — exit-leg overlap check, with the shared-start exemption

**Files:**
- Modify: `huts/src/tourSearch/search.ts`
- Modify: `huts/src/tourSearch/search.test.ts`

**Interfaces:**
- Consumes: `State.prevLeg`, `State.approachEdgeId` (Task 5); `nearHubIds` (Task 4).
- Produces: no new exported interface — `collectFinished` now rejects overlapping exit legs the same
  way the expansion loop rejects overlapping hut-hut legs.

- [ ] **Step 1: Write the failing tests**

Add to `huts/src/tourSearch/search.test.ts`, as two new describe blocks after the one added in Task 5:

```ts
describe('searchChains (car-loop shared-start overlap avoidance)', () => {
  const loopEdge = { fromIndex: 0, toIndex: 1, variant: 0, distanceM: 5000, ascentM: 200, descentM: 200, maxEleM: 2000, sacRank: 1, viaFerrata: false, roadM: 0, ungradedM: 0, inferredM: 0, snapM: 0, edgeId: 1 }
  const PREFIX_START: Record<number, number[]> = { 900: [555], 901: [555] } // near the shared start point, both directions

  function buildLoopGraphData(exitSharesNonExemptId: boolean): GraphData {
    const SORTED_START: Record<number, number[]> = {
      900: [555, 111],
      901: exitSharesNonExemptId ? [555, 111] : [555, 222],
    }
    return {
      hutEdges: { hutIds: ['A', 'B'], variantNames: { 0: 'FAST_ANY' }, records: [loopEdge] },
      approaches: {
        records: [{ hutIndex: 0, startId: 999, sourceType: SOURCE_TYPE_PARKING, variant: 0, accessUnknown: false, distanceM: 2000, ascentM: 100, descentM: 50, access: null, edgeId: 900 }],
        reverseIndex: {
          hut_to_starts: {
            1: [{ hut_id: 1, start_id: 999, source_type: SOURCE_TYPE_PARKING, variant: 0, distance_m: 2000, ascent_m: 50, descent_m: 100, edge_id: 901 }],
          },
          start_to_huts: {},
        },
      },
      hutEdgeIds: { getSortedIds: () => new Int32Array(0), getPrefixIds: () => new Int32Array(0), getSuffixIds: () => new Int32Array(0) },
      startEdgeIds: {
        getSortedIds: (edgeId) => Int32Array.from(SORTED_START[edgeId] ?? []),
        getPrefixIds: (edgeId) => Int32Array.from(PREFIX_START[edgeId] ?? []),
        getSuffixIds: () => new Int32Array(0),
      },
    }
  }

  it('keeps a car-mode loop that only shares the run near the common start point', () => {
    const { chains } = searchChains(
      { mode: 'car', legCountMin: 3, legCountMax: 3, ...generousConstraints },
      buildLoopGraphData(false),
    )
    const kept = chains.find((c) => c.huts.length === 2)
    expect(kept).toBeDefined()
    expect(kept!.startId).toBe(999)
    expect(kept!.exitStartId).toBe(999)
  })

  it('excludes a car-mode loop with a genuine overlap away from the shared start point', () => {
    const { chains, killCounters } = searchChains(
      { mode: 'car', legCountMin: 3, legCountMax: 3, ...generousConstraints },
      buildLoopGraphData(true),
    )
    expect(chains.some((c) => c.huts.length === 2)).toBe(false)
    expect(killCounters.trackOverlap).toBeGreaterThan(0)
  })
})

describe('searchChains (single-hut approach/exit trim)', () => {
  const graphDataSingleHutTrim: GraphData = {
    hutEdges: { hutIds: ['A'], variantNames: { 0: 'FAST_ANY' }, records: [] },
    approaches: {
      records: [{ hutIndex: 0, startId: 300, sourceType: SOURCE_TYPE_STATION, variant: 0, accessUnknown: false, distanceM: 2000, ascentM: 100, descentM: 50, access: null, edgeId: 950 }],
      reverseIndex: {
        hut_to_starts: {
          0: [{ hut_id: 0, start_id: 301, source_type: SOURCE_TYPE_STATION, variant: 0, distance_m: 2000, ascent_m: 50, descent_m: 100, edge_id: 951 }],
        },
        start_to_huts: {},
      },
    },
    hutEdgeIds: { getSortedIds: () => new Int32Array(0), getPrefixIds: () => new Int32Array(0), getSuffixIds: () => new Int32Array(0) },
    startEdgeIds: {
      getSortedIds: (edgeId) => Int32Array.from(({ 950: [321, 111], 951: [321, 222] } as Record<number, number[]>)[edgeId] ?? []),
      getPrefixIds: () => new Int32Array(0),
      getSuffixIds: (edgeId) => Int32Array.from(({ 950: [321], 951: [321] } as Record<number, number[]>)[edgeId] ?? []),
    },
  }

  it('trims the run shared out of a single hut between the approach and exit legs', () => {
    const { chains } = searchChains(
      { mode: 'transit', legCountMin: 2, legCountMax: 2, ...generousConstraints },
      graphDataSingleHutTrim,
    )
    const kept = chains.find((c) => c.huts.length === 1)
    expect(kept).toBeDefined()
    expect(kept!.startId).toBe(300)
    expect(kept!.exitStartId).toBe(301)
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd huts && npx vitest run src/tourSearch/search.test.ts -t "shared-start overlap"`
Run: `cd huts && npx vitest run src/tourSearch/search.test.ts -t "single-hut approach"`
Expected: the "excludes a car-mode loop with a genuine overlap" test currently FAILS (nothing
rejects it today, since `collectFinished` never checks exit legs against `usedEdgeIds` at all — the
chain is kept when it should be excluded). The other two may already pass today (there's nothing
currently excluding them) — that's fine, same as Task 5 Step 2; Step 3 makes them pass for the right
reason.

- [ ] **Step 3: Add the exit-leg overlap check to `collectFinished`**

In `huts/src/tourSearch/search.ts`, change:

```ts
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
```

to (`edgeIdTables` here is the one Task 5 already declared at function scope, above `collectFinished`
— not redeclared):

```ts
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

          const exitLegForLookup = { edgeId: exitLeg.edgeId, reversed: exitLeg.reversed, kind: 'start' as const }
          let exempt: Set<number> = EMPTY_EDGE_IDS
          if (s.prevLeg) {
            // Same shared-hut trim as the expansion loop, at the chain's LAST hut h - s.prevLeg is
            // either the last hut-hut leg, or (a zero-nights chain) the approach leg itself.
            const prevNear = nearHubIds(edgeIdTables, s.prevLeg, 'arriving')
            const newNear = nearHubIds(edgeIdTables, exitLegForLookup, 'departing')
            exempt = new Set(trimSharedHubIds(prevNear, newNear))
          }
          if (exitLeg.startId === s.startId) {
            // Loop closure (car mode, or a coincidental match on any other mode): the trail out of
            // the shared start point is unavoidably shared too, same reasoning as the shared-hut
            // case - "near start" is always the record's prefix (access is always stored as
            // from_id), regardless of either leg's reversed flag.
            const approachNearStart = graphData.startEdgeIds.getPrefixIds(s.approachEdgeId)
            const exitNearStart = graphData.startEdgeIds.getPrefixIds(exitLeg.edgeId)
            for (const id of trimSharedHubIds(approachNearStart, exitNearStart)) exempt.add(id)
          }
          const exitSortedIds = graphData.startEdgeIds.getSortedIds(exitLeg.edgeId)
          if (hasOverlap(exitSortedIds, exempt, s.usedEdgeIds)) { killCounters.trackOverlap++; continue }

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
```

(`collectFinished` is defined, and first invoked, before the expansion loop's first iteration —
which is fine, since `edgeIdTables` is a plain object built once at the top of `searchChains`, in
Task 5's change, before either `collectFinished` or the loop exist.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd huts && npx vitest run src/tourSearch/search.test.ts`
Expected: all PASS, including every pre-existing test in the file.

- [ ] **Step 5: Run the full client test suite and typecheck**

Run: `cd huts && npm run typecheck && npm test`
Expected: both PASS.

- [ ] **Step 6: Commit**

```bash
cd /home/superhellth/open-alps
git add huts/src/tourSearch/search.ts huts/src/tourSearch/search.test.ts
git commit -m "$(cat <<'EOF'
feat(frontend): check exit legs for overlap, with a shared-start exemption

collectFinished never checked exit legs against usedEdgeIds at all - this
closes that gap using the same trim/hasOverlap machinery the expansion
loop already uses, plus a shared-start exemption (mirroring the existing
shared-hut one) so a car-mode loop returning to the same trailhead isn't
excluded purely for the unavoidable stretch of access trail both ends
share.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TScTEg46Qwae85AttDMav1
EOF
)"
```

---

## Post-plan note (not a task — do not execute)

This plan intentionally does not run any `doit` task. `huts/public/data/start-edge-ids.bin/.json`
won't exist until a pipeline run happens; until then, `loadStartEdgeIdsData` will 404 against the
real static server (same situation `hut-edge-ids.*` was in after the 2026-08-29 plan, per
`realData.smoke.test.ts`'s stub). When the user is ready to run the pipeline, `RECORD_SCHEMA_VERSION`
having bumped means `doit` will rebuild `build_hub_edges` + `build_access_edges` + everything
downstream of them, not just `build_start_edge_ids` — confirm that's understood before invoking
`doit`, per the root `CLAUDE.md`'s standing rule to always ask first.
