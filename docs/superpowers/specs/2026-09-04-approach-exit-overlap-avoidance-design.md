# Extend Overlap Avoidance to Approach/Exit Legs — Design

**Follows on from** `docs/superpowers/specs/2026-08-29-avoid-overlapping-tracks-design.md` (hut-to-hut
legs, done), which explicitly deferred approach/exit legs: "needs the same edge-id treatment for
start-edges data — separate future work, and a 147 MB-class sidecar problem to solve first."

**That blocker is gone.** `docs/superpowers/specs/2026-09-02-hub-edge-scaling-design.md` (done)
restructured `start_edges/` materialization so full geometry is only ever built for the small
selected subset of access↔hut pairs that survive `select_approach_pairs.py` (tens of thousands of
records, not the ~1M pairs the routing pass touches) — and its §A3 already reverses
`path.base_edge_ids` into the access→hut storage order specifically so `write_edge_ids` could be
turned on for `start_edges` later "without a silent correctness regression." This spec is that
follow-up.

**Problem restated:** the hut-to-hut overlap check only covers `search.ts`'s expansion loop over
hut-hut legs. Approach legs (start point → first hut) and exit legs (last hut → start point) are
never checked against `usedEdgeIds`, and exit legs aren't checked against anything at all — so a
suggested tour can walk in or out over ground another leg in the same chain already used, including
the reported case: two different tours sharing the same trailhead approach corridor for part of
their length, or (car mode) a "loop" that isn't actually a loop over new ground.

**Scope:** approach and exit legs only, checked against each other and against the chain's hut-hut
legs. No change to the hut-hut rule itself (§4 of the 2026-08-29 design is unchanged and reused
as-is). No UI toggle, matching the original decision.

## 1. Pipeline: turn on `write_edge_ids` for `start_edges`

`build_access_edges.py:263` currently calls:

```python
write_edge_records(access_records, out_dir / "start_edges", write_edge_ids=False)
```

Change `write_edge_ids` to `True`. `write_edge_records` (`pipeline/lib/edge_output.py`) is shared
code already exercised by `hut_edges` — no format change, `start_edges/records.npy` starts getting
real `edge_id_offset`/`edge_id_count` + `prefix_ids`/`suffix_ids` instead of the `-1`/`0` padding it
writes today, and a new `start_edges/edge_ids.npy` sibling appears next to `records.npy` — the exact
same shape `hut_edges/edge_ids.npy` already has.

This is safe to flip immediately because of two things already true in `build_access_edges.py`
(2026-09-02 spec §A3):

- `path.base_edge_ids` is reversed into access→hut storage order before being packed
  (`build_access_edges.py:131,151`) — the same traversal order `write_edge_records` expects.
- Records are stored access(start)→hut, matching `HutEdgeRecord`'s from→to convention exactly:
  `prefix_ids` sits near `from_id` (the access/start point), `suffix_ids` near `to_id` (the hut).
  This identity is what makes §3 below able to reuse the hut-edge overlap math unchanged.

**Schema versioning.** `RECORD_DTYPE`'s *shape* doesn't change, but its *content contract* for
`start_edges` does (populated ids vs. padding), and doit doesn't track a script's own source as a
file_dep in this pipeline (`pipeline/lib/doit_support.py`'s `pipeline_task`/`rel()` docstrings) — a
tracked param has to change or the task looks up to date forever. Bump
`binfmt.RECORD_SCHEMA_VERSION` (`pipeline/lib/binfmt.py:124`, currently 3) — the pipeline's existing
idiom for exactly this situation, already wired as `_RECORD_SCHEMA_VERSION_PARAM` on both
`task_build_hub_edges` and `task_build_access_edges` (`pipeline/dag/graph_building.py`). The bump
reruns both tasks; `build_hub_edges`'s own output is unaffected (it already passes
`write_edge_ids=True`), but it shares the tracking param, so it reruns too. Accepted cost: post the
2026-09-02 scaling work, `hub_edge_query` is projected under 10 minutes, not the multi-hour cost the
root `CLAUDE.md` warns about for `build_base_graph`.

## 2. Pipeline: ship `start-edge-ids.bin`/`.json`

`pipeline/phases/postprocessing/build_edge_ids.py` is already generic over `--edges-dir` — it just
copies `<dir>/edge_ids.npy` through and packs `<dir>/records.npy`'s new columns into a manifest.
Zero code changes needed there.

Add `task_build_start_edge_ids` to `pipeline/dag/postprocessing.py`, a straight mirror of the
existing `task_build_edge_ids` (`postprocessing.py:185-196`) pointed at `start_edges/`:

```python
def task_build_start_edge_ids():
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

Add `"build_start_edge_ids"` to `dodo.py`'s `default_tasks` list, next to `"build_edge_ids"`. Add
`"start-edge-ids.bin"` and `"start-edge-ids.json"` to `PUBLIC_FILES` (`dodo.py`), next to
`"hut-edge-ids.bin"`/`"hut-edge-ids.json"`, so `copy_public_data` ships them.

**Sizing:** proportional to `start_edges/records.npy`'s row count, which §B of the 2026-09-02 spec
already cut to the selected-pair set (tens of thousands, not the ~1M-pair routing set) — the same
order of magnitude as `hut-edge-ids.bin`'s existing 4.8 MB raw / smaller gzipped, not the abandoned
147 MB figure the original design was blocked on.

## 3. Client: load the new sidecar

Generalize `loadHutEdgeIdsData` (`huts/src/tourSearch/loadHutEdgeIds.ts`) to take the file basename
pair as a parameter — `hut-edge-ids`/`start-edge-ids` produce byte-identical manifest shapes, so one
implementation serves both rather than a near-duplicate module. `GraphData` gains `startEdgeIds:
HutEdgeIdsData` (interface name kept as-is; it's not hut-specific in shape). `loadTourSearchData`
(`huts/src/tourSearch/index.ts`) fetches it in the same `Promise.all`.

## 4. Search algorithm: unify hut-leg and start-leg overlap bookkeeping

**Key fact this design leans on:** `ApproachRecord`/`StartLeg` and `HutEdgeRecord`/`HutLeg` share the
exact same storage convention (§1 above) — `prefix` near `from`, `suffix` near `to`, `reversed`
meaning "traversed opposite to storage direction." The existing arrival/departure formulas in
`search.ts` (`reversed ? prefix : suffix` for a leg arriving at the shared point, `reversed ? suffix
: prefix` for a leg departing it) are therefore correct for start-legs unchanged — they only need to
read from `startEdgeIds` instead of `hutEdgeIds` when the leg in question is a start-leg.

**`overlap.ts` gains one small dispatch helper** (the trim/overlap primitives, `trimSharedHubIds`/
`hasOverlap`, are already leg-agnostic and need no change):

```ts
export type EdgeKind = 'hut' | 'start'

export function nearHubIds(
  tables: { hut: HutEdgeIdsData; start: HutEdgeIdsData },
  leg: { edgeId: number; reversed: boolean; kind: EdgeKind },
  role: 'arriving' | 'departing',
): Int32Array {
  const table = leg.kind === 'hut' ? tables.hut : tables.start
  const wantSuffix = role === 'arriving' ? !leg.reversed : leg.reversed
  return wantSuffix ? table.getSuffixIds(leg.edgeId) : table.getPrefixIds(leg.edgeId)
}
```

**`search.ts` changes:**

- `State.prevHutLeg: { edgeId: number; reversed: boolean } | null` generalizes to `State.prevLeg: {
  edgeId: number; reversed: boolean; kind: EdgeKind } | null`.
- `State.usedEdgeIds` is seeded from the **approach leg's own full sorted-id set** (via
  `startEdgeIds`) at initial-state construction, instead of `EMPTY_EDGE_IDS`. This is what makes the
  rest fall out of the *existing* expansion-loop machinery for free: every subsequent leg (hut-hut or
  the eventual exit) is already checked against `usedEdgeIds`, so an approach leg's ground is
  automatically protected against reuse arbitrarily far down the chain, not just against the
  immediately adjacent hut leg.
- `State.approachEdgeId: number` is added, set once at initial-state construction and carried
  through unchanged — needed by §5's shared-start check, which can't be reconstructed from
  `prevLeg` once hut-hut legs have advanced it.
- Initial-state construction sets `prevLeg = { edgeId: approachLeg.edgeId, reversed:
  approachLeg.reversed, kind: 'start' }` (previously `prevHutLeg: null`).
- The expansion loop's existing overlap check is unchanged in shape (still runs once per candidate
  hut-hut leg, still not part of the dominance key — see the 2026-08-29 design §3 for why), just
  calls `nearHubIds(tables, s.prevLeg, 'arriving')` / `nearHubIds(tables, { ...leg, kind: 'hut' },
  'departing')` instead of the old inline `hutEdgeIds.getPrefixIds`/`getSuffixIds` calls.
- After accepting a hut-hut leg, `prevLeg` updates to `{ edgeId: leg.edgeId, reversed: leg.reversed,
  kind: 'hut' }`, as before (renamed field only).
- **`collectFinished` gains the overlap check it's never had.** For each candidate exit leg: compute
  the shared-hut exemption via `nearHubIds` against `s.prevLeg` (works uniformly whether `prevLeg` is
  a hut-hut leg or — for a single-hut, zero-nights tour — the approach leg itself, both arms already
  using `kind` to pick the right table) and `{ ...exitLeg, kind: 'start' }`, union it with §5's
  shared-start exemption, and reject via `hasOverlap` against `s.usedEdgeIds` exactly like the
  expansion loop does. This closes the "exit legs aren't checked against anything" gap noted above.

## 5. Shared-start exemption (car-mode loop closures)

Access/approach records store the access point as `from` (§1), so "near start" is always `prefix_ids`
— a fixed selector, unlike the hut case, because the record's own storage direction never puts the
start point at the `to` end regardless of `reversed`. `car` mode already requires `exitLeg.startId
=== s.startId` (loop closure); whenever that holds (checked generally, not gated to `car`, since a
coincidental match on another mode should get the same treatment), trim the shared run between
`startEdgeIds.getPrefixIds(s.approachEdgeId)` and `startEdgeIds.getPrefixIds(exitLeg.edgeId)` with
the existing `trimSharedHubIds`, and union it into the exempt set `collectFinished` passes to
`hasOverlap`.

Without this, a car-mode tour returning to the same parking lot would almost always be excluded
purely for sharing the unavoidable few hundred metres of trailhead access trail on both ends — the
exact failure mode §4 of the 2026-08-29 design already identified and fixed for shared huts, now
recurring at shared start points.

## 6. Diagnostics

No new kill counter — `trackOverlap` (`KillCounters`, 2026-08-29 design) already counts any
overlap-driven exclusion; approach/exit-leg overlaps increment the same counter, since from a
diagnostics standpoint they're the same phenomenon the counter was named for.

## Out of scope (unchanged from the original design)

- Any UI toggle.
- Making the search exact under the new rule (same dominance-pruning caveat as the 2026-08-29
  design — not every candidate reaches the check, so this remains a pruning heuristic, not an exact
  filter).
- Re-deriving or changing the hut-hut rule itself.

## Testing

- **Pipeline:** extend `pipeline/tests/test_build_access_edges.py` for the `write_edge_ids=True`
  path — assert a synthetic access→hut path's `edge_ids.npy`/`prefix_ids`/`suffix_ids` come out
  correctly reversed into storage order and ascending-sorted, mirroring the existing hut-edges
  round-trip test. `pipeline/tests/test_build_edge_ids.py` needs no change (already generic over
  `--edges-dir`) but gains a case pointed at a `start_edges`-shaped fixture to confirm the manifest
  shape matches.
- **Client:** extend `huts/src/tourSearch/search.test.ts` with synthetic fixtures:
  - an approach leg overlapping a later (non-adjacent) hut-hut leg is excluded, and `trackOverlap`
    increments;
  - an approach leg and the first hut-hut leg sharing only the run out of the first hut are kept
    (shared-hut exemption applies to a start-leg/hut-leg pair, not just hut-leg/hut-leg);
  - a car-mode loop sharing only the run near the shared start point is kept (§5);
  - a car-mode loop with a genuine overlap away from both shared points is excluded;
  - a single-hut (zero-nights) tour where approach and exit share the hut is correctly trimmed at
    that hut (the `prevLeg.kind === 'start'` path through `collectFinished`).
  - `realData.smoke.test.ts` gets its before/after chain-count band re-baselined once real data
    ships, same as the original design required.
