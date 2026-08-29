# Avoid Overlapping Tracks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Exception for this repo:** the root `CLAUDE.md` forbids `superpowers:subagent-driven-development`
> (and any worktree/subagent-driven execution) in `open-alps`. Use **superpowers:executing-plans**
> only, in-session, on the current checkout.

**Goal:** Persist per-hut-edge trail-segment (base-graph edge) identity through the pipeline, ship
it to the client, and use it during tour search to exclude chains that re-cross the same physical
trail on two different hut-edges — except for the unavoidable short run leaving a hut two legs
share as an endpoint.

**Architecture:** Pipeline: thread a disambiguated global `base_edge_id` through
`lib/cell_igraph.py`'s igraph construction and `accumulate_path`, persist it per hut-edge record
(full sorted set for exact-overlap checks, plus a small traversal-ordered prefix/suffix for the
shared-hub exemption), and ship it as a new sibling data file `hut-edge-ids.bin`/`.json`. Client:
load that file eagerly alongside `hut-edge-payload.bin`, and check it during DFS expansion
(`search.ts`) — reject a candidate leg whose base-edge ids collide with ids already used earlier in
the chain, after exempting the short run shared with the immediately preceding leg at their common
hut.

**Tech Stack:** Python/numpy pipeline (`pipeline/`, doit-orchestrated), TypeScript/Vitest client
(`huts/src/tourSearch/`).

**Spec:** `docs/superpowers/specs/2026-08-29-avoid-overlapping-tracks-design.md` — this plan
implements it section by section; read both together.

## Global Constraints

- **Never run any `pipeline/` `doit` task without first asking the user and getting explicit
  confirmation** — this applies even to tasks that look cheap (root `CLAUDE.md`). Tasks 1–8 below
  are pure code + unit tests against synthetic fixtures and do not require running the pipeline.
  Task 11 is the one step that regenerates real data and MUST pause for explicit user confirmation
  before invoking `doit`.
- Only bump `record_schema_version` (not `edge_schema_version`/`snap_schema_version`) for this
  change, so only `task_build_hub_edges` reruns — not the ~4h `build_base_graph`.
- Store each hut-edge record's full base-edge-id set **sorted ascending** (spec §1) — only set
  membership matters for the main overlap check, and it's what `edge_ids.npy` and
  `hut-edge-ids.bin` both carry.
- Traversal-ordered `k = 8` ids near each endpoint (spec §4) travel as separate fixed-width
  `prefix_ids`/`suffix_ids` columns, **not** derivable from the sorted set.
- Approach/exit legs are out of scope (spec, "Scope") — the client check only ever runs on
  interior hut-hut legs, which is what `search.ts`'s expansion loop already restricts to.
- No UI toggle — the check is unconditional wherever it's wired in.
- The overlap check does **not** enter the dominance key in `search.ts` (spec §3) — it stays
  `(hutIndex, startId, visitedKey)`.

---

## File Structure

Pipeline:
- Modify `pipeline/lib/cell_igraph.py` — carries `base_edge_id` through `BaseIgraphArrays`,
  `build_base_igraph_arrays`, `build_igraph_from_base`, `PathResult`, `accumulate_path`.
- Modify `pipeline/lib/binfmt.py` — splits `SCHEMA_VERSION`, adds `RECORD_DTYPE` fields.
- Modify `pipeline/dag/graph_building.py` — wires the three split schema-version tracking params.
- Modify `pipeline/phases/graph_building/build_hub_edges.py` — collects `base_edge_ids` per record,
  writes `hut_edges/edge_ids.npy` + prefix/suffix columns (hut-edges only).
- Create `pipeline/phases/postprocessing/build_edge_ids.py` — packs `hut_edges/records.npy` +
  `edge_ids.npy` into the client-facing `hut-edge-ids.bin`/`.json`.
- Modify `pipeline/dag/postprocessing.py` — new `task_build_edge_ids`.
- Modify `pipeline/dodo.py` — adds the two new filenames to `PUBLIC_FILES`.
- Modify `pipeline/tests/test_build_hub_edges.py` — new coverage for the above.
- Modify `pipeline/tests/test_build_edge_payload.py` — fixes `_record()` helper for the grown
  `RECORD_DTYPE`.
- Create `pipeline/tests/test_build_edge_ids.py` — round-trip test for the new packer.
- Modify `pipeline/tests/test_dodo_wiring.py` — wiring tests for the schema-version split and the
  new task.

Client:
- Create `huts/src/tourSearch/loadHutEdgeIds.ts` — fetches/parses `hut-edge-ids.bin`/`.json`.
- Create `huts/src/tourSearch/overlap.ts` — pure helpers: shared-hub-run trimming + overlap test.
- Modify `huts/src/tourSearch/types.ts` — `HutEdgeIdsData`, `GraphData.hutEdgeIds`,
  `KillCounters.trackOverlap`.
- Modify `huts/src/tourSearch/index.ts` — loads `hutEdgeIds` alongside the existing two fetches.
- Modify `huts/src/tourSearch/legFilters.ts` — `createKillCounters` gains `trackOverlap: 0`.
- Modify `huts/src/tourSearch/search.ts` — `State` carries `usedEdgeIds`/`prevHutLeg`; expansion
  loop runs the overlap check before accepting a leg.
- Create `huts/src/tourSearch/overlap.test.ts` — unit tests for the pure helpers.
- Modify `huts/src/tourSearch/search.test.ts` — new `describe('searchChains (overlap avoidance)')`
  block.
- Modify `huts/src/tourSearch/realData.smoke.test.ts` — loads real `hut-edge-ids` data, extends
  assertions (gated behind Task 11's real pipeline run).

---

### Task 1: `cell_igraph.py` — thread a disambiguated global base-edge id through igraph construction

**Files:**
- Modify: `pipeline/lib/cell_igraph.py`
- Test: `pipeline/tests/test_build_hub_edges.py` (new test functions, imports already exist there
  per the file's current `from lib.cell_igraph import ...` lines)

**Interfaces:**
- Consumes: `subgraph.local_edges["edge_id"]` (global base-graph edge id, `lib/binfmt.py`'s
  `EDGE_DTYPE`, preserved verbatim by `lib/subgraph.py`'s `gather_padded_subgraph`).
- Produces: `BaseIgraphArrays.base_edge_ids: list[int]` and a `"base_edge_id"` igraph edge
  attribute, both consumed by Task 2's `accumulate_path` change.

Disambiguation formula (spec §1): for original edge `i` (`i < n_orig`), `base_edge_id = edge_id * 3`.
For a hub-split synthetic edge, the half nearer `u` (appended first, at line 117 in the loop below)
gets `edge_id * 3 + 1`; the half nearer `v` (appended second, at line 131) gets `edge_id * 3 + 2`.
Max observed `edge_id` is 4,730,711, so `* 3 + 2` stays under `int32`.

- [ ] **Step 1: Write the failing test**

Add to `pipeline/tests/test_build_hub_edges.py`:

```python
def _one_edge_subgraph_for_split():
    """Two local nodes joined by one base edge (global edge_id=7), long enough to mid-chain-split."""
    nodes = np.zeros(2, dtype=binfmt.NODE_DTYPE)
    nodes["lon"] = [11.0, 11.01]
    nodes["lat"] = [47.0, 47.0]
    edges = np.zeros(1, dtype=binfmt.EDGE_DTYPE)
    edges[0] = (0, 1, 700.0, 0.0, 0.0, 0.0, 700.0, 50.0, 20.0, 1, False, True, 0, 0, 7)
    return LocalSubgraph(
        global_node_ids=np.array([100, 101]),
        local_nodes=nodes,
        local_edges=edges,
        interior=np.zeros(0, dtype=binfmt.COORD_DTYPE),
        local_node_ele=np.zeros(2, dtype=np.float32),
        interior_ele=np.zeros(0, dtype=np.float32),
    )


def test_synthetic_split_halves_get_distinct_base_edge_ids():
    subgraph = _one_edge_subgraph_for_split()
    split = SplitResult(
        split_coord=(11.005, 47.0),
        dist_to_u=350.0, dist_to_v=350.0,
        road_m_to_u=0.0, road_m_to_v=0.0,
        ungraded_m_to_u=0.0, ungraded_m_to_v=0.0,
        inferred_m_to_u=0.0, inferred_m_to_v=0.0,
        interior_to_u=[], interior_to_v=[],
    )
    hub_snaps = {("hut", 1): SnapResult(edge_local_index=0, split=split)}

    base = build_base_igraph_arrays(subgraph, hub_snaps)

    # index 0 = original edge (edge_id=7 -> 21), index 1 = the u-side synthetic half (-> 22),
    # index 2 = the v-side synthetic half (-> 23). This is the false-overlap bug §1 guards against:
    # a naive mapping would report the SAME id for both halves.
    assert base.base_edge_ids == [21, 22, 23]
    assert base.base_edge_ids[1] != base.base_edge_ids[2]

    graph, hub_vertex, _ = build_igraph_from_base(base)
    # original edge (index 0) was removed by the split; only the two synthetic halves survive.
    assert graph.ecount() == 2
    assert set(graph.es["base_edge_id"]) == {22, 23}
```

Add the two new imports at the top of the file alongside the existing `lib.cell_igraph` imports:

```python
from lib.hub_snap import SnapResult
from lib.edge_split import SplitResult
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pipeline && pixi run pytest tests/test_build_hub_edges.py::test_synthetic_split_halves_get_distinct_base_edge_ids -v`
Expected: FAIL — `AttributeError: 'BaseIgraphArrays' object has no attribute 'base_edge_ids'` (or a
`TypeError` from the dataclass constructor once you notice `base_edge_ids` isn't a field yet).

- [ ] **Step 3: Implement**

In `pipeline/lib/cell_igraph.py`, add the field to `BaseIgraphArrays` (after `edge_source`):

```python
    edge_source: list
    # base_edge_ids[i] is the disambiguated global base-graph edge id for igraph edge i - see
    # this module's build_base_igraph_arrays for the split-half disambiguation (spec §1 of
    # docs/superpowers/specs/2026-08-29-avoid-overlapping-tracks-design.md): edge_id*3 for an
    # original edge, edge_id*3+1/+2 for the u-side/v-side half of a hub-split edge, so the two
    # halves of one split edge never collide.
    base_edge_ids: list
```

In `build_base_igraph_arrays`, right after `edge_source = list(range(n_orig))`:

```python
    n_orig = len(subgraph.local_edges)
    edge_source = list(range(n_orig))
    edge_ids_col = subgraph.local_edges["edge_id"]
    base_edge_ids = [int(edge_ids_col[i]) * 3 for i in range(n_orig)]
```

In the snap loop, immediately after each `edge_source.append(ei)` call add the matching
`base_edge_ids.append(...)` — first occurrence (u-side half, currently line 130) gets `+ 1`, second
occurrence (v-side half, currently line 144) gets `+ 2`:

```python
        edges_uv.append((u, vid))
        ...
        edge_source.append(ei)
        base_edge_ids.append(int(edge_ids_col[ei]) * 3 + 1)
        edges_uv.append((vid, v))
        ...
        edge_source.append(ei)
        base_edge_ids.append(int(edge_ids_col[ei]) * 3 + 2)
```

Add `base_edge_ids=base_edge_ids` to the `BaseIgraphArrays(...)` return construction.

In `build_igraph_from_base`, add one more filtered attribute to `edge_attrs`:

```python
        "constrained_ok": _filter(base.constrained_oks), "interior": _filter(base.interiors),
        "base_edge_id": _filter(base.base_edge_ids),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pipeline && pixi run pytest tests/test_build_hub_edges.py::test_synthetic_split_halves_get_distinct_base_edge_ids -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/lib/cell_igraph.py pipeline/tests/test_build_hub_edges.py
git commit -m "feat(pipeline): thread disambiguated base-edge id through igraph construction"
```

---

### Task 2: `PathResult`/`accumulate_path` — collect traversed base-edge ids

**Files:**
- Modify: `pipeline/lib/cell_igraph.py`
- Test: `pipeline/tests/test_build_hub_edges.py`

**Interfaces:**
- Consumes: the `"base_edge_id"` igraph edge attribute from Task 1.
- Produces: `PathResult.base_edge_ids: list[int]`, in src→tgt traversal order — consumed by Task 4
  (`build_hub_edges.py`'s record construction).

- [ ] **Step 1: Write the failing test**

Add to `pipeline/tests/test_build_hub_edges.py`:

```python
def test_accumulate_path_reports_traversed_base_edge_ids_in_order():
    subgraph = _one_edge_subgraph_for_split()
    split = SplitResult(
        split_coord=(11.005, 47.0),
        dist_to_u=350.0, dist_to_v=350.0,
        road_m_to_u=0.0, road_m_to_v=0.0,
        ungraded_m_to_u=0.0, ungraded_m_to_v=0.0,
        inferred_m_to_u=0.0, inferred_m_to_v=0.0,
        interior_to_u=[], interior_to_v=[],
    )
    hub_snaps = {("hut", 1): SnapResult(edge_local_index=0, split=split)}
    base = build_base_igraph_arrays(subgraph, hub_snaps)
    graph, hub_vertex, vertex_coords = build_igraph_from_base(base)

    result = path_for(graph, vertex_coords, 0, 1)

    assert result.base_edge_ids == [22, 23]


def test_accumulate_path_same_source_and_target_has_empty_base_edge_ids():
    subgraph = _one_edge_subgraph_for_split()
    base = build_base_igraph_arrays(subgraph, {})
    graph, _, vertex_coords = build_igraph_from_base(base)

    result = path_for(graph, vertex_coords, 0, 0)

    assert result.base_edge_ids == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pipeline && pixi run pytest tests/test_build_hub_edges.py::test_accumulate_path_reports_traversed_base_edge_ids_in_order -v`
Expected: FAIL — `AttributeError: 'PathResult' object has no attribute 'base_edge_ids'`

- [ ] **Step 3: Implement**

In `pipeline/lib/cell_igraph.py`:

```python
PathResult = namedtuple(
    "PathResult",
    "coords distance_m road_m ungraded_m inferred_m ascent_m descent_m max_ele_m sac_rank "
    "via_ferrata base_edge_ids",
)
```

```python
    if src_v == tgt_v:
        return PathResult([], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -1, False, [])
    trail_coords = []
    distance_m = 0.0
    ...
    has_via_ferrata = False
    base_edge_ids = []
    cur = src_v
    for eid in epath:
        e = graph.es[eid]
        forward = e.source == cur
        nxt = e.target if forward else e.source
        interior = e["interior"] if forward else list(reversed(e["interior"]))
        trail_coords.append(vertex_coords[cur])
        trail_coords.extend(interior)
        distance_m += e["dist"]
        road_m += e["road_m"]
        ungraded_m += e["ungraded_m"]
        inferred_m += e["inferred_m"]
        ascent_m += e["ascent_m"] if forward else e["descent_m"]
        descent_m += e["descent_m"] if forward else e["ascent_m"]
        if e["max_ele_m"] > max_ele_m:
            max_ele_m = e["max_ele_m"]
        if e["sac_rank"] > max_sac_rank:
            max_sac_rank = e["sac_rank"]
        if e["via_ferrata"]:
            has_via_ferrata = True
        base_edge_ids.append(e["base_edge_id"])
        cur = nxt
    trail_coords.append(vertex_coords[cur])
    return PathResult(
        trail_coords, distance_m, road_m, ungraded_m, inferred_m, ascent_m, descent_m,
        max_ele_m, max_sac_rank, has_via_ferrata, base_edge_ids,
    )
```

Note: `base_edge_id` is direction-independent (it identifies physical ground, not a signed
delta), so — unlike `ascent_m`/`descent_m` — it needs no `forward` swap.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pipeline && pixi run pytest tests/test_build_hub_edges.py -k base_edge_id -v`
Expected: PASS (both new tests)

- [ ] **Step 5: Commit**

```bash
git add pipeline/lib/cell_igraph.py pipeline/tests/test_build_hub_edges.py
git commit -m "feat(pipeline): collect traversed base-edge ids in accumulate_path"
```

---

### Task 3: `binfmt.py` — split schema version, add `RECORD_DTYPE` fields

**Files:**
- Modify: `pipeline/lib/binfmt.py`
- Modify: `pipeline/tests/test_build_edge_payload.py` (its `_record()` helper builds a
  `RECORD_DTYPE` tuple positionally and will break the moment the dtype grows)
- Test: `pipeline/tests/test_dodo_wiring.py` (Task 5 wires the params; this task just needs
  `test_build_edge_payload.py` to keep passing)

**Interfaces:**
- Produces: `binfmt.EDGE_SCHEMA_VERSION`, `binfmt.SNAP_SCHEMA_VERSION`,
  `binfmt.RECORD_SCHEMA_VERSION` (replacing the single `binfmt.SCHEMA_VERSION`); `RECORD_DTYPE`
  gains `edge_id_offset`, `edge_id_count`, `prefix_ids` (8-wide `i4`), `prefix_count`,
  `suffix_ids` (8-wide `i4`), `suffix_count` — consumed by Task 4/5/6.

- [ ] **Step 1: Write the failing test**

`test_build_edge_payload.py`'s existing tests will fail once `RECORD_DTYPE` grows, because
`_record()`'s return tuple is one shorter than the dtype. That failure IS this step's red bar —
no new test needed. Confirm the current green baseline first:

Run: `cd pipeline && pixi run pytest tests/test_build_edge_payload.py -v`
Expected: PASS (baseline, before touching `RECORD_DTYPE`)

- [ ] **Step 2: Change `RECORD_DTYPE` and confirm the expected break**

In `pipeline/lib/binfmt.py`, extend `RECORD_DTYPE`:

```python
RECORD_DTYPE = np.dtype([
    ("from_id", "i8"), ("to_id", "i8"), ("from_type", "u1"), ("to_type", "u1"),
    ("variant", "u1"), ("distance_m", "f4"), ("road_m", "f4"),
    ("ascent_m", "f4"), ("descent_m", "f4"),
    ("max_ele_m", "f4"),
    ("ungraded_m", "f4"),
    ("inferred_m", "f4"),
    ("snap_m", "f4"),
    ("sac_rank", "i1"), ("via_ferrata", "bool"),
    ("geom_offset", "i8"), ("geom_count", "i4"),
    ("profile_offset", "i8"), ("profile_count", "i4"),
    # Trail-segment identity for the "avoid overlapping tracks" check (docs/superpowers/specs/
    # 2026-08-29-avoid-overlapping-tracks-design.md). edge_id_offset/count index a per-record
    # ascending-sorted slice of hut_edges/edge_ids.npy (the FULL base-edge-id set, for the
    # non-adjacent-leg overlap check). prefix_ids/suffix_ids are the first/last K_TRAVERSAL ids in
    # TRAVERSAL order (prefix: outward from from_id: suffix: outward from to_id, i.e. the last-K
    # run reversed) - needed because the shared-hub exemption (spec §4) has to walk inward from a
    # specific endpoint, which the sorted set can't do. -1-padded past *_count when a record has
    # fewer than K_TRAVERSAL base edges. Only ever populated for hut_edges records - start_edges
    # keeps these zeroed (spec §1: gated on a parameter, hut-edges-only).
    ("edge_id_offset", "i8"), ("edge_id_count", "i4"),
    ("prefix_ids", "i4", (8,)), ("prefix_count", "u1"),
    ("suffix_ids", "i4", (8,)), ("suffix_count", "u1"),
])
```

Replace the single schema version constant:

```python
# Split into three independent tracking params (one per dtype each cares about) so bumping one
# doesn't force-rerun tasks that don't touch that dtype - see pipeline/dag/graph_building.py.
EDGE_SCHEMA_VERSION = 2
SNAP_SCHEMA_VERSION = 2
RECORD_SCHEMA_VERSION = 3  # bumped: RECORD_DTYPE gained edge_id_offset/count + prefix/suffix ids
```

Run: `cd pipeline && pixi run pytest tests/test_build_edge_payload.py -v`
Expected: FAIL — numpy raises on `_record()`'s now-too-short tuple (`ValueError: could not assign
tuple of length 19 to structure with 25 fields` or similar).

- [ ] **Step 3: Fix the ripple in `test_build_edge_payload.py`**

In `pipeline/tests/test_build_edge_payload.py`, extend `_record()`'s return tuple with zeroed
defaults for the new fields:

```python
def _record(from_id, to_id, variant, distance_m=1000.0, ascent_m=50.0, descent_m=20.0,
            max_ele_m=1500.0, sac_rank=2, via_ferrata=False, road_m=10.0, ungraded_m=0.0,
            inferred_m=0.0, snap_m=5.0):
    return (
        from_id, to_id, binfmt.TYPE_HUT, binfmt.TYPE_HUT, variant,
        distance_m, road_m, ascent_m, descent_m, max_ele_m, ungraded_m, inferred_m, snap_m,
        sac_rank, via_ferrata, 0, 2, 0, 3,
        0, 0, (-1,) * 8, 0, (-1,) * 8, 0,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pipeline && pixi run pytest tests/test_build_edge_payload.py -v`
Expected: PASS

Also grep for any other direct use of the old name to catch remaining breakage:

Run: `cd pipeline && grep -rn "binfmt.SCHEMA_VERSION\b" --include='*.py' .`
Expected: no matches outside `dag/graph_building.py` (fixed in Task 4) — if any other file
references it, update it to the specific `*_SCHEMA_VERSION` constant that dtype maps to.

- [ ] **Step 5: Commit**

```bash
git add pipeline/lib/binfmt.py pipeline/tests/test_build_edge_payload.py
git commit -m "feat(pipeline): add trail-segment-id fields to RECORD_DTYPE, split schema version"
```

---

### Task 4: `dag/graph_building.py` — wire the three split schema-version params

**Files:**
- Modify: `pipeline/dag/graph_building.py`
- Test: `pipeline/tests/test_dodo_wiring.py`

**Interfaces:**
- Consumes: `binfmt.EDGE_SCHEMA_VERSION`/`SNAP_SCHEMA_VERSION`/`RECORD_SCHEMA_VERSION` (Task 3).

- [ ] **Step 1: Write the failing test**

Add to `pipeline/tests/test_dodo_wiring.py` (follow that file's existing pattern of importing
`dodo`/task functions and asserting on the returned task dict's `params`):

```python
def test_build_base_graph_tracks_only_edge_schema_version():
    from dag.graph_building import task_build_base_graph
    task = task_build_base_graph()
    param_names = {p["name"] for p in task["params"]}
    assert "edge_schema_version" in param_names
    assert "snap_schema_version" not in param_names
    assert "record_schema_version" not in param_names


def test_build_hub_edges_tracks_all_three_schema_versions():
    from dag.graph_building import task_build_hub_edges
    task = task_build_hub_edges()
    param_names = {p["name"] for p in task["params"]}
    assert {"edge_schema_version", "snap_schema_version", "record_schema_version"} <= param_names


def test_snap_hubs_tracks_only_snap_schema_version():
    from dag.graph_building import task_snap_hubs
    task = task_snap_hubs()
    param_names = {p["name"] for p in task["params"]}
    assert "snap_schema_version" in param_names
    assert "edge_schema_version" not in param_names
    assert "record_schema_version" not in param_names


def test_gather_route_subgraphs_tracks_only_edge_schema_version():
    from dag.graph_building import task_gather_route_subgraphs
    task = task_gather_route_subgraphs()
    param_names = {p["name"] for p in task["params"]}
    assert "edge_schema_version" in param_names
    assert "snap_schema_version" not in param_names
    assert "record_schema_version" not in param_names
```

(If `test_dodo_wiring.py`'s existing tests read `params` differently — e.g. via `tracking_param`'s
own name attribute rather than a dict with a `"name"` key — match whatever accessor pattern the
file's existing tests already use for `_SCHEMA_VERSION_PARAM`; grep the file for
`schema_version` first to confirm the exact shape before writing this step.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pipeline && pixi run pytest tests/test_dodo_wiring.py -k schema_version -v`
Expected: FAIL — `AttributeError: module 'lib.binfmt' has no attribute ...` is already fixed by
Task 3, so this should fail instead on `param_names` still containing only `"schema_version"`
(the old single param name), not the three new ones.

- [ ] **Step 3: Implement**

In `pipeline/dag/graph_building.py`, replace:

```python
_SCHEMA_VERSION_PARAM = tracking_param("schema_version", int, binfmt.SCHEMA_VERSION)
```

with:

```python
# Split so bumping RECORD_DTYPE (this change) doesn't force-rerun task_build_base_graph's ~4h
# EDGE_DTYPE build - see root CLAUDE.md's warning on that task and lib/binfmt.py's dtype table.
_EDGE_SCHEMA_VERSION_PARAM = tracking_param("edge_schema_version", int, binfmt.EDGE_SCHEMA_VERSION)
_SNAP_SCHEMA_VERSION_PARAM = tracking_param("snap_schema_version", int, binfmt.SNAP_SCHEMA_VERSION)
_RECORD_SCHEMA_VERSION_PARAM = tracking_param(
    "record_schema_version", int, binfmt.RECORD_SCHEMA_VERSION
)
```

Then update each task's `tracking_params` list, replacing the single `_SCHEMA_VERSION_PARAM` entry
with the params matching what that task actually reads/writes:

- `task_build_base_graph`: `_EDGE_SCHEMA_VERSION_PARAM` only (writes `EDGE_DTYPE`).
- `task_snap_hubs`: `_SNAP_SCHEMA_VERSION_PARAM` only (writes `HUB_SNAP_DTYPE`).
- `task_gather_route_subgraphs`: `_EDGE_SCHEMA_VERSION_PARAM` only (re-serializes `local_edges`,
  which is `EDGE_DTYPE`, via `lib/subgraph.py`'s `save_local_subgraph`).
- `task_build_hub_edges`: all three — `_EDGE_SCHEMA_VERSION_PARAM`, `_SNAP_SCHEMA_VERSION_PARAM`,
  `_RECORD_SCHEMA_VERSION_PARAM` (reads `EDGE_DTYPE` + `HUB_SNAP_DTYPE`, writes `RECORD_DTYPE`).

Keep every other existing param in each task's `tracking_params`/`params` list unchanged — only
swap out the schema-version entry.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pipeline && pixi run pytest tests/test_dodo_wiring.py -v`
Expected: PASS (all wiring tests, including the pre-existing ones)

- [ ] **Step 5: Commit**

```bash
git add pipeline/dag/graph_building.py pipeline/tests/test_dodo_wiring.py
git commit -m "refactor(pipeline): split shared schema_version tracking param in three"
```

---

### Task 5: `build_hub_edges.py` — collect and persist per-record base-edge ids

**Files:**
- Modify: `pipeline/phases/graph_building/build_hub_edges.py`
- Test: `pipeline/tests/test_build_hub_edges.py`

**Interfaces:**
- Consumes: `path.base_edge_ids` (Task 2), `RECORD_DTYPE`'s new fields (Task 3).
- Produces: `hut_edges/edge_ids.npy` (flat `i4`, ascending sorted per record, concatenated in
  record order) and `records.npy` with `edge_id_offset`/`edge_id_count`/`prefix_ids`/
  `prefix_count`/`suffix_ids`/`suffix_count` populated — consumed by Task 6.

- [ ] **Step 1: Write the failing test**

Add to `pipeline/tests/test_build_hub_edges.py` (mirrors the existing
`test_write_edge_output_preserves_each_record_variant`-style tests around `_write_edge_output`):

```python
def _record_with_geometry(from_id, to_id, base_edge_ids):
    return {
        "from_id": from_id, "from_type": binfmt.TYPE_HUT,
        "to_id": to_id, "to_type": binfmt.TYPE_HUT,
        "variant": binfmt.VARIANT_FAST_ANY,
        "distance_m": 1000.0, "road_m": 0.0, "ascent_m": 50.0, "descent_m": 20.0,
        "max_ele_m": 1500.0, "ungraded_m": 0.0, "inferred_m": 0.0, "snap_m": 5.0,
        "sac_rank": 1, "via_ferrata": False,
        "geometry": [(11.0, 47.0), (11.01, 47.0)],
        "base_edge_ids": base_edge_ids,
    }


def test_write_edge_output_writes_sorted_edge_ids_and_prefix_suffix(tmp_path):
    records = [
        _record_with_geometry(0, 1, [30, 10, 20]),  # traversal order: 30 then 10 then 20
        _record_with_geometry(1, 2, [40, 40, 50]),  # a repeated id must collapse in the sorted set
    ]
    out_dir = tmp_path / "hut_edges"
    out_dir.mkdir()

    _write_edge_output(records, out_dir, write_edge_ids=True)

    records_arr = binfmt.load_array(out_dir / "records.npy", mmap=False)
    edge_ids_arr = binfmt.load_array(out_dir / "edge_ids.npy", mmap=False)

    # record 0: sorted set {10,20,30}, prefix = first 8 in traversal order ([30,10,20], only 3
    # available), suffix = last 8 in traversal order REVERSED to be outward-from-to_id ([20,10,30]).
    r0 = records_arr[0]
    assert edge_ids_arr[r0["edge_id_offset"]:r0["edge_id_offset"] + r0["edge_id_count"]].tolist() == [10, 20, 30]
    assert r0["prefix_count"] == 3
    assert r0["prefix_ids"][:3].tolist() == [30, 10, 20]
    assert r0["prefix_ids"][3] == -1
    assert r0["suffix_count"] == 3
    assert r0["suffix_ids"][:3].tolist() == [20, 10, 30]

    # record 1: duplicate id 40 collapses to one entry in the sorted set.
    r1 = records_arr[1]
    assert edge_ids_arr[r1["edge_id_offset"]:r1["edge_id_offset"] + r1["edge_id_count"]].tolist() == [40, 50]


def test_write_edge_output_skips_edge_ids_when_not_requested(tmp_path):
    records = [_record_with_geometry(0, 1, [10, 20])]
    out_dir = tmp_path / "start_edges"
    out_dir.mkdir()

    _write_edge_output(records, out_dir, write_edge_ids=False)

    assert not (out_dir / "edge_ids.npy").exists()
    records_arr = binfmt.load_array(out_dir / "records.npy", mmap=False)
    assert records_arr[0]["edge_id_count"] == 0
    assert records_arr[0]["prefix_count"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pipeline && pixi run pytest tests/test_build_hub_edges.py -k write_edge_output_writes_sorted -v`
Expected: FAIL — `TypeError: _write_edge_output() got an unexpected keyword argument 'write_edge_ids'`

- [ ] **Step 3: Implement**

In `pipeline/phases/graph_building/build_hub_edges.py`, update `compute_hub_edges_for_cell`'s
record dict (around the existing `"geometry": geometry,` line) to also carry the raw traversal-order
ids:

```python
                records.append({
                    "from_id": hub["id"], "from_type": hub["type"],
                    "to_id": t["id"], "to_type": t["type"],
                    "variant": variant.code,
                    "distance_m": float(path.distance_m + snap_m),
                    "road_m": float(path.road_m),
                    "ascent_m": float(ascent_m), "descent_m": float(descent_m),
                    "max_ele_m": float(path.max_ele_m) if np.isfinite(path.max_ele_m) else 0.0,
                    "ungraded_m": float(path.ungraded_m), "inferred_m": float(path.inferred_m),
                    "snap_m": float(snap_m),
                    "sac_rank": int(path.sac_rank),
                    "via_ferrata": bool(path.via_ferrata),
                    "geometry": geometry,
                    "base_edge_ids": path.base_edge_ids,
                })
```

Rewrite `_write_edge_output`:

```python
K_TRAVERSAL = 8  # spec §4: ~1km at 132m mean base-edge length; revisit once real overlap-length
                 # distribution is visible from the first real build.


def _write_edge_output(records: list, out_dir: Path, write_edge_ids: bool = False) -> None:
    """Packs merge_and_dedup's dict records into binfmt.RECORD_DTYPE + a flat geometry.npy
    (binfmt.COORD_DTYPE), mirroring how build_base_graph.py packs contracted-edge interior
    polylines: one growing geometry array, each record's geom_offset/geom_count pointing into
    it. profile_offset/profile_count stay 0 here - the elevation profile pass fills those in a
    later pass over this same records.npy.

    A constrained row frequently routes the exact same polyline as FAST_ANY (spec C7) - identical
    coordinate runs are deduplicated by content hash so those variants share one geom_offset
    instead of the geometry file growing linearly in variant count for zero new information.
    No collision re-check against the stored run: blake2b-128 over the run counts this pipeline
    will ever see has a collision probability far below floating-point noise in the coordinates
    themselves - deliberate, not an oversight.

    write_edge_ids: True for hut_edges only (spec §1 of the overlapping-tracks design gates this
    on a parameter - start_edges' geometry sidecar alone is 147MB and approaches are out of scope).
    When True, also writes out_dir/edge_ids.npy: each record's FULL base-edge-id set, deduped and
    sorted ascending, concatenated across records in record order - RECORD_DTYPE's
    edge_id_offset/edge_id_count slice into it. prefix_ids/suffix_ids are small enough to live
    directly on RECORD_DTYPE (fixed-width K_TRAVERSAL, -1-padded)."""
    records_arr = np.zeros(len(records), dtype=binfmt.RECORD_DTYPE)
    flat_geometry = []
    flat_edge_ids = []
    cursor = 0
    edge_id_cursor = 0
    seen_geoms = {}   # blake2b of the packed coordinate run -> geom_offset
    for i, r in enumerate(records):
        geom = r["geometry"]
        key = hashlib.blake2b(
            np.asarray(geom, dtype=np.float64).tobytes(), digest_size=16
        ).digest()
        offset = seen_geoms.get(key)
        if offset is None:
            offset = cursor
            seen_geoms[key] = offset
            flat_geometry.extend(geom)
            cursor += len(geom)

        if write_edge_ids:
            traversal_ids = r["base_edge_ids"]
            sorted_ids = sorted(set(traversal_ids))
            edge_id_offset = edge_id_cursor
            edge_id_count = len(sorted_ids)
            flat_edge_ids.extend(sorted_ids)
            edge_id_cursor += edge_id_count
            prefix = traversal_ids[:K_TRAVERSAL]
            suffix = list(reversed(traversal_ids[-K_TRAVERSAL:])) if traversal_ids else []
            prefix_count = len(prefix)
            suffix_count = len(suffix)
            prefix_ids = tuple(prefix + [-1] * (K_TRAVERSAL - prefix_count))
            suffix_ids = tuple(suffix + [-1] * (K_TRAVERSAL - suffix_count))
        else:
            edge_id_offset, edge_id_count = 0, 0
            prefix_ids = suffix_ids = (-1,) * K_TRAVERSAL
            prefix_count = suffix_count = 0

        records_arr[i] = (
            r["from_id"], r["to_id"], r["from_type"], r["to_type"], r["variant"],
            r["distance_m"], r["road_m"], r["ascent_m"], r["descent_m"], r["max_ele_m"],
            r["ungraded_m"], r["inferred_m"], r["snap_m"], r["sac_rank"],
            r["via_ferrata"], offset, len(geom), 0, 0,
            edge_id_offset, edge_id_count, prefix_ids, prefix_count, suffix_ids, suffix_count,
        )

    geometry_arr = np.zeros(len(flat_geometry), dtype=binfmt.COORD_DTYPE)
    if flat_geometry:
        geometry_arr["lon"] = [p[0] for p in flat_geometry]
        geometry_arr["lat"] = [p[1] for p in flat_geometry]

    binfmt.save_array(out_dir / "records.npy", records_arr)
    binfmt.save_array(out_dir / "geometry.npy", geometry_arr)
    if write_edge_ids:
        binfmt.save_array(out_dir / "edge_ids.npy", np.array(flat_edge_ids, dtype="i4"))
```

Update the two call sites (around what was lines 456-457):

```python
    _write_edge_output(hut_records, out_dir / "hut_edges", write_edge_ids=True)
    _write_edge_output(access_records, out_dir / "start_edges", write_edge_ids=False)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pipeline && pixi run pytest tests/test_build_hub_edges.py -v`
Expected: PASS (whole file — confirms no regression in the pre-existing `_write_edge_output`
tests either)

- [ ] **Step 5: Commit**

```bash
git add pipeline/phases/graph_building/build_hub_edges.py pipeline/tests/test_build_hub_edges.py
git commit -m "feat(pipeline): persist per-hut-edge base-edge-id set, prefix and suffix"
```

---

### Task 6: New `build_edge_ids.py` — pack the client-facing sibling file

**Files:**
- Create: `pipeline/phases/postprocessing/build_edge_ids.py`
- Test: Create `pipeline/tests/test_build_edge_ids.py`

**Interfaces:**
- Consumes: `hut_edges/records.npy`, `hut_edges/edge_ids.npy` (Task 5).
- Produces: `pack_edge_ids(records, flat_edge_ids) -> tuple[bytes, dict]` and a CLI writing
  `hut-edge-ids.bin`/`.json` — consumed by Task 7 (task wiring) and the client Task 9 loader.

Layout (spec §2, following `hut-edge-geometry.json`'s flat-counts-array manifest shape, not
`hut-edge-payload.json`'s columnar one): `hut-edge-ids.bin` is three concatenated blobs — sorted
ids (`sum(edge_id_count)` × `i4`), then prefix ids (`rows * k` × `i4`, -1-padded), then suffix ids
(same). The manifest carries `rows`, `k`, the three `*_count` arrays (for the client to
reconstruct offsets, mirroring `hut-edge-geometry.json`'s `point_counts`), and each blob's byte
length so the client can locate blob boundaries without re-deriving them.

- [ ] **Step 1: Write the failing test**

Create `pipeline/tests/test_build_edge_ids.py`:

```python
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from lib import binfmt  # noqa: E402
from postprocessing.build_edge_ids import pack_edge_ids  # noqa: E402


def _record(edge_id_offset, edge_id_count, prefix_ids, prefix_count, suffix_ids, suffix_count):
    return (
        0, 1, binfmt.TYPE_HUT, binfmt.TYPE_HUT, binfmt.VARIANT_FAST_ANY,
        1000.0, 0.0, 50.0, 20.0, 1500.0, 0.0, 0.0, 5.0, 1, False, 0, 2, 0, 0,
        edge_id_offset, edge_id_count,
        tuple(prefix_ids), prefix_count, tuple(suffix_ids), suffix_count,
    )


def test_pack_edge_ids_round_trips_two_records():
    records = np.array([
        _record(0, 3, [30, 10, 20, -1, -1, -1, -1, -1], 3, [20, 10, 30, -1, -1, -1, -1, -1], 3),
        _record(3, 2, [40, -1, -1, -1, -1, -1, -1, -1], 1, [50, -1, -1, -1, -1, -1, -1, -1], 1),
    ], dtype=binfmt.RECORD_DTYPE)
    flat_edge_ids = np.array([10, 20, 30, 40, 50], dtype="i4")

    payload, manifest = pack_edge_ids(records, flat_edge_ids)

    assert manifest["rows"] == 2
    assert manifest["k"] == 8
    assert manifest["edge_id_count"] == [3, 2]
    assert manifest["prefix_count"] == [3, 1]
    assert manifest["suffix_count"] == [3, 1]

    sorted_bytes = manifest["sorted_bytes"]
    prefix_bytes = manifest["prefix_bytes"]
    suffix_bytes = manifest["suffix_bytes"]
    assert sorted_bytes + prefix_bytes + suffix_bytes == len(payload)

    sorted_arr = np.frombuffer(payload[:sorted_bytes], dtype="i4")
    prefix_arr = np.frombuffer(payload[sorted_bytes:sorted_bytes + prefix_bytes], dtype="i4")
    suffix_arr = np.frombuffer(
        payload[sorted_bytes + prefix_bytes:sorted_bytes + prefix_bytes + suffix_bytes], dtype="i4"
    )

    assert sorted_arr.tolist() == [10, 20, 30, 40, 50]
    assert prefix_arr[:8].tolist() == [30, 10, 20, -1, -1, -1, -1, -1]
    assert prefix_arr[8:16].tolist() == [40, -1, -1, -1, -1, -1, -1, -1]
    assert suffix_arr[:8].tolist() == [20, 10, 30, -1, -1, -1, -1, -1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pipeline && pixi run pytest tests/test_build_edge_ids.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'postprocessing.build_edge_ids'`

- [ ] **Step 3: Implement**

Create `pipeline/phases/postprocessing/build_edge_ids.py`:

```python
"""Packs hut_edges/records.npy + hut_edges/edge_ids.npy (build_hub_edges.py) into the client-
facing hut-edge-ids.bin/.json sibling of hut-edge-payload.bin - the trail-segment identity the
"avoid overlapping tracks" search-time check needs (docs/superpowers/specs/
2026-08-29-avoid-overlapping-tracks-design.md §2). Follows hut-edge-geometry.json's flat-counts-
array manifest shape (build_edge_tiles.py), not hut-edge-payload.json's columnar {dtype,offset}
map - this is a different kind of file (ragged per-row arrays, not fixed-width columns)."""

import argparse
import json
from pathlib import Path

import numpy as np

from lib import binfmt
from lib.pipeline import OSM_DIR
from lib.timing import phase

K_TRAVERSAL = 8


def pack_edge_ids(records: np.ndarray, flat_edge_ids: np.ndarray) -> tuple:
    """flat_edge_ids: hut_edges/edge_ids.npy as-is - already the per-record sorted-ascending runs
    concatenated in record order (build_hub_edges.py's _write_edge_output), so no re-gathering is
    needed here, just a straight-through byte copy."""
    rows = len(records)
    sorted_bytes_arr = flat_edge_ids.astype("i4").tobytes()
    prefix_bytes_arr = records["prefix_ids"].astype("i4").tobytes()
    suffix_bytes_arr = records["suffix_ids"].astype("i4").tobytes()

    payload = sorted_bytes_arr + prefix_bytes_arr + suffix_bytes_arr
    manifest = {
        "rows": rows,
        "k": K_TRAVERSAL,
        "edge_id_count": records["edge_id_count"].tolist(),
        "prefix_count": records["prefix_count"].tolist(),
        "suffix_count": records["suffix_count"].tolist(),
        "sorted_bytes": len(sorted_bytes_arr),
        "prefix_bytes": len(prefix_bytes_arr),
        "suffix_bytes": len(suffix_bytes_arr),
    }
    return payload, manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--edges-dir", default=str(OSM_DIR / "hut_edges"))
    parser.add_argument("--out-bin", default=str(OSM_DIR / "hut-edge-ids.bin"))
    parser.add_argument("--out-manifest", default=str(OSM_DIR / "hut-edge-ids.json"))
    args = parser.parse_args()

    with phase("build_edge_ids.py", "build_edge_ids"):
        records = binfmt.load_array(Path(args.edges_dir) / "records.npy", mmap=False)
        flat_edge_ids = binfmt.load_array(Path(args.edges_dir) / "edge_ids.npy", mmap=False)
        payload, manifest = pack_edge_ids(records, flat_edge_ids)

        out_bin = Path(args.out_bin)
        out_bin.parent.mkdir(parents=True, exist_ok=True)
        out_bin.write_bytes(payload)
        with open(args.out_manifest, "w") as f:
            json.dump(manifest, f)
        print(f"wrote {out_bin} ({len(payload)} bytes) and {args.out_manifest}", flush=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pipeline && pixi run pytest tests/test_build_edge_ids.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/phases/postprocessing/build_edge_ids.py pipeline/tests/test_build_edge_ids.py
git commit -m "feat(pipeline): pack hut-edge-ids.bin/.json client sidecar"
```

---

### Task 7: Wire `build_edge_ids` into the DAG and `copy_public_data`

**Files:**
- Modify: `pipeline/dag/postprocessing.py`
- Modify: `pipeline/dodo.py`
- Test: `pipeline/tests/test_dodo_wiring.py`

**Interfaces:**
- Consumes: `phases/postprocessing/build_edge_ids.py` (Task 6).
- Produces: `task_build_edge_ids` in the doit DAG; `hut-edge-ids.bin`/`.json` copied into
  `huts/public/data/` by `copy_public_data`.

- [ ] **Step 1: Write the failing test**

Add to `pipeline/tests/test_dodo_wiring.py`:

```python
def test_build_edge_ids_task_depends_on_hut_edges_records_and_ids():
    from dag.postprocessing import task_build_edge_ids
    task = task_build_edge_ids()
    file_deps = {str(p) for p in task["file_dep"]}
    assert any("hut_edges/records.npy" in p for p in file_deps)
    assert any("hut_edges/edge_ids.npy" in p for p in file_deps)
    targets = {str(p) for p in task["targets"]}
    assert any(p.endswith("hut-edge-ids.bin") for p in targets)
    assert any(p.endswith("hut-edge-ids.json") for p in targets)


def test_public_files_includes_hut_edge_ids():
    from dodo import PUBLIC_FILES
    assert "hut-edge-ids.bin" in PUBLIC_FILES
    assert "hut-edge-ids.json" in PUBLIC_FILES
```

(Match the exact `file_dep`/`targets` accessor style — string vs. `Path` — that
`test_dodo_wiring.py`'s existing tests already use; adjust the comparison accordingly if it
differs from the sketch above.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pipeline && pixi run pytest tests/test_dodo_wiring.py -k edge_ids -v`
Expected: FAIL — `ImportError: cannot import name 'task_build_edge_ids'` /
`AssertionError` on `PUBLIC_FILES`.

- [ ] **Step 3: Implement**

In `pipeline/dag/postprocessing.py`, add (near `task_build_edge_payload`):

```python
def task_build_edge_ids():
    return pipeline_task(
        "phases/postprocessing/build_edge_ids.py",
        args=[
            f"--edges-dir {OSM_DIR / 'hut_edges'}",
            f"--out-bin {OSM_DIR / 'hut-edge-ids.bin'}",
            f"--out-manifest {OSM_DIR / 'hut-edge-ids.json'}",
        ],
        task_dep=["build_hub_edges"],
        file_dep=[OSM_DIR / "hut_edges" / "records.npy", OSM_DIR / "hut_edges" / "edge_ids.npy"],
        targets=[OSM_DIR / "hut-edge-ids.bin", OSM_DIR / "hut-edge-ids.json"],
    )
```

In `pipeline/dodo.py`, add the two filenames to `PUBLIC_FILES`, next to the `hut-edge-payload.*`
pair:

```python
    "hut-edge-payload.bin",
    "hut-edge-payload.json",
    "hut-edge-ids.bin",
    "hut-edge-ids.json",
    "partner_betriebe.geojson",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pipeline && pixi run pytest tests/test_dodo_wiring.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/dag/postprocessing.py pipeline/dodo.py pipeline/tests/test_dodo_wiring.py
git commit -m "feat(pipeline): wire build_edge_ids task and ship it via copy_public_data"
```

---

### Task 8: Client — `loadHutEdgeIds.ts` loader

**Files:**
- Create: `huts/src/tourSearch/loadHutEdgeIds.ts`
- Modify: `huts/src/tourSearch/types.ts` — add `HutEdgeIdsData`
- Modify: `huts/src/tourSearch/index.ts` — load it alongside the existing two fetches
- Test: Create `huts/src/tourSearch/loadHutEdgeIds.test.ts`

**Interfaces:**
- Consumes: `hut-edge-ids.bin`/`.json` (Task 6/7's output shape).
- Produces: `HutEdgeIdsData { getSortedIds, getPrefixIds, getSuffixIds }`,
  `loadHutEdgeIdsData(baseUrl?): Promise<HutEdgeIdsData>`, `GraphData.hutEdgeIds` — consumed by
  Task 10 (`search.ts`).

- [ ] **Step 1: Write the failing test**

Create `huts/src/tourSearch/loadHutEdgeIds.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { loadHutEdgeIdsData } from './loadHutEdges.js'

function buildFixtureBuffer() {
  // 2 records: record 0 sorted=[10,20,30] prefix=[30,10,20,...-1] suffix=[20,10,30,...-1],
  // record 1 sorted=[40,50] prefix=[40,...-1] suffix=[50,...-1].
  const k = 8
  const sorted = Int32Array.from([10, 20, 30, 40, 50])
  const prefix = new Int32Array(2 * k).fill(-1)
  prefix.set([30, 10, 20], 0)
  prefix.set([40], k)
  const suffix = new Int32Array(2 * k).fill(-1)
  suffix.set([20, 10, 30], 0)
  suffix.set([50], k)

  const buffer = new ArrayBuffer(sorted.byteLength + prefix.byteLength + suffix.byteLength)
  new Int32Array(buffer, 0, sorted.length).set(sorted)
  new Int32Array(buffer, sorted.byteLength, prefix.length).set(prefix)
  new Int32Array(buffer, sorted.byteLength + prefix.byteLength, suffix.length).set(suffix)

  const manifest = {
    rows: 2, k,
    edge_id_count: [3, 2], prefix_count: [3, 1], suffix_count: [3, 1],
    sorted_bytes: sorted.byteLength, prefix_bytes: prefix.byteLength, suffix_bytes: suffix.byteLength,
  }
  return { buffer, manifest }
}

describe('loadHutEdgeIdsData', () => {
  const { buffer, manifest } = buildFixtureBuffer()

  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.endsWith('.json')) return { json: async () => manifest } as Response
      return { arrayBuffer: async () => buffer } as Response
    }))
  })
  afterEach(() => vi.unstubAllGlobals())

  it('slices sorted ids per record via the reconstructed prefix-sum offsets', async () => {
    const data = await loadHutEdgeIdsData('/data')
    expect(Array.from(data.getSortedIds(0))).toEqual([10, 20, 30])
    expect(Array.from(data.getSortedIds(1))).toEqual([40, 50])
  })

  it('slices prefix/suffix ids per record, dropping -1 padding via *_count', async () => {
    const data = await loadHutEdgeIdsData('/data')
    expect(Array.from(data.getPrefixIds(0))).toEqual([30, 10, 20])
    expect(Array.from(data.getSuffixIds(0))).toEqual([20, 10, 30])
    expect(Array.from(data.getPrefixIds(1))).toEqual([40])
    expect(Array.from(data.getSuffixIds(1))).toEqual([50])
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd huts && npm test -- src/tourSearch/loadHutEdgeIds.test.ts`
Expected: FAIL — `loadHutEdgeIdsData` doesn't exist yet (fix the import to `./loadHutEdgeIds.js`
in the next step; it's deliberately wrong above to force a look at the file that doesn't exist
yet — correct it once Step 3 creates the real module).

- [ ] **Step 3: Implement**

Fix the test's import to `import { loadHutEdgeIdsData } from './loadHutEdgeIds.js'`.

In `huts/src/tourSearch/types.ts`, add near the other `*Data` interfaces:

```ts
export interface HutEdgeIdsData {
  getSortedIds(edgeId: number): Int32Array
  getPrefixIds(edgeId: number): Int32Array
  getSuffixIds(edgeId: number): Int32Array
}
```

And add it to `GraphData`:

```ts
export interface GraphData {
  hutEdges: HutEdgesData
  approaches: ApproachesData
  hutEdgeIds: HutEdgeIdsData
}
```

Create `huts/src/tourSearch/loadHutEdgeIds.ts`:

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

/** Loads hut-edge-ids.bin/.json (pipeline/phases/postprocessing/build_edge_ids.py) - the
 *  trail-segment identity behind the "avoid overlapping tracks" check. Fetched wholesale like
 *  hut-edge-payload.bin, not lazily per-leg like geometry: the overlap check runs during search,
 *  before any tour is chosen (spec §2 of docs/superpowers/specs/
 *  2026-08-29-avoid-overlapping-tracks-design.md). edgeId indexes into this exactly like it
 *  indexes into hut-edge-payload.bin (same row order, HutEdgeRecord.edgeId). */
export async function loadHutEdgeIdsData(baseUrl = '/data'): Promise<HutEdgeIdsData> {
  const manifest: HutEdgeIdsManifest = await (await fetch(`${baseUrl}/hut-edge-ids.json`)).json()
  const buffer = await (await fetch(`${baseUrl}/hut-edge-ids.bin`)).arrayBuffer()

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
```

In `huts/src/tourSearch/index.ts`, load it alongside the existing two fetches:

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

- [ ] **Step 4: Run test to verify it passes**

Run: `cd huts && npm test -- src/tourSearch/loadHutEdgeIds.test.ts`
Expected: PASS

Also run the typecheck, since `GraphData` gained a required field that every existing literal
`GraphData` fixture in the test suite must now satisfy (this will surface exactly which files
Task 9 needs to touch):

Run: `cd huts && npm run typecheck`
Expected: FAIL, listing every file constructing a `GraphData` literal without `hutEdgeIds` — note
them down; Task 9 fixes `search.test.ts`'s fixtures, but check the typecheck output for any other
file this plan didn't anticipate (e.g. `TourSearchPage.test.tsx`) and add a minimal
`hutEdgeIds` stub there too before moving on.

- [ ] **Step 5: Commit**

```bash
git add huts/src/tourSearch/loadHutEdgeIds.ts huts/src/tourSearch/loadHutEdgeIds.test.ts \
        huts/src/tourSearch/types.ts huts/src/tourSearch/index.ts
git commit -m "feat(huts): load hut-edge-ids.bin/.json alongside the hut-edge payload"
```

---

### Task 9: Client — `overlap.ts` pure helpers

**Files:**
- Create: `huts/src/tourSearch/overlap.ts`
- Create: `huts/src/tourSearch/overlap.test.ts`

**Interfaces:**
- Produces: `trimSharedHubIds(prevNear, newNear): Set<number>`,
  `hasOverlap(idsNew, exempt, usedIds): boolean` — consumed by Task 11 (`search.ts`).

- [ ] **Step 1: Write the failing test**

Create `huts/src/tourSearch/overlap.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { trimSharedHubIds, hasOverlap } from './overlap.js'

describe('trimSharedHubIds', () => {
  it('exempts the matching run walking outward from the shared hub', () => {
    const exempt = trimSharedHubIds([100, 200, 300], [100, 200, 999])
    expect(exempt).toEqual(new Set([100, 200]))
  })

  it('stops at the first mismatch, even if a later id matches too', () => {
    const exempt = trimSharedHubIds([100, 999, 300], [100, 200, 300])
    expect(exempt).toEqual(new Set([100]))
  })

  it('is empty when the two legs share no run out of the hub at all', () => {
    const exempt = trimSharedHubIds([100], [200])
    expect(exempt).toEqual(new Set())
  })

  it('handles arrays of different lengths', () => {
    const exempt = trimSharedHubIds([100, 200], [100])
    expect(exempt).toEqual(new Set([100]))
  })
})

describe('hasOverlap', () => {
  it('is true when a non-exempt id is already used', () => {
    expect(hasOverlap([100, 200], new Set(), new Set([200, 300]))).toBe(true)
  })

  it('is false when every used id is exempted', () => {
    expect(hasOverlap([100, 200], new Set([200]), new Set([200, 300]))).toBe(false)
  })

  it('is false when the id sets are genuinely disjoint', () => {
    expect(hasOverlap([100, 200], new Set(), new Set([300, 400]))).toBe(false)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd huts && npm test -- src/tourSearch/overlap.test.ts`
Expected: FAIL — `Cannot find module './overlap.js'`

- [ ] **Step 3: Implement**

Create `huts/src/tourSearch/overlap.ts`:

```ts
/** Given the shared hut's outward-ordered base-edge-id runs for two adjacent legs (spec §4 of
 *  docs/superpowers/specs/2026-08-29-avoid-overlapping-tracks-design.md), returns the ids exempt
 *  from the overlap check because they're the unavoidable stretch of trail leaving the shared
 *  hut. Walks both arrays from the hut outward and keeps the matching run; a mismatch anywhere
 *  stops the walk immediately - only a CONTIGUOUS run out of the hut is the innocent case, a
 *  later coincidental match further out is a real (excludable) overlap. */
export function trimSharedHubIds(
  prevNear: ArrayLike<number>,
  newNear: ArrayLike<number>,
): Set<number> {
  const exempt = new Set<number>()
  const n = Math.min(prevNear.length, newNear.length)
  for (let i = 0; i < n; i++) {
    if (prevNear[i] !== newNear[i]) break
    exempt.add(prevNear[i])
  }
  return exempt
}

/** True if any id in idsNew, other than the exempted shared-hub run, is already in usedIds. */
export function hasOverlap(
  idsNew: ArrayLike<number>,
  exempt: Set<number>,
  usedIds: Set<number>,
): boolean {
  for (let i = 0; i < idsNew.length; i++) {
    const id = idsNew[i]
    if (exempt.has(id)) continue
    if (usedIds.has(id)) return true
  }
  return false
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd huts && npm test -- src/tourSearch/overlap.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add huts/src/tourSearch/overlap.ts huts/src/tourSearch/overlap.test.ts
git commit -m "feat(huts): add shared-hub-run trimming and overlap-set helpers"
```

---

### Task 10: Client — `KillCounters.trackOverlap`

**Files:**
- Modify: `huts/src/tourSearch/types.ts`
- Modify: `huts/src/tourSearch/legFilters.ts`

**Interfaces:**
- Produces: `KillCounters.trackOverlap: number`, `createKillCounters()` initializing it to 0 —
  consumed by Task 11.

- [ ] **Step 1: Write the failing test**

`legFilters.ts` presumably already has a test file (`legFilters.test.ts`) covering
`createKillCounters`; if so add there, otherwise inline this check into Task 11's tests (the
expansion-loop test already asserts `killCounters.trackOverlap` is incremented, which will fail to
compile until this field exists — that IS this task's red bar). Confirm which applies:

Run: `ls huts/src/tourSearch/legFilters.test.ts 2>/dev/null && echo exists || echo none`

If it exists, add:

```ts
it('createKillCounters starts trackOverlap at 0', () => {
  expect(createKillCounters().trackOverlap).toBe(0)
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd huts && npm run typecheck`
Expected: FAIL — `Property 'trackOverlap' does not exist on type 'KillCounters'` (from the test
above, or deferred to Task 11's `search.ts` change if no `legFilters.test.ts` exists yet).

- [ ] **Step 3: Implement**

In `huts/src/tourSearch/types.ts`:

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
}
```

In `huts/src/tourSearch/legFilters.ts`:

```ts
export function createKillCounters(): KillCounters {
  return {
    maxLegTime: 0, minLegTime: 0, legAscentCap: 0, maxEleM: 0, viaFerrata: 0, revisit: 0,
    hutFiltered: 0, trackOverlap: 0,
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd huts && npm run typecheck && npm test -- src/tourSearch/legFilters.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add huts/src/tourSearch/types.ts huts/src/tourSearch/legFilters.ts
git commit -m "feat(huts): add trackOverlap kill counter"
```

---

### Task 11: Client — overlap check in `search.ts`'s expansion loop

**Files:**
- Modify: `huts/src/tourSearch/search.ts`
- Modify: `huts/src/tourSearch/search.test.ts` — new `describe` block + fix existing `graphData`
  fixture(s) to satisfy the now-required `GraphData.hutEdgeIds`

**Interfaces:**
- Consumes: `graphData.hutEdgeIds` (Task 8), `trimSharedHubIds`/`hasOverlap` (Task 9),
  `KillCounters.trackOverlap` (Task 10).
- Produces: chains that reuse a physical trail segment (except the shared-hub exemption) are
  excluded from `searchChains`'s output.

- [ ] **Step 1: Fix the existing fixture so the suite still compiles**

`search.test.ts`'s module-level `graphData: GraphData` (and the `loopGraphData` override further
down) now need a `hutEdgeIds` stub, since `GraphData` gained a required field in Task 8. Add a
shared stub that never reports an overlap, at the top of `search.test.ts`:

```ts
function emptyHutEdgeIdsStub(): GraphData['hutEdgeIds'] {
  return {
    getSortedIds: () => new Int32Array(0),
    getPrefixIds: () => new Int32Array(0),
    getSuffixIds: () => new Int32Array(0),
  }
}
```

And add `hutEdgeIds: emptyHutEdgeIdsStub(),` to the module-level `graphData` object literal
(alongside `hutEdges`/`approaches`).

Run: `cd huts && npm run typecheck`
Expected: PASS again (this step alone should be enough to fix the break Task 8's typecheck run
surfaced for this file — confirm no other `GraphData` literal remains broken).

- [ ] **Step 2: Write the failing test**

Add to `search.test.ts`, after the existing `describe('searchChains (car)', ...)` block:

```ts
describe('searchChains (overlap avoidance)', () => {
  const overlapEdge = (fromIndex: number, toIndex: number, edgeId: number) => ({
    fromIndex, toIndex, variant: 0, distanceM: 5000, ascentM: 200, descentM: 200, maxEleM: 2000,
    sacRank: 1, viaFerrata: false, roadM: 0, ungradedM: 0, inferredM: 0, snapM: 0, edgeId,
  })

  // Chain 0 -[e01]-> 1 -[e12]-> 2 -[e23]-> 3. e01 and e12 share base-edge id 100, but ONLY in the
  // run leaving their common hut 1 - spec §4's exemption should keep a chain using just those two.
  // e01 and e23 independently share id 200, with NO common hut between them - spec §4's hard rule
  // should exclude any chain using both.
  const SORTED: Record<number, number[]> = { 1: [100, 200], 2: [100, 300], 3: [200, 400] }
  const PREFIX: Record<number, number[]> = { 1: [200], 2: [100], 3: [400] }  // near from_id
  const SUFFIX: Record<number, number[]> = { 1: [100], 2: [300], 3: [200] }  // near to_id

  const overlapGraphData: GraphData = {
    hutEdges: {
      hutIds: ['A', 'B', 'C', 'D'],
      variantNames: { 0: 'FAST_ANY' },
      records: [overlapEdge(0, 1, 1), overlapEdge(1, 2, 2), overlapEdge(2, 3, 3)],
    },
    approaches: {
      records: [
        { hutIndex: 0, startId: 100, sourceType: 1, accessUnknown: false, distanceM: 2000, ascentM: 100, descentM: 50, access: null, edgeId: 9000 },
      ],
      reverseIndex: {
        hut_to_starts: {
          2: [{ hut_id: 2, start_id: 300, source_type: 1, variant: 0, distance_m: 2000, ascent_m: 50, descent_m: 100, edge_id: 9002 }],
          3: [{ hut_id: 3, start_id: 200, source_type: 1, variant: 0, distance_m: 2000, ascent_m: 50, descent_m: 100, edge_id: 9001 }],
        },
        start_to_huts: {},
      },
    },
    hutEdgeIds: {
      getSortedIds: (edgeId) => Int32Array.from(SORTED[edgeId] ?? []),
      getPrefixIds: (edgeId) => Int32Array.from(PREFIX[edgeId] ?? []),
      getSuffixIds: (edgeId) => Int32Array.from(SUFFIX[edgeId] ?? []),
    },
  }

  it('excludes a chain whose non-adjacent legs share a base-edge id', () => {
    const { chains, killCounters } = searchChains(
      { mode: 'transit', legCountMin: 2, legCountMax: 6, ...generousConstraints },
      overlapGraphData,
    )
    expect(chains.some((c) => c.huts.length === 4)).toBe(false)
    expect(killCounters.trackOverlap).toBeGreaterThan(0)
  })

  it('keeps a chain whose adjacent legs only share the run out of their common hut', () => {
    const { chains } = searchChains(
      { mode: 'transit', legCountMin: 2, legCountMax: 6, ...generousConstraints },
      overlapGraphData,
    )
    const kept = chains.find((c) => c.huts.length === 3 && c.exitStartId === 300)
    expect(kept).toBeDefined()
    expect(kept!.huts).toEqual([0, 1, 2])
  })
})
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd huts && npm test -- src/tourSearch/search.test.ts -t "overlap avoidance"`
Expected: FAIL — the first test fails because nothing yet excludes the 4-hut chain, and
`killCounters.trackOverlap` stays 0.

- [ ] **Step 4: Implement**

In `huts/src/tourSearch/search.ts`, add the import:

```ts
import { trimSharedHubIds, hasOverlap } from './overlap.js'
```

Extend `State`:

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

Add a shared empty-set constant right below the `State` interface (never mutated — only ever read
or spread into a fresh `Set` — so it's safe to share across every seed state):

```ts
  const EMPTY_EDGE_IDS: Set<number> = new Set()
```

In the seed loop, extend the constructed `state`:

```ts
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

In the expansion loop, insert the overlap check right after the existing `legPasses` check
(after `if (!legPasses(leg, constraints, killCounters)) continue`) and extend `next`:

```ts
        for (const leg of legs) {
          const h2 = leg.toIndex
          if (allowedHutIndices && !allowedHutIndices.has(h2)) { killCounters.hutFiltered++; continue }
          if (s.path.includes(h2)) { killCounters.revisit++; continue }
          if (!legPasses(leg, constraints, killCounters)) continue

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

          const nextUsedEdgeIds = new Set(s.usedEdgeIds)
          for (let i = 0; i < sortedIdsNew.length; i++) nextUsedEdgeIds.add(sortedIdsNew[i])

          const nextVisitedKey = s.visitedKey | (1n << BigInt(h2))
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
          if (!nextLayer.has(h2)) nextLayer.set(h2, new Map())
          insertDominant(nextLayer.get(h2)!, `${next.startId}|${nextVisitedKey}`, next)
        }
```

This does **not** touch the dominance key (`${next.startId}|${nextVisitedKey}`, unchanged) or
`collectFinished` (approach/exit legs stay untouched, out of scope per spec).

- [ ] **Step 5: Run test to verify it passes**

Run: `cd huts && npm test -- src/tourSearch/search.test.ts`
Expected: PASS (whole file — confirms no regression in the pre-existing dominance/revisit/mode
tests either, since `EMPTY_EDGE_IDS` makes every unrelated fixture's `getSortedIds` return `[]`
and the check is a no-op there).

Run the whole suite once more for good measure:

Run: `cd huts && npm test && npm run typecheck && npm run lint`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add huts/src/tourSearch/search.ts huts/src/tourSearch/search.test.ts
git commit -m "feat(huts): exclude chains that re-cross a trail segment during search expansion"
```

---

### Task 12: Regenerate real pipeline data and extend the smoke test (requires user confirmation)

**This task must not be run automatically.** Per root `CLAUDE.md`: never run any `pipeline/` doit
task without first asking the user and getting explicit confirmation, even one that looks cheap —
a freshness check can cascade. Tasks 1–11 are fully verifiable without this step (synthetic
fixtures only); do not skip straight here.

**Files:**
- Modify: `huts/src/tourSearch/realData.smoke.test.ts`

**Interfaces:**
- Consumes: real `huts/public/data/hut-edge-ids.bin`/`.json`, produced by running the pipeline.

- [ ] **Step 1: Ask the user for explicit confirmation before running any `doit` task**

State plainly: this reruns `build_hub_edges` (and downstream `build_edge_ids`,
`copy_public_data`) against real AT+Bayern data. Because only `record_schema_version` changed
(Task 3/4), this should NOT trigger the ~4h `build_base_graph`/`snap_hubs`/
`gather_route_subgraphs` rebuild — but confirm that assumption by checking `doit list --status`'s
output before running anything, and show the user what it reports before proceeding.

Do not proceed past this step without the user's explicit go-ahead.

- [ ] **Step 2: Run the pipeline (only after confirmation)**

Run: `cd pipeline && pixi run doit list --status` — inspect and share which tasks doit reports as
stale; confirm it's only `build_hub_edges`, `build_edge_ids`, and `copy_public_data` before
continuing.

Run: `cd pipeline && pixi run doit build_edge_ids copy_public_data`

Confirm `huts/public/data/hut-edge-ids.bin` and `.json` now exist:

Run: `ls -la huts/public/data/hut-edge-ids.*`

- [ ] **Step 3: Write the failing/extending test**

Find `realData.smoke.test.ts`'s existing local `loadHutEdgesFromDisk()`/`loadApproachesFromDisk()`
helpers (they reimplement the columnar `readColumns` decode in Node, bypassing `fetch`, per that
file's existing pattern) and add a sibling `loadHutEdgeIdsFromDisk()` that mirrors
`loadHutEdgeIds.ts`'s parsing logic but reads from `fs.readFileSync` against
`huts/public/data/hut-edge-ids.{json,bin}` instead of `fetch`. Wire its result into the
`GraphData` object the file already builds for its `findTours` calls (adding `hutEdgeIds` to that
literal — same fix pattern as Task 11's `search.test.ts`, just against real data now).

Add:

```ts
it('finds tours whose legs pass the overlap check where the shipped payload has base-edge data', () => {
  const graphData = /* ...as already assembled in this file, now including hutEdgeIds... */
  const { chains, killCounters } = findTours(
    { mode: 'transit', legCountMin: 2, legCountMax: 4, maxLegTimeH: 8, allowViaFerrata: true },
    graphData,
  )
  expect(chains.length).toBeGreaterThan(0)
  console.log(`overlap-avoidance smoke: ${chains.length} chains, trackOverlap kills=${killCounters.trackOverlap}`)
})
```

- [ ] **Step 4: Run once, unasserted on the exact count, to capture the real baseline**

Run: `cd huts && npm test -- src/tourSearch/realData.smoke.test.ts 2>&1 | grep "overlap-avoidance smoke"`

Record the printed chain count `N`.

- [ ] **Step 5: Turn the observation into a banded regression guard**

Per spec "Testing": assert the chain count stays inside an expected band, so a future rule change
that quietly empties the result list fails loudly. Replace the unasserted `console.log` line with:

```ts
  // Baseline captured <today's date> against the shipped payload: N chains. A future change to
  // the overlap rule (or the underlying data) is expected to shift this somewhat - the band is a
  // sanity floor/ceiling, not an exact-match assertion.
  expect(chains.length).toBeGreaterThan(Math.floor(N * 0.5))
  expect(chains.length).toBeLessThan(Math.ceil(N * 1.5))
```

(substituting the actual captured `N` for the literal, and today's actual date in the comment)

- [ ] **Step 6: Run test to verify it passes**

Run: `cd huts && npm test -- src/tourSearch/realData.smoke.test.ts`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add huts/src/tourSearch/realData.smoke.test.ts huts/public/data/hut-edge-ids.bin \
        huts/public/data/hut-edge-ids.json
git commit -m "test(huts): extend real-payload smoke test with overlap-avoidance baseline"
```

Note: whether `huts/public/data/*` is tracked in git at all should match how the sibling
`hut-edge-payload.bin`/`.json` are currently handled — check `git status`/`.gitignore` before this
`git add` and follow the existing convention rather than introducing a new one.

---

## Self-Review Notes

- **Spec §1 (pipeline identity)** → Tasks 1, 2, 3, 5.
- **Spec §1's synthetic-split disambiguation** → Task 1's core test.
- **Spec §1's schema-version split** → Tasks 3, 4.
- **Spec §2 (delivery, manifest shape, unconditional fetch)** → Tasks 6, 7, 8.
- **Spec §3 (expansion-time check, not post-filter; dominance untouched; approach/exit skipped;
  `trackOverlap` counter)** → Tasks 10, 11.
- **Spec §4 (shared-hub exemption, k=8 traversal ids)** → Tasks 5, 6, 9, 11.
- **Testing section's four bullets** → pipeline synthetic-graph split test (Task 1), round-trip
  test (Task 6, extended by Task 5's write test), `search.test.ts` overlap cases (Task 11), smoke
  test band (Task 12).
- **Out-of-scope items** (approach/exit overlap, UI toggle, exact search) — deliberately not
  implemented anywhere in this plan; Task 11's check only runs in the expansion loop, which only
  ever handles hut-hut legs.
