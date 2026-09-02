# Hub-edge scaling (A/B/C1/C2/D3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Do NOT use
> superpowers:subagent-driven-development or any worktree/subagent-spinning approach for this
> plan** — the repo's root `CLAUDE.md` forbids git worktrees and subagent-driven execution here.
> Execute every task directly, in-session, on the current checkout/branch.

**Goal:** Make `build_hub_edges` scale to the 4.9×-larger access-point set (76,669 points) by
inverting the routing direction so Dijkstra count depends on hut count (846) instead of access
count, splitting the expensive "route + materialize geometry" step into a cheap distance/time pass
followed by geometry-only-for-selected-pairs, fixing the `hub_snap` node-search bottleneck the
inversion promotes to the top line, and fixing a real longitude bug in the start-point prefilter.

**Architecture:** `build_hub_edges.py`'s per-cell routing loop is rewritten so **huts are the
Dijkstra sources** and every candidate hub (huts + access points) in the padded cell is a target in
one batched `distances()` call — cutting Dijkstra count ~90×. The same rewrite splits what used to
be one combined `hut_edges + start_edges` output into `hut_edges/` (unchanged, full geometry) and a
new compact `access_distances.npy` (distance/time scalars only, no geometry, no path walk). A new
`select_approach_pairs.py` task picks the top-20-per-(hut,source-type) candidates globally plus the
loop-closure reverse index, and a new `build_access_edges.py` task re-routes and materializes
geometry for *only* that selected pair set, writing the final `start_edges/`. `hub_snap.py`'s
node-nearest search gets a cKDTree (currently a full linear scan, and about to become the
long-pole once the routing pass above stops dominating). `filter_start_points.py`'s longitude bug
(and an unrelated query-batching cleanup) land last, since fixing it grows the kept set further and
must not land before the scaling fixes that make the larger set affordable.

**Tech Stack:** Python (pixi env `alpen-osm`), numpy structured arrays (`lib/binfmt.py`), igraph
(`python-igraph`), scipy `cKDTree`, pytest (`pixi run pytest` from `pipeline/`).

**Spec:** `docs/superpowers/specs/2026-09-02-hub-edge-scaling-design.md`

## Global Constraints

- Never run any `doit` task (individually or the full DAG) as part of this plan — every task here
  is validated by `pixi run pytest` against small synthetic fixtures, exactly like the existing
  tests in `pipeline/tests/`. Actually rerunning `build_hub_edges`/`snap_hubs`/etc. against real
  `data/` requires explicit user confirmation per the root `CLAUDE.md`, and is out of scope for
  this plan.
- `RECORD_DTYPE`, the `hut_edges/`/`start_edges/` directory layout, the access→hut storage
  convention, `approaches.bin`/`approaches.json`'s shape, the variant grid, the speed model, and
  `maxEdgeKm` are all **unchanged** (spec Non-goals). Only how records get computed and how many
  get full geometry materialized changes.
- No change to `huts/` source in this plan (spec Non-goals) — `#graph`'s start-edge layer shrinking
  from "every access edge" to "approach-relevant access edges only" is an accepted, deliberate
  consequence of §B, not something to compensate for client-side.
- `select_approaches`' reserved-type-slot overwrite bug (`docs/backlog/approach-reserved-type-slot-
  overwrite.md`) is preserved verbatim — do not fix it as a drive-by in this plan.
- The scalars-only path walk that would make B4's selection exact
  (`docs/backlog/exact-approach-selection-scalars-only-path-walk.md`) is explicitly out of scope —
  ship the over-selection (top-20) instead.
- C3 (station clustering) and C4 (a separate `maxApproachKm` cap) are **not implemented** by this
  plan — C3 has two open placement/id-semantics questions the spec leaves unresolved, and C4 is
  rejected outright (spec §C4).

---

## File Structure

| File | Change |
| --- | --- |
| `pipeline/phases/graph_building/build_hub_edges.py` | Core rewrite: A4 timer step, A1–A3 direction inversion + record reorientation, A5 scheduling fix, B3 split output (`hut_edges/` unchanged, new `access_distances.npy`) |
| `pipeline/lib/hub_snap.py` | D3: cKDTree-backed node-nearest search |
| `pipeline/lib/binfmt.py` | New `ACCESS_DISTANCE_DTYPE`, new `ACCESS_DISTANCE_SCHEMA_VERSION` |
| `pipeline/lib/edge_output.py` | New `write_access_distances()` |
| `pipeline/phases/postprocessing/select_approach_pairs.py` | **New file** — B2/B4: global top-K + reverse-index closure over `access_distances.npy` |
| `pipeline/phases/graph_building/build_access_edges.py` | **New file** — B5: re-routes and materializes geometry for the selected pair set only, writes `start_edges/` |
| `pipeline/dag/graph_building.py` | Rewire `task_build_hub_edges`'s targets, add `task_build_access_edges` |
| `pipeline/dag/postprocessing.py` | Add `task_select_approach_pairs`; repoint `task_build_start_edge_tiles`/`task_build_approach_table` file/task deps at `build_access_edges` |
| `pipeline/dag/elevation.py` | Repoint `task_build_profiles`'s `start_edges` file_dep/task_dep at `build_access_edges` |
| `pipeline/phases/preprocessing/filter_start_points.py` | C1 longitude fix, C2 batched KD-tree query |
| `pipeline/tests/test_build_hub_edges.py` | Updated for the new `compute_hub_edges_for_cell` return shape and direction |
| `pipeline/tests/test_hub_snap.py` | New cKDTree-caching test |
| `pipeline/tests/test_edge_output.py` | New `write_access_distances` tests |
| `pipeline/tests/test_select_approach_pairs.py` | **New file** |
| `pipeline/tests/test_build_access_edges.py` | **New file** |
| `pipeline/tests/test_filter_start_points.py` | New longitude-bug regression test |

## Interfaces Carried Across Tasks

- `compute_hub_edges_for_cell(subgraph, core_hubs, all_hubs, max_edge_km, snaps, variants, timer=None) -> (hut_records: list, access_rows: list)` — **return shape changes** from a flat `list` to a `(hut_records, access_rows)` tuple in Task 3. `hut_records` keeps today's dict shape (`from_id/from_type/to_id/to_type/variant/distance_m/road_m/ascent_m/descent_m/max_ele_m/ungraded_m/inferred_m/snap_m/sac_rank/via_ferrata/geometry/base_edge_ids`). `access_rows` is new: `{"hut_id": int, "start_id": int, "start_type": int, "variant": int, "distance_m": float, "time_s": float}`.
- `binfmt.ACCESS_DISTANCE_DTYPE` (Task 3): `[("hut_id","u2"), ("start_id","i8"), ("start_type","u1"), ("variant","u1"), ("distance_m","f4"), ("time_s","f4")]`.
- `edge_output.write_access_distances(rows: list, path: Path) -> None` (Task 3): packs `access_rows` dicts into one `ACCESS_DISTANCE_DTYPE` array at `path`.
- `select_approach_pairs.select_pairs(access_distances: np.ndarray, k: int) -> np.ndarray` (Task 4): returns a structured array of the same `ACCESS_DISTANCE_DTYPE` shape restricted to the union of (a) top-k-by-`time_s` per `(hut_id, start_type)` group and (b) every row whose `start_id` appears in (a) — i.e. every variant of a selected start point, not just the ranking one. Consumed by Task 5.
- `build_access_edges.py`'s `__main__` reads Task 4's output and calls (unchanged) `compute_hub_edges_for_cell`-adjacent routing to write `start_edges/records.npy` + `geometry.npy` via the existing `edge_output.write_edge_records`.

---

## Task 1: Instrument `build_base_igraph_arrays` cost (A4 prerequisite)

Adds a `StepTimer` step around the per-cell igraph-array build so its cost is visible in
`data/timings.jsonl` once A's inversion increases per-cell candidate counts (spec A4: "the
igraph/array-building term becomes a leading cost rather than a rounding error" after A). This is
pure instrumentation — no behavior change — and is a correctness-neutral first commit that later
tasks (Task 3) build on.

**Files:**
- Modify: `pipeline/phases/graph_building/build_hub_edges.py:143` (`compute_hub_edges_for_cell`)
- Test: `pipeline/tests/test_build_hub_edges.py:393-411` (`test_compute_hub_edges_for_cell_fills_the_step_timer`)

**Interfaces:**
- Consumes: `lib.timing.StepTimer` (`pipeline/lib/timing.py`), already imported in
  `build_hub_edges.py`.
- Produces: a new `"build_base_arrays"` key in every `StepTimer.seconds`/`StepTimer.calls` this
  function fills — read by `test_compute_hub_edges_for_cell_fills_the_step_timer` and, later, by
  `pipeline/CLAUDE.md`'s step-timing table (documentation update in Task 3's commit, not here).

- [ ] **Step 1: Write the failing test**

Extend the existing step-timer test in `pipeline/tests/test_build_hub_edges.py` to assert the new
step key is present:

```python
def test_compute_hub_edges_for_cell_fills_the_step_timer():
    # The per-step split is what tells a long run apart: snapping scales with hub count, the
    # distance/path steps with subgraph size x pair count, and (A4) igraph-array construction
    # scales with candidate count per cell - each needs its own column, not one wall-clock number.
    subgraph = _line_subgraph()
    core_hubs = [
        {"id": 1, "type": binfmt.TYPE_HUT, "lon": 0.0001, "lat": 0.0},
        {"id": 2, "type": binfmt.TYPE_HUT, "lon": 0.0089, "lat": 0.0},
    ]
    timer = StepTimer()
    snaps = snap_hubs_for_cell(subgraph, core_hubs, core_hubs, max_snap_m=50.0)
    compute_hub_edges_for_cell(
        subgraph, core_hubs, core_hubs, max_edge_km=5.0, snaps=snaps,
        variants=FAST_ANY_ONLY, timer=timer,
    )
    assert set(timer.seconds) == {"snap", "build_base_arrays", "build_igraph", "distances", "paths"}
    assert timer.calls["snap"] == 1          # one timed pass over the whole snap loop
    assert timer.calls["build_base_arrays"] == 1   # built ONCE per cell, not once per variant
    assert timer.calls["snap_hubs"] == 2     # both huts snapped onto the line
    assert timer.calls["distances"] == 2     # one distance query per core hub
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pipeline && pixi run pytest tests/test_build_hub_edges.py::test_compute_hub_edges_for_cell_fills_the_step_timer -v`
Expected: FAIL — `AssertionError` on the `set(timer.seconds)` comparison (missing `"build_base_arrays"`).

- [ ] **Step 3: Wrap the array build in a timer step**

In `pipeline/phases/graph_building/build_hub_edges.py`, change:

```python
    base_arrays = build_base_igraph_arrays(subgraph, snaps)
```

to:

```python
    with timer.step("build_base_arrays"):
        base_arrays = build_base_igraph_arrays(subgraph, snaps)
```

(this is the line at `build_hub_edges.py:143`, inside `compute_hub_edges_for_cell`, right after the
`# Built once for this cell+snap set ...` comment block — leave that comment as-is).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pipeline && pixi run pytest tests/test_build_hub_edges.py::test_compute_hub_edges_for_cell_fills_the_step_timer -v`
Expected: PASS

- [ ] **Step 5: Run the full pipeline test suite to check for regressions**

Run: `cd pipeline && pixi run pytest -v`
Expected: PASS (no other test asserts the exact `set(timer.seconds)` for this function).

- [ ] **Step 6: Commit**

```bash
cd pipeline
git add phases/graph_building/build_hub_edges.py tests/test_build_hub_edges.py
git commit -m "$(cat <<'EOF'
perf(pipeline): time build_base_igraph_arrays as its own StepTimer step

Prerequisite for evaluating the hub-edge routing direction inversion (spec
2026-09-02-hub-edge-scaling-design.md, A4): the array-build cost currently lands in the cell's
wall clock but no timer column, so it can't be told apart from build_igraph/distances/paths once
A shrinks distances to a fraction of the run.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_017cYyJEYLeD7yGBdMP27QrV
EOF
)"
```

---

## Task 2: `hub_snap` node-nearest search via cKDTree (D3)

Replaces `snap_hub_to_subgraph`'s full `_haversine_m_vec` linear scan over every node in the
subgraph (O(hubs × nodes)) with a cKDTree query, cached on the subgraph exactly the way
`_build_edge_spatial_index`/`_candidate_edges_near` already cache the edge index. This is the fix
spec §D calls out as "immediately the top line" once A/B land (846s wall / 8,722 CPU-s at the
current hub count already, and linear in hub count).

**Files:**
- Modify: `pipeline/lib/hub_snap.py`
- Test: `pipeline/tests/test_hub_snap.py`, `pipeline/tests/test_build_hub_edges.py` (existing snap
  tests must still pass with the projected-metres distance)

**Interfaces:**
- Consumes: `scipy.spatial.cKDTree` (already imported in `hub_snap.py` for the edge index),
  `lib.grid.KM_PER_DEG_LAT`, `_project_m` (both already in `hub_snap.py`).
- Produces: `_nearest_node(subgraph, hub_lon, hub_lat) -> (local_node_index: int|None, distance_m: float)`,
  a new private helper `snap_hub_to_subgraph` calls instead of the inline `_haversine_m_vec` scan.
  Cached on `subgraph._node_spatial_index` the same way `subgraph._edge_spatial_index` already is.

- [ ] **Step 1: Write the failing test — KD-tree is built once and cached**

Add to `pipeline/tests/test_hub_snap.py`:

```python
def test_node_index_is_built_once_and_cached(monkeypatch):
    # D3: the KD-tree build (O(nodes log nodes)) must happen once per subgraph, not once per hub -
    # same caching contract _build_edge_spatial_index already has for the edge index.
    subgraph = _line_subgraph([100, 101], edge_id=7)
    calls = []
    real_build = hub_snap._build_node_spatial_index

    def _counting_build(sg):
        calls.append(1)
        return real_build(sg)

    monkeypatch.setattr(hub_snap, "_build_node_spatial_index", _counting_build)

    hub_snap.snap_hub_to_subgraph(subgraph, hub_lon=0.0001, hub_lat=0.0, max_snap_m=50.0)
    hub_snap.snap_hub_to_subgraph(subgraph, hub_lon=0.0002, hub_lat=0.0, max_snap_m=50.0)

    assert len(calls) == 1


def test_nearest_node_matches_the_closest_node_by_projected_distance():
    subgraph = _line_subgraph([100, 101], edge_id=7)
    idx, dist_m = hub_snap._nearest_node(subgraph, hub_lon=0.0001, hub_lat=0.0)
    assert idx == 0
    assert dist_m == pytest.approx(11.1, rel=0.05)  # 0.0001 deg lon at the equator


def test_nearest_node_on_an_empty_subgraph_reports_no_candidate():
    empty = LocalSubgraph(
        global_node_ids=np.zeros(0, dtype=np.int64),
        local_nodes=np.zeros(0, dtype=binfmt.NODE_DTYPE),
        local_edges=np.zeros(0, dtype=binfmt.EDGE_DTYPE),
        interior=np.zeros(0, dtype=binfmt.COORD_DTYPE),
        local_node_ele=np.zeros(0, dtype=np.float32),
        interior_ele=np.zeros(0, dtype=np.float32),
    )
    idx, dist_m = hub_snap._nearest_node(empty, hub_lon=0.0, hub_lat=0.0)
    assert idx is None
    assert dist_m == float("inf")
```

Add `import pytest` at the top of `pipeline/tests/test_hub_snap.py` (not currently imported) —
insert after the existing `import numpy as np` line.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd pipeline && pixi run pytest tests/test_hub_snap.py -k "node_index or nearest_node" -v`
Expected: FAIL — `AttributeError: module 'lib.hub_snap' has no attribute '_build_node_spatial_index'`
(and `_nearest_node`).

- [ ] **Step 3: Add the cached KD-tree helpers**

In `pipeline/lib/hub_snap.py`, add right after `_build_edge_spatial_index` (before
`_candidate_edges_near`):

```python
def _build_node_spatial_index(subgraph: LocalSubgraph):
    """cKDTree over every LOCAL node's projected (x, y) position, cached on the subgraph exactly
    the way _build_edge_spatial_index's edge index already is (D3: this used to be a full
    _haversine_m_vec scan over every node, once per hub - O(hubs x nodes) on a subgraph that can
    hold hundreds of thousands of nodes after A widens the candidate set)."""
    if len(subgraph.local_nodes) == 0:
        return None
    ref_lat = float(np.mean(subgraph.local_nodes["lat"]))
    km_per_deg_lng = KM_PER_DEG_LAT * math.cos(math.radians(ref_lat))
    xs, ys = _project_m(subgraph.local_nodes["lon"], subgraph.local_nodes["lat"], km_per_deg_lng)
    tree = cKDTree(np.column_stack([xs, ys]))
    return tree, km_per_deg_lng


def _nearest_node(subgraph: LocalSubgraph, hub_lon: float, hub_lat: float) -> tuple:
    """(local_node_index, distance_m) for the nearest existing graph node to (hub_lon, hub_lat),
    via the cached cKDTree above. distance_m is in the same local equirectangular-projected-metres
    space _build_edge_spatial_index already uses for its own candidate search, not exact
    haversine - close enough at cell scale (tens of km), and the tie-break between two nodes
    equidistant to within projection error can differ from the old exact-haversine argmin (D3);
    irrelevant to output quality. Returns (None, inf) when the subgraph has no nodes at all."""
    index = getattr(subgraph, "_node_spatial_index", "unset")
    if index == "unset":
        index = _build_node_spatial_index(subgraph)
        subgraph._node_spatial_index = index
    if index is None:
        return None, float("inf")
    tree, km_per_deg_lng = index
    x, y = _project_m(hub_lon, hub_lat, km_per_deg_lng)
    dist, idx = tree.query([x, y], k=1)
    return int(idx), float(dist)
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `cd pipeline && pixi run pytest tests/test_hub_snap.py -k "node_index or nearest_node" -v`
Expected: PASS

- [ ] **Step 5: Wire `snap_hub_to_subgraph` to use the KD-tree instead of the linear scan**

In `pipeline/lib/hub_snap.py`, replace the node-search block inside `snap_hub_to_subgraph`
(currently lines 163–213):

```python
    no_trail_data = len(subgraph.local_nodes) == 0 and len(subgraph.local_edges) == 0
    node_dists = None
    # An existing graph node within range always wins over a mid-chain split, even if some
    # point along an incident edge is geometrically a hair closer - a hub sitting a few meters
    # off a real node is meant to snap to that node, not spawn a near-duplicate virtual vertex
    # right next to it.
    if len(subgraph.local_nodes) > 0:
        node_dists = _haversine_m_vec(
            hub_lon, hub_lat, subgraph.local_nodes["lon"], subgraph.local_nodes["lat"]
        )
        best_i = int(np.argmin(node_dists))
        if node_dists[best_i] <= max_snap_m:
            gap_m = float(node_dists[best_i])
            gap_dz_m = (0.0 if hub_ele_m is None
                        else float(hub_ele_m) - float(subgraph.local_node_ele[best_i]))
            if (max_snap_ascent_m is not None and hub_ele_m is not None
                    and abs(gap_dz_m) > max_snap_ascent_m):
                return SnapRejection(gap_m=gap_m, dz_m=gap_dz_m, reason="vertical_offset")
            return SnapResult(node_index=best_i, gap_m=gap_m, gap_dz_m=gap_dz_m)
```

with:

```python
    no_trail_data = len(subgraph.local_nodes) == 0 and len(subgraph.local_edges) == 0
    best_node_i, best_node_d = None, float("inf")
    # An existing graph node within range always wins over a mid-chain split, even if some
    # point along an incident edge is geometrically a hair closer - a hub sitting a few meters
    # off a real node is meant to snap to that node, not spawn a near-duplicate virtual vertex
    # right next to it.
    if len(subgraph.local_nodes) > 0:
        best_node_i, best_node_d = _nearest_node(subgraph, hub_lon, hub_lat)
        if best_node_d <= max_snap_m:
            gap_m = best_node_d
            gap_dz_m = (0.0 if hub_ele_m is None
                        else float(hub_ele_m) - float(subgraph.local_node_ele[best_node_i]))
            if (max_snap_ascent_m is not None and hub_ele_m is not None
                    and abs(gap_dz_m) > max_snap_ascent_m):
                return SnapRejection(gap_m=gap_m, dz_m=gap_dz_m, reason="vertical_offset")
            return SnapResult(node_index=best_node_i, gap_m=gap_m, gap_dz_m=gap_dz_m)
```

Then update the fallback report further down (currently):

```python
    if best_edge is None:
        # A node within max_snap_m (if any nodes exist at all) is the most informative distance
        # to report even though it lost - it tells the report how far away the nearest trail data
        # actually was, not just that nothing qualified.
        fallback_gap_m = (float(node_dists[int(np.argmin(node_dists))])
                           if node_dists is not None and len(node_dists) else float("inf"))
        reason = "no_trail_data" if no_trail_data else "gap_too_far"
        return SnapRejection(gap_m=fallback_gap_m, dz_m=0.0, reason=reason)
```

to:

```python
    if best_edge is None:
        # A node within max_snap_m (if any nodes exist at all) is the most informative distance
        # to report even though it lost - it tells the report how far away the nearest trail data
        # actually was, not just that nothing qualified.
        reason = "no_trail_data" if no_trail_data else "gap_too_far"
        return SnapRejection(gap_m=best_node_d, dz_m=0.0, reason=reason)
```

Finally, remove the now-unused `_haversine_m_vec` import (`from lib.geo import haversine_m_vec as
_haversine_m_vec` near the top of the file) — grep the file to confirm it has no other callers
before deleting the import line.

- [ ] **Step 6: Run the whole hub_snap and build_hub_edges test files**

Run: `cd pipeline && pixi run pytest tests/test_hub_snap.py tests/test_build_hub_edges.py -v`
Expected: PASS. (`test_snap_result_reports_the_gap` asserts `gap_m == pytest.approx(55.6,
rel=0.05)` — the projected-metres distance at this scale stays within that tolerance; if it does
not, widen `rel` to `0.1` rather than reintroducing the linear scan, per spec D3's explicit
"snap results are not guaranteed bit-identical across this change".)

- [ ] **Step 7: Run the full suite**

Run: `cd pipeline && pixi run pytest -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
cd pipeline
git add lib/hub_snap.py tests/test_hub_snap.py
git commit -m "$(cat <<'EOF'
perf(pipeline): index hub_snap's node search with a cKDTree

snap_hub_to_subgraph scanned every subgraph node with a full haversine vector per hub - O(hubs x
nodes), and D1/D2 of spec 2026-09-02-hub-edge-scaling-design.md measured this as the pipeline's
next bottleneck (846s wall / 8,722 CPU-s already) once the routing-direction inversion removes
distances/paths from the critical path. Caches a cKDTree per subgraph the same way the existing
edge spatial index already does - same projected-metres coordinate space, so the two agree.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_017cYyJEYLeD7yGBdMP27QrV
EOF
)"
```

---

## Task 3: Invert routing direction and split hut/access output (A1–A3, A5, B1–B3)

The core rewrite. `compute_hub_edges_for_cell` now routes **from** each core **hut** to every
candidate hub (hut or access point) in one batched pass, instead of from every core hub to every
candidate hut. Hut-hut records keep today's shape (full path geometry, written to `hut_edges/`
unchanged). Access records are reoriented (A3: reversed path, swapped ascent/descent, re-ordered
`fold_endpoint_snaps` args) but **no longer path-walked or geometry-materialized here** — they
become compact `(hut_id, start_id, start_type, variant, distance_m, time_s)` rows written to a new
`access_distances.npy` (B3). `_cell_workload_score` switches from total hub count to hut count
(A5), since after inversion routing cost is driven by huts, not hubs.

**Files:**
- Modify: `pipeline/lib/binfmt.py` (new dtype + schema version)
- Modify: `pipeline/lib/edge_output.py` (new `write_access_distances`)
- Modify: `pipeline/phases/graph_building/build_hub_edges.py` (the core rewrite)
- Test: `pipeline/tests/test_build_hub_edges.py` (many existing tests updated for the new return
  shape; new tests for the inversion/reorientation/scheduling)
- Test: `pipeline/tests/test_edge_output.py` (new `write_access_distances` tests)

**Interfaces:**
- Consumes: `binfmt.TYPE_HUT`/`TYPE_STATION`/`TYPE_PARKING`/`TYPE_PARTNER`, `lib.cell_igraph`'s
  `build_base_igraph_arrays`/`build_igraph_from_base`/`accumulate_path`, `lib.edge_output`'s
  `fold_endpoint_snaps`/`write_edge_records` (unchanged), `lib.variants.edge_mask`.
- Produces: `binfmt.ACCESS_DISTANCE_DTYPE`, `edge_output.write_access_distances(rows, path)`,
  `compute_hub_edges_for_cell(...) -> (hut_records, access_rows)` (see "Interfaces Carried Across
  Tasks" above), `_cell_workload_score(route_subgraphs_dir, cell_id, n_huts)` (param renamed from
  `n_hubs`, same signature shape). `access_rows` dicts are consumed downstream by Task 4.

### Step group A — `binfmt.py` and `edge_output.py`

- [ ] **Step 1: Write the failing test for the new dtype/writer**

Add to `pipeline/tests/test_edge_output.py`:

```python
from lib.edge_output import write_access_distances  # noqa: E402


def _access_row(hut_id=3, start_id=100, start_type=binfmt.TYPE_PARKING, variant=0,
                 distance_m=1200.0, time_s=900.0):
    return {"hut_id": hut_id, "start_id": start_id, "start_type": start_type, "variant": variant,
            "distance_m": distance_m, "time_s": time_s}


def test_write_access_distances_round_trips_fields(tmp_path):
    path = tmp_path / "access_distances.npy"
    write_access_distances([_access_row(), _access_row(hut_id=7, start_type=binfmt.TYPE_STATION)],
                            path)
    arr = binfmt.load_array(path, mmap=False)
    assert len(arr) == 2
    assert arr["hut_id"].tolist() == [3, 7]
    assert arr["start_type"].tolist() == [binfmt.TYPE_PARKING, binfmt.TYPE_STATION]
    assert arr["distance_m"][0] == pytest.approx(1200.0)
    assert arr["time_s"][0] == pytest.approx(900.0)


def test_write_access_distances_handles_empty_input(tmp_path):
    path = tmp_path / "access_distances.npy"
    write_access_distances([], path)
    arr = binfmt.load_array(path, mmap=False)
    assert len(arr) == 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd pipeline && pixi run pytest tests/test_edge_output.py -k access_distances -v`
Expected: FAIL — `ImportError: cannot import name 'write_access_distances'`.

- [ ] **Step 3: Add `ACCESS_DISTANCE_DTYPE` to `binfmt.py`**

In `pipeline/lib/binfmt.py`, add right after `RECORD_DTYPE`'s closing `])` (before
`PROFILE_DTYPE`):

```python
# build_hub_edges.py's B3 output (spec 2026-09-02-hub-edge-scaling-design.md): hut -> access-point
# distance/time ONLY, no geometry, no path walk - one row per (hut, start, variant). The cheap,
# complete "which trailheads can reach which hut" answer select_approach_pairs.py ranks/selects
# over before build_access_edges.py pays for a path walk on the survivors only.
ACCESS_DISTANCE_DTYPE = np.dtype([
    ("hut_id", "u2"), ("start_id", "i8"), ("start_type", "u1"), ("variant", "u1"),
    ("distance_m", "f4"), ("time_s", "f4"),
])
```

Then bump the schema-version block (right after `RECORD_SCHEMA_VERSION`):

```python
ACCESS_DISTANCE_SCHEMA_VERSION = 1  # new dtype (spec 2026-09-02-hub-edge-scaling-design.md, B3)
```

- [ ] **Step 4: Add `write_access_distances` to `edge_output.py`**

In `pipeline/lib/edge_output.py`, add after `write_edge_records` (before `fold_endpoint_snaps`):

```python
def write_access_distances(rows: list, path: Path) -> None:
    """Packs build_hub_edges.py's hut->access scalar rows (spec 2026-09-02-hub-edge-scaling-
    design.md B3: distance/time only, no geometry, no path walk) into one flat
    binfmt.ACCESS_DISTANCE_DTYPE array. Each row: {hut_id, start_id, start_type, variant,
    distance_m, time_s} - distance_m already has both ends' snap gap folded in (SnapResult.gap_m
    is direction-free, unlike ascent_m/descent_m, so no path walk is needed to fold it)."""
    arr = np.zeros(len(rows), dtype=binfmt.ACCESS_DISTANCE_DTYPE)
    for i, r in enumerate(rows):
        arr[i] = (r["hut_id"], r["start_id"], r["start_type"], r["variant"],
                   r["distance_m"], r["time_s"])
    binfmt.save_array(path, arr)
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd pipeline && pixi run pytest tests/test_edge_output.py -v`
Expected: PASS

### Step group B — invert `compute_hub_edges_for_cell`

- [ ] **Step 6: Write the failing tests for the inverted, split-output behavior**

Replace the whole body of `pipeline/tests/test_build_hub_edges.py` from
`test_compute_hub_edges_for_cell_connects_two_huts_on_the_line` (line 222) through
`test_compute_hub_edges_for_cell_emits_access_to_hut_only_once` (line 355) with:

```python
def test_compute_hub_edges_for_cell_connects_two_huts_on_the_line():
    subgraph = _line_subgraph()
    core_hubs = [
        {"id": 1, "type": binfmt.TYPE_HUT, "lon": 0.0001, "lat": 0.0},
        {"id": 2, "type": binfmt.TYPE_HUT, "lon": 0.0089, "lat": 0.0},
    ]
    snaps = snap_hubs_for_cell(subgraph, core_hubs, core_hubs, max_snap_m=50.0)
    hut_records, access_rows = compute_hub_edges_for_cell(
        subgraph, core_hubs, core_hubs, max_edge_km=5.0, snaps=snaps,
        variants=FAST_ANY_ONLY,
    )
    assert len(hut_records) == 1
    assert access_rows == []
    assert hut_records[0]["distance_m"] < 5000


def test_compute_hub_edges_for_cell_returns_full_path_geometry_for_hut_hut():
    subgraph = _line_subgraph()
    core_hubs = [
        {"id": 1, "type": binfmt.TYPE_HUT, "lon": 0.0001, "lat": 0.0},
        {"id": 2, "type": binfmt.TYPE_HUT, "lon": 0.0089, "lat": 0.0},
    ]
    snaps = snap_hubs_for_cell(subgraph, core_hubs, core_hubs, max_snap_m=50.0)
    hut_records, _ = compute_hub_edges_for_cell(
        subgraph, core_hubs, core_hubs, max_edge_km=5.0, snaps=snaps,
        variants=FAST_ANY_ONLY,
    )
    assert len(hut_records) == 1
    geometry = hut_records[0]["geometry"]
    assert len(geometry) >= 2
    assert geometry[0] == (core_hubs[0]["lon"], core_hubs[0]["lat"])
    assert geometry[-1] == (core_hubs[1]["lon"], core_hubs[1]["lat"])


def test_record_distance_includes_both_snap_gaps():
    # both huts sit off the trail line - the shipped distance_m must be the routed trail distance
    # (the edge's explicit dist=1000.0) PLUS both ends' hub-to-trail gaps, not just the trail leg
    # (spec E3: "the gap is currently free").
    subgraph = _line_subgraph()
    core_hubs = [
        {"id": 1, "type": binfmt.TYPE_HUT, "lon": 0.0, "lat": 0.0004},
        {"id": 2, "type": binfmt.TYPE_HUT, "lon": 0.009, "lat": 0.0003},
    ]
    snaps = snap_hubs_for_cell(subgraph, core_hubs, core_hubs, max_snap_m=50.0)
    hut_records, _ = compute_hub_edges_for_cell(
        subgraph, core_hubs, core_hubs, max_edge_km=5.0, snaps=snaps,
        variants=FAST_ANY_ONLY,
    )
    assert len(hut_records) == 1
    r = hut_records[0]
    assert r["snap_m"] > 0
    assert r["distance_m"] == pytest.approx(1000.0 + r["snap_m"], rel=1e-3)


def test_snap_gap_climb_lands_in_ascent_not_only_distance():
    # hub 1 sits 40m below its own snap point (a valley hut reached by climbing UP to the trail),
    # hub 2 sits exactly at its snap point's elevation (isolates the effect to one end).
    nodes = np.zeros(2, dtype=binfmt.NODE_DTYPE)
    nodes[0] = (0.0, 0.0, 0)
    nodes[1] = (0.009, 0.0, 0)
    edges = np.zeros(1, dtype=binfmt.EDGE_DTYPE)
    edges[0] = (0, 1, 1000.0, 0.0, 0.0, 0.0, 1000.0, 0.0, 0.0, -1, False, True, 0, 0, 0)
    interior = np.zeros(0, dtype=binfmt.COORD_DTYPE)
    subgraph = LocalSubgraph(
        global_node_ids=np.array([100, 101]), local_nodes=nodes, local_edges=edges,
        interior=interior,
        local_node_ele=np.array([1000.0, 1000.0], dtype=np.float32),
        interior_ele=np.zeros(len(interior), dtype=np.float32),
    )
    core_hubs = [
        {"id": 1, "type": binfmt.TYPE_HUT, "lon": 0.0, "lat": 0.0004, "ele": 960.0},
        {"id": 2, "type": binfmt.TYPE_HUT, "lon": 0.009, "lat": 0.0003, "ele": 1000.0},
    ]
    snaps = snap_hubs_for_cell(subgraph, core_hubs, core_hubs, max_snap_m=50.0)
    hut_records, _ = compute_hub_edges_for_cell(
        subgraph, core_hubs, core_hubs, max_edge_km=5.0, snaps=snaps,
        variants=FAST_ANY_ONLY,
    )
    assert len(hut_records) == 1
    assert hut_records[0]["ascent_m"] >= 40.0


def test_compute_hub_edges_for_cell_skips_access_to_access_pairs():
    # A station and a parking lot, no hut anywhere: with only huts as sources (A1), neither is
    # ever a Dijkstra source, so nothing routes at all.
    subgraph = _line_subgraph()
    core_hubs = [
        {"id": 1, "type": binfmt.TYPE_STATION, "lon": 0.0001, "lat": 0.0},
        {"id": 2, "type": binfmt.TYPE_PARKING, "lon": 0.0089, "lat": 0.0},
    ]
    snaps = snap_hubs_for_cell(subgraph, core_hubs, core_hubs, max_snap_m=50.0)
    hut_records, access_rows = compute_hub_edges_for_cell(
        subgraph, core_hubs, core_hubs, max_edge_km=5.0, snaps=snaps,
        variants=FAST_ANY_ONLY,
    )
    assert hut_records == []
    assert access_rows == []


def test_hut_source_routes_to_an_access_point_target():
    # A1: the hut is the ONLY core hub of this cell; the station is a candidate TARGET
    # (all_hubs), not a core hub - this is the inverted shape every real cell has (spec A5: huts
    # are core hubs of their own cell, access points almost never are, of the two).
    subgraph = _line_subgraph()
    hut = {"id": 1, "type": binfmt.TYPE_HUT, "lon": 0.0001, "lat": 0.0}
    station = {"id": 2, "type": binfmt.TYPE_STATION, "lon": 0.0089, "lat": 0.0}
    core_hubs = [hut]
    all_hubs = [hut, station]
    snaps = snap_hubs_for_cell(subgraph, core_hubs, all_hubs, max_snap_m=50.0)
    hut_records, access_rows = compute_hub_edges_for_cell(
        subgraph, core_hubs, all_hubs, max_edge_km=5.0, snaps=snaps,
        variants=FAST_ANY_ONLY,
    )
    assert hut_records == []
    assert len(access_rows) == 1
    row = access_rows[0]
    assert row["hut_id"] == 1
    assert row["start_id"] == 2
    assert row["start_type"] == binfmt.TYPE_STATION
    assert row["distance_m"] < 5000
    assert row["time_s"] > 0


def test_access_row_distance_includes_the_snap_gap():
    # Same snap-gap invariant as hut-hut (test_record_distance_includes_both_snap_gaps), but for
    # an access row, which folds the gap WITHOUT a path walk (SnapResult.gap_m is direction-free).
    subgraph = _line_subgraph()
    hut = {"id": 1, "type": binfmt.TYPE_HUT, "lon": 0.0, "lat": 0.0004}
    station = {"id": 2, "type": binfmt.TYPE_STATION, "lon": 0.009, "lat": 0.0003}
    core_hubs = [hut]
    all_hubs = [hut, station]
    snaps = snap_hubs_for_cell(subgraph, core_hubs, all_hubs, max_snap_m=50.0)
    _, access_rows = compute_hub_edges_for_cell(
        subgraph, core_hubs, all_hubs, max_edge_km=5.0, snaps=snaps,
        variants=FAST_ANY_ONLY,
    )
    assert len(access_rows) == 1
    assert access_rows[0]["distance_m"] > 1000.0  # trail leg (1000.0) plus both snap gaps


def test_access_row_has_no_geometry_or_ascent_fields():
    # B3: access rows are scalars-only by construction - asserting the dict shape guards against
    # a future edit accidentally reintroducing a path walk / geometry field here.
    subgraph = _line_subgraph()
    hut = {"id": 1, "type": binfmt.TYPE_HUT, "lon": 0.0001, "lat": 0.0}
    station = {"id": 2, "type": binfmt.TYPE_STATION, "lon": 0.0089, "lat": 0.0}
    core_hubs = [hut]
    all_hubs = [hut, station]
    snaps = snap_hubs_for_cell(subgraph, core_hubs, all_hubs, max_snap_m=50.0)
    _, access_rows = compute_hub_edges_for_cell(
        subgraph, core_hubs, all_hubs, max_edge_km=5.0, snaps=snaps,
        variants=FAST_ANY_ONLY,
    )
    assert set(access_rows[0]) == {"hut_id", "start_id", "start_type", "variant", "distance_m", "time_s"}


def test_only_hut_core_hubs_are_dijkstra_sources():
    # A1: a station/parking core hub of a cell must never itself become a routing source, even
    # when a hut also shares that cell.
    subgraph = _line_subgraph()
    hut = {"id": 1, "type": binfmt.TYPE_HUT, "lon": 0.0001, "lat": 0.0}
    station = {"id": 2, "type": binfmt.TYPE_STATION, "lon": 0.0089, "lat": 0.0}
    core_hubs = [hut, station]  # both core hubs of this cell
    all_hubs = [hut, station]
    snaps = snap_hubs_for_cell(subgraph, core_hubs, all_hubs, max_snap_m=50.0)
    hut_records, access_rows = compute_hub_edges_for_cell(
        subgraph, core_hubs, all_hubs, max_edge_km=5.0, snaps=snaps,
        variants=FAST_ANY_ONLY,
    )
    assert hut_records == []
    assert len(access_rows) == 1  # only the hut->station direction, never station->anything
```

Also update `test_compute_hub_edges_for_cell_fills_the_step_timer` (from Task 1) — it already
unpacks nothing from the return value, so it stays correct as-is, but confirm it now expects
`compute_hub_edges_for_cell` to still accept the same call shape (it does).

- [ ] **Step 7: Run to verify the new/changed tests fail**

Run: `cd pipeline && pixi run pytest tests/test_build_hub_edges.py -v`
Expected: FAIL — old tests fail on tuple-unpack (`ValueError: too many values to unpack`) or
`AttributeError`/`KeyError` for tests calling the new behavior that doesn't exist yet.

- [ ] **Step 8: Rewrite `compute_hub_edges_for_cell`**

Replace the whole function body in `pipeline/phases/graph_building/build_hub_edges.py` (currently
lines 87–237) with:

```python
def compute_hub_edges_for_cell(subgraph: LocalSubgraph, core_hubs: list,
                                all_hubs: list, max_edge_km: float, snaps: dict,
                                variants: list, timer: StepTimer = None) -> tuple:
    """all_hubs: candidate targets already filtered (by the caller) to hubs whose straight-line
    distance to this cell could possibly be within max_edge_km of trail distance - trail distance
    is always >= straight-line distance, so a bbox padded by max_edge_km around the cell is a safe
    superset. Without that prefilter this used to snap every hub in the whole bbox against every
    cell's local subgraph (O(cells * total_hubs) snap calls), which is what made this step take
    hours instead of minutes.

    Direction inverted from the original build (spec 2026-09-02-hub-edge-scaling-design.md, A1):
    only HUTS among core_hubs are ever routed FROM. Dijkstra count is then driven by hut count
    (~846 total) instead of access-point count (76,669+), and adding more access points costs
    nothing in the distances step. A station/parking core hub of this cell is never itself a
    Dijkstra source - it is only ever a TARGET, reached from whichever cell holds the hut that
    can see it (A2's padded-bbox coverage argument is symmetric, so no pair is lost or
    duplicated by this).

    Returns (hut_records, access_rows):
      - hut_records: hut<->hut edges, full path geometry, same dict shape as before this change
        (from_id/from_type/to_id/to_type/variant/distance_m/road_m/ascent_m/descent_m/max_ele_m/
        ungraded_m/inferred_m/snap_m/sac_rank/via_ferrata/geometry/base_edge_ids).
      - access_rows: hut->access distance/time ONLY, no geometry, no path walk (spec B3):
        {hut_id, start_id, start_type, variant, distance_m, time_s}. distance_m already has both
        ends' snap gap folded in (SnapResult.gap_m is direction-free, so this needs no path walk);
        stored access->hut by the SAME convention start_edges/records.npy always used, even though
        the router itself walked hut->access (A3) - callers reading access_rows never see the
        router's own traversal direction.

    snaps: {(hub_type, hub_id): SnapResult}, already computed for every hub this cell could need -
    build_hub_edges.py's own __main__ gets this from snap_hubs.py's persisted cache
    (hub_snap.reconstruct_local_snaps); a standalone caller without that cache can build one via
    snap_hubs_for_cell(). A key missing from `snaps` is simply not routed - already reported by
    whichever caller built the dict (snap_hubs.py's unsnapped_huts.json, or snap_hubs_for_cell's
    own `rejections` param).

    variants: list of lib/variants.py Variant rows to route (spec C2). Snapping is shared across
    rows - a hub's location doesn't depend on a routing constraint - but each row gets its own
    masked igraph and its own cutoff/path pass, because a constrained row can only ever be a
    smaller subgraph than FAST_ANY (never the same distances).

    timer: optional lib/timing.py StepTimer, filled with the per-step split (snap /
    build_base_arrays / build_igraph / distances / paths) so the parent can merge every worker's
    totals and report where the run actually went."""
    if not core_hubs:
        return [], []
    timer = timer if timer is not None else StepTimer()

    hut_sources = [h for h in core_hubs if h["type"] == binfmt.TYPE_HUT]
    if not hut_sources:
        return [], []

    with timer.step("snap"):
        relevant_snaps = {}
        for hub in core_hubs + all_hubs:
            key = (hub["type"], hub["id"])
            if key in relevant_snaps:
                continue
            snap = snaps.get(key)
            if snap is not None:
                relevant_snaps[key] = snap
    snaps = relevant_snaps
    timer.count("snap_hubs", len(snaps))

    max_edge_m = max_edge_km * 1000
    hut_records = []
    access_rows = []
    # Built once for this cell+snap set - lib/cell_igraph.py's build_base_igraph_arrays' Python-
    # level column/interior/max_ele_m work doesn't depend on the variant, only which resulting
    # edges get kept does (opt #1: this used to rerun that work from scratch once per variant, see
    # BaseIgraphArrays' docstring).
    with timer.step("build_base_arrays"):
        base_arrays = build_base_igraph_arrays(subgraph, snaps)
    for variant in variants:
        mask = variants_lib.edge_mask(subgraph.local_edges, variant)
        with timer.step("build_igraph"):
            graph, hub_vertex, vertex_coords = build_igraph_from_base(base_arrays, edge_mask=mask)
        # a hut-hut pair where both ends are core hubs of this cell is visited from both sides
        # below (each is its own source); collapse it to the one record merge_and_dedup would
        # otherwise keep anyway - core_hubs of a single cell call all belong to the same shard, so
        # merge_and_dedup's cross-shard dedup never sees the in-shard duplicate to drop it. Reset
        # per variant: a pair dropped by one row must still be tried by the next.
        seen_hut_pairs = set()
        for hub in hut_sources:
            src_key = (hub["type"], hub["id"])
            if src_key not in hub_vertex:
                continue
            src_v = hub_vertex[src_key]
            targets = [t for t in all_hubs if (t["type"], t["id"]) != src_key
                       and (t["type"], t["id"]) in hub_vertex]
            if not targets:
                continue
            target_vs = [hub_vertex[(t["type"], t["id"])] for t in targets]
            # Two different hubs can snap to the same graph vertex (both within max_snap_m of one
            # existing node), so target_vs can contain duplicates - igraph's distances() rejects a
            # target list with duplicates, so query only the unique vertex set and fan the results
            # back out per-target by vertex id.
            unique_target_vs = sorted(set(target_vs))
            # cutoff uses real-distance ("dist") weights on THIS variant's masked subgraph - a
            # constrained row's cutoff can only be a subset of FAST_ANY's, never wider (spec C2).
            with timer.step("distances"):
                unique_dists = graph.distances(
                    source=[src_v], target=unique_target_vs, weights="dist"
                )[0]
            timer.count("distance_targets", len(unique_target_vs))
            dist_by_vertex = dict(zip(unique_target_vs, unique_dists))
            cutoff_dists = [dist_by_vertex[tv] for tv in target_vs]

            in_cutoff = []
            for t, tv, cutoff_d in zip(targets, target_vs, cutoff_dists):
                if not np.isfinite(cutoff_d) or cutoff_d > max_edge_m:
                    continue
                if t["type"] == binfmt.TYPE_HUT:
                    pair_key = tuple(sorted([src_key, (t["type"], t["id"])]))
                    if pair_key in seen_hut_pairs:
                        continue
                    seen_hut_pairs.add(pair_key)
                in_cutoff.append((t, tv))
            if not in_cutoff:
                continue

            # B3: hut targets need a full path walk (hut_edges ships geometry); access targets
            # need only time_s, which a SECOND batched distances() call gives for free (same
            # O(E log V) class as the cutoff pass above) - no get_shortest_paths/path walk for
            # access at all, which is the whole point of splitting this from the old single pass.
            access_in_cutoff_vs = sorted(
                {tv for t, tv in in_cutoff if t["type"] != binfmt.TYPE_HUT}
            )
            with timer.step("distances"):
                access_time_dists = (
                    graph.distances(source=[src_v], target=access_in_cutoff_vs, weights="weight")[0]
                    if access_in_cutoff_vs else []
                )
            time_by_vertex = dict(zip(access_in_cutoff_vs, access_time_dists))

            hut_in_cutoff = [(t, tv) for t, tv in in_cutoff if t["type"] == binfmt.TYPE_HUT]
            unique_path_vs = sorted({tv for _, tv in hut_in_cutoff if tv != src_v})
            with timer.step("paths"):
                epaths = (
                    graph.get_shortest_paths(src_v, to=unique_path_vs, weights="weight", output="epath")
                    if unique_path_vs else []
                )
            path_by_vertex = {
                tv: accumulate_path(graph, vertex_coords, src_v, tv, epath)
                for tv, epath in zip(unique_path_vs, epaths)
            }

            src_snap = snaps[src_key]
            for t, tv in in_cutoff:
                tgt_snap = snaps[(t["type"], t["id"])]
                if t["type"] != binfmt.TYPE_HUT:
                    # B3: no path walk for access targets - distance_m folds the (direction-free)
                    # snap gap onto the dist-cutoff distance directly.
                    snap_m = src_snap.gap_m + tgt_snap.gap_m
                    access_rows.append({
                        "hut_id": hub["id"], "start_id": t["id"], "start_type": t["type"],
                        "variant": variant.code,
                        "distance_m": float(dist_by_vertex[tv] + snap_m),
                        "time_s": float(time_by_vertex[tv]),
                    })
                    continue

                path = (path_by_vertex[tv] if tv != src_v
                        else accumulate_path(graph, vertex_coords, src_v, tv, []))
                # spec C8: the cutoff above ran on `dist`, but the routed path is TIME-shortest,
                # whose distance_m can exceed the cap - re-check on the routed path itself.
                if path.distance_m > max_edge_m:
                    continue
                # spec E3: the path sums only routed edges, so the hub-to-trail gap at both ends
                # is priced in here - it was contributing zero distance/ascent/descent otherwise.
                snap_m, ascent_m, descent_m = fold_endpoint_snaps(path, src_snap, tgt_snap)
                geometry = [(hub["lon"], hub["lat"]), *path.coords, (t["lon"], t["lat"])]
                hut_records.append({
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
    return hut_records, access_rows
```

Notes on what changed vs. the pre-image, for the reviewer:
- `hut_targets`/`targets` restricted to huts is GONE — `targets` is now every candidate in
  `all_hubs` (huts and access points alike).
- The old single `records` list is now two: `hut_records` (unchanged shape, unchanged geometry
  logic) and `access_rows` (new, scalars only).
- A3's "reverse the path, swap ascent/descent, then fold" is **not needed** for `access_rows`
  because B3 access rows carry no `ascent_m`/`descent_m`/geometry at all — those only get computed
  later, in Task 5's `build_access_edges.py`, which re-routes the SELECTED pairs from scratch and
  performs the full A3 reorientation at that point (see Task 5). Folding `snap_m` here needs no
  reorientation because `SnapResult.gap_m` is direction-free (A3's docstring note).
- The `seen_hut_pairs` dedup logic, `max_edge_km` cutoff re-check, and `fold_endpoint_snaps`
  ordering for hut-hut pairs are all unchanged from the pre-image.

- [ ] **Step 9: Run to verify the tests pass**

Run: `cd pipeline && pixi run pytest tests/test_build_hub_edges.py -v`
Expected: PASS for every test touched in Step 6. Tests further down the file
(`test_merge_and_dedup_*`, `test_igraph_routes_on_time_not_distance`,
`test_edge_mask_removes_edges_from_the_built_graph`, the T2/T3 variant tests, the base-igraph-
array-reuse tests, the batched-path test, the `_cell_workload_score` tests, the unset-`time_s`
tests) call `compute_hub_edges_for_cell` or lower-level helpers unaffected by this rewrite's
signature change — check each one's assertions still match a `(hut_records, access_rows)` tuple
where they unpack it (e.g. `test_variant_rows_are_not_collapsed_into_one_record`,
`test_merge_and_dedup_keeps_directional_start_edges` calls `merge_and_dedup` directly on hand-built
dicts, unaffected; `test_route_exceeding_max_edge_km_is_dropped` and
`test_a_variant_with_no_obeying_path_emits_no_record` and
`test_compute_hub_edges_for_cell_rejects_unset_time_s` all call `compute_hub_edges_for_cell` with
hut-only `core_hubs`/`all_hubs`, so update each to unpack `hut_records, _ =` /
`hut_records, access_rows =` and assert against `hut_records` where they previously asserted
against `records`). Fix any remaining unpack mismatches the same way before moving on.

### Step group C — `snap_hubs_for_cell`, `_cell_workload_score`, `_run_cell`, `__main__`

- [ ] **Step 10: Write the failing test for the workload-score rename**

Update the three `_cell_workload_score` tests (currently `pipeline/tests/test_build_hub_edges.py:613-638`)
to use the renamed `n_huts` keyword — the assertions are unchanged, only the keyword name:

```python
def test_cell_workload_score_scales_with_cached_subgraph_size(tmp_path):
    big_dir = cell_dir_for(tmp_path, 1)
    small_dir = cell_dir_for(tmp_path, 2)
    big_dir.mkdir(parents=True)
    small_dir.mkdir(parents=True)
    (big_dir / "local_edges.npy").write_bytes(b"\x00" * 1000)
    (small_dir / "local_edges.npy").write_bytes(b"\x00" * 10)
    assert (_cell_workload_score(tmp_path, 1, n_huts=1)
            > _cell_workload_score(tmp_path, 2, n_huts=1))


def test_cell_workload_score_scales_with_hut_count():
    # A5: after the direction inversion, routing cost is driven by HUT count, not total hub count
    # (the two are wildly uncorrelated - spec measured cells with thousands of hubs and single
    # digits of huts) - LPT scheduling must sort on hut count, not len(core_hubs).
    cell_dir = cell_dir_for(Path("/tmp/does-not-need-to-exist"), 1)


def test_cell_workload_score_scales_with_hut_count(tmp_path):
    cell_dir = cell_dir_for(tmp_path, 1)
    cell_dir.mkdir(parents=True)
    (cell_dir / "local_edges.npy").write_bytes(b"\x00" * 1000)
    assert (_cell_workload_score(tmp_path, 1, n_huts=5)
            > _cell_workload_score(tmp_path, 1, n_huts=1))


def test_cell_workload_score_is_zero_for_an_uncached_cell(tmp_path):
    assert _cell_workload_score(tmp_path, 999, n_huts=3) == 0
```

(Drop the stray intermediate `def test_cell_workload_score_scales_with_hut_count():` half-body
shown above — that was scratch; only the final three functions belong in the file, replacing the
existing three at lines 613–638 exactly.)

- [ ] **Step 11: Run to verify it fails**

Run: `cd pipeline && pixi run pytest tests/test_build_hub_edges.py -k cell_workload_score -v`
Expected: FAIL — `TypeError: _cell_workload_score() got an unexpected keyword argument 'n_huts'`.

- [ ] **Step 12: Rename the `_cell_workload_score` parameter and update its docstring**

In `pipeline/phases/graph_building/build_hub_edges.py`, change the signature (currently line 256):

```python
def _cell_workload_score(route_subgraphs_dir: Path, cell_id: int, n_hubs: int) -> int:
```

to:

```python
def _cell_workload_score(route_subgraphs_dir: Path, cell_id: int, n_huts: int) -> int:
```

and update the body's `max(1, n_hubs)` to `max(1, n_huts)`, and the docstring's closing sentence
from "Multiplying by n_hubs (how many of this cell's hubs get routed out of that subgraph)..." to:

```python
    """... Multiplying by n_huts (how many of this cell's HUTS get routed out of that subgraph as
    Dijkstra sources - spec A5: after the direction inversion, routing cost is driven by hut
    count, not total hub count, and the two are wildly uncorrelated; a cell can hold thousands of
    access-point hubs and a handful of huts) accounts for routing cost also scaling with source
    count, not just subgraph size. Sorting tasks by this score, largest first, before submitting
    to ProcessPoolExecutor minimizes makespan on the fixed worker pool: an unsorted or arbitrarily-
    ordered submission can leave a big cell as a straggler near the end, with every other worker
    idle waiting on it."""
```

- [ ] **Step 13: Run to verify it passes**

Run: `cd pipeline && pixi run pytest tests/test_build_hub_edges.py -k cell_workload_score -v`
Expected: PASS

- [ ] **Step 14: Update `snap_hubs_for_cell` to snap every candidate, not just hut targets**

`snap_hubs_for_cell` (the standalone test/analysis convenience) currently snaps
`core_hubs + hut_targets`. After A1, a hut source needs snaps for every candidate in `all_hubs`
(huts and access points), not just the hut subset. In
`pipeline/phases/graph_building/build_hub_edges.py`, change:

```python
def snap_hubs_for_cell(subgraph: LocalSubgraph, core_hubs: list, all_hubs: list,
                        max_snap_m: float, max_snap_ascent_m: float = None,
                        rejections: list = None) -> dict:
    """..."""
    hut_targets = [h for h in all_hubs if h["type"] == binfmt.TYPE_HUT]
    snaps = {}
    for hub in core_hubs + hut_targets:
```

to:

```python
def snap_hubs_for_cell(subgraph: LocalSubgraph, core_hubs: list, all_hubs: list,
                        max_snap_m: float, max_snap_ascent_m: float = None,
                        rejections: list = None) -> dict:
    """... (spec 2026-09-02-hub-edge-scaling-design.md A1: every candidate in all_hubs needs a
    snap now, not just the hut subset - a hut source routes to huts AND access points in one
    pass) ..."""
    snaps = {}
    for hub in core_hubs + all_hubs:
```

(the loop body below is unchanged — only the iterable changes from `core_hubs + hut_targets` to
`core_hubs + all_hubs`).

This is exercised indirectly by every test in Step 6/9 that already calls `snap_hubs_for_cell` with
`all_hubs` including a station — no new test needed here beyond those.

- [ ] **Step 15: Run the file's test suite**

Run: `cd pipeline && pixi run pytest tests/test_build_hub_edges.py -v`
Expected: PASS

- [ ] **Step 16: Update `merge_and_dedup`'s docstring/usage split and add `merge_access_rows`**

`merge_and_dedup` (unchanged logic) now only ever receives `hut_records` shards. Add a small
sibling for access rows — no dedup needed (A2's "no duplication" argument: each hut is a core hub
of exactly one cell, so each `(hut, access)` pair is emitted by exactly one worker) but shards still
need concatenating. In `pipeline/phases/graph_building/build_hub_edges.py`, add right after
`merge_and_dedup`:

```python
def merge_access_rows(shard_access_rows: list) -> list:
    """Flattens every worker's access_rows list into one - no dedup needed (spec A2: each hut is
    a core hub of exactly one cell, so each (hut, access, variant) row is emitted by exactly one
    worker; this is NOT true of hut_records, which merge_and_dedup above still dedups)."""
    return [row for shard in shard_access_rows for row in shard]
```

- [ ] **Step 17: Write the failing test for `merge_access_rows`**

Add to `pipeline/tests/test_build_hub_edges.py`, near `test_merge_and_dedup_drops_duplicate_hut_pairs`:

```python
def test_merge_access_rows_concatenates_without_dedup():
    shard_a = [{"hut_id": 1, "start_id": 100, "start_type": binfmt.TYPE_STATION, "variant": 0,
                "distance_m": 1000.0, "time_s": 900.0}]
    shard_b = [{"hut_id": 2, "start_id": 200, "start_type": binfmt.TYPE_PARKING, "variant": 0,
                "distance_m": 500.0, "time_s": 400.0}]
    merged = merge_access_rows([shard_a, shard_b])
    assert len(merged) == 2
```

Add `merge_access_rows` to the `from graph_building.build_hub_edges import (...)` block at the top
of the test file.

- [ ] **Step 18: Run to verify it fails then passes**

Run: `cd pipeline && pixi run pytest tests/test_build_hub_edges.py -k merge_access_rows -v`
Expected: first FAIL (`ImportError`), then PASS after Step 16's addition.

- [ ] **Step 19: Update `_run_cell` and `__main__`**

In `pipeline/phases/graph_building/build_hub_edges.py`, change `_run_cell` (currently lines
274–290):

```python
def _run_cell(args):
    route_subgraphs_dir, base_graph_dir, cell_id, core_hubs, candidate_hubs, max_edge_km, \
        variants, local_persisted = args
    t0 = time.time()
    timer = StepTimer()
    with timer.step("gather_subgraph"):
        subgraph = load_local_subgraph(cell_dir_for(route_subgraphs_dir, cell_id), base_graph_dir)
    hut_targets = [h for h in candidate_hubs if h["type"] == binfmt.TYPE_HUT]
    keys = {(h["type"], h["id"]) for h in core_hubs} | {(h["type"], h["id"]) for h in hut_targets}
    local_snaps = hub_snap.reconstruct_local_snaps(subgraph, keys, local_persisted)
    records = compute_hub_edges_for_cell(subgraph, core_hubs, candidate_hubs, max_edge_km,
                                          local_snaps, variants=variants, timer=timer)
    return {
        "cell_id": cell_id, "elapsed_s": time.time() - t0, "n_core_hubs": len(core_hubs),
        "n_nodes": len(subgraph.local_nodes), "n_edges": len(subgraph.local_edges),
        "records": records, "timer": timer,
    }
```

to:

```python
def _run_cell(args):
    route_subgraphs_dir, base_graph_dir, cell_id, core_hubs, candidate_hubs, max_edge_km, \
        variants, local_persisted = args
    t0 = time.time()
    timer = StepTimer()
    with timer.step("gather_subgraph"):
        subgraph = load_local_subgraph(cell_dir_for(route_subgraphs_dir, cell_id), base_graph_dir)
    # A4: every candidate in the padded cell needs a snap now (hut sources route to huts AND
    # access points), not just the hut subset - core_hubs is already a subset of candidate_hubs
    # (its own cell is inside its own padded bounds), so candidate_hubs alone covers both.
    keys = {(h["type"], h["id"]) for h in candidate_hubs}
    local_snaps = hub_snap.reconstruct_local_snaps(subgraph, keys, local_persisted)
    hut_records, access_rows = compute_hub_edges_for_cell(
        subgraph, core_hubs, candidate_hubs, max_edge_km, local_snaps, variants=variants,
        timer=timer,
    )
    n_huts = sum(1 for h in core_hubs if h["type"] == binfmt.TYPE_HUT)
    return {
        "cell_id": cell_id, "elapsed_s": time.time() - t0, "n_core_hubs": len(core_hubs),
        "n_core_huts": n_huts,
        "n_nodes": len(subgraph.local_nodes), "n_edges": len(subgraph.local_edges),
        "hut_records": hut_records, "access_rows": access_rows, "timer": timer,
    }
```

Then in `__main__` (currently lines 334–414), make these changes:

1. Task-building loop — the `local_persisted` filter and the `tasks.append(...)` tuple stay
   structurally the same (they already pass `candidate_hubs` through), but the comment above
   `local_persisted` should note the widened key set:

```python
    tasks = []
    for cid, hubs in hubs_by_cell.items():
        candidate_hubs = _candidate_hubs_for_cell(cid)
        # A4: filter persisted-snaps down to EVERY candidate this cell could route to now (huts
        # and access points alike), not just this cell's own hubs + hut targets - see
        # snap_hubs_for_cell's docstring for why the candidate set widened.
        keys = {(h["type"], h["id"]) for h in candidate_hubs}
        local_persisted = {k: persisted_snaps[k] for k in keys if k in persisted_snaps}
        tasks.append((
            Path(args.route_subgraphs_dir), Path(args.base_graph_dir), cid, hubs, candidate_hubs,
            args.max_edge_km, active_variants, local_persisted,
        ))
```

(the `hut_targets`/second `keys` line that used to compute a hut-only subset is deleted — the new
`keys` line supersedes it, and `candidate_hubs` is already the full bbox-padded superset.)

2. The LPT sort — change:

```python
    tasks.sort(
        key=lambda t: _cell_workload_score(route_subgraphs_dir_path, t[2], len(t[3])),
        reverse=True,
    )
```

to:

```python
    tasks.sort(
        key=lambda t: _cell_workload_score(
            route_subgraphs_dir_path, t[2], sum(1 for h in t[3] if h["type"] == binfmt.TYPE_HUT)
        ),
        reverse=True,
    )
```

3. The result-collection loop — change:

```python
    shard_records = []
    tracker = ProgressTracker(total)
    ...
    with phase(...) as meta:
        for result in run_pool(tasks, _run_cell, workers=args.workers):
            shard_records.append(result["records"])
            run_timer.merge(result["timer"])
            eta = tracker.eta_suffix()
            cell_s = result["timer"].seconds
            print(
                f"[{tracker.completed}/{total}] cell {result['cell_id']}: "
                f"{result['elapsed_s']:.1f}s ({result['n_core_hubs']} hubs, "
                f"{result['n_nodes']:,} nodes, {result['n_edges']:,} edges) -> "
                f"{len(result['records'])} edge records "
                f"| slice {cell_s.get('gather_subgraph', 0):.1f}s, snap "
                f"{cell_s.get('snap', 0):.1f}s, igraph "
                f"{cell_s.get('build_igraph', 0):.1f}s, dist "
                f"{cell_s.get('distances', 0):.1f}s, paths {cell_s.get('paths', 0):.1f}s "
                f"| {eta}",
                flush=True,
            )
        meta.update(run_timer.as_meta())
```

to:

```python
    shard_hut_records = []
    shard_access_rows = []
    tracker = ProgressTracker(total)
    ...
    with phase(...) as meta:
        for result in run_pool(tasks, _run_cell, workers=args.workers):
            shard_hut_records.append(result["hut_records"])
            shard_access_rows.append(result["access_rows"])
            run_timer.merge(result["timer"])
            eta = tracker.eta_suffix()
            cell_s = result["timer"].seconds
            print(
                f"[{tracker.completed}/{total}] cell {result['cell_id']}: "
                f"{result['elapsed_s']:.1f}s ({result['n_core_huts']} huts of "
                f"{result['n_core_hubs']} hubs, {result['n_nodes']:,} nodes, "
                f"{result['n_edges']:,} edges) -> {len(result['hut_records'])} hut edges, "
                f"{len(result['access_rows'])} access rows "
                f"| slice {cell_s.get('gather_subgraph', 0):.1f}s, snap "
                f"{cell_s.get('snap', 0):.1f}s, base_arrays "
                f"{cell_s.get('build_base_arrays', 0):.1f}s, igraph "
                f"{cell_s.get('build_igraph', 0):.1f}s, dist "
                f"{cell_s.get('distances', 0):.1f}s, paths {cell_s.get('paths', 0):.1f}s "
                f"| {eta}",
                flush=True,
            )
        meta.update(run_timer.as_meta())
```

4. The finalize/write section — change:

```python
    merged = merge_and_dedup(shard_records)
    hut_records = [r for r in merged if r["to_type"] == binfmt.TYPE_HUT and r["from_type"] == binfmt.TYPE_HUT]
    # "access edges": station/parking <-> hut. ...
    access_records = [r for r in merged if r["from_type"] != binfmt.TYPE_HUT]

    print(f"hut-hut edges: {len(hut_records)}, "
          f"access edges (station/parking <-> hut): {len(access_records)}")
    # Per-variant breakdown ...
    hut_counts_by_variant = Counter(r["variant"] for r in hut_records)
    access_counts_by_variant = Counter(r["variant"] for r in access_records)
    for variant in active_variants:
        print(f"  {variant.name}: hut-hut {hut_counts_by_variant.get(variant.code, 0)}, "
              f"access {access_counts_by_variant.get(variant.code, 0)}")

    out_dir = Path(args.out_dir)
    write_edge_records(hut_records, out_dir / "hut_edges", write_edge_ids=True)
    write_edge_records(access_records, out_dir / "start_edges", write_edge_ids=False)
    print(f"written {out_dir / 'hut_edges'} and {out_dir / 'start_edges'}")
```

to:

```python
    hut_records = merge_and_dedup(shard_hut_records)
    access_rows = merge_access_rows(shard_access_rows)

    print(f"hut-hut edges: {len(hut_records)}, "
          f"access distance rows (station/parking/partner -> hut, no geometry): {len(access_rows)}")
    # Per-variant breakdown (spec C2's grid, active_variants above) - build_hub_edges.py is the
    # one place that runs every row, so this is the cheapest place to sanity-check a variant's
    # row actually produced edges rather than reloading records.npy separately afterward.
    hut_counts_by_variant = Counter(r["variant"] for r in hut_records)
    access_counts_by_variant = Counter(r["variant"] for r in access_rows)
    for variant in active_variants:
        print(f"  {variant.name}: hut-hut {hut_counts_by_variant.get(variant.code, 0)}, "
              f"access {access_counts_by_variant.get(variant.code, 0)}")

    out_dir = Path(args.out_dir)
    write_edge_records(hut_records, out_dir / "hut_edges", write_edge_ids=True)
    write_access_distances(access_rows, out_dir / "access_distances.npy")
    print(f"written {out_dir / 'hut_edges'} and {out_dir / 'access_distances.npy'}")
```

5. Update the `from lib.edge_output import fold_endpoint_snaps, write_edge_records` import line
   (currently line 38) to also pull in the new writer:

```python
from lib.edge_output import fold_endpoint_snaps, write_edge_records, write_access_distances  # noqa: E402
```

6. Update the module docstring's opening summary line (currently line 2's "This script just
   reloads both caches and does the actual per-cell, per-variant routing") to mention the split
   output — append one sentence: `"Writes hut_edges/ (full geometry) and access_distances.npy
   (distance/time scalars only, no geometry - spec 2026-09-02-hub-edge-scaling-design.md B3); a
   later select_approach_pairs.py + build_access_edges.py pair materializes start_edges/ from the
   selected subset."`

- [ ] **Step 20: Run the whole test file**

Run: `cd pipeline && pixi run pytest tests/test_build_hub_edges.py -v`
Expected: PASS — every test in the file, old and new.

- [ ] **Step 21: Run the full pipeline suite**

Run: `cd pipeline && pixi run pytest -v`
Expected: PASS

- [ ] **Step 22: Commit**

```bash
cd pipeline
git add lib/binfmt.py lib/edge_output.py phases/graph_building/build_hub_edges.py \
        tests/test_build_hub_edges.py tests/test_edge_output.py
git commit -m "$(cat <<'EOF'
perf(pipeline): invert hub-edge routing direction, split hut/access output

Implements A1-A3/A5/B1-B3 of spec 2026-09-02-hub-edge-scaling-design.md: huts become the Dijkstra
sources (~846 total) instead of every access point (76,669+), cutting Dijkstra count ~90x and
making the distances step independent of access-point count. Access records are no longer
path-walked or geometry-materialized in this pass - they become compact distance/time-only rows
in a new access_distances.npy; a later select_approach_pairs.py + build_access_edges.py pair
(follow-up commits) re-routes and materializes geometry only for the selected subset.
_cell_workload_score now sorts on hut count, not total hub count, since routing cost is driven by
sources (huts) after the inversion and the two are only weakly correlated per cell.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_017cYyJEYLeD7yGBdMP27QrV
EOF
)"
```

---

## Task 4: `select_approach_pairs.py` — global top-K + reverse-index closure (B2, B4)

New script: reads `access_distances.npy` (Task 3's output), for each `(hut_id, start_type)` group
ranks candidates by `time_s` ascending and keeps the top 20 (spec B4's decision: over-select 20,
measured to leave DIN-best-3 outside the selection only 1.2% of the time even against a
deliberately worse `distance_m` proxy), then computes the loop-closure reverse index — every
variant of every `(hut, start)` pair for any start id that made the top-20 cut in ANY variant (spec
B5's "every variant, not just FAST_ANY" — `build_tables`'s E2 closure loops records with no variant
filter, so restricting this to FAST_ANY would silently truncate it). Writes a plain list of
`(hut_id, start_id, start_type, variant)` pairs that Task 5's `build_access_edges.py` must
materialize.

**Files:**
- Create: `pipeline/phases/postprocessing/select_approach_pairs.py`
- Test: `pipeline/tests/test_select_approach_pairs.py`

**Interfaces:**
- Consumes: `binfmt.ACCESS_DISTANCE_DTYPE` array (Task 3), `binfmt.VARIANT_FAST_ANY`.
- Produces: `select_pairs(access_distances: np.ndarray, k: int) -> np.ndarray` — same dtype as the
  input, filtered to the union of the top-k-by-`time_s`-per-`(hut_id, start_type)` group (ranked
  over `VARIANT_FAST_ANY` rows only, matching `build_approach_table.py`'s existing "an approach is
  a fastest, unconstrained leg" rule) plus every row (any variant) whose `start_id` is in that
  top-k set. Also writes `select_approach_pairs.py`'s own on-disk output,
  `data/osm/selected_access_pairs.npy` (same dtype), consumed by Task 5.

- [ ] **Step 1: Write the failing test**

Create `pipeline/tests/test_select_approach_pairs.py`:

```python
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from lib import binfmt  # noqa: E402
from postprocessing.select_approach_pairs import select_pairs  # noqa: E402


def _row(hut_id, start_id, start_type, variant, distance_m, time_s):
    return (hut_id, start_id, start_type, variant, distance_m, time_s)


def _arr(rows):
    return np.array(rows, dtype=binfmt.ACCESS_DISTANCE_DTYPE)


def test_keeps_only_the_k_fastest_fast_any_candidates_per_hut_and_source_type():
    rows = _arr([
        _row(1, 100, binfmt.TYPE_PARKING, binfmt.VARIANT_FAST_ANY, 1000.0, 500.0),
        _row(1, 101, binfmt.TYPE_PARKING, binfmt.VARIANT_FAST_ANY, 2000.0, 900.0),
        _row(1, 102, binfmt.TYPE_PARKING, binfmt.VARIANT_FAST_ANY, 3000.0, 1500.0),
    ])
    selected = select_pairs(rows, k=2)
    assert sorted(selected["start_id"].tolist()) == [100, 101]  # the two fastest by time_s


def test_selection_is_per_hut_and_source_type_group():
    # hut 1's parking candidates must not compete against hut 2's for the k slots.
    rows = _arr([
        _row(1, 100, binfmt.TYPE_PARKING, binfmt.VARIANT_FAST_ANY, 1000.0, 500.0),
        _row(2, 200, binfmt.TYPE_PARKING, binfmt.VARIANT_FAST_ANY, 1000.0, 500.0),
    ])
    selected = select_pairs(rows, k=1)
    assert set(selected["start_id"].tolist()) == {100, 200}


def test_station_and_parking_slots_are_independent():
    rows = _arr([
        _row(1, 100, binfmt.TYPE_PARKING, binfmt.VARIANT_FAST_ANY, 1000.0, 500.0),
        _row(1, 200, binfmt.TYPE_STATION, binfmt.VARIANT_FAST_ANY, 5000.0, 4000.0),
    ])
    selected = select_pairs(rows, k=1)
    assert set(selected["start_id"].tolist()) == {100, 200}


def test_reverse_index_closure_pulls_in_every_variant_of_a_selected_start():
    # start 100 is selected on FAST_ANY; its FAST_T2 row for the SAME hut must ship too, even
    # though FAST_T2 rows are never themselves ranking candidates (spec B5).
    rows = _arr([
        _row(1, 100, binfmt.TYPE_PARKING, binfmt.VARIANT_FAST_ANY, 1000.0, 500.0),
        _row(1, 100, binfmt.TYPE_PARKING, binfmt.VARIANT_FAST_T2, 1200.0, 600.0),
    ])
    selected = select_pairs(rows, k=1)
    assert sorted(selected["variant"].tolist()) == [binfmt.VARIANT_FAST_ANY, binfmt.VARIANT_FAST_T2]


def test_reverse_index_closure_pulls_in_a_selected_start_reaching_a_different_hut():
    # start 100 is selected as hut 1's approach; hut 2 also has a (non-selected-rank) row to the
    # SAME start 100 - the loop-closure index must ship that pair too (spec E2/B2: the client's
    # car mode needs exit start-point == entry start-point across the whole trip, not just the
    # entry hut's own top-k).
    rows = _arr([
        _row(1, 100, binfmt.TYPE_PARKING, binfmt.VARIANT_FAST_ANY, 1000.0, 500.0),
        _row(2, 100, binfmt.TYPE_PARKING, binfmt.VARIANT_FAST_ANY, 9000.0, 8000.0),
        _row(2, 999, binfmt.TYPE_PARKING, binfmt.VARIANT_FAST_ANY, 1000.0, 500.0),
    ])
    selected = select_pairs(rows, k=1)
    # hut 2's own top-1 is start 999, but start 100's closure must still bring in (hut 2, 100).
    pairs = {(int(r["hut_id"]), int(r["start_id"])) for r in selected}
    assert (2, 100) in pairs
    assert (2, 999) in pairs


def test_empty_input_returns_empty_output():
    selected = select_pairs(_arr([]), k=20)
    assert len(selected) == 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd pipeline && pixi run pytest tests/test_select_approach_pairs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'postprocessing.select_approach_pairs'`.

- [ ] **Step 3: Write `select_approach_pairs.py`**

Create `pipeline/phases/postprocessing/select_approach_pairs.py`:

```python
#!/usr/bin/env python3
"""B2/B4 of docs/superpowers/specs/2026-09-02-hub-edge-scaling-design.md: the global selection
step that decides WHICH (hut, start, variant) pairs are worth materializing full path geometry
for, before build_access_edges.py pays for that materialization.

Top-K-per-hut is cell-local (every candidate for a hut lies inside its own cell's padded set, a
worker could rank it), but the loop-closure reverse index (every hut reachable from a RETAINED
start id, build_approach_table.py's E2) is not - a retained start point may be reachable from huts
in a neighbouring cell. That closure is the one thing that forces this to be its own global,
whole-table pass rather than in-worker selection inside build_hub_edges.py.

Ranks on time_s (build_hub_edges.py's B3 output already carries it, no path walk needed) over
VARIANT_FAST_ANY rows only - same "an approach is a fastest, unconstrained leg" rule
build_approach_table.py's own selection already uses - and over-selects k=20 per (hut, source
type) rather than trying to match build_approach_table.py's eventual DIN-duration re-rank exactly
(measured: top-20 leaves the true DIN-best-3 outside the selection only 1.2% of the time, using a
deliberately worse distance_m proxy as the upper bound - see spec B4).

Usage: python pipeline/phases/postprocessing/select_approach_pairs.py [--k 20]
Requires data/osm/access_distances.npy (build_hub_edges.py's output).
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib import binfmt  # noqa: E402
from lib.pipeline import OSM_DIR, load_config  # noqa: E402
from lib.timing import phase  # noqa: E402

SCRIPT_NAME = "select_approach_pairs.py"


def select_pairs(access_distances: np.ndarray, k: int) -> np.ndarray:
    """Returns the subset of `access_distances` worth materializing geometry for: the union of
    (a) the k fastest (by time_s) VARIANT_FAST_ANY rows per (hut_id, start_type) group, and
    (b) every row (any variant) whose start_id appears in (a) - the loop-closure reverse index
    (spec B5: build_tables loops records with no variant filter, so restricting (b) to FAST_ANY
    would silently truncate the closure)."""
    if len(access_distances) == 0:
        return access_distances

    by_group = defaultdict(list)
    for i, r in enumerate(access_distances):
        if int(r["variant"]) != binfmt.VARIANT_FAST_ANY:
            continue
        by_group[(int(r["hut_id"]), int(r["start_type"]))].append(i)

    retained_indices = set()
    retained_start_ids = set()
    for indices in by_group.values():
        indices.sort(key=lambda i: float(access_distances[i]["time_s"]))
        top = indices[:k]
        retained_indices.update(top)
        retained_start_ids.update(int(access_distances[i]["start_id"]) for i in top)

    for i, r in enumerate(access_distances):
        if int(r["start_id"]) in retained_start_ids:
            retained_indices.add(i)

    return access_distances[sorted(retained_indices)]


if __name__ == "__main__":
    config = load_config()
    parser = argparse.ArgumentParser()
    parser.add_argument("--access-distances", default=str(OSM_DIR / "access_distances.npy"),
                         help="path to build_hub_edges.py's access_distances.npy")
    parser.add_argument("--k", type=int, default=config["approach"].get("selectK", 20),
                         help="candidates retained per (hut, source type) before build_approach_table.py's own re-rank (see pipeline.config.json's approach.selectK)")
    parser.add_argument("--out", default=str(OSM_DIR / "selected_access_pairs.npy"),
                         help="path to write the selected pair list")
    args = parser.parse_args()

    with phase(SCRIPT_NAME, "select_approach_pairs"):
        access_distances = binfmt.load_array(Path(args.access_distances), mmap=False)
        print(f"access_distances rows: {len(access_distances):,}", flush=True)

        selected = select_pairs(access_distances, args.k)
        print(f"selected pairs (k={args.k}): {len(selected):,}", flush=True)

        binfmt.save_array(Path(args.out), selected)
        print(f"written {args.out}", flush=True)
```

Add `"selectK": 20` under the existing `"approach"` block in `pipeline/pipeline.config.json` (find
the `"approach": { "k": ... }` block and add `"selectK": 20` alongside `"k"`).

- [ ] **Step 4: Run to verify it passes**

Run: `cd pipeline && pixi run pytest tests/test_select_approach_pairs.py -v`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `cd pipeline && pixi run pytest -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd pipeline
git add phases/postprocessing/select_approach_pairs.py tests/test_select_approach_pairs.py \
        pipeline.config.json
git commit -m "$(cat <<'EOF'
feat(pipeline): add select_approach_pairs.py (global top-K + reverse-index closure)

Implements B2/B4 of spec 2026-09-02-hub-edge-scaling-design.md: ranks build_hub_edges.py's new
scalars-only access_distances.npy by time_s, keeps the top 20 per (hut, source type) plus every
variant of every retained start id's pairs (the loop-closure reverse index build_approach_table.py
needs), and writes the survivor list build_access_edges.py will materialize geometry for. This is
the piece that keeps geometry materialization proportional to what ships (~60k pairs) instead of
the full routed pair set (~1M projected).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_017cYyJEYLeD7yGBdMP27QrV
EOF
)"
```

---

## Task 5: `build_access_edges.py` — materialize geometry for selected pairs only (B5, B6)

New script: for every cell that owns at least one selected pair's hut, reload the cached padded
subgraph + snaps (same caches `build_hub_edges.py` uses), route (hut source, per A1) but restrict
targets to exactly this cell's selected access-point ids, walk the paths, apply A3's reorientation
(reverse path, swap ascent/descent, fold snaps in access order), and write `start_edges/records.npy`
+ `geometry.npy` via the existing `edge_output.write_edge_records`.

**Files:**
- Create: `pipeline/phases/graph_building/build_access_edges.py`
- Test: `pipeline/tests/test_build_access_edges.py`

**Interfaces:**
- Consumes: `select_approach_pairs.py`'s `selected_access_pairs.npy` (Task 4), the same
  `load_local_subgraph`/`hub_snap.reconstruct_local_snaps`/`build_base_igraph_arrays`/
  `build_igraph_from_base`/`accumulate_path` primitives `build_hub_edges.py` uses, `lib.hubs`'
  `load_all_hubs`/`bucket_by_cell`, `lib.edge_output.write_edge_records`/`fold_endpoint_snaps`.
- Produces: `route_selected_pairs_for_cell(subgraph, hut_sources, selected_targets_by_hut, snaps,
  variants) -> list` — one dict per materialized access record, same shape as `hut_records` dicts
  from Task 3 (`from_id/from_type/to_id/to_type/variant/distance_m/road_m/ascent_m/descent_m/
  max_ele_m/ungraded_m/inferred_m/snap_m/sac_rank/via_ferrata/geometry/base_edge_ids`), stored
  access→hut (A3's reorientation applied here). Writes `data/osm/start_edges/{records,geometry}.npy`.

- [ ] **Step 1: Write the failing test**

Create `pipeline/tests/test_build_access_edges.py`:

```python
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from lib import binfmt  # noqa: E402
from lib import variants  # noqa: E402
from lib.subgraph import LocalSubgraph  # noqa: E402
from graph_building.build_hub_edges import snap_hubs_for_cell  # noqa: E402
from graph_building.build_access_edges import route_selected_pairs_for_cell  # noqa: E402

FAST_ANY_ONLY = [variants.VARIANTS[binfmt.VARIANT_FAST_ANY]]


def _line_subgraph():
    nodes = np.zeros(2, dtype=binfmt.NODE_DTYPE)
    nodes[0] = (0.0, 0.0, 0)
    nodes[1] = (0.009, 0.0, 0)
    edges = np.zeros(1, dtype=binfmt.EDGE_DTYPE)
    edges[0] = (0, 1, 1000.0, 0.0, 0.0, 0.0, 1000.0, binfmt.UNSET, binfmt.UNSET, -1, False, True,
                0, 0, 0)
    interior = np.zeros(0, dtype=binfmt.COORD_DTYPE)
    return LocalSubgraph(
        global_node_ids=np.array([100, 101]), local_nodes=nodes, local_edges=edges,
        interior=interior,
        local_node_ele=np.zeros(len(nodes), dtype=np.float32),
        interior_ele=np.zeros(len(interior), dtype=np.float32),
    )


def test_materializes_geometry_only_for_selected_targets():
    subgraph = _line_subgraph()
    hut = {"id": 1, "type": binfmt.TYPE_HUT, "lon": 0.0001, "lat": 0.0}
    station = {"id": 2, "type": binfmt.TYPE_STATION, "lon": 0.0089, "lat": 0.0}
    all_hubs = [hut, station]
    snaps = snap_hubs_for_cell(subgraph, [hut], all_hubs, max_snap_m=50.0)
    selected_targets_by_hut = {1: [station]}

    records = route_selected_pairs_for_cell(
        subgraph, [hut], selected_targets_by_hut, snaps, variants=FAST_ANY_ONLY,
    )

    assert len(records) == 1
    r = records[0]
    # A3: stored access -> hut, even though the router walked hut -> access.
    assert r["from_id"] == station["id"] and r["from_type"] == binfmt.TYPE_STATION
    assert r["to_id"] == hut["id"] and r["to_type"] == binfmt.TYPE_HUT
    assert r["geometry"][0] == (station["lon"], station["lat"])
    assert r["geometry"][-1] == (hut["lon"], hut["lat"])


def test_unselected_target_is_never_routed():
    subgraph = _line_subgraph()
    hut = {"id": 1, "type": binfmt.TYPE_HUT, "lon": 0.0001, "lat": 0.0}
    station = {"id": 2, "type": binfmt.TYPE_STATION, "lon": 0.0089, "lat": 0.0}
    snaps = snap_hubs_for_cell(subgraph, [hut], [hut, station], max_snap_m=50.0)

    records = route_selected_pairs_for_cell(
        subgraph, [hut], selected_targets_by_hut={1: []}, snaps=snaps, variants=FAST_ANY_ONLY,
    )

    assert records == []


def test_ascent_descent_are_swapped_relative_to_the_hut_sourced_walk():
    # hut sits ABOVE its own snap point (climbing down FROM the hut to the trail is descent from
    # the hut's perspective); once reoriented to access->hut storage, that same physical drop must
    # read as the ACCESS side's ascent (climbing UP from the trail to the hut).
    nodes = np.zeros(2, dtype=binfmt.NODE_DTYPE)
    nodes[0] = (0.0, 0.0, 0)
    nodes[1] = (0.009, 0.0, 0)
    edges = np.zeros(1, dtype=binfmt.EDGE_DTYPE)
    edges[0] = (0, 1, 1000.0, 0.0, 0.0, 0.0, 1000.0, 80.0, 0.0, -1, False, True, 0, 0, 0)
    interior = np.zeros(0, dtype=binfmt.COORD_DTYPE)
    subgraph = LocalSubgraph(
        global_node_ids=np.array([100, 101]), local_nodes=nodes, local_edges=edges,
        interior=interior,
        local_node_ele=np.zeros(2, dtype=np.float32),
        interior_ele=np.zeros(0, dtype=np.float32),
    )
    hut = {"id": 1, "type": binfmt.TYPE_HUT, "lon": 0.0001, "lat": 0.0}
    station = {"id": 2, "type": binfmt.TYPE_STATION, "lon": 0.0089, "lat": 0.0}
    snaps = snap_hubs_for_cell(subgraph, [hut], [hut, station], max_snap_m=50.0)

    records = route_selected_pairs_for_cell(
        subgraph, [hut], {1: [station]}, snaps, variants=FAST_ANY_ONLY,
    )

    # the edge is 80m of ascent walking 0->1 (hut's side); reversed to access(2)->hut(1) storage
    # the SAME physical climb is now traversed 1->0, so it must land in descent, not ascent.
    assert records[0]["descent_m"] >= 80.0
    assert records[0]["ascent_m"] < 80.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd pipeline && pixi run pytest tests/test_build_access_edges.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'graph_building.build_access_edges'`.

- [ ] **Step 3: Write `build_access_edges.py`**

Create `pipeline/phases/graph_building/build_access_edges.py`:

```python
#!/usr/bin/env python3
"""B5/B6 of docs/superpowers/specs/2026-09-02-hub-edge-scaling-design.md: materializes full path
geometry ONLY for the pairs select_approach_pairs.py selected, writing the final start_edges/. This
is the second (and last) igraph pass over each cell's cached subgraph - build_hub_edges.py's own
first pass already proved which pairs are within max_edge_km (access_distances.npy); this one pays
for get_shortest_paths only on the survivors.

Routes with huts as sources, same direction as build_hub_edges.py (A1), then reorients each result
into the access->hut storage convention every consumer of start_edges/ expects (A3: reverse
path.coords, swap ascent_m/descent_m, THEN fold_endpoint_snaps with (access_snap, hut_snap) order -
see route_selected_pairs_for_cell's docstring for why the order matters).

Usage: python pipeline/phases/graph_building/build_access_edges.py [--max-edge-km 30] [--workers N]
Requires data/osm/selected_access_pairs.npy (select_approach_pairs.py), data/osm/hub_snaps.npy +
hub_snap_interior.npy (snap_hubs.py), data/osm/route_subgraphs/ (gather_route_subgraphs.py).
"""

import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import binfmt  # noqa: E402
from lib import hub_snap  # noqa: E402
from lib import variants as variants_lib  # noqa: E402
from lib.cell_igraph import accumulate_path, build_base_igraph_arrays, build_igraph_from_base  # noqa: E402
from lib.edge_output import fold_endpoint_snaps, write_edge_records  # noqa: E402
from lib.grid import Grid  # noqa: E402
from lib.hubs import bucket_by_cell, load_all_hubs  # noqa: E402
from lib.pipeline import OSM_DIR, load_config  # noqa: E402
from lib.progress import ProgressTracker, run_pool  # noqa: E402
from lib.subgraph import load_local_subgraph  # noqa: E402
from lib.timing import StepTimer, phase  # noqa: E402
from graph_building.gather_route_subgraphs import cell_dir_for  # noqa: E402

SCRIPT_NAME = "build_access_edges.py"


def route_selected_pairs_for_cell(subgraph, hut_sources: list, selected_targets_by_hut: dict,
                                   snaps: dict, variants: list, timer: StepTimer = None) -> list:
    """hut_sources: this cell's core huts (build_hub_edges.py already proved these are the only
    valid Dijkstra sources for access edges, A1). selected_targets_by_hut: {hut_id: [access hub
    dict, ...]} - EXACTLY the targets select_approach_pairs.py kept for that hut; a hut with an
    empty or missing list here is simply not routed.

    Returns one dict per materialized record, access->hut oriented (A3): the path is walked
    hut->access (matching build_hub_edges.py's own direction, so both passes agree on which
    subgraph/snap state produced a given distance), then reversed before being packed - reverse
    path.coords, SWAP ascent_m/descent_m (base-graph ascent/descent is stored in a fixed u->v
    direction; a path walking v->u must swap them, same rule accumulate_path already applies per
    edge), THEN call fold_endpoint_snaps with (access_snap, hut_snap) order - fold_endpoint_snaps
    attributes each end's gap differently for departure vs. arrival, so it must see the
    already-reoriented path and the two snaps in the SAME (access-first) order the caller will
    store the record in."""
    timer = timer if timer is not None else StepTimer()
    if not hut_sources:
        return []

    with timer.step("build_base_arrays"):
        base_arrays = build_base_igraph_arrays(subgraph, snaps)

    records = []
    for variant in variants:
        mask = variants_lib.edge_mask(subgraph.local_edges, variant)
        with timer.step("build_igraph"):
            graph, hub_vertex, vertex_coords = build_igraph_from_base(base_arrays, edge_mask=mask)

        for hub in hut_sources:
            src_key = (hub["type"], hub["id"])
            targets = selected_targets_by_hut.get(hub["id"], [])
            if src_key not in hub_vertex or not targets:
                continue
            src_v = hub_vertex[src_key]
            routable = [t for t in targets if (t["type"], t["id"]) in hub_vertex]
            if not routable:
                continue
            target_vs = [hub_vertex[(t["type"], t["id"])] for t in routable]
            unique_path_vs = sorted({tv for tv in target_vs if tv != src_v})
            with timer.step("paths"):
                epaths = (
                    graph.get_shortest_paths(src_v, to=unique_path_vs, weights="weight", output="epath")
                    if unique_path_vs else []
                )
            path_by_vertex = {
                tv: accumulate_path(graph, vertex_coords, src_v, tv, epath)
                for tv, epath in zip(unique_path_vs, epaths)
            }

            src_snap = snaps[src_key]
            for t, tv in zip(routable, target_vs):
                path = (path_by_vertex[tv] if tv != src_v
                        else accumulate_path(graph, vertex_coords, src_v, tv, []))
                tgt_snap = snaps[(t["type"], t["id"])]
                # A3: reverse before folding - fold_endpoint_snaps' gap attribution depends on
                # traversal direction, so it must see the path already reoriented access->hut.
                reversed_path = path._replace(
                    coords=list(reversed(path.coords)),
                    ascent_m=path.descent_m, descent_m=path.ascent_m,
                    base_edge_ids=list(reversed(path.base_edge_ids)),
                )
                snap_m, ascent_m, descent_m = fold_endpoint_snaps(reversed_path, tgt_snap, src_snap)
                geometry = [(t["lon"], t["lat"]), *reversed_path.coords, (hub["lon"], hub["lat"])]
                records.append({
                    "from_id": t["id"], "from_type": t["type"],
                    "to_id": hub["id"], "to_type": hub["type"],
                    "variant": variant.code,
                    "distance_m": float(reversed_path.distance_m + snap_m),
                    "road_m": float(reversed_path.road_m),
                    "ascent_m": float(ascent_m), "descent_m": float(descent_m),
                    "max_ele_m": (float(reversed_path.max_ele_m)
                                  if np.isfinite(reversed_path.max_ele_m) else 0.0),
                    "ungraded_m": float(reversed_path.ungraded_m),
                    "inferred_m": float(reversed_path.inferred_m),
                    "snap_m": float(snap_m),
                    "sac_rank": int(reversed_path.sac_rank),
                    "via_ferrata": bool(reversed_path.via_ferrata),
                    "geometry": geometry,
                    "base_edge_ids": reversed_path.base_edge_ids,
                })
    return records


def _run_cell(args):
    route_subgraphs_dir, base_graph_dir, cell_id, hut_sources, selected_targets_by_hut, \
        variants, local_persisted = args
    t0 = time.time()
    timer = StepTimer()
    with timer.step("gather_subgraph"):
        subgraph = load_local_subgraph(cell_dir_for(route_subgraphs_dir, cell_id), base_graph_dir)
    keys = {(h["type"], h["id"]) for h in hut_sources}
    for targets in selected_targets_by_hut.values():
        keys.update((t["type"], t["id"]) for t in targets)
    with timer.step("snap"):
        local_snaps = hub_snap.reconstruct_local_snaps(subgraph, keys, local_persisted)
    records = route_selected_pairs_for_cell(
        subgraph, hut_sources, selected_targets_by_hut, local_snaps, variants=variants, timer=timer,
    )
    return {"cell_id": cell_id, "elapsed_s": time.time() - t0, "records": records, "timer": timer}


if __name__ == "__main__":
    config = load_config()
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-graph-dir", default=str(OSM_DIR / "base_graph"))
    parser.add_argument("--route-subgraphs-dir", default=str(OSM_DIR / "route_subgraphs"))
    parser.add_argument("--selected-pairs", default=str(OSM_DIR / "selected_access_pairs.npy"))
    parser.add_argument("--out-dir", default=str(OSM_DIR),
                         help="directory to write start_edges/ into")
    parser.add_argument("--workers", type=int, default=None)
    args = parser.parse_args()

    manifest = binfmt.load_manifest(Path(args.base_graph_dir) / "manifest.json")
    grid = Grid(manifest["bbox"], manifest["tile_size_km"])

    all_hubs_flat = load_all_hubs(OSM_DIR)
    hub_by_key = {(h["type"], h["id"]): h for h in all_hubs_flat}
    huts_by_cell = bucket_by_cell([h for h in all_hubs_flat if h["type"] == binfmt.TYPE_HUT], grid)

    selected = binfmt.load_array(Path(args.selected_pairs), mmap=False)
    print(f"selected pairs to materialize: {len(selected):,}", flush=True)

    hub_snaps_arr = binfmt.load_array(Path(args.out_dir) / "hub_snaps.npy", mmap=False)
    hub_snap_interior_arr = binfmt.load_array(
        Path(args.out_dir) / "hub_snap_interior.npy", mmap=False
    )
    persisted_snaps = hub_snap.load_persisted_snaps(hub_snaps_arr, hub_snap_interior_arr)

    active_variants = variants_lib.enabled_variants(config)

    # {hut_id: {access hub dict, ...}} across every variant - a cell's routing pass reroutes every
    # active variant regardless of which one(s) selected the pair (spec B5: it re-runs one
    # Dijkstra per (hut, variant), the same shape as build_hub_edges.py's first pass).
    targets_by_hut = {}
    for r in selected:
        hut_id = int(r["hut_id"])
        key = (int(r["start_type"]), int(r["start_id"]))
        targets_by_hut.setdefault(hut_id, {})[key] = hub_by_key[key]

    tasks = []
    for cell_id, cell_huts in huts_by_cell.items():
        selected_targets_by_hut = {
            h["id"]: list(targets_by_hut.get(h["id"], {}).values())
            for h in cell_huts if h["id"] in targets_by_hut
        }
        if not selected_targets_by_hut:
            continue
        keys = {(h["type"], h["id"]) for h in cell_huts}
        for targets in selected_targets_by_hut.values():
            keys.update((t["type"], t["id"]) for t in targets)
        local_persisted = {k: persisted_snaps[k] for k in keys if k in persisted_snaps}
        tasks.append((
            Path(args.route_subgraphs_dir), Path(args.base_graph_dir), cell_id, cell_huts,
            selected_targets_by_hut, active_variants, local_persisted,
        ))

    total = len(tasks)
    print(f"{total} cells with selected pairs to materialize", flush=True)
    shard_records = []
    tracker = ProgressTracker(total)
    run_timer = StepTimer()
    with phase(SCRIPT_NAME, "build_access_edges", n_cells=total,
               n_pairs=len(selected), workers=args.workers) as meta:
        for result in run_pool(tasks, _run_cell, workers=args.workers):
            shard_records.append(result["records"])
            run_timer.merge(result["timer"])
            eta = tracker.eta_suffix()
            print(
                f"[{tracker.completed}/{total}] cell {result['cell_id']}: "
                f"{result['elapsed_s']:.1f}s -> {len(result['records'])} records | {eta}",
                flush=True,
            )
        meta.update(run_timer.as_meta())

    print(f"step totals (summed over workers): {run_timer.summary()}", flush=True)

    access_records = [r for shard in shard_records for r in shard]
    print(f"materialized access edges: {len(access_records)}", flush=True)

    out_dir = Path(args.out_dir)
    write_edge_records(access_records, out_dir / "start_edges", write_edge_ids=False)
    print(f"written {out_dir / 'start_edges'}")
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd pipeline && pixi run pytest tests/test_build_access_edges.py -v`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `cd pipeline && pixi run pytest -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd pipeline
git add phases/graph_building/build_access_edges.py tests/test_build_access_edges.py
git commit -m "$(cat <<'EOF'
feat(pipeline): add build_access_edges.py (geometry only for selected pairs)

Implements B5/B6 of spec 2026-09-02-hub-edge-scaling-design.md: the second and final igraph pass
over each cell's cached subgraph, restricted to select_approach_pairs.py's survivor list (tens of
thousands of pairs, not the ~1M full routed set projected at the new access-point density). Writes
the final start_edges/{records,geometry}.npy - geometry.npy drops from a projected ~14GB to well
under 1GB (spec B6). Reuses build_hub_edges.py's hut-sourced routing direction (A1) and applies the
same A3 path-reorientation before storing access->hut, so both passes agree on direction.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_017cYyJEYLeD7yGBdMP27QrV
EOF
)"
```

---

## Task 6: Rewire the `doit` DAG (B1, B7) and drop the stale artifact (P3)

Points `task_build_hub_edges` at its new targets (`hut_edges/records.npy` +
`access_distances.npy`), adds `task_select_approach_pairs` and `task_build_access_edges`, and
repoints every task that used to depend on `build_hub_edges` for `start_edges/` (namely
`task_build_profiles`, `task_build_start_edge_tiles`, `task_build_approach_table`) at
`build_access_edges` instead. Also deletes the stale, un-tracked 654 MB
`huts/public/data/start-edge-stats.json` noticed in spec P3 (not in `PUBLIC_FILES`, so
`copy_public_data` never touches it — this is a one-time manual cleanup, not a DAG change).

This task does not run `doit` (per the root `CLAUDE.md`'s standing restriction) — it is validated
by confirming the wiring is internally consistent (every `file_dep`/`task_dep`/`targets` triple
resolves) and, where a `pipeline_task()`/task-shape test already exists, by the existing test
suite.

**Files:**
- Modify: `pipeline/dag/graph_building.py`
- Modify: `pipeline/dag/postprocessing.py`
- Modify: `pipeline/dag/elevation.py`
- Modify: `pipeline/pipeline.config.json` comment/doc note (optional — `approach.selectK` already
  added in Task 4)

**Interfaces:**
- Consumes: `lib.doit_support.cli_param`/`pipeline_task`/`tracking_param`, `lib.binfmt`'s
  `ACCESS_DISTANCE_SCHEMA_VERSION` (Task 3).
- Produces: `task_build_hub_edges` (retargeted), `task_select_approach_pairs` (new),
  `task_build_access_edges` (new) in `dag/graph_building.py`/`dag/postprocessing.py`; updated
  `task_dep`/`file_dep` on `task_build_profiles` (`dag/elevation.py`),
  `task_build_start_edge_tiles`/`task_build_approach_table` (`dag/postprocessing.py`).

- [ ] **Step 1: Update `task_build_hub_edges` in `dag/graph_building.py`**

Change (currently lines 93–112):

```python
def task_build_hub_edges():
    return pipeline_task(
        "phases/graph_building/build_hub_edges.py",
        params=[cli_param("max_edge_km", "max-edge-km", float, CONFIG["graph"]["maxEdgeKm"])],
        tracking_params=[
            tracking_param("variants_json", str, json.dumps(CONFIG["graph"]["variants"], sort_keys=True)),
            _EDGE_SCHEMA_VERSION_PARAM, _SNAP_SCHEMA_VERSION_PARAM, _RECORD_SCHEMA_VERSION_PARAM,
        ],
        task_dep=["snap_hubs", "gather_route_subgraphs"],
        file_dep=[
            OSM_DIR / "base_graph" / "manifest.json",
            OSM_DIR / "huts.geojson", OSM_DIR / "start_points.npy",
            OSM_DIR / "hub_snaps.npy", OSM_DIR / "hub_snap_interior.npy",
            OSM_DIR / "route_subgraphs" / "manifest.json",
        ],
        targets=[OSM_DIR / "hut_edges" / "records.npy", OSM_DIR / "start_edges" / "records.npy"],
    )
```

to:

```python
def task_build_hub_edges():
    # B1/B3 of spec 2026-09-02-hub-edge-scaling-design.md: this task now writes hut_edges/ (full
    # geometry, unchanged) and access_distances.npy (distance/time scalars only, no geometry) -
    # start_edges/ is now build_access_edges' target, materialized only for the pairs
    # select_approach_pairs.py selects out of access_distances.npy.
    return pipeline_task(
        "phases/graph_building/build_hub_edges.py",
        params=[cli_param("max_edge_km", "max-edge-km", float, CONFIG["graph"]["maxEdgeKm"])],
        tracking_params=[
            tracking_param("variants_json", str, json.dumps(CONFIG["graph"]["variants"], sort_keys=True)),
            _EDGE_SCHEMA_VERSION_PARAM, _SNAP_SCHEMA_VERSION_PARAM, _RECORD_SCHEMA_VERSION_PARAM,
            _ACCESS_DISTANCE_SCHEMA_VERSION_PARAM,
        ],
        task_dep=["snap_hubs", "gather_route_subgraphs"],
        file_dep=[
            OSM_DIR / "base_graph" / "manifest.json",
            OSM_DIR / "huts.geojson", OSM_DIR / "start_points.npy",
            OSM_DIR / "hub_snaps.npy", OSM_DIR / "hub_snap_interior.npy",
            OSM_DIR / "route_subgraphs" / "manifest.json",
        ],
        targets=[OSM_DIR / "hut_edges" / "records.npy", OSM_DIR / "access_distances.npy"],
    )


def task_select_approach_pairs():
    # B2/B4: global selection over access_distances.npy - must run whole-table (loop-closure
    # reverse index isn't cell-local), so it is its own task rather than in-worker selection.
    return pipeline_task(
        "phases/postprocessing/select_approach_pairs.py",
        params=[cli_param("k", "k", int, CONFIG["approach"].get("selectK", 20))],
        task_dep=["build_hub_edges"],
        file_dep=[OSM_DIR / "access_distances.npy"],
        targets=[OSM_DIR / "selected_access_pairs.npy"],
    )


def task_build_access_edges():
    # B5/B6: the second and final igraph pass, restricted to select_approach_pairs.py's survivor
    # list - this is what writes the actual start_edges/ every downstream consumer reads.
    return pipeline_task(
        "phases/graph_building/build_access_edges.py",
        tracking_params=[
            tracking_param("variants_json", str, json.dumps(CONFIG["graph"]["variants"], sort_keys=True)),
            _EDGE_SCHEMA_VERSION_PARAM, _SNAP_SCHEMA_VERSION_PARAM, _RECORD_SCHEMA_VERSION_PARAM,
        ],
        task_dep=["select_approach_pairs", "snap_hubs", "gather_route_subgraphs"],
        file_dep=[
            OSM_DIR / "base_graph" / "manifest.json",
            OSM_DIR / "huts.geojson", OSM_DIR / "start_points.npy",
            OSM_DIR / "hub_snaps.npy", OSM_DIR / "hub_snap_interior.npy",
            OSM_DIR / "route_subgraphs" / "manifest.json",
            OSM_DIR / "selected_access_pairs.npy",
        ],
        targets=[OSM_DIR / "start_edges" / "records.npy"],
    )
```

Add the missing tracking-param constant near the top of the file, alongside the existing three:

```python
_ACCESS_DISTANCE_SCHEMA_VERSION_PARAM = tracking_param(
    "access_distance_schema_version", int, binfmt.ACCESS_DISTANCE_SCHEMA_VERSION
)
```

- [ ] **Step 2: Register the two new tasks in `dodo.py`'s task list**

`pipeline/dodo.py`'s `DOIT_CONFIG["default_tasks"]` list needs `select_approach_pairs` and
`build_access_edges` inserted between `build_hub_edges` and `build_profiles` (the order the DAG
already implies via `task_dep`, but `doit`'s default-tasks list is what a bare `doit` invocation
walks). Find the list (it currently reads, abbreviated, `[..., "build_hub_edges", ...,
"build_profiles", ...]`) and insert `"select_approach_pairs", "build_access_edges",` right after
`"build_hub_edges"` and before `"build_profiles"`.

- [ ] **Step 3: Repoint `task_build_profiles` in `dag/elevation.py`**

Change (currently, per the earlier grep, around line 62-82):

```python
def task_build_profiles():
    return pipeline_task(
        "phases/elevation/build_profiles.py",
        params=[cli_param("profile_points", "profile-points", int,
                          CONFIG["dem"].get("profilePoints", 30))],
        task_dep=["build_hub_edges", "match_tour_edges"],  # same files they mutate in place
        file_dep=[
            OSM_DIR / "base_graph" / "interior_ele.npy",
            OSM_DIR / "hut_edges" / "records.npy", OSM_DIR / "start_edges" / "records.npy",
            OSM_DIR / "tour_edges" / "records.npy",
        ],
```

to:

```python
def task_build_profiles():
    return pipeline_task(
        "phases/elevation/build_profiles.py",
        params=[cli_param("profile_points", "profile-points", int,
                          CONFIG["dem"].get("profilePoints", 30))],
        # start_edges/ is now build_access_edges' target, not build_hub_edges' (spec
        # 2026-09-02-hub-edge-scaling-design.md B1/B7) - same "mutates records.npy in place
        # without declaring it as a target" reasoning as before, just against the new owner.
        task_dep=["build_hub_edges", "build_access_edges", "match_tour_edges"],
        file_dep=[
            OSM_DIR / "base_graph" / "interior_ele.npy",
            OSM_DIR / "hut_edges" / "records.npy", OSM_DIR / "start_edges" / "records.npy",
            OSM_DIR / "tour_edges" / "records.npy",
        ],
```

(the rest of the function — `targets=[...]` etc. — is unchanged).

- [ ] **Step 4: Repoint `task_build_start_edge_tiles` and `task_build_approach_table` in `dag/postprocessing.py`**

Both already only `file_dep` on `OSM_DIR / "start_edges" / "records.npy"` and `task_dep=
["build_profiles"]` — that stays correct as long as `build_profiles` itself now depends on
`build_access_edges` (Step 3), since `build_profiles` is what rewrites `records.npy`'s
`profile_offset`/`profile_count` in place. No change needed to
`task_build_start_edge_tiles`/`task_build_approach_table` themselves — confirm this by re-reading
both after Step 3 and checking neither references `build_hub_edges` directly (they don't; they
only reference `build_profiles`).

- [ ] **Step 5: Delete the stale `start-edge-stats.json` public artifact**

```bash
rm -f /home/superhellth/open-alps/huts/public/data/start-edge-stats.json
```

(P3 note: this file is 654 MB, not in `dodo.py`'s `PUBLIC_FILES`, and is a stale artifact of an
earlier run — `copy_public_data` never wrote or reads it, so removing it is safe and has no DAG
consequence.)

- [ ] **Step 6: Sanity-check the wiring**

Run: `cd pipeline && python -c "
import sys
sys.path.insert(0, '.')
import dodo
print('dodo.py imports cleanly')
for name in ('task_build_hub_edges', 'task_select_approach_pairs', 'task_build_access_edges'):
    pass
"`

This only proves `dodo.py` and its `dag/*.py` modules still import without error (a real
`pipeline.config.json`/`data/` layout is assumed present in this repo checkout, per
`pipeline/README.md`'s setup — if `pixi run doit list` is available in this environment, prefer
running that instead: `cd pipeline && pixi run doit list 2>&1 | grep -E "build_hub_edges|select_approach_pairs|build_access_edges|build_profiles"`
should show all four tasks with no error, confirming doit accepted the graph shape (this does NOT
execute any task — `doit list` is a dry inspection, never runs an action).

- [ ] **Step 7: Run the full pytest suite once more**

Run: `cd pipeline && pixi run pytest -v`
Expected: PASS (no test exercises `dodo.py`'s task graph directly, so this step reconfirms nothing
in the DAG rewiring broke unrelated Python import paths, e.g. via `pipeline_task`/`cli_param`
shared helpers).

- [ ] **Step 8: Commit**

```bash
cd pipeline
git add dag/graph_building.py dag/postprocessing.py dag/elevation.py dodo.py
git add -f -- '../huts/public/data/start-edge-stats.json' 2>/dev/null || true
git rm --cached -- '../huts/public/data/start-edge-stats.json' 2>/dev/null || true
git commit -m "$(cat <<'EOF'
feat(pipeline): wire select_approach_pairs/build_access_edges into the doit DAG

Implements B1/B7 of spec 2026-09-02-hub-edge-scaling-design.md: build_hub_edges now targets
hut_edges/records.npy + access_distances.npy; select_approach_pairs and build_access_edges are new
tasks between it and build_profiles; build_profiles' task_dep on start_edges' owner moves from
build_hub_edges to build_access_edges (same in-place-rewrite reasoning as before, new owner).
Also removes huts/public/data/start-edge-stats.json - a stale 654MB artifact not in PUBLIC_FILES,
so copy_public_data never wrote or reads it (spec P3).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_017cYyJEYLeD7yGBdMP27QrV
EOF
)"
```

(If `huts/public/data/start-edge-stats.json` was never tracked by git in the first place — likely,
since `huts/public/data/` holds pipeline-copied outputs — the two `git add -f`/`git rm --cached`
lines above are harmless no-ops; `rm -f` in Step 5 is what actually matters. Check `git status`
before committing and drop those two lines entirely if the file shows as untracked/already gone
rather than staged for deletion.)

---

## Task 7: Fix `filter_start_points.py`'s longitude bug, batch its KD-tree query (C1, C2)

`filter_to_hut_range` builds a `cKDTree` over raw `(lon, lat)` degrees and thresholds at
`max_edge_km * (1/111.320)` degrees — that constant is km-per-degree of **latitude**, so at
47.5°N (where a degree of longitude is only ~75.2 km) the filter is an ellipse squashed east-west
and silently drops points up to ~30 km due east/west of a hut that should have been kept (spec
C1 — the error is one-sided, it never wrongly admits a point). Fixed by projecting into
approximately-equal-scale coordinates (`lon * cos(mid_lat)`, matching `lib/grid.py`'s
`km_per_deg_lng`) before building the tree. C2 batches the per-point `.query()` loop into one
vectorized call while the tree is already being rebuilt for C1 (buys no measurable time per spec —
`filter_start_points` runs in 3.48s end to end — but is the natural thing to do while touching this
function anyway). Lands **last**, after Tasks 1–6, because it makes the kept set larger, and doing
that before the scaling fixes land would make runtime worse, not better (spec C1: "it must land
after them, or it makes the current runtime worse").

**Files:**
- Modify: `pipeline/phases/preprocessing/filter_start_points.py`
- Test: `pipeline/tests/test_filter_start_points.py`

**Interfaces:**
- Consumes: `lib.grid.KM_PER_DEG_LAT` (new import — matches the existing `km_per_deg_lng`
  convention `lib/grid.py`'s `Grid.__init__` and `lib/hub_snap.py`'s `_project_m` both use).
- Produces: `filter_to_hut_range(start_points, hut_coords, max_edge_km) -> list` — same signature
  and return shape, corrected math + vectorized query internally.

- [ ] **Step 1: Write the failing regression test**

Add to `pipeline/tests/test_filter_start_points.py` (near the top, after the existing
`filter_to_hut_range` tests):

```python
def test_keeps_a_point_due_east_at_the_true_km_distance():
    # Regression for spec C1: the old filter thresholded at max_edge_km/111.320 degrees - the
    # km-per-degree of LATITUDE, not longitude. At 47.5N a degree of longitude is ~75.2km, so a
    # point exactly 20km due east of a hut (well inside a 30km cap) sat at 20/75.2 = 0.266 deg,
    # OUTSIDE the old 30/111.320 = 0.269deg threshold by a hair for some points, and farther out
    # points up to ~30km east were dropped outright even though they're inside range. Use a point
    # at a longitude offset that is trail-irrelevant-but-real-world-close: 25km due east at
    # 47.5N is 25/75.2 = 0.3325 deg of longitude - OUTSIDE the old latitude-based threshold
    # (30/111.320 = 0.2695 deg) even though 25km < 30km max_edge_km.
    lat = 47.5
    hut_coords = np.array([(11.0, lat)])
    lon_offset_deg_for_25km_east = 25.0 / (111.320 * np.cos(np.radians(lat)))
    points = [{"lon": 11.0 + lon_offset_deg_for_25km_east, "lat": lat, "osm_id": 1, "type": "parking"}]
    kept = filter_to_hut_range(points, hut_coords, max_edge_km=30.0)
    assert len(kept) == 1


def test_still_drops_a_point_genuinely_farther_than_max_edge_km_in_any_direction():
    lat = 47.5
    hut_coords = np.array([(11.0, lat)])
    lon_offset_deg_for_50km_east = 50.0 / (111.320 * np.cos(np.radians(lat)))
    points = [{"lon": 11.0 + lon_offset_deg_for_50km_east, "lat": lat, "osm_id": 1, "type": "parking"}]
    kept = filter_to_hut_range(points, hut_coords, max_edge_km=30.0)
    assert len(kept) == 0


def test_still_drops_a_point_genuinely_far_north_south():
    # sanity check that the latitude axis (unaffected by the bug) still behaves correctly after
    # the fix - km-per-degree of latitude is ~constant everywhere, so no projection is needed
    # there, only on longitude.
    hut_coords = np.array([(11.0, 47.0)])
    points = [{"lon": 11.0, "lat": 47.0 + 1.0, "osm_id": 1, "type": "parking"}]  # ~111km north
    kept = filter_to_hut_range(points, hut_coords, max_edge_km=30.0)
    assert len(kept) == 0
```

- [ ] **Step 2: Run to verify the new tests fail**

Run: `cd pipeline && pixi run pytest tests/test_filter_start_points.py -k "east or north_south" -v`
Expected: FAIL on `test_keeps_a_point_due_east_at_the_true_km_distance` (the point is wrongly
dropped by the current, unprojected filter). The other two should already pass (they're not
exercising the bug), confirming they're true regression guards, not accidental passes.

- [ ] **Step 3: Fix `filter_to_hut_range`**

In `pipeline/phases/preprocessing/filter_start_points.py`, add the import:

```python
from lib.grid import KM_PER_DEG_LAT  # noqa: E402
```

(alongside the existing `from lib.pipeline import OSM_DIR, load_config` import line).

Replace `filter_to_hut_range` (currently lines 51–61):

```python
def filter_to_hut_range(start_points: list, hut_coords: np.ndarray, max_edge_km: float) -> list:
    if not start_points or len(hut_coords) == 0:
        return []
    hut_tree = cKDTree(hut_coords)
    deg_per_km = 1 / 111.320
    kept = []
    for p in start_points:
        dist_deg, _ = hut_tree.query((p["lon"], p["lat"]), k=1)
        if dist_deg <= max_edge_km * deg_per_km:
            kept.append(p)
    return kept
```

with:

```python
def filter_to_hut_range(start_points: list, hut_coords: np.ndarray, max_edge_km: float) -> list:
    """C1/C2 of spec 2026-09-02-hub-edge-scaling-design.md: the old version built a cKDTree over
    raw (lon, lat) degrees and thresholded at max_edge_km / KM_PER_DEG_LAT - that constant is
    km-per-degree of LATITUDE, so at higher latitudes (a degree of longitude is shorter than a
    degree of latitude everywhere outside the equator) the filter was an ellipse squashed
    east-west, silently dropping valid trailheads up to max_edge_km due east/west of a hut. Fixed
    by scaling longitude by cos(mid_lat) before building the tree - the same projection
    lib/grid.py's Grid.km_per_deg_lng and lib/hub_snap.py's _project_m already use - so both axes
    of the tree are in the same locally-equal-scale units before thresholding.

    C2: also batches the per-point query into one vectorized cKDTree.query call over the whole
    array (was a Python loop, one query() per point) - no measurable time saved
    (filter_start_points runs in 3.48s end to end), done because C1 already forces the tree to be
    rebuilt in projected coordinates anyway."""
    if not start_points or len(hut_coords) == 0:
        return []
    mid_lat = float(np.mean(hut_coords[:, 1]))
    lng_scale = math.cos(math.radians(mid_lat))
    hut_tree = cKDTree(np.column_stack([hut_coords[:, 0] * lng_scale, hut_coords[:, 1]]))

    point_lons = np.array([p["lon"] for p in start_points])
    point_lats = np.array([p["lat"] for p in start_points])
    query_points = np.column_stack([point_lons * lng_scale, point_lats])
    dist_deg, _ = hut_tree.query(query_points, k=1)

    deg_per_km = 1 / KM_PER_DEG_LAT
    max_dist_deg = max_edge_km * deg_per_km
    return [p for p, d in zip(start_points, dist_deg) if d <= max_dist_deg]
```

Add `import math` to the top of the file (alongside the existing `import json`/`sys`/`Path`
imports) — it is not currently imported.

- [ ] **Step 4: Run to verify all three tests pass**

Run: `cd pipeline && pixi run pytest tests/test_filter_start_points.py -v`
Expected: PASS — including `test_preserves_input_order_of_survivors` (Step 3's list-comprehension
form preserves input order the same way the original loop did) and the other pre-existing tests
(`test_keeps_point_within_range_of_a_hut`, `test_drops_point_far_from_every_hut`,
`test_keeps_point_near_the_second_hut_only`), which used points close enough to the equator-ish
`HUT_COORDS` fixture (`lat=47.0`) that the projection correction doesn't flip their pass/fail
status — verify this by reading the diff between expected/actual for each; if any of those three
now fail, the fixture's longitude offsets were implicitly relying on the bug and need adjusting to
the same true-distance style used in Step 1's new tests (recompute the offset via
`km_offset / (111.320 * cos(radians(47.0)))` instead of a bare degree literal).

- [ ] **Step 5: Run the full pipeline suite**

Run: `cd pipeline && pixi run pytest -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd pipeline
git add phases/preprocessing/filter_start_points.py tests/test_filter_start_points.py
git commit -m "$(cat <<'EOF'
fix(pipeline): correct filter_start_points' longitude scale, batch its KD-tree query

filter_to_hut_range thresholded at max_edge_km / KM_PER_DEG_LAT in raw (lon, lat) degree space -
that constant is km-per-degree of LATITUDE, so the filter was an ellipse squashed east-west at any
latitude away from the equator, silently dropping valid trailheads up to max_edge_km due east/west
of a hut (spec 2026-09-02-hub-edge-scaling-design.md C1). Fixed by scaling longitude by
cos(mid_lat), matching lib/grid.py's own km_per_deg_lng convention. Also batches the per-point
query loop into one vectorized cKDTree.query call (C2) while the tree is already being rebuilt for
the fix.

Lands last, after the routing-direction inversion and geometry-selection split (A/B, prior
commits) - fixing this bug grows the kept access-point set further, and landing it before those
scaling fixes would make the pipeline's runtime worse rather than better.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_017cYyJEYLeD7yGBdMP27QrV
EOF
)"
```

---

## Self-Review Notes

**Spec coverage:**
- A1–A3 (invert direction, reorient access records) → Task 3.
- A4 (timer step for `build_base_igraph_arrays`) → Task 1 (landed early as the prerequisite the
  spec calls for) and reused in Task 3's rewrite.
- A5 (scheduling on hut count) → Task 3, Step group C.
- A6 (A and B must ship together / memory wall) → satisfied by construction: Task 3 already writes
  `access_distances.npy` instead of full geometry access records, so the inverted direction never
  ships with the old full-geometry access emit turned on.
- B1 (task DAG shape) → Task 6.
- B2 (why a separate global step) → Task 4.
- B3 (intermediate contract) → Task 3 (`ACCESS_DISTANCE_DTYPE` + `write_access_distances`).
- B4 (over-selection factor, k=20) → Task 4.
- B5 (what `build_access_edges` materializes, reverse-index closure over every variant) → Tasks 4
  and 5.
- B6 (expected sizes) → not independently coded (a consequence of B1–B5's implementation, not a
  separate task) — noted in Task 5's commit message.
- B7 (`build_approach_table.py` after this) → confirmed unchanged in Task 6, Step 4 (it already
  only depends on `start_edges/records.npy` + `build_profiles`, both still correct after the
  rewire).
- C1/C2 (longitude bug, batched query) → Task 7.
- C3 (station clustering) — **not implemented**, per spec's own open questions (placement + id
  semantics unresolved) and this plan's Global Constraints.
- C4 (separate `maxApproachKm`) — **rejected in the spec**, not implemented.
- D1–D3 (`hub_snap` cKDTree fix) → Task 2.
- Open question 4 (validation strategy: `--only-cell`/analysis script diffing against current
  `start_edges/records.npy`) — **not included as a coded task**: it requires a real, already-built
  `data/osm/` (base graph, route subgraphs, existing `start_edges/records.npy` to diff against),
  and running any such script against real `data/` is exactly the category of action the root
  `CLAUDE.md` requires explicit user confirmation for. Flagging this explicitly rather than
  silently dropping it: **before this plan's changes are ever run against real `data/`, ask the
  user whether to write the `--only-cell` validation script (spec open question 4) first**, and get
  their explicit go-ahead before running anything.
- Open question 5 (measure `build_base_igraph_arrays` cost at the new candidate density) — the
  instrumentation lands in Task 1, but the actual *measurement* only happens on a real run, which
  (per the same restriction) requires separate user confirmation and is out of scope here.
- Open question 2 (C3 placement/id semantics) — genuinely open in the spec; not this plan's to
  resolve.

**Placeholder scan:** every step above either shows the exact code to write/replace or the exact
shell command to run; no "add appropriate handling" or "similar to Task N" steps remain.

**Type consistency:** `compute_hub_edges_for_cell`'s new `(hut_records, access_rows)` return shape
is used consistently across Task 3 (definition + `_run_cell`), and `access_rows`' dict keys
(`hut_id/start_id/start_type/variant/distance_m/time_s`) match `ACCESS_DISTANCE_DTYPE`'s field
names/order used by `write_access_distances` (Task 3) and read back by `select_pairs` (Task 4) and
`build_access_edges.py`'s `targets_by_hut` construction (Task 5). `route_selected_pairs_for_cell`'s
returned record dicts match `write_edge_records`'s expected shape exactly (same field set
`compute_hub_edges_for_cell`'s `hut_records` already used, verified against
`pipeline/lib/edge_output.py`'s `write_edge_records` field list).
