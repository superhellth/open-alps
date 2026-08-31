# Plan 002: Cache the base-graph gather across tour legs in `match_tour_edges.py`

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 3e59f51..HEAD -- pipeline/phases/graph_building/match_tour_edges.py pipeline/lib/subgraph.py pipeline/dag/graph_building.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition — this file is under **active
> development** on the `feat/official-tours-integration` branch (see "Why
> this matters" below), so drift is more likely here than in most plans.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED
- **Depends on**: none (but see "active development" note below)
- **Category**: perf
- **Planned at**: commit `3e59f51`, 2026-08-31

## Why this matters

`pipeline/phases/graph_building/match_tour_edges.py`'s main loop calls
`gather_subgraph_for_bounds(base_graph_dir, grid, bounds)` (imported from `lib/subgraph.py`) once
**per tour leg**, inside a nested `for tour in tours: for leg_index, from_hut, to_hut in legs:`
loop, with no caching across legs or tours. Each call reopens 6 memory-mapped base-graph arrays
(`nodes.npy`, `cell_index.npy`, `node_edge_index.npy`, `node_edge_ids.npy`, `edges.npy`,
`interior.npy`) from disk and rebuilds the cell-union + one-hop-closure gather from scratch.

The codebase already solved exactly this problem for the hub-edge path: `build_hub_edges.py` used
to do a similar per-query gather and was split into `gather_route_subgraphs.py` (persists a
per-cell `LocalSubgraph` cache under `data/osm/route_subgraphs/`) plus `build_hub_edges.py` (loads
the cache and parallelizes cell processing via `ProcessPoolExecutor`) — see
`docs/superpowers/plans/2026-08-23-split-build-hub-edges.md` and `gather_route_subgraphs.py`'s own
module docstring. `match_tour_edges.py` never adopted that pattern: it has no `task_dep` on
`gather_route_subgraphs` in `dag/graph_building.py`, and its leg loop is single-threaded.

This is currently masked by small scope — `pipeline/tours/` holds only `Kaisertour` (4 legs) and
`Welser Höhenweg` (5 legs) today — but the root `pipeline/CLAUDE.md` explicitly documents
official-tours integration as an active direction, and every additional tour/leg pays a full
re-gather instead of a cache hit.

**Active-development context**: this file is mid-migration. A design spec
(`docs/superpowers/specs/2026-08-30-tour-folder-ingestion-design.md`) plans to retarget
`match_tour_edges.py`'s *input* (read GPX files from `pipeline/tours/` instead of AV's
Outdooractive-fetched `tours.json`/`tour_traces.json`) and its *endpoint resolution* (nearest hub
of any type — hut, station, or parking — instead of `assign_hut_position`'s chain-position
assignment), while explicitly keeping the "corridor/route/record core" — which is exactly the
`gather_subgraph_for_bounds` → `clip_subgraph_to_bounds` → `match_leg` sequence this plan touches
(see that spec's §6: *"`match_tour_edges.py` is retargeted, not replaced — same corridor/route/
record core, new input and new endpoint resolution"*). That means this perf fix should still be
valid after that migration lands, but if you find the migration has already landed when you start
(check: does the file still import `assign_hut_position`/`reassemble_fragments` from
`lib/tour_geometry.py`, or does it read `.gpx` files from `pipeline/tours/`?), re-read the current
file's leg loop structure before applying the plan — the loop shape should be structurally similar
(still one gather call per leg) but confirm before proceeding, and treat a completely different
loop shape as a STOP condition.

## Current state

`pipeline/phases/graph_building/match_tour_edges.py` (current version, reassembly-based — not yet
migrated):

```python
    with phase(SCRIPT_NAME, "match_tour_edges", n_tours=len(tours)):
        for tour in tours:
            legs = build_tour_legs(tour)
            if not legs:
                continue
            hut_coords_in_order = [hut_coords[h] for h in tour["hutIndices"] if h != -1]
            paths = traces_by_tour_id.get(tour["tourId"], [])
            chains, oriented = _chain_for_tour(
                paths, args.fragment_break_m, hut_coords_in_order, tour["isLoop"],
                oa_points=oa_points_by_tour_id.get(tour["tourId"]),
            )
            all_points = [p for chain in chains for p in chain]

            for leg_index, from_hut, to_hut in legs:
                from_coord, to_coord = hut_coords[from_hut], hut_coords[to_hut]
                gap_ctx = {"tourId": tour["tourId"], "shortCode": tour["shortCode"], "legIndex": leg_index}

                if oriented is None:
                    gaps.append({**gap_ctx, "reason": "chain_not_reassembled", "detail": {"n_chains": len(chains)}})
                    continue

                from_pos = assign_hut_position(oriented, from_coord, args.max_hut_trace_m)
                to_pos = assign_hut_position(oriented, to_coord, args.max_hut_trace_m)
                if from_pos is None or to_pos is None:
                    gaps.append({**gap_ctx, "reason": "hut_far_from_trace",
                                 "detail": {"from_dist_m": from_pos and from_pos[1],
                                            "to_dist_m": to_pos and to_pos[1]}})
                    continue

                leg_points = leg_chain_slice(oriented, from_pos[0], to_pos[0])
                trace_length_m = sum(
                    _leg_segment_m(leg_points[i], leg_points[i + 1]) for i in range(len(leg_points) - 1)
                )
                bounds = corridor_bounds(leg_points or all_points, args.corridor_buffer_m, grid)
                subgraph = clip_subgraph_to_bounds(
                    gather_subgraph_for_bounds(base_graph_dir, grid, bounds), bounds,
                )

                src_key, tgt_key = (binfmt.TYPE_HUT, from_hut), (binfmt.TYPE_HUT, to_hut)
                result = match_leg(subgraph, src_key, tgt_key, persisted_snaps,
                                    trace_length_m, args.length_divergence_ratio)
                if not result["ok"]:
                    gaps.append({**gap_ctx, "reason": result["reason"], "detail": result["detail"]})
                    continue

                record = build_tour_record(
                    from_hut, to_hut, from_coord, to_coord,
                    result["path"], result["src_snap"], result["tgt_snap"],
                )
                all_records.append(record)
                tour_meta_rows.append((tour["tourId"], leg_index))
```

`gather_subgraph_for_bounds` (`lib/subgraph.py:32-`) — reads 6 `.npy` arrays via `binfmt.load_array`
(mmap'd, so file-open cost dominates over data cost) and computes:

```python
def gather_subgraph_for_bounds(base_graph_dir: Path, grid, bounds: dict) -> LocalSubgraph:
    """Gathers every base-graph node/edge whose cell overlaps `bounds`, plus the one-hop edge-
    incidence closure ... factored out so a caller with its own bbox (match_tour_edges.py's
    per-leg corridor, sized off a chain slice rather than a grid cell) can reuse the exact same
    gather instead of re-deriving it from a cell_id it doesn't have."""
    base_graph_dir = Path(base_graph_dir)
    nodes = binfmt.load_array(base_graph_dir / "nodes.npy")
    cell_index = binfmt.load_array(base_graph_dir / "cell_index.npy")
    node_edge_index = binfmt.load_array(base_graph_dir / "node_edge_index.npy")
    node_edge_ids = binfmt.load_array(base_graph_dir / "node_edge_ids.npy")
    edges = binfmt.load_array(base_graph_dir / "edges.npy")
    interior = binfmt.load_array(base_graph_dir / "interior.npy")
    node_ele_path = base_graph_dir / "node_ele.npy"
    interior_ele_path = base_graph_dir / "interior_ele.npy"
    node_ele = (binfmt.load_array(node_ele_path) if node_ele_path.exists()
                else np.zeros(len(nodes), dtype=np.float32))
    interior_ele = (binfmt.load_array(interior_ele_path) if interior_ele_path.exists()
                     else np.zeros(len(interior), dtype=np.float32))

    overlapping_cells = grid.cell_ids_overlapping(bounds)
    # ... (cell-union + one-hop closure, unchanged by this plan)
```

Note its own docstring says the bbox-driven variant exists precisely so a caller with a leg-sized
bbox "can reuse the exact same gather instead of re-deriving it from a cell_id" — i.e. this
function was already designed to be called repeatedly with different small bounds, but nothing
caches the underlying array loads across those calls.

`lib/grid.py`'s `Grid.cell_ids_overlapping(bounds)` returns the list of cell ids a bbox spans —
each `.npy` array open is the dominant fixed cost per call (mmap setup + `cell_ids_overlapping`
scan), not the per-cell slicing itself.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Run pipeline tests | `pixi run pytest -q` (from `pipeline/`) | all pass |
| Run just this file's tests | `pixi run pytest tests/test_match_tour_edges.py tests/test_subgraph.py -q` | all pass |
| Check DAG wiring didn't break | `pixi run pytest tests/test_dodo_wiring.py -q` | all pass |

## Suggested executor toolkit

- Read `pipeline/lib/subgraph.py` in full before starting — `gather_padded_subgraph` (the
  `build_hub_edges.py`-side sibling of `gather_subgraph_for_bounds`) shows the array-loading shape
  this plan should reuse/wrap, not reinvent.
- Read `pipeline/phases/graph_building/gather_route_subgraphs.py` in full — it's the existing
  precedent for "persist a gather so a downstream script doesn't redo it," though this plan takes
  the lighter-weight in-process-cache approach (see Step 1) rather than a separate persisted-cache
  DAG task, since tour legs are far fewer than hub-edge cells and a full second DAG task would be
  disproportionate effort for the current scale.

## Scope

**In scope** (the only files you should modify):
- `pipeline/phases/graph_building/match_tour_edges.py`
- `pipeline/tests/test_match_tour_edges.py` (add test coverage for the cache)

**Out of scope**:
- Do NOT change `lib/subgraph.py`'s `gather_subgraph_for_bounds`/`clip_subgraph_to_bounds`
  functions themselves, or `gather_route_subgraphs.py` — this plan adds caching at the
  `match_tour_edges.py` call-site level, not inside the shared gather function (which is also used
  by other callers with different bounds-reuse patterns).
- Do NOT parallelize the leg loop with a `ProcessPoolExecutor` in this plan — that's a larger,
  higher-risk change (shared mutable `gaps`/`all_records` lists would need reworking for
  multiprocessing) than the caching fix, and caching alone removes most of the redundant I/O for
  the current tour count. If the caching fix alone doesn't bring runtime to an acceptable level at
  real scale, that's a separate follow-up plan.
- Do NOT touch `dag/graph_building.py`'s `task_match_tour_edges` wiring — this plan doesn't add a
  new persisted output or file_dep, only in-process caching within one run.
- Do NOT touch the tour-folder-ingestion migration described in the design spec — if you find
  that migration has already landed, re-verify Current State first per the note above, but don't
  implement the migration itself here.

## Git workflow

- Branch: stay on `feat/official-tours-integration` (the current branch already targets this file)
  unless the operator says otherwise.
- Commit message style: lowercase, `<module>: <imperative description>`, e.g. `graph_building:
  cache base-graph gather across tour legs in match_tour_edges`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add an in-process gather cache keyed by the overlapping-cell tuple

In `match_tour_edges.py`, before the `for tour in tours:` loop, add:

```python
_subgraph_cache: dict[tuple[int, ...], "LocalSubgraph"] = {}


def _cached_gather_for_bounds(base_graph_dir, grid, bounds):
    """Caches gather_subgraph_for_bounds by its overlapping-cell-id tuple, since two legs whose
    corridors fall in the same set of grid cells can reuse the identical LocalSubgraph gather
    (array loads dominate the cost, not the per-call cell-union/closure work) - see
    lib/subgraph.py's gather_subgraph_for_bounds docstring, which already anticipated repeated
    calls with different small bounds from this exact caller."""
    key = tuple(sorted(grid.cell_ids_overlapping(bounds)))
    if key not in _subgraph_cache:
        _subgraph_cache[key] = gather_subgraph_for_bounds(base_graph_dir, grid, bounds)
    return _subgraph_cache[key]
```

Place it near the top of the file, after the existing imports, matching the file's existing
function-ordering convention (grep the file for where other module-level helper functions like
`corridor_bounds` are defined and put it in the same region).

Import `LocalSubgraph` for the type hint from `lib.subgraph` if not already imported (check the
existing `from lib.subgraph import clip_subgraph_to_bounds, gather_subgraph_for_bounds` line and
extend it, or use a string-quoted forward-reference type hint if you'd rather not import a name
used only for typing — match whichever style the rest of the file uses for type hints).

**Verify**: `pixi run python -c "import ast; ast.parse(open('phases/graph_building/match_tour_edges.py').read())"` (from `pipeline/`) → no syntax error.

### Step 2: Route the leg loop's gather call through the cache

Replace:

```python
                subgraph = clip_subgraph_to_bounds(
                    gather_subgraph_for_bounds(base_graph_dir, grid, bounds), bounds,
                )
```

with:

```python
                subgraph = clip_subgraph_to_bounds(
                    _cached_gather_for_bounds(base_graph_dir, grid, bounds), bounds,
                )
```

`clip_subgraph_to_bounds` still runs per-leg on the (now possibly cached) gathered subgraph — it's
cheap array slicing, not file I/O, and correctly narrows the coarser cell-union gather back down to
the leg's own tighter corridor bounds each time, so leg-specific correctness is unaffected by
sharing the underlying gather.

**Verify**: `pixi run pytest tests/test_match_tour_edges.py -q` → all pass, same pass count as
before this step.

### Step 3: Add a cache-hit test

In `tests/test_match_tour_edges.py`, find the existing test fixtures/helpers used to build a small
synthetic base graph (grep the file for how `gather_subgraph_for_bounds` or `LocalSubgraph` is
constructed in existing tests — likely via a `tmp_path` fixture writing small `.npy` arrays, or a
helper shared with `tests/test_subgraph.py`). Using that same fixture pattern, write a test that:

1. Calls `_cached_gather_for_bounds` twice with two different `bounds` dicts whose
   `grid.cell_ids_overlapping(bounds)` returns the **same** cell-id set (e.g. two bounds both
   fully inside one cell).
2. Asserts the second call returns the **same object** (`is`, not `==`) as the first — proving the
   cache hit avoided a re-gather, not just that the results are equal.
3. Add a second case: two bounds whose overlapping cells differ, asserting the results are
   **different objects** (cache correctly keyed, not a blanket single-entry cache).

Model the test's fixture setup after whatever existing test in `tests/test_match_tour_edges.py` or
`tests/test_subgraph.py` already builds a minimal on-disk base graph directory for
`gather_subgraph_for_bounds` — do not invent a new fixture shape if one already exists.

**Verify**: `pixi run pytest tests/test_match_tour_edges.py -k cache -v` → new test(s) pass.

## Test plan

- New tests: cache-hit-same-object and cache-miss-different-object, in
  `tests/test_match_tour_edges.py`, per Step 3.
- Existing tests: `tests/test_match_tour_edges.py`'s golden end-to-end tests (mentioned in
  `pipeline/CLAUDE.md`'s git log as "add golden end-to-end and Rundtour closing-leg tests",
  commit `e73a2a3`) must still pass unchanged — they exercise the full leg-matching path and would
  catch any behavioral change from routing through the cache.
- Verification: `pixi run pytest tests/test_match_tour_edges.py tests/test_subgraph.py -q` → all
  pass, including the new cache tests.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `pixi run pytest -q` (from `pipeline/`) → all pass, same or greater count than baseline
- [ ] `grep -n "_cached_gather_for_bounds" pipeline/phases/graph_building/match_tour_edges.py` shows the helper defined once and called once (replacing the old direct call)
- [ ] New cache tests in `tests/test_match_tour_edges.py` exist and pass
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- The file's leg loop no longer matches the "Current state" excerpt in structure (e.g. the
  tour-folder-ingestion migration landed and changed the loop shape, gather call site, or removed
  `gather_subgraph_for_bounds` entirely) — re-confirm against the live file before adapting the
  plan, and if the gather call site is gone or fundamentally restructured, report back rather than
  guessing where to re-apply the caching idea.
- No existing test fixture builds a small on-disk base graph directory for
  `gather_subgraph_for_bounds`/`LocalSubgraph` that Step 3 can reuse — report and ask whether to
  build one from scratch (larger scope than this plan estimated) or skip the new test and rely on
  the existing golden tests' pass/fail as the only signal (weaker coverage, but still safe).
- A test's verification fails twice after a reasonable fix attempt.

## Maintenance notes

- If tour count/leg count grows enough that even the cached version is too slow, the next step is
  parallelizing the leg loop (deliberately deferred here — see "Out of scope") or persisting the
  cache the way `gather_route_subgraphs.py` does for hub edges.
- If the tour-folder-ingestion migration (docs/superpowers/specs/2026-08-30-tour-folder-ingestion-design.md)
  lands after this plan, its executor should confirm the cache still applies to the retargeted
  loop (same corridor/route/record core, per that spec's §6) rather than silently dropping it.
- A reviewer should check that `_cached_gather_for_bounds`'s cache key
  (`tuple(sorted(grid.cell_ids_overlapping(bounds)))`) is deterministic and hashable — it is,
  since `cell_ids_overlapping` returns a list of ints — and that the cache is process-local (no
  cross-run persistence intended or needed here).
