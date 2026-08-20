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
   - Loads its own cell's nodes/edges directly from `raw_graph/` (cell-sorted, so this is a
     contiguous slice via `cell_index.npy` — no distance-based padded buffer needed, see
     "Correctness" below for why).
   - Classifies every incident edge of its own nodes as **safe** (both endpoints' home
     `cell_id` == this tile) or **unsafe** (endpoints in different cells).
   - Runs `contract_structural()` with a new `forced_keep` mask: any node touching at least one
     unsafe edge is forced `keep`, regardless of its true degree (this tile can't see that node's
     complete edge set, so it can't know its real degree).
   - Splits its contraction output into **final** chain edges (both endpoints are true interior
     keep-nodes, never touch an unsafe edge — these are done, no reconciliation needed) and
     **boundary** chain edges (at least one endpoint is a forced-keep boundary node — provisional,
     go to phase 3).
   - Additionally emits every unsafe edge it owns (see tie-break below) directly, uncontracted,
     into the boundary set.

3. **Serial stitch pass.** Collect every tile's boundary nodes + boundary chain edges + owned
   unsafe edges into one small graph (small because it's bounded by total tile *boundary length*,
   not tile count or total node count — most of the graph is already fully resolved in phase 2).
   Run the *unmodified* `contract_structural()` (no `forced_keep`) over it once, serially. This
   resolves any node that was only forced-`keep` due to tiling but is actually a true pass-through
   once its full edge set (assembled from every tile that touched it) is known.

**Final output** = every tile's final (non-boundary-touching) chain edges, union phase 3's
stitched chain edges. No further dedup: by construction (see below) each raw edge is walked by
exactly one tile or reported exactly once as unsafe, so nothing overlaps. Node/edge id
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
  in its own tile's local contraction — only its own tile can ever see its complete true edge set
  (a node's home tile's one-hop closure over its own nodes' edges always includes every edge that
  node has, since raw edges are short single OSM-way-segment hops, not long chains).

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

**Consequence:** gathering a tile's data doesn't need `build_hub_edges.py`'s distance-based
`buffer_km` padding at all (that buffer exists because hub-to-hub paths are bounded by
`maxEdgeKm`, which has no equivalent bound here — chains are structural, not distance-capped). A
tile only needs its own cell-sorted slice of `raw_graph/` plus a one-hop closure to pull in unsafe
edges' far endpoints (for their coordinates) — the classification itself is a local property
(compare two `cell_id`s already stored per node), no padded gather needed.

## New/changed interfaces

- **`lib/contraction.py`'s `contract_structural()`**: add optional `forced_keep: np.ndarray[bool]`
  (default all-`False`), same shape as the existing `keep` computation. Change
  `keep = degree != 2` to `keep = (degree != 2) | forced_keep`. Small, targeted, backward
  compatible — every existing caller/test that doesn't pass it is unaffected. Keeps
  `progress_every` (added earlier this session) as-is.
- **New module, `lib/tile_contraction.py`** (or a function set in `build_base_graph.py` — decide
  during planning based on how much other code wants to import it): the per-tile worker function
  (classify safe/unsafe, build `forced_keep`, call `contract_structural`, split final vs.
  boundary), and the phase-3 stitch function (collect boundary state across tiles, run
  `contract_structural` once more, merge with every tile's final edges).
- **`build_base_graph.py`**: `stream_osm` unchanged; after it, persist `raw_graph/` (new); replace
  the single `contract_structural()` call with the tiled `ProcessPoolExecutor` dispatch + stitch;
  the existing post-contraction packing/cell-sort code (currently lines ~121-187) is unchanged,
  just fed the merged result instead of one direct `contract_structural()` return value.
- **`data/osm/raw_graph/`**: new intermediate directory, same shape as `base_graph/`, gitignored
  like everything else under `data/`. Not consumed by anything except this new phase 2 — not a
  new app-facing or `copy_public_data` artifact.

## Testing strategy

- **Unit**: `contract_structural`'s new `forced_keep` param — a fixture where a degree-2 node is
  forced `keep` anyway, asserting it survives as its own node instead of being absorbed (extends
  the existing `test_contraction.py` chain fixture pattern).
- **Unit**: safe/unsafe edge classification as a pure function of two nodes' `cell_id`s — trivial,
  fully isolated from the graph algorithm.
- **Integration**: the 3-way-junction worked example above, built as an explicit small fixture
  (3+ tiles, a node with mixed safe/unsafe edges, a longer chain crossing exactly one boundary,
  and a chain crossing *two* boundaries in sequence to exercise phase 3 needing to walk through a
  node that was itself only resolved by an earlier phase-3 pass) — assert the tiled result exactly
  matches `contract_structural()` run once, untiled, over the same full graph. This
  reference-equivalence test (tiled vs. untiled on identical input) is the real correctness gate,
  not just "doesn't crash."
- **Validation against real data**: run tiled `build_base_graph.py` against the real
  AT+Bayern `trails.osm.pbf` and diff its `base_graph/` output against the current untiled
  output (byte-for-byte or structurally, node/edge count + spot-checked distances) before trusting
  timing numbers — this is the one step that requires actually eating the real run.

## Open questions for planning

- Exact worker task granularity/scheduling (mirror `build_hub_edges.py`'s per-cell
  `ProcessPoolExecutor` dispatch, including progress logging per the session's new
  `pipeline/CLAUDE.md` rule).
- Whether `raw_graph/` should be deleted after a successful run (it's a large intermediate, not
  needed once `base_graph/` exists) or kept for debugging/re-tiling without re-streaming.
- Whether `doit`'s `file_dep`/`targets` wiring for `build_base_graph` needs updating for the new
  intermediate target.
