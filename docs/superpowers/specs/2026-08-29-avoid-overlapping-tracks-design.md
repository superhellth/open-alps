# Avoid Overlapping Tracks — Design

**Problem:** Most suggested multi-day tours reuse the same physical trail twice or more. The
existing search already forbids revisiting a hut vertex within one chain
(`huts/src/tourSearch/search.ts:111`), so a literal hut-edge can never repeat — but two *different*
hut-edges (different hut pairs) can still run along the same physical trail on the ground for part
of their length. That's the overlap users are seeing: e.g. day 1 crosses a col from hut A to hut B,
and a later day crosses the same col again from hut C to hut D. This is a new form of overlap,
distinct from the existing vertex-revisit rule, and needs the actual underlying trail-segment
identity to detect exactly.

(An earlier draft also named "different variants of the same pair" as a source. It isn't:
`buildAdjacency` filters to the single variant `resolveVariant` picks for the query, so two
variants of one pair can never both appear in a chain.)

**Scope:** Hut-to-hut edges only. Approach/exit legs (start point ↔ first/last hut) are explicitly
out of scope for this change — they use separate start-edge data not yet threaded for this, and can
be extended later if needed.

**Decision:** Always on, no UI toggle. A tour is excluded when two of its hut-edges share a physical
trail segment *away from the hut they have in common* — see §4 for why the "away from" qualifier is
not optional.

## 1. Pipeline: persist per-hut-edge trail-segment identity

Base-graph edges already have a stable global identity: `edge_id` == row position in
`base_graph/edges.npy` (`pipeline/phases/graph_building/build_base_graph.py:201`). Today this
identity is available on `subgraph.local_edges["edge_id"]` (a row-subset copy, IDs preserved,
`pipeline/lib/subgraph.py`, and it survives the `route_subgraphs` disk cache, which persists the
full `EDGE_DTYPE`) but is discarded the moment a per-cell igraph shortest path is walked in
`accumulate_path` (`pipeline/lib/cell_igraph.py:216`) — the loop reads only scalar terrain
attributes off each igraph edge and never records which edge it was.

Edge-id granularity is *exact* for this purpose, not an approximation: `build_base_graph` structurally
contracts chains, so a base edge is a junction-to-junction run with no branches. Two hut-edges that
touch the same trail between the same two junctions necessarily share that edge's id; there is no
"partially overlapping edge" case to miss — except at hub split points, handled below.

**Change:** In `accumulate_path`'s loop, resolve each igraph edge index back to its global
`edge_id`. Igraph edge index isn't a stable 1:1 mapping to `local_edges` row position once
`build_igraph_from_base`'s `_filter()` drops/splits edges for hub-snapping — but the existing
`edge_source[i]` array (already used to inherit `sac_rank`/`via_ferrata`/`max_ele_m` onto synthetic
split edges, `pipeline/lib/cell_igraph.py:47-51`) gives the original local-edge index for any igraph
edge, synthetic or not. Collect these into a new `PathResult.edge_ids: list[int]` field.

**Synthetic halves must not collapse onto the parent.** `edge_source` maps *both* halves of a
hub-split edge to the same parent local index (`cell_igraph.py:130,144`). A naive
`local_edges["edge_id"][edge_source[i]]` therefore reports the same id for the half arriving at a
hub and the half leaving it — a false overlap between two legs that touch disjoint ground. Emit a
disambiguated id instead:

```
base = local_edges["edge_id"][edge_source[i]]
out  = base * 3 + (0 if i < n_orig else 1 + half_index)   # half_index 0 = ..._to_u, 1 = ..._to_v
```

Max observed `edge_id` is 4,730,711, so `* 3 + 2` stays under `int32` comfortably. This is a small
effect by count — only 242 of 4,730,712 base edges are split (21 hut, 209 parking, 11 station, 1
partner) — but those sit at trailheads where many routes converge, so it is worth the arithmetic.

`build_hub_edges.py`'s `_write_edge_output` writes this out following the exact same ragged-array
(CSR) pattern already used for `geom_offset`/`geom_count`: a new flat `hut_edges/edge_ids.npy`
(`int32`), and a new `edge_id_offset`/`edge_id_count` pair added to `RECORD_DTYPE`
(`pipeline/lib/binfmt.py:26-37`). **Store each record's ids sorted ascending**, not in traversal
order — only set membership matters downstream, sorting makes the client-side check a linear merge
instead of a `Set` build, and it makes the file delta-compressible.

**`_write_edge_output` is shared by both layers** (`build_hub_edges.py:456-457`, `hut_edges` and
`start_edges`). Emitting edge-ids unconditionally would also produce a `start_edges/edge_ids.npy`,
which is enormous (that layer's geometry sidecar alone is 147 MB) and unused while approaches are
out of scope. Gate it on a parameter, hut-edges-only for now.

**Schema versioning:** `RECORD_DTYPE` changes require bumping `binfmt.SCHEMA_VERSION`, which today
is one shared `_SCHEMA_VERSION_PARAM` read by **four** tasks — `task_build_base_graph`,
`task_snap_hubs`, `task_gather_route_subgraphs` and `task_build_hub_edges`
(`pipeline/dag/graph_building.py`). Bumping it would force-rerun all four even though only
`build_hub_edges`' own output shape changes. Split it into three independent tracking params by the
dtype each task actually depends on:

| param | dtype it tracks | tasks |
| --- | --- | --- |
| `edge_schema_version` | `EDGE_DTYPE` | `build_base_graph`, `gather_route_subgraphs` |
| `snap_schema_version` | `HUB_SNAP_DTYPE` | `snap_hubs` |
| `record_schema_version` | `RECORD_DTYPE` | `build_hub_edges` |

Only `record_schema_version` moves for this change, so only `task_build_hub_edges` reruns. This
avoids an unnecessary ~4 h `build_base_graph` rebuild (per `data/timings.jsonl` and the root
`CLAUDE.md` warning about that task).

**Sizing (measured against current AT+Bayern data, not estimated):** 8,237 hut-edge records; base
graph mean edge length 132.2 m; per-record base-edge count works out to mean 144, median 156, p95
221, max 228 (the max being the `maxEdgeKm` cap). Total ≈ **1.19 M ids ⇒ 4.8 MB raw as `int32`** —
about the size of the existing `hut-edge-geometry.bin` (5.8 MB), and far above `hut-edge-payload.bin`
(321 KB). Sorted ids delta-compress well; measure and record the gzipped figure when the file is
first built, since that is what actually gates page load.

## 2. Delivery to the client

The edge-id data must be available *during search*, before any tour is chosen, because the overlap
check runs across candidate chains inside the in-browser search algorithm. It therefore can't be
fetched lazily per opened tour the way `hut-edge-geometry.bin` is (byte-range per leg,
`loadLegGeometry.ts`, per the 2026-08-27 geometry design) — it has to be loaded wholesale like
`hut-edge-payload.bin` already is.

Ship it as a new sibling pair, `hut-edge-ids.bin` + a small JSON manifest, row-aligned with
`hut-edge-payload.bin`'s row order (`HutEdgeRecord.edgeId` is literally the payload row index, set
in `loadHutEdges.ts`) so a leg's row index indexes directly into this file. Follow
**`hut-edge-geometry.json`'s manifest shape** — a flat `counts` array plus a client-side prefix sum
— not `hut-edge-payload.json`'s columnar `{dtype, offset}` map, which describes a different kind of
file. Add to the pipeline's `copy_public_data` task outputs alongside the existing payload files,
and fetch it unconditionally in `huts/src/tourSearch/loadHutEdges.ts` — no feature flag, since this
is always-on.

## 3. Search algorithm integration

**Check during expansion, not as a post-filter on finished chains.** In the expansion loop
(`search.ts:108`), before accepting a leg onto a state, intersect the leg's id array against the
running union of ids already used by that state; reject on a hit. Each state carries its own
`Set<number>` (or sorted array) of used ids, extended on each accepted leg.

Two things this is *not*:

- It does **not** go into the dominance key (`insertDominant`, `search.ts:51`). That key stays
  `(hutIndex, startId, visitedKey)`. Attaching a variable-length id set to the key would make state
  comparison expensive and defeat the pruning that makes exact DFS tractable here.
- It is therefore **not exact**, and the spec should not claim it is. Dominance keeps only the
  lowest-duration state per key, so if the fastest ordering of a hut set self-overlaps and a slower
  ordering doesn't, the non-overlapping tour is lost. An earlier draft placed this check as a
  post-filter in `collectFinished` and argued it was "naturally checked once per finished
  candidate" — that argument doesn't hold, because dominance means not every candidate reaches the
  check. Post-filtering has exactly the same loss and additionally wastes the work of expanding
  chains already known to be doomed, so expansion-time is strictly better on both axes.

Cost: one intersection per expansion attempt against a set bounded by `legCountMax` × ~150 ids —
small next to the state-space walk itself, and it prunes subtrees rather than leaves.

**Skip approach and exit legs.** `LegSummary.edgeId` (`types.ts:86`) carries a *hut-edge* row index
for interior legs but a *start-edge* row index for `legs[0]` and `legs[legs.length - 1]`, with no
discriminator on the type. Indexing the hut-edge sidecar with a start-leg id silently reads the
wrong record. Since approaches are out of scope, the check runs only over hut-hut legs; the
expansion-loop placement gets this for free, since only hut legs are added there.

Add a new kill counter alongside the existing `revisit` counter — `trackOverlap`, added to
`KillCounters` (`types.ts:122`) and `createKillCounters` (`legFilters.ts`) — so overlap-driven
exclusions are visible in search diagnostics the same way vertex-revisits already are. The name
"overlap" is now unambiguous in this namespace: `findTours`' `overlapThreshold` option (inter-tour
hut-set similarity) was removed on 2026-08-29 and survives only as a private constant in
`diversity.ts`.

## 4. The rule: shared trail away from the shared hut

**A hard "any shared base-edge excludes the tour" rule is not viable.** Two legs meeting at the same
hut have to leave that hut somehow; for a hut on a spur or at a valley head, `A→B` and `B→C`
necessarily share the trail out of B. Measured over `hut_edges/records.npy` geometry (FAST_ANY,
3,519 records, 580 huts with ≥2 legs), sampling where each leg is at a given distance out from the
shared hut:

| distance out from shared hut | leg-pairs departing on the same trail | huts where *every* leg-pair coincides |
| --- | --- | --- |
| 200 m | 50.5% (24,889 / 49,259) | 86 / 580 (15%) |
| 500 m | 44.9% | 55 / 580 |
| 1000 m | 42.0% | 43 / 580 |

At a 132 m mean base-edge length, coinciding 200 m out means sharing at least one base edge
essentially always. So a hard rule would exclude roughly half of all adjacent-leg transitions and
would make 86 huts (15%) unreachable as an intermediate stop in *any* tour — silently, with no
toggle and no UI explanation. It also isn't the reported problem: shared trail in the first metres
out of a shared hut is unavoidable geometry, not a defect. The complaint is a col re-crossed on a
later day.

**Rule:** for each pair of hut-legs, if they share an endpoint hut, drop the common prefix/suffix
adjacent to that hut before intersecting — walk both id lists inward from the shared hut and discard
the matching run. Any shared id that survives is a real overlap and excludes the tour. Non-adjacent
pairs (no shared hut) are intersected whole.

Note this needs the traversal-ordered ids at the *ends* of each record even though §1 stores them
sorted. Cheapest fix: store sorted ids for the intersection plus the first and last `k` ids in
traversal order (k ≈ 8 covers ~1 km at 132 m/edge) as a small separate column. Decide k when the
first build lands and the overlap-length distribution is visible.

Deliberately still excluded: any percentage- or length-of-tour threshold. Once the shared-hut
prefix is exempted, a surviving shared segment is treated as disqualifying regardless of length.

## Out of scope (explicitly deferred)

- Approach/exit leg overlap checking (needs the same edge-id treatment for start-edges data —
  separate future work, and a 147 MB-class sidecar problem to solve first).
- Any UI toggle. This is unconditional behavior.
- Making the search exact under the new rule (would require relaxing dominance to top-k per key).
  Documented as a known loss above rather than fixed.

## Testing

- Pipeline: unit test `accumulate_path` returns correct `edge_ids` for a synthetic small graph,
  including the hub-snap-split/synthetic-edge case — assert the two halves of one split edge get
  *distinct* ids, which is the false-overlap bug §1 guards against.
- Pipeline: `build_hub_edges.py` round-trip test — write then read back `edge_id_offset`/
  `edge_id_count` + `edge_ids.npy`, confirm correct per-record slices and ascending order within a
  record. Assert `start_edges/` gets no `edge_ids.npy`.
- Client: unit test in `huts/src/tourSearch/search.test.ts` — synthetic fixture where two
  non-adjacent hut-edges share a base-edge-id; assert the chain is excluded and `trackOverlap`
  increments. Assert a chain with genuinely disjoint id sets still passes. Assert the adjacent-hut
  case: two legs sharing only the run out of their common hut are **kept**.
- Client: `realData.smoke.test.ts` — record the chain count before/after on the shipped payload and
  assert it stays inside an expected band, so a future rule change that quietly empties the result
  list fails loudly.
