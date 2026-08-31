# Plan 006: Stop silently dropping isolated degree-2 cycles in `contract_structural`

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 3e59f51..HEAD -- pipeline/lib/contraction.py pipeline/tests/test_contraction.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S (test) + M (fix)
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `3e59f51`, 2026-08-31

## Why this matters

`lib/contraction.py`'s `contract_structural` collapses every run of degree-2 "pass-through" nodes
into one chain edge, walking outward from every degree-≠2 "keep" node (`keep_idxs_list`, line 66's
loop). A closed loop of trail segments where **every** node has degree exactly 2 — i.e. no
junction/dead-end node anywhere on the loop — has no keep-node entry point: `keep_idxs_list` never
contains any of its nodes, so the outer loop never visits it, `visited_edge` never gets set for any
of its edges, and none of its nodes appear in the final `keep_idxs` either. The whole loop's
geometry silently vanishes from the base graph with **no counted or reported metric** — the
function returns successfully as if nothing was missed.

This directly contradicts the pipeline's own established convention of never silently dropping
data — `hub_snap.py`'s `SnapRejection` and `match_tour_edges.py`'s `gaps` list both exist precisely
so failed/skipped cases are counted and reported rather than vanishing (see
`docs/superpowers/specs/2026-08-30-tour-folder-ingestion-design.md`'s explicit requirement:
"Reporting the nearest candidate *and its distance* even when it exceeds the threshold is
required: that is what makes the backlog's coverage gaps measurable rather than invisible").
`contract_structural` currently has no equivalent for its own edge case.

This is likely rare in practice (an isolated OSM way loop with genuinely zero junction nodes
anywhere on it — e.g. a short disconnected circular path fragment, or a mapping artifact), but it
has zero visibility today: nobody would know it happened without reading this code directly.

## Current state

`lib/contraction.py:66-121` (the relevant excerpt — full function is longer; read the live file
before editing):

```python
    keep_idxs_list = np.flatnonzero(keep).tolist()
    total_keep = len(keep_idxs_list)
    for processed, k in enumerate(keep_idxs_list, start=1):
        if progress_every and processed % progress_every == 0:
            print(f"  contract_structural: {processed:,}/{total_keep:,} junction nodes "
                  f"processed -> {len(c_u):,} chain edges so far", flush=True)
        nbrs, edges_here = _neighbors(k)
        for nb, e in zip(nbrs, edges_here):
            if visited_edge[e]:
                continue
            visited_edge[e] = True
            d_sum = float(edges_dist[e])
            road_sum = d_sum if edges_road[e] else 0.0
            ungraded_sum = float(edges_ungraded[e])
            inferred_sum = float(edges_inferred[e])
            sac_max = int(edges_sac_rank[e])
            vf_any = bool(edges_via_ferrata[e])
            ok_all = bool(edges_constrained_ok[e])
            interior = []
            cur = nb
            prev_edge = e
            while not keep[cur]:
                interior.append((float(coords[cur, 0]), float(coords[cur, 1])))
                cnbrs, cedges = _neighbors(cur)
                nxt = None
                for nb2, e2 in zip(cnbrs, cedges):
                    if e2 != prev_edge:
                        nxt = (nb2, e2)
                        break
                if nxt is None:
                    break
                nb2, e2 = nxt
                visited_edge[e2] = True
                d_sum += edges_dist[e2]
                if edges_road[e2]:
                    road_sum += edges_dist[e2]
                ungraded_sum += edges_ungraded[e2]
                inferred_sum += edges_inferred[e2]
                if edges_sac_rank[e2] > sac_max:
                    sac_max = int(edges_sac_rank[e2])
                if edges_via_ferrata[e2]:
                    vf_any = True
                if not edges_constrained_ok[e2]:
                    ok_all = False
                prev_edge, cur = e2, nb2
            c_u.append(k)
            c_v.append(cur)
            c_dist.append(d_sum)
            c_road_m.append(road_sum)
            c_ungraded_m.append(ungraded_sum)
            c_inferred_m.append(inferred_sum)
            c_sac_rank.append(sac_max)
            c_via_ferrata.append(vf_any)
            c_constrained_ok.append(ok_all)
            c_interior.append(interior)
```

`keep = degree != 2` (line ~56, computed earlier from `np.bincount` over edge endpoints). The
outer loop only iterates `keep_idxs_list = np.flatnonzero(keep).tolist()` — nodes with degree ≠ 2.
A node whose only neighbors are also degree-2 has no way to be `k` in that loop, and its incident
edges are only ever marked `visited_edge` from *inside* the inner `while not keep[cur]` walk,
which itself only starts from a `keep`-node's edge. A ring with zero `keep` nodes anywhere on it is
therefore never entered from any direction.

`ContractedGraph` (the dataclass returned, `lib/contraction.py:19-29`) has no field today for
"edges dropped" or "isolated cycles found" — any addition needs a new field or a separate return
value (see Step 2).

Existing test fixture pattern, `tests/test_contraction.py:8-21` (`_chain_fixture`, a straight
5-node chain) and `tests/test_contraction.py:56-75` (`test_junction_node_is_not_contracted`, a
3-way junction) — both construct `coords`/`edges_i`/`edges_j`/... arrays by hand and call
`contract_structural(*fixture)` or `contract_structural(coords, edges_i, edges_j, ...)` directly,
then assert on `result.coords`/`result.edges_u`/etc. Follow this exact fixture-construction style.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Run contraction tests | `pixi run pytest tests/test_contraction.py -q` (from `pipeline/`) | all pass |
| Run full pipeline tests | `pixi run pytest -q` | all pass |
| Run build_base_graph tests too (contraction is called from there) | `pixi run pytest tests/test_build_base_graph.py -q` | all pass |

## Scope

**In scope** (the only files you should modify):
- `pipeline/lib/contraction.py`
- `pipeline/tests/test_contraction.py`

**Out of scope**:
- Do NOT change how `contract_structural` is called from
  `phases/graph_building/build_base_graph.py` in this plan beyond what's needed to surface the new
  count (see Step 3) — no change to `build_base_graph.py`'s own control flow or output files
  otherwise.
- Do NOT attempt to fix or special-case any other contraction edge case not described here (e.g.
  self-loop single edges, multi-edges between the same two keep-nodes) unless you discover one is
  actually present in the isolated-cycle fix's own logic and blocking it — if so, treat it as a
  STOP condition and report rather than expanding scope.

## Git workflow

- Branch: stay on the current branch unless the operator says otherwise.
- Commit message style: lowercase, `<module>: <imperative description>`, e.g. `lib: contract
  isolated degree-2 cycles into self-loop edges instead of dropping them`.
- Commit the failing characterization test first (Step 1), then the fix (Step 2) as a separate
  commit, matching this repo's evident preference for small, reviewable increments (see
  `git log --oneline` for `lib/contraction.py`-adjacent commits' granularity).
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add a failing characterization test for the isolated-cycle case

In `tests/test_contraction.py`, add a fixture for a **closed triangle** of three degree-2 nodes —
no keep-node anywhere:

```python
def test_isolated_cycle_with_no_junction_is_not_silently_dropped():
    # A closed triangle: 0 -- 1 -- 2 -- 0. Every node has degree 2 (two incident edges each), so
    # there is no keep-node (degree != 2) anywhere on this ring - the case CORRECT-01 describes.
    coords = np.array([(0.0, 0.0), (1.0, 0.0), (0.5, 1.0)])
    edges_i = np.array([0, 1, 2])
    edges_j = np.array([1, 2, 0])
    edges_dist = np.array([100.0, 100.0, 100.0])
    edges_road = np.array([False, False, False])
    edges_ungraded = np.array([0.0, 0.0, 0.0])
    edges_inferred = np.array([0.0, 0.0, 0.0])
    edges_sac_rank = np.array([1, 1, 1], dtype=np.int8)
    edges_via_ferrata = np.array([False, False, False])
    edges_constrained_ok = np.array([True, True, True])

    result = contract_structural(
        coords, edges_i, edges_j, edges_dist, edges_road, edges_ungraded, edges_inferred,
        edges_sac_rank, edges_via_ferrata, edges_constrained_ok,
    )

    # Today (before the fix): result.coords has 0 rows, result.edges_u has 0 entries - the whole
    # triangle vanished with no signal. After the fix, exactly one self-loop edge should be
    # emitted (one node kept as the loop's anchor, u == v, distance = 300.0, interior holding the
    # other two nodes' coordinates in ring order) - see contraction.py's isolated-cycle handling.
    assert len(result.coords) == 1
    assert len(result.edges_u) == 1
    assert result.edges_u[0] == result.edges_v[0]  # self-loop
    assert abs(result.edges_dist[0] - 300.0) < 1e-6
    assert len(result.interior_coords[0]) == 2  # the other two ring nodes
```

Run it now and confirm it **fails** against the current code (before Step 2's fix) — this proves
the test actually exercises the gap, not just a coincidentally-already-passing assertion.

**Verify**: `pixi run pytest tests/test_contraction.py -k isolated_cycle -v` → **fails**, with an
assertion mismatch on `len(result.coords) == 1` (current code returns 0). This failure is expected
at this step — do not treat it as a problem yet.

### Step 2: Fix `contract_structural` to close isolated cycles instead of dropping them

After the existing `for processed, k in enumerate(keep_idxs_list, start=1): ...` loop (i.e. once
every keep-node-reachable chain has been walked and `visited_edge` reflects that), add a second
pass that finds any edges still unvisited, groups them into their connected ring components, and
emits one self-loop contracted edge per ring — using the **same node** (the ring's own lowest-index
node) as both `u` and `v`:

```python
    # Any edge still unvisited here belongs to an isolated cycle with no keep-node anywhere on it
    # (every node degree == 2) - the outer loop above can only be entered from a keep-node, so a
    # pure ring never gets visited from any direction. Close each such ring into one self-loop
    # contracted edge instead of silently dropping it, using the ring's lowest node index as an
    # arbitrary anchor (any node on a pure ring is an equally valid contraction start point).
    remaining = np.flatnonzero(~visited_edge)
    n_isolated_cycles = 0
    if len(remaining) > 0:
        seen_in_cycle = np.zeros(n_nodes, dtype=bool)
        for e0 in remaining.tolist():
            if visited_edge[e0]:
                continue
            start = int(min(end_node[e0], end_other[np.flatnonzero(end_edge == e0)[0]]))
            if seen_in_cycle[start]:
                continue
            # Walk the ring starting at `start`, in one direction, until back at `start`.
            nbrs0, edges0 = _neighbors(start)
            # Prefer the still-unvisited direction (a ring node always has exactly 2 incident
            # edges; at least one is unvisited here by construction).
            nb, e = next((nb, e) for nb, e in zip(nbrs0, edges0) if not visited_edge[e])
            visited_edge[e] = True
            seen_in_cycle[start] = True
            d_sum = float(edges_dist[e])
            road_sum = d_sum if edges_road[e] else 0.0
            ungraded_sum = float(edges_ungraded[e])
            inferred_sum = float(edges_inferred[e])
            sac_max = int(edges_sac_rank[e])
            vf_any = bool(edges_via_ferrata[e])
            ok_all = bool(edges_constrained_ok[e])
            interior = []
            cur, prev_edge = nb, e
            while cur != start:
                seen_in_cycle[cur] = True
                interior.append((float(coords[cur, 0]), float(coords[cur, 1])))
                cnbrs, cedges = _neighbors(cur)
                nb2, e2 = next((nb2, e2) for nb2, e2 in zip(cnbrs, cedges) if e2 != prev_edge)
                visited_edge[e2] = True
                d_sum += edges_dist[e2]
                if edges_road[e2]:
                    road_sum += edges_dist[e2]
                ungraded_sum += edges_ungraded[e2]
                inferred_sum += edges_inferred[e2]
                if edges_sac_rank[e2] > sac_max:
                    sac_max = int(edges_sac_rank[e2])
                if edges_via_ferrata[e2]:
                    vf_any = True
                if not edges_constrained_ok[e2]:
                    ok_all = False
                prev_edge, cur = e2, nb2
            c_u.append(start)
            c_v.append(start)
            c_dist.append(d_sum)
            c_road_m.append(road_sum)
            c_ungraded_m.append(ungraded_sum)
            c_inferred_m.append(inferred_sum)
            c_sac_rank.append(sac_max)
            c_via_ferrata.append(vf_any)
            c_constrained_ok.append(ok_all)
            c_interior.append(interior)
            n_isolated_cycles += 1
        keep[start] = True  # WRONG if reused across iterations - see note below; fix in review
    if n_isolated_cycles:
        print(f"  contract_structural: closed {n_isolated_cycles:,} isolated degree-2 cycle(s) "
              f"with no junction node (see lib/contraction.py isolated-cycle handling)", flush=True)
```

**This pseudocode has a known bug you must fix while implementing, not copy verbatim**: `keep` is
a fixed-size boolean array computed once (`keep = degree != 2`, near the top of the function) and
is read later by `new_index = np.full(n_nodes, -1, ...); new_index[keep_idxs] = ...` — but
`keep_idxs = np.flatnonzero(keep)` is computed *before* this new isolated-cycle pass runs (it's
used inside the pass's own `_neighbors`/walk logic implicitly via `keep[cur]` — wait, this new pass
does NOT call `keep[cur]`, it walks by `cur != start` instead, so it doesn't depend on `keep` for
its own walk). The real issue: each isolated cycle's anchor node (`start`) must be added to the
*final* `keep_idxs` so `new_index[start]` gets a valid remapped position — but `keep_idxs` is
computed from the `keep` array *after* both passes, at the line `keep_idxs = np.flatnonzero(keep)`
near the function's end (see the tail of the existing function, after the main loop, before
`return ContractedGraph(...)`). So: mark `keep[start] = True` for **every** ring's anchor node
(not just the last one — the single `keep[start] = True` shown above, outside the `for e0 in
remaining` loop, is wrong; it must be inside the loop, right after `seen_in_cycle[start] = True`)
before that final `keep_idxs = np.flatnonzero(keep)` line runs. Trace through the full existing
function tail (after the point where you insert this new pass) to confirm exactly where
`keep_idxs = np.flatnonzero(keep)` and `new_index[keep_idxs] = np.arange(len(keep_idxs))` happen
relative to your insertion point, and place `keep[start] = True` so it's guaranteed to run before
that line, for every ring found.

**Verify**: `pixi run pytest tests/test_contraction.py -v` → **all pass**, including
`test_isolated_cycle_with_no_junction_is_not_silently_dropped` from Step 1.

### Step 3: Surface the count from `build_base_graph.py`'s caller (optional but recommended)

Check how `phases/graph_building/build_base_graph.py` calls `contract_structural` today (grep
`contract_structural` in that file) and whether it already logs a summary after contraction (e.g.
node/edge counts). If it does, add the isolated-cycle count to that existing summary line rather
than adding a new print statement — this plan's Step 2 already prints its own line when
`n_isolated_cycles > 0`, so this step is about *not losing* that signal if `build_base_graph.py`
captures/filters subprocess output somewhere, and about deciding whether the count belongs in
`data/timings.jsonl`'s `phase(...)` meta (see `pipeline/CLAUDE.md`'s "Timing pipeline phases"
section for the pattern: `meta.update(...)` inside a `with phase(...) as meta:` block). If
`build_base_graph.py`'s `contract_structural` call already sits inside such a `phase(...)` block,
add `n_isolated_cycles` to that block's `meta` dict — this makes the count queryable from
`timings.jsonl` the same way other pipeline anomalies are (per `pipeline/CLAUDE.md`'s established
convention), consistent with "never silently drop."

This requires `contract_structural` to return the count somewhere accessible — either as a new
field on `ContractedGraph` (e.g. `n_isolated_cycles: int = 0`, added to the dataclass in Step 2) or
a second return value. Prefer adding it as a `ContractedGraph` field (least disruptive to existing
callers, since it's a new field with a default) over changing the return signature.

**Verify**: `pixi run pytest tests/test_build_base_graph.py -q` → all pass after adding the field
and wiring it through, if `build_base_graph.py` needed updating to read it.

## Test plan

- `test_isolated_cycle_with_no_junction_is_not_silently_dropped` (Step 1) — the core
  characterization/regression test for this fix.
- Consider one more case: a *larger* ring (5+ nodes) to make sure the walk-back-to-start loop
  terminates correctly and doesn't off-by-one on the closing edge — optional, add if you want
  higher confidence, following the same fixture style.
- All existing `test_contraction.py` tests (`test_straight_chain_collapses_to_one_edge`,
  `test_contraction_sums_road_m_only_for_road_segments`,
  `test_contraction_takes_max_sac_rank_along_chain`,
  `test_contraction_ors_via_ferrata_along_chain`,
  `test_contraction_preserves_interior_polyline_in_order`,
  `test_junction_node_is_not_contracted`) must continue to pass unchanged — they exercise graphs
  that already have keep-nodes, so the new isolated-cycle pass should find `remaining` empty for
  all of them and be a no-op.
- Verification: `pixi run pytest tests/test_contraction.py tests/test_build_base_graph.py -q` →
  all pass.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `pixi run pytest tests/test_contraction.py -v` → all pass, including the new isolated-cycle
      test
- [ ] `pixi run pytest -q` (from `pipeline/`) → all pass, same or greater count than baseline
- [ ] The new isolated-cycle test, run against a `git stash` of just the Step 2 fix (or by
      temporarily reverting it), fails — confirming it's a real regression test, not a vacuous one
      (you can do this check mentally by having already observed the Step 1 failure before
      applying Step 2; no need to re-verify by literally stashing, but be able to state you
      confirmed it)
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- The live `contract_structural` differs structurally from the excerpt above (e.g. the `keep`
  array or `_neighbors`/`end_node`/`end_edge` machinery has been refactored) — re-derive the fix's
  insertion point from the live code rather than assuming line numbers match.
- You find the "known bug" callout in Step 2 (the `keep[start] = True` placement) doesn't apply
  the way described once you're looking at the real function tail (e.g. `keep_idxs` is computed
  differently than described) — re-read the actual tail of the function and place the fix
  correctly; if genuinely unclear where `keep_idxs`/`new_index` get finalized, stop and report
  rather than guessing.
- A ring of exactly 1 or 2 nodes turns out to be geometrically possible in real base-graph data
  (self-loop way, or a doubled edge between the same two nodes) and the walk logic above doesn't
  handle it cleanly — these are degenerate cases this plan's fixture (3-node triangle) doesn't
  cover; report rather than silently special-casing.

## Maintenance notes

- A reviewer should double check the `keep[start] = True` placement fix (flagged explicitly above
  as pseudocode-with-a-known-bug) — this is the one part of this plan most likely to need real
  judgment rather than mechanical translation.
- If `n_isolated_cycles` becomes non-zero on a real AT+Bayern rebuild, that's worth investigating
  *why* such a ring exists in the OSM data (a genuine mapping artifact, or a real physically closed
  loop trail with no junction) — this plan only ensures it's no longer silently dropped, not that
  its cause is understood on first occurrence.
- This fix does not attempt to route through an isolated cycle from outside it (a self-loop edge
  isn't reachable from any other keep-node, by definition of "isolated") — it exists purely so the
  geometry and its length are preserved and visible in the base graph's edge count, not to make it
  routable. That's the right scope for this fix; making an isolated ring meaningfully routable
  would require it to actually connect to the rest of the graph, which is a data problem, not a
  contraction-algorithm problem.
