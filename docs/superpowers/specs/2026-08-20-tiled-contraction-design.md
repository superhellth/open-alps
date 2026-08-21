# Tiled base-graph contraction

Date: 2026-08-20
Status: approved for planning

## Goal

`build_base_graph.py`'s two phases are logged in `data/timings.jsonl` at `stream_osm` ≈ 914s
(~15 min) and `contract_structural` ≈ 3963s (~66 min) — ~81 min total, not the "~4 hours" both
`pipeline/README.md` and `pipeline/CLAUDE.md` currently cite (that figure is from the pre-V2
`build_hut_graph.py`; the docs haven't been updated to the real V2 numbers — fix separately from
this spec). `contract_structural` is 81% of the real cost and runs single-threaded over the whole
merged AT+Bayern graph in one pass.

This spec tiles `contract_structural` across a `ProcessPoolExecutor`, reusing the *same* `Grid`
(`lib/grid.py`) and `tile_size_km` that `build_hub_edges.py` already uses — no second tiling
scheme, no separate config knob unless real profiling later proves the two steps want different
sizes (YAGNI: don't split the knob on no evidence).

## Non-goals

- **Tiling `stream_osm`.** It's already a single linear pyosmium pass building flat in-memory
  arrays (~15 min, 19% of cost) and stays that way. Parallelizing it means pre-splitting
  `trails.osm.pbf` by bbox (`osmium extract --strategy complete_ways`) and deduplicating
  boundary-straddling ways by way id afterward — a second, genuinely different kind of tiling
  logic for a comparatively small win. Left as a possible future addition, not part of this spec.
- **Changing `build_hub_edges.py`.** Its tiling is untouched; this spec only makes
  `build_base_graph.py` use the same `Grid`/`tile_size_km` for its own new tiled phase.
- **A configurable contraction-specific tile size.** Start with one shared value (see Goal).

## Architecture: ghost/halo-node parallel contraction

Standard pattern for parallel graph contraction: each tile computes a locally-correct partial
result plus explicit boundary state ("ghost" edges/nodes it can't fully resolve), and a cheap
final serial pass reconciles the boundaries. Three phases:

1. **Persist the raw (pre-contraction) graph.** Right after `stream_osm`, write `handler`'s flat
   arrays to `data/osm/raw_graph/` using the *same* `lib/binfmt.py` layout as today's
   `base_graph/` (`nodes.npy`, `cell_index.npy`, `node_edge_index.npy`, `node_edge_ids.npy`,
   `edges.npy`, `interior.npy`, `manifest.json`) — every raw edge gets `interior_offset=0`,
   `interior_count=0` (nothing's contracted yet). This is a new step, but it's the same node/cell
   assignment `build_base_graph.py` already does today, just persisted before contraction instead
   of after.

2. **Per-tile parallel contraction** (`ProcessPoolExecutor`, one worker per grid cell — same
   pattern as `build_hub_edges.py`'s `_run_cell`). Each worker:
   - Loads its own cell's nodes from `raw_graph/` — nodes *are* cell-sorted, so that's one
     contiguous slice via `cell_index.npy` — then gathers those nodes' incident edges through the
     `node_edge_index.npy`/`node_edge_ids.npy` CSR, exactly like `lib/subgraph.py` does. Note the
     edge array is **not** cell-sorted: this is a scattered read into a multi-GB `edges.npy`, done
     concurrently by every worker (see "Cost of `raw_graph/`"). No distance-based padded buffer is
     needed, see "Correctness" below for why.
   - Classifies every incident edge of its own nodes as **safe** (both endpoints' home
     `cell_id` == this tile) or **unsafe** (endpoints in different cells).
   - Runs `contract_structural()` over its **safe edges only** — unsafe edges are excluded from
     the contraction input entirely, not merely fenced off by `forced_keep`. This is load-bearing:
     `forced_keep` stops a walk that *ends* at a boundary node, but not one that *starts* there. If
     unsafe edge (B, C) were left in the input, the walk starting at forced-keep B would traverse
     it and emit a chain edge (B, C) — while the owning tile also reports (B, C) directly, per the
     next bullets. That is exactly the duplication the safe/unsafe split exists to prevent, and it
     breaks the "no edge dedup needed" invariant below. C is present in the tile's local node set
     (pulled in for its coordinates by the one-hop closure), so nothing stops the walk on its own.
   - Passes a new `forced_keep` mask: any node touching at least one unsafe edge is forced `keep`,
     regardless of its true degree (this tile can't see that node's complete edge set, so it can't
     know its real degree).
   - Splits its contraction output into **final** chain edges (both endpoints are true interior
     keep-nodes, never touch an unsafe edge — these are done, no reconciliation needed) and
     **boundary** chain edges (at least one endpoint is a forced-keep boundary node — provisional,
     go to phase 3).
   - Additionally emits every unsafe edge it owns (see tie-break below) directly, uncontracted,
     into the boundary set.
   - Writes its results as `.npy` shards under `data/osm/tile_contraction/<cell_id>/` and returns
     only the paths + counts. It must **not** return the contracted graph itself: chain edges carry
     `interior_coords` as `list[list[tuple]]`, and the full graph has ~33M interior points
     (current `interior.npy` is 529 MB), so pickling that back through `ProcessPoolExecutor` would
     plausibly cost more than the contraction it parallelizes.

3. **Serial stitch pass.** Collect every tile's boundary nodes + boundary chain edges + owned
   unsafe edges into one small graph (small because it's bounded by total tile *boundary length*,
   not tile count or total node count — most of the graph is already fully resolved in phase 2).
   Run `contract_structural()` over it once, serially. This resolves any node that was only
   forced-`keep` due to tiling but is actually a true pass-through once its full edge set
   (assembled from every tile that touched it) is known. Phase 3 is a *single* pass — a chain
   crossing several tile boundaries in sequence resolves in that one call, no iteration to a fixed
   point.

   Phase 3 is **not** an unmodified `contract_structural()` call. It needs all three of the
   extensions in "New/changed interfaces" below, for reasons spelled out in "Correctness: what
   phase 3 must not lose".

**Final output** = every tile's final (non-boundary-touching) chain edges, union phase 3's
stitched chain edges. No edge dedup needed: by construction (see below) each raw edge is walked by
exactly one tile (safe edges — and only that tile has them in its contraction input at all) or
reported exactly once as unsafe, so nothing overlaps. Boundary *nodes* are
collected by global raw-node id, which does need a `np.unique` — a tile pulls in the far endpoints
of its unsafe edges for their coordinates, so the same node is contributed by more than one tile. Node/edge id
renumbering and the cell-sort into the final `base_graph/` files stays exactly as it is today
(`build_base_graph.py`'s existing post-contraction packing code) — it now runs once over the
*merged* result instead of over a single global `contract_structural()` call's output.

## Correctness: safe/unsafe edge classification (the part that took two tries)

**First draft (rejected):** "any node not owned by this tile is forced-keep, any walk reaching it
just stops." This causes double-reporting: if raw edge (B, C) has B owned by tile X and C owned by
tile Y, X's walk (starting from its own interior) can legitimately walk *through* B (a true
interior node, degree 2, fully known to X since B is X's own core node) and report a chain ending
at C. But Y *independently* starts a walk at its own core node C, follows the edge back toward B,
and immediately reports a spurious short edge (C, B) — B was already correctly absorbed by X, but
Y has no way to know that. The result: B appears twice in the merged output — once correctly
absorbed as interior, once as a phantom boundary node from Y's partial, wrong-granularity view.

**Fix — classify by edge, not by node:**

- A raw edge is **safe** for tile T iff *both* its endpoints have home `cell_id` == T. Only T ever
  walks/absorbs a safe edge — by definition, no other tile's nodes are involved, so there's no
  ambiguity about who processes it.
- A raw edge is **unsafe** iff its two endpoints have different home cells. Neither tile walks
  through an unsafe edge — it's reported once, directly, uncontracted, into the boundary set, by a
  fixed tie-break (owning tile = home tile of the numerically smaller of the two endpoint ids) so
  no cross-tile coordination is needed during the parallel phase.
- A node is a **boundary node** iff it has at least one incident unsafe edge. It's forced `keep`
  in its own tile's local contraction — only its own tile can ever see its complete true edge set.
  That completeness comes from `node_edge_index.npy` being a *global, per-node* CSR incidence
  index: gathering a node's CSR row yields every edge it has, whatever their length or the cells
  of their far endpoints. (It has nothing to do with raw edges being short single-way-segment
  hops — that happens to be true, but is not what makes the closure complete.)

Worked check (a 3-way junction straddling two tile boundaries: B is X's, C is Y's, C also connects
onward to D which is Z's): edge (B,C) is unsafe → reported once (say by X, per tie-break), never
walked by either tile. X's walk from its own interior junction absorbs B (true interior, degree 2,
fully knowable to X) and stops at B only if B has an unsafe edge — which it does (the edge to C) —
so X reports a *final* chain ending at boundary node B, and the unsafe edge (B,C) separately.
Y independently reports its own interior chain from C toward its own interior, plus the unsafe
edge (C,D) it owns (or doesn't, per tie-break — then Z reports it). Phase 3's graph around this
cluster ends up with exactly: (chain ending at B), (B,C) direct, (chain ending at C from Y's
side), (C,D) direct — C's true degree (3, if that's the real total) is fully and exactly
represented, with no duplication and nothing missing.

**Pre-existing behaviour worth knowing before the equivalence test:** a pure degree-2 cycle with no
keep node on it anywhere is *dropped* by today's `contract_structural()` — walks only ever start at
keep nodes, so nothing enters the cycle. The tiled version drops it too: such a cycle's forced-keep
boundary nodes are absorbed in phase 3 once their true degree (2) is known, leaving again no keep
node to start from. Same output, so reference equivalence holds — but it will look like a
suspicious mutual absence when a diff is examined, so it's recorded here rather than rediscovered.

**Consequence:** gathering a tile's data doesn't need `build_hub_edges.py`'s distance-based
`buffer_km` padding at all (that buffer exists because hub-to-hub paths are bounded by
`maxEdgeKm`, which has no equivalent bound here — chains are structural, not distance-capped). A
tile only needs its own cell-sorted slice of `raw_graph/` plus a one-hop closure to pull in unsafe
edges' far endpoints (for their coordinates) — the classification itself is a local property
(compare two `cell_id`s already stored per node), no padded gather needed.

## Correctness: what phase 3 must not lose

Phase 3's input is not raw edges — it's *already-contracted chain edges*. Today's
`contract_structural()` assumes raw input in three ways, each of which silently corrupts output if
phase 3 feeds it chain edges unchanged:

**(a) It would delete real junctions.** Phase 3's graph holds only *boundary* chain edges. A true
junction `J` that is itself not a boundary node can still have some of its edges in that set:

```
J, true degree 4:  2 final edges    (both endpoints non-boundary) -> stay in the tile's output
                   2 boundary edges (far endpoints B1, B2 are boundary nodes) -> phase 3
phase-3 degree(J) == 2  ->  keep[J] is False  ->  J absorbed
                        ->  chain(B1..J) + chain(J..B2) merged into one edge
                        ->  the 2 final edges now reference a node that no longer exists
```

A crossroads a little way inside a tile edge produces exactly this. So **phase 3 also passes
`forced_keep`**: set for every node that has at least one *final* edge (plus, trivially, any node
whose true degree the stitch graph still can't see). The tile-boundary mask and this one are
different masks computed the same way — a node is forced `keep` whenever some of its incident
edges are invisible to the contraction being run.

**(b) It would destroy interior geometry.** `contract_structural` builds a chain's interior purely
from the *node* coords it walks through (`lib/contraction.py:79`); there is no interior input. When
phase 3 contracts two chain edges together, both of their existing `interior_coords` polylines are
dropped and only the shared midpoint node's coordinate survives. Every boundary-crossing chain
would come out geometrically gutted. Phase 3 therefore needs an `edges_interior` input,
concatenated in walk order — **and reversed when the walk traverses an edge from its `v` end to its
`u` end**, which the current walk loop has no reason to track and does not.

**(c) It would inflate `road_m`.** The existing signature takes `edges_road` as a **bool** and does
`road_sum += full edge dist if edges_road[e]` (`lib/contraction.py:72,92-93`). Chain edges carry a
*fractional* `road_m` (a chain can be part road, part trail). Passing `road_m > 0` would charge the
whole chain length as road. Phase 3 needs to pass float `road_m` and sum it directly.

Together these mean the interface change is not one small backward-compatible parameter — see
below.

## Cost of `raw_graph/`

Phase 1 is not free and the spec should not pretend it is. Sizing from the current real
`data/osm/base_graph/`: 6.85M contracted nodes + 33.1M interior points ≈ **~40M raw nodes**, and
~8.3M chain edges + 33.1M absorbed edges ≈ **~41M raw edges**. At the `lib/binfmt.py` dtypes:

| file | size |
|---|---|
| `nodes.npy` (40M × 20 B) | ~0.80 GB |
| `edges.npy` (41M × 62 B) | ~2.6 GB |
| `node_edge_ids.npy` (2 × 41M × 8 B) | ~0.66 GB |
| `node_edge_index.npy` (40M × 12 B) | ~0.48 GB |
| **total** | **~4.5 GB** |

Written once serially, then read back with scattered (non-cell-sorted) access by every worker.
Phase 1 also adds a cell-assignment + CSR sort over 40M nodes that today only runs over the 6.85M
contracted ones. This is the overhead the ~66 min of contraction has to beat, and the reason
worker results go to disk shards rather than back through pickle.

At `tileSizeKm: 60` over the configured bbox the grid is **11 × 8 = 88 cells**, many of them
near-empty. 88 tasks is plenty for scheduling, but the wall-clock floor is set by the single
densest alpine cell, not by the mean — so the realistic target is "well under 66 min", not
"66 min ÷ core count".

## New/changed interfaces

- **`lib/contraction.py`'s `contract_structural()`**: three optional params, all defaulting to
  `None` (never an array as a default arg) and all no-ops when omitted, so every existing
  caller/test is unaffected and `progress_every` stays as-is:
  - `forced_keep: np.ndarray[bool] | None` — `keep = (degree != 2) | forced_keep`. Used by both
    phase 2 (tile-boundary nodes) and phase 3 (nodes owning final edges), per (a) above.
  - `edges_interior: list[list[tuple]] | None` — per-input-edge existing interior polyline,
    concatenated into the output chain's interior in walk order, reversed when the walk enters an
    edge at its `v` end. Requires the walk loop to track traversal direction, which it currently
    doesn't. Per (b) above.
  - `edges_road_m: np.ndarray[float] | None` — when given, supersedes the `edges_road` bool and is
    summed directly instead of re-deriving road length from `dist`. Per (c) above.
- **New module, `lib/tile_contraction.py`** (or a function set in `build_base_graph.py` — decide
  during planning based on how much other code wants to import it): the per-tile worker function
  (classify safe/unsafe, build `forced_keep`, call `contract_structural`, split final vs.
  boundary, write `.npy` shards), and the phase-3 stitch function (collect boundary state across
  tiles, build phase 3's own `forced_keep` from which nodes own final edges, run
  `contract_structural` once more with interior + `road_m` passed through, merge with every tile's
  final edges).
- **`build_base_graph.py`**: `stream_osm` unchanged; after it, persist `raw_graph/` (new); replace
  the single `contract_structural()` call with the tiled `ProcessPoolExecutor` dispatch + stitch;
  the existing post-contraction packing/cell-sort code (currently lines ~129-194) is unchanged,
  just fed the merged result instead of one direct `contract_structural()` return value.
- **`data/osm/raw_graph/`**: new intermediate directory, same shape as `base_graph/`, gitignored
  like everything else under `data/`, ~4.5 GB (see "Cost of `raw_graph/`"). Not consumed by
  anything except this new phase 2 — not a new app-facing or `copy_public_data` artifact.
- **`data/osm/tile_contraction/<cell_id>/`**: per-worker output shards (final edges, boundary
  edges, boundary nodes), read back by the phase-3 stitch. Same gitignored-intermediate status;
  exists to keep worker results off the pickle path.

## Testing strategy

- **Unit**: `contract_structural`'s new `forced_keep` param — a fixture where a degree-2 node is
  forced `keep` anyway, asserting it survives as its own node instead of being absorbed (extends
  the existing `test_contraction.py` chain fixture pattern).
- **Unit**: `edges_interior` pass-through — contract two chain edges that each already carry an
  interior polyline, assert the merged edge's interior is the concatenation in walk order, and
  include the case where the walk enters the second edge at its `v` end so the reversal is
  actually exercised (per (b)).
- **Unit**: `edges_road_m` pass-through — a part-road chain edge, assert the merged `road_m` is the
  sum of the inputs' `road_m` and not the sum of their `dist` (per (c)).
- **Unit**: safe/unsafe edge classification as a pure function of two nodes' `cell_id`s — trivial,
  fully isolated from the graph algorithm.
- **Integration**: the 3-way-junction worked example above, built as an explicit small fixture
  (3+ tiles, a node with mixed safe/unsafe edges, a longer chain crossing exactly one boundary,
  and a chain crossing *two* boundaries in sequence, which phase 3's single pass must resolve
  end-to-end).
- **Integration, the duplicate-edge regression**: a two-tile fixture with one unsafe edge (B, C)
  where B is a forced-keep boundary node whose only other incident edge is safe. Assert (B, C)
  appears exactly *once* in the merged output. If the worker leaves unsafe edges in its
  `contract_structural` input instead of excluding them, B's walk emits its own (B, C) chain
  alongside the owner tile's direct report and this fixture sees two. Multiset comparison, not set
  — per the reference-equivalence note below.
- **Integration, the (a) regression**: an explicit fixture with a true degree-4 junction placed so
  that exactly two of its chain edges are final and two are boundary. Assert the junction survives
  in the merged output. Without phase 3's `forced_keep` this fixture must fail — write it and
  watch it fail first.
- **Reference equivalence** (the real correctness gate, not "doesn't crash"): tiled vs. untiled
  `contract_structural()` over the same full graph. Compare a **canonical form**, not the raw
  arrays — walk order differs between the two, so edge row order and final node ids legitimately
  differ. Canonicalize as a sorted **multiset** (a sorted *list*, compared element-wise — not a
  `set`) of `(u_coord, v_coord, dist, road_m, sac_rank, via_ferrata, interior_polyline)` with each
  edge's endpoint pair and polyline normalized to one orientation. A `set` would be wrong here in
  the one direction that matters: two genuinely distinct parallel trails between the same junction
  pair can canonicalize identically, and a set silently collapses them — hiding either a real
  parallel edge that the tiled run lost, or a duplicate edge that it invented. Duplicate-edge bugs
  are precisely this test's job to catch, so it must not be blind to multiplicity.
- **Validation against real data**: run tiled `build_base_graph.py` against the real
  AT+Bayern `trails.osm.pbf` and diff its `base_graph/` output against the current untiled output
  before trusting timing numbers — this is the one step that requires actually eating the real run.
  Same caveat: **not** byte-for-byte. Compare node/edge counts, the canonical form above (or a hash
  of it), and spot-checked distances/polylines.

## Open questions for planning

- Exact worker task granularity/scheduling (mirror `build_hub_edges.py`'s per-cell
  `ProcessPoolExecutor` dispatch, including progress logging per the session's new
  `pipeline/CLAUDE.md` rule).
- Whether `raw_graph/` should be deleted after a successful run (it's a large intermediate, not
  needed once `base_graph/` exists) or kept for debugging/re-tiling without re-streaming.
- Whether `doit`'s `file_dep`/`targets` wiring for `build_base_graph` needs updating for the new
  intermediate targets (`raw_graph/`, `tile_contraction/`).
- Same question for `tile_contraction/` shards: delete after a successful stitch, or keep so phase
  3 can be re-run without re-contracting.
- Whether phase 1's ~4.5 GB write plus scattered per-worker reads is better avoided entirely by
  keeping the raw arrays in shared memory (`multiprocessing.shared_memory`) instead of on disk.
  Cheaper in I/O, but loses the "re-tile without re-streaming" property and needs the whole raw
  graph resident at once. Decide with a measurement of phase 1's write time, not upfront. Note the
  dev box is Windows, so `ProcessPoolExecutor` uses **spawn**, not fork: workers inherit nothing
  and each `shared_memory` block has to be re-attached by name in every worker. That's more
  plumbing than the mmap-per-worker route `build_hub_edges.py` already uses, and it removes most of
  the "just inherit the arrays" appeal the option would have under fork.
- Per-worker `progress_every` output interleaves across 88 processes. Either drop it inside workers
  and log only per-cell completion (the `build_hub_edges.py` pattern `pipeline/CLAUDE.md` mandates),
  or funnel it through a queue.
