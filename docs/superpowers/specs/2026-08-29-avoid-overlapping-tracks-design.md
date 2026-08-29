# Avoid Overlapping Tracks — Design

**Problem:** Most suggested multi-day tours reuse the same physical trail twice or more. The
existing search already forbids revisiting a hut vertex within one chain
(`huts/src/tourSearch/search.ts:111`), so a literal hut-edge (same `from`/`to`/`variant`) can never
repeat — but two *different* hut-edges (different hut pairs, or different variants of the same pair)
can still run along the same physical trail on the ground for part of their length. That's the
overlap users are seeing: e.g. day 1 crosses a col from hut A to hut B, and a later day crosses the
same col again from hut C to hut D. This is a new form of overlap, distinct from the existing
vertex-revisit rule, and needs the actual underlying trail-segment identity to detect exactly.

**Scope:** Hut-to-hut edges only. Approach/exit legs (start point ↔ first/last hut) are explicitly
out of scope for this change — they use separate start-edge data not yet threaded for this, and can
be extended later if needed.

**Decision:** Always on, no UI toggle. Any tour containing two hut-edges (used anywhere in the
chain, not just adjacent) that share so much as one physical trail segment is excluded outright.
This is baked into default search behavior, not an opt-in.

## 1. Pipeline: persist per-hut-edge trail-segment identity

Base-graph edges already have a stable global identity: `edge_id` == row position in
`base_graph/edges.npy` (`pipeline/phases/graph_building/build_base_graph.py:201`). Today this
identity is available on `subgraph.local_edges["edge_id"]` (a row-subset copy, IDs preserved,
`pipeline/lib/subgraph.py`) but is discarded the moment a per-cell igraph shortest path is walked in
`accumulate_path` (`pipeline/lib/cell_igraph.py:216`) — the loop reads only scalar terrain attributes
off each igraph edge and never records which edge it was.

**Change:** In `accumulate_path`'s loop, resolve each igraph edge index back to its global
`edge_id`. Igraph edge index isn't a stable 1:1 mapping to `local_edges` row position once
`build_igraph_from_base`'s `_filter()` drops/splits edges for hub-snapping — but the existing
`edge_source[i]` array (already used to inherit `sac_rank`/`via_ferrata`/`max_ele_m` onto synthetic
split edges, `pipeline/lib/cell_igraph.py:47-51`) gives the original local-edge index for any igraph
edge, synthetic or not. So: `global_edge_id = local_edges["edge_id"][edge_source[i]]`. Collect these
into a new `PathResult.edge_ids: list[int]` field.

`build_hub_edges.py`'s `_write_edge_output` writes this out following the exact same ragged-array
(CSR) pattern already used for `geom_offset`/`geom_count` (content-hash-deduped `geometry.npy`
sidecar): a new flat `hut_edges/edge_ids.npy` (`int32` — max observed `edge_id` is ~4.7M, comfortably
under `int32` range, halving storage vs `int64`), and a new `edge_id_offset`/`edge_id_count` pair
added to `RECORD_DTYPE` (`pipeline/lib/binfmt.py:26-37`).

**Schema versioning:** `RECORD_DTYPE` changes require bumping `binfmt.SCHEMA_VERSION`, which today is
one shared `_SCHEMA_VERSION_PARAM` read by both `task_build_base_graph` and `task_build_hub_edges`'s
`uptodate` check (`pipeline/dag/graph_building.py`) — bumping it would force-rerun *both* tasks even
though `build_base_graph`'s own output shape (`EDGE_DTYPE`) doesn't change. Split this into two
independent tracking params, one per task's own dtype, so only `task_build_hub_edges` reruns. This
avoids an unnecessary ~4h `build_base_graph` rebuild (per `data/timings.jsonl` and root `CLAUDE.md`'s
warning about this task).

**Sizing (measured against current AT+Bayern data):** ~8,237 hut-edge records, median hut-edge
distance ~20.6km over a base graph with ~132m mean edge length ⇒ roughly 150–370 base edges per
hut-edge path. Working estimate: ~10²–10³ edge-ids per record, ⇒ ~10MB raw for `edge_ids.npy`
(`int32`) across all records — smaller than today's `geometry.npy` (129MB) but far larger than the
existing `hut-edge-payload.bin` (~320KB, all fixed-width scalar columns).

## 2. Delivery to the client

Unlike geometry — fetched lazily per-selection via `hut-edges.pmtiles` map tiles, only for a tour a
user has opened — the edge-id data must be available *during search*, before any tour is chosen,
because the overlap check runs across all candidate chains inside the in-browser search algorithm.
It therefore can't be tile-lazy; it has to be loaded wholesale like `hut-edge-payload.bin` already
is.

Ship it as a new sibling pair, `hut-edge-ids.bin` + a small JSON manifest (offsets/counts, row count,
dtype — mirroring the existing `hut-edge-payload.json` manifest shape), row-aligned with
`hut-edge-payload.bin`'s existing row order so a hut-edge's payload row index indexes directly into
this file's offset/count table. Add to the pipeline's `copy_public_data` task outputs alongside the
existing payload files, and fetch it unconditionally in `huts/src/tourSearch/loadHutEdges.ts`
alongside the existing payload fetch — no feature flag, since this is always-on.

## 3. Search algorithm integration

Overlap checking is a **post-filter at chain-finish time**, not folded into the per-state dominance
key used during expansion (`insertDominant`, `search.ts:51`). The search already prunes its
exponential state space via a `(hutIndex, startId, visitedKey)` key where `visitedKey` is a compact
hut-index bitmask; attaching a variable-length, per-state *set of used base-edge-ids* to that key
would make state comparison and the dominance check itself expensive, defeating the pruning that
makes exact DFS tractable here. The overlap property is naturally checked once, per finished
candidate, instead.

In `collectFinished` (`search.ts:80`), before final sort/truncation, for each finished chain:

1. For every leg in the chain, look up its base-edge-id array from the new sidecar (indexed by the
   leg's row index into `hut-edge-payload.bin`, same identity already carried on `HutEdgeRecord`).
2. Check **all pairs** of legs in the chain (not just adjacent legs — the reported problem was a
   repeated segment appearing much later in a multi-day loop, not necessarily on consecutive days)
   for a shared edge-id, via `Set` intersection.
3. If any pair shares at least one edge-id, drop the chain entirely.

Chain length is bounded by `legCountMax` (small, single-digit), so this is O(legs²) per candidate
with each pairwise check O(edge-ids-per-leg) — cheap relative to the state-space search itself, even
across hundreds of finished chains.

Add a new kill counter (alongside the existing `revisit` counter, `search.ts:111`) — e.g.
`trackOverlap` — so overlap-driven exclusions are visible in search diagnostics the same way
vertex-revisits already are.

## Out of scope (explicitly deferred)

- Approach/exit leg overlap checking (needs the same edge-id treatment for start-edges data —
  separate future work).
- Any UI toggle or threshold tuning — this is unconditional, hard-exclude behavior.
- Any percentage/length-based overlap threshold — any shared base-edge counts as overlap.

## Testing

- Pipeline: unit test `accumulate_path` returns correct `edge_ids` for a synthetic small graph,
  including the hub-snap-split/synthetic-edge case (verify `edge_source` resolution is correct for
  synthetic edges, not just original ones).
- Pipeline: `build_hub_edges.py` round-trip test — write then read back `edge_id_offset`/
  `edge_id_count` + `edge_ids.npy`, confirm correct per-record slices.
- Client: unit test in `huts/src/tourSearch/search.test.ts` — synthetic fixture where two
  non-adjacent hut-edges share a base-edge-id; assert the chain is excluded and the kill counter
  increments. Also assert a chain with genuinely disjoint edge-id sets still passes.
