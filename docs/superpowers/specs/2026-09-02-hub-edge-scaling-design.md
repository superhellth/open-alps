# Scaling `build_hub_edges` to a bus-stop-sized access-point set

Date: 2026-09-02
Status: draft, not yet approved for planning
Revised: 2026-09-02 after review — every figure below has been checked against the repo and
`data/` (see "Verified figures" at the end); §A/§B gained the scheduling, memory, DAG and
payload consequences the first draft missed, and open questions 1 and 3 are now answered.

Follows on from `docs/superpowers/specs/2026-08-19-pipeline-v2-design.md`, whose per-cell
tiled/multiprocess restructuring of the hub-edge query is still the right shape. Nothing in the
V2 output contract (`RECORD_DTYPE`, `hut_edges/` + `start_edges/`, the access→hut storage
direction, the variant grid) is changed by this spec — only how those records are computed, and
how many of them get full geometry materialized.

## Problem

Commits `c572e47`/`5601f86` extended `fetch_stations_parking.py` to bus stations. `start_points.npy`
now holds **76,669** access points (65,810 station, 10,749 parking, 110 partner) against the
**15,674** the last full run used — 4.9×. Three things break at that multiplier, and only the first
is the one that was noticed.

### P1 — the routing pass is linear in access-point count

Measured `hub_edge_query` at the old hub count (846 huts + 15,674 access points, 4 variants,
12 workers, `data/timings.jsonl`):

| step | CPU-s (summed over workers) | share |
| --- | --- | --- |
| `distances` | 24,641 – 26,217 | **85%** |
| `paths` | 3,635 – 3,868 | 13% |
| `build_igraph` | 305 – 764 | 2% |
| `gather_subgraph` | 6 – 11 | ~0% |

Wall clock 2,940 – 3,158 s (~52 min).

The `distances` step is `graph.distances(source=[src_v], target=unique_target_vs, weights="dist")`
(`build_hub_edges.py:171`). igraph runs a single-source Dijkstra over the entire masked cell
subgraph for that call, with no distance cutoff. A route subgraph is a 60 km cell padded by
`maxEdgeKm` = 30 km, i.e. ~120×120 km — `cell_0/local_edges.npy` is 90 MB, ~940k edges over ~800k
nodes, and the hut targets are spread across the whole of it, so the Dijkstra settles essentially
the full subgraph whether or not igraph early-exits once the target set is reached.

> Correction to the first draft: it asserted igraph "does not early-exit once the target list is
> settled". igraph's Dijkstra does appear to track a remaining-target count and break on it. This
> changes nothing here — the targets span the padded box either way — but §A's projection should
> be read as a floor rather than an exact figure, because the inverted direction's target set is
> larger and more spread and may settle marginally more of the subgraph per call.
>
> A related dead end, recorded so it is not re-litigated: python-igraph **1.0.0**'s
> `Graph.distances(source, target, weights, mode, algorithm)` has **no cutoff parameter**, so
> "just cap the Dijkstra at `maxEdgeKm`" is not reachable without swapping the routing call to
> `scipy.sparse.csgraph.dijkstra(..., limit=)`. After §A the whole step costs ~20 CPU-minutes, so
> that trade is not worth making.

So the cost model is:

```
distances_cost  =  n_hubs x n_variants x O(E_cell log V_cell)
```

Target count is ~free; source count is linear. Back-solving from the measurement:
25,000 CPU-s / (16,520 hubs × 4 variants) = **0.378 s per Dijkstra**.

Projected at the new hub count: 77,515 × 4 × 0.378 s = **~117,000 CPU-s ≈ 32.5 CPU-h**, i.e.
**~2.7 h wall** on 12 workers for `distances` alone, ~3.5 h once `paths` scales with it.

### P2 — the geometry output blows up, and is then thrown away

`data/osm/start_edges/geometry.npy` is **already 2.9 GB** at 212,862 records, because an access
edge averages **1,087 geometry points** (`geom_count.mean()` over FAST_ANY rows). At 4.9× that is
roughly 1M records and **~14 GB** on disk.

What actually ships from it (`build_approach_table.py`, `approaches.json`):

| | rows |
| --- | --- |
| `start_edges/records.npy` (all variants) | 212,862 |
| … FAST_ANY only | 74,616 |
| retained approach table (k=3 per hut + reserved type slots) | **1,829** |
| reverse-index pairs (loop closure) | 30,934 |

So the pipeline routes and materializes full geometry for ~200k pairs (→ ~1M) in order to ship
~33k. The selection that discards 99% of it lives one layer too late, in postprocessing.

### P3 — the same blowup lands in the browser, and that is the user-visible half

P2 as first written reads like disk hygiene. It is not: the per-record geometry is *shipped*.
Current `huts/public/data/`:

| file | today | projected at 4.9× | how the client uses it |
| --- | --- | --- | --- |
| `start-edge-geometry.bin` | **147 MB** | ~720 MB | byte-ranged per leg (`loadLegGeometry.ts`) |
| `start-edge-geometry.json` | **713 KB** | ~3.5 MB | **fetched whole** on the first approach render — one `point_counts` entry per record |
| `start-edges.pmtiles` | **102 MB** | ~500 MB | `GraphPage.tsx`'s raw-network view |
| `approaches.json` | **11 MB** | grows with density | reverse index, fetched whole by `loadApproaches.ts` |

`start-edge-geometry.json` is the sharp one: it is a flat JSON array with one entry per
`start_edges` record, downloaded in full before any approach leg can be drawn. §B fixes all four
by construction, and that — not the 14 GB of intermediates — is the reason §B is not optional.

(Unrelated but noticed while measuring: `start-edge-stats.json` is **654 MB** in
`huts/public/data/` and is not in `dodo.py`'s `PUBLIC_FILES`. It is a stale artifact of an earlier
run and can be deleted.)

## Non-goals

- Changing `RECORD_DTYPE`, the `hut_edges/`/`start_edges/` directory layout, the access→hut storage
  convention, or `approaches.bin`/`approaches.json`'s shape.
- Changing the variant grid, the speed model, or `maxEdgeKm` as the hut↔hut leg cap.
- Any change to `huts/` source. This is entirely a `pipeline/` problem (bad/oversized emitted
  data), and per the root `CLAUDE.md`'s "Fix problems at their root layer" it must not be papered
  over with a client-side filter. Note that §B nonetheless *changes what the client receives*: the
  `#graph` route's start-edge layer goes from "every access edge" to "approach-relevant access
  edges only", and the payload sizes in P3 drop by an order of magnitude. That is a consequence to
  accept deliberately, not a surprise to discover during the run.
- Extending scope past AT+Bayern.
- Making the approach selection *exact* rather than an over-selected approximation. B4 measures the
  approximation and sizes the margin so it is small; the scalars-only path walk that would remove it
  entirely costs roughly a second `paths` pass and is parked as
  `docs/backlog/exact-approach-selection-scalars-only-path-walk.md`.
- Fixing `select_approaches`' reserved-type-slot overwrite. It is a real, measured shipped-data bug
  (102 of 610 huts) that §B7 preserves verbatim; it is filed separately as
  `docs/backlog/approach-reserved-type-slot-overwrite.md` so it does not ride along on a
  performance change.

---

## A. Invert the routing direction — huts become the sources

**A1.** `compute_hub_edges_for_cell` already only ever routes *to* huts (`hut_targets`, line 123),
and `build_igraph_from_base` builds the graph `directed=False` (`lib/cell_igraph.py:221`). The
source/target roles are therefore free to swap, and the current assignment is the expensive one.

Change the per-cell loop to:

- **sources** = `[h for h in core_hubs if h["type"] == binfmt.TYPE_HUT]` — the huts whose cell this
  is (~18 per cell on average, 846 total).
- **targets** = every candidate hub in the padded bounds — huts *and* access points.

One Dijkstra per (hut, variant) yields the distance to every access point in range at once.
Dijkstra count drops from 310,060 to **3,384**: a ~90× cut on the step that is 85% of the run, and
`distances` becomes **independent of access-point count**. Adding another 60k bus stops after this
costs nothing in this step.

**A2 — correctness of the pair set.** The padded-bounds argument is symmetric, so no pair is lost
or duplicated:

- Coverage: an access point `A` within `maxEdgeKm` beeline of a hut `H` in cell `C` necessarily
  lies in `bbox(C) + maxEdgeKm`, which is exactly `_candidate_hubs_for_cell(C)`. Trail distance ≥
  beeline distance, so the beeline bbox is a safe superset — the same argument the current
  direction relies on, mirrored.
- Subgraph adequacy: `gather_padded_subgraph` pads by `maxEdgeKm` around `C`, so every point on a
  ≤ `maxEdgeKm` path *from* a node in `C` is inside the slice. Unchanged — the source is still in
  `C`.
- No duplication: each hut is a core hub of exactly one cell, so each `(hut, access)` pair is
  emitted by exactly one worker. `merge_and_dedup`'s existing directional pass-through for access
  records stays correct as-is. Hut↔hut pairs keep the existing `seen_hut_pairs` in-cell dedup plus
  the cross-shard dedup.

**A2b — the pair set is preserved exactly; individual routes may differ slightly.** The cutoff at
line 187 runs on `dist`, but the emitted path is **time**-shortest and can exceed `maxEdgeKm` —
which is precisely why line 214 re-checks `path.distance_m > max_edge_m` on the routed path. A
time-shortest path longer than 30 km is not guaranteed to fit inside the padded box, and *which*
box it escapes differs between the two directions: today the pair `(A, H)` is routed on
`padded(cell(A))`, after A on `padded(cell(H))`. Both boxes provably contain the whole
`dist`-shortest path, so no pair appears or disappears — but a handful of records can come back
with a different polyline, or be clipped in one direction and not the other. This is a pre-existing
property of the padded-box scheme, not something A introduces; A only changes which routes it bites.
Validation (open question 4) must therefore budget for a small non-zero diff rather than demand
equality.

**A3 — record orientation.** Records are stored access→hut by convention. A hut-sourced path must
be reversed before being written as an access record:

1. Reverse `path.coords` (and build `geometry` with the access point first, hut last).
2. **Swap `ascent_m`/`descent_m` on the `PathResult`** — the base graph stores them in a fixed u→v
   direction and `accumulate_path` already swaps per traversed edge, so the swap at path level is
   the exact inverse.
3. **Then** call `fold_endpoint_snaps(path, access_snap, hut_snap)`. Order matters: the fold
   attributes each end's `gap_dz_m` differently for departure vs. arrival
   (`lib/edge_output.py:103-105`), so it must be handed an already-correctly-oriented path *and*
   the two snaps in stored order. Swapping after folding mis-attributes the two gaps.

`distance_m`, `road_m`, `max_ele_m`, `ungraded_m`, `inferred_m`, `sac_rank`, `via_ferrata` are
direction-free. `path.base_edge_ids` is traversal-ordered and must be reversed too — today that is
latent rather than live, because `write_edge_records(..., write_edge_ids=False)` for `start_edges`
leaves `prefix_ids`/`suffix_ids` as `-1` padding; reverse it anyway so turning `write_edge_ids` on
later is not a silent correctness regression. Hut↔hut records need no reorientation.

**A4 — igraph size, measured.** Every candidate access point in the padded region now needs a snap
vertex in the cell igraph, not just the core ones. Measured over the current `start_points.npy` and
the live grid (60 km cells, 30 km padding):

| candidate hubs per padded cell | mean | median | p90 | max |
| --- | --- | --- | --- | --- |
| | 4,932 | 4,754 | 9,208 | 11,862 |

versus ~1,300 today. Each mid-chain snap nets +1 vertex and +1 edge, so ~+5k edges on a 940k-edge
graph — under 1%, and `build_igraph` itself stays cheap per call.

**What is not cheap is the Python-level per-snap work**, and it is currently *unmeasurable*:
`base_arrays = build_base_igraph_arrays(subgraph, snaps)` at `build_hub_edges.py:143` sits outside
every `timer.step`, so it lands in the cell's wall clock but in none of the step columns. Adding a
timer step around it is a prerequisite for evaluating A, not an afterthought — the first draft's
"build_igraph is 2% of the run, so this is noise" reasoning is 2% of the *old* run, and after A
removes 95% of `distances` the igraph/array-building term becomes a leading cost rather than a
rounding error.

Two knock-on costs in the same family, both expected to be tolerable but worth watching: the
`keys` set in `_run_cell` and the `local_persisted` dict pickled into each worker both grow from
"core hubs + huts" to "core huts + all candidates" (~5–12k rows), as does
`hub_snap.reconstruct_local_snaps`' translation loop.

**A5 — scheduling inverts with the direction, and `_cell_workload_score` must follow.**
`_cell_workload_score` multiplies subgraph bytes by `len(core_hubs)`. After A the routing cost is
driven by core **huts**, and the two are wildly uncorrelated — measured: cell 19 has 5,561 core hubs
and **4** huts; cell 42 has 5,183 hubs and 4 huts; cell 27 has 3,264 hubs and 44 huts. Left as-is,
LPT would schedule the cheapest cells first and straggle on the expensive ones, which is worse than
no sorting at all.

The hut distribution also changes the shape of the run: **only 46 of 60 cells contain a hut**, so 14
cells become no-ops, and the top 12 cells hold 71% of all huts (largest cell: 76). Makespan on 12
workers is then set by that 76-hut cell — 76 × 4 × 0.378 s ≈ 122 s of `distances`, plus its igraph
builds — which is what makes the "under 10 min" target in the outcome table credible.

**A6 — A cannot land alone: it is a memory wall, not just a disk one.** The first draft treated
"A-only still writes ~14 GB" as a disk-space judgement call. It is not survivable at all:

- `accumulate_path` accumulates `trail_coords` as a **Python list of coordinate tuples**.
- `_run_cell` returns those records through `ProcessPoolExecutor`, and `__main__` accumulates
  `shard_records` for **every cell** before `merge_and_dedup` and `write_edge_records` run.
- Today that is 231M coordinate tuples resident in the parent (2.9 GB as packed f4 pairs on disk;
  on the order of 16 GB as live Python objects) against a 23 GB machine.

At 4.9× the parent OOMs long before anything reaches disk. **A and B ship together** — or A lands
with the access half of the emit temporarily switched off. This answers open question 3.

---

## B. Split "distance" from "geometry", and select before materializing

Even with A, `paths`, the ~14 GB write and the P3 payload remain, all proportional to the pair count
rather than to what ships. The fix is to move the k-selection out of `build_approach_table.py` and
into the DAG, so geometry is only ever built for records that survive.

**B1 — new task DAG shape.** The first draft's four-node tree omitted everything hanging off
`start_edges/records.npy`, and split one Dijkstra pass into two for no gain. Corrected:

```
gather_route_subgraphs
  └─ build_hub_edges              sources = huts, ONE Dijkstra pass per (hut, variant)
        ├─> hut_edges/            hut <-> hut, with geometry   (~8k records today)
        └─> access_distances.npy  hut -> access, distance/time ONLY, no geometry
              └─ select_approach_pairs    NEW: global, pure numpy, seconds
                    └─ build_access_edges  geometry for the selected pairs -> start_edges/
                          ├─ build_profiles        (rewrites profile_offset IN PLACE)
                          ├─ build_start_edge_tiles
                          ├─ build_approach_table
                          └─ build_edge_payload / build_edge_ids
```

Two things this fixes over the first draft:

- **`build_hut_edges` and `build_access_distances` must not be separate tasks.** One Dijkstra per
  (hut, variant) already settles hut *and* access targets simultaneously — splitting them doubles
  the Dijkstra count and the cell-igraph builds (which A4 shows are now a leading term) for zero
  benefit. Keep one task with two outputs. `build_access_edges` is then the only extra igraph pass:
  two passes total, not three.
- **`build_profiles` ordering is load-bearing and non-obvious.** It rewrites
  `records.npy`'s `profile_offset`/`profile_count` in place and is *not* declared as a target, which
  is why `dag/postprocessing.py` wires the tile tasks to it with `task_dep` rather than `file_dep`.
  Inserting `build_access_edges` between `build_hub_edges` and `build_profiles` means that
  `task_dep` chain has to be re-derived, not just re-pointed.

**B2 — why a separate global step is needed at all.** Top-K-per-hut is **cell-local**: every
candidate for a hut lies inside its own cell's padded set, so a worker can already rank them. But
the loop-closure reverse index (E2 in `build_approach_table.py` — every hut reachable from a
*retained* start id) is not: a retained start point may be reachable from huts in a neighbouring
cell. That closure is what forces one global round trip, hence `select_approach_pairs` as its own
task rather than in-worker selection.

**B3 — intermediate contract.** `build_hub_edges` writes one compact row per
`(hut_id u2, start_id u8, start_type u1, variant u1)`: `distance_m f4`, `time_s f4`. No coords, no
profile. ~1.04M rows × 20 B = **~21 MB**. This is also a genuinely useful artifact on its own — it
is the first cheap, complete answer to "which trailheads can reach which hut", queryable without
touching geometry.

**B4 — ranking without a path walk, and the over-selection factor.**
`build_approach_table.py` ranks candidates by `speed.din_duration_h(distance_m, ascent_m,
descent_m)`, which needs `ascent_m`/`descent_m` — and those only exist after a path walk. The
Dijkstra yields `time_s` for free (it is the routing objective). So either rank on a proxy and
over-select, or pay for a walk. Measured, then decided:

*The measurement.* Over the current run's 74,616 FAST_ANY rows, grouped by (hut, source_type) —
1,348 groups, mean 55 candidates, max 1,345 — using `distance_m` as a **deliberately worse** stand-in
for `time_s` (the real objective is not stored, so this is an upper bound on the churn a
correlated-but-different metric causes):

| over-select | DIN-best-3 falling outside it |
| --- | --- |
| top-3 | 14.9% |
| top-5 | 5.6% |
| top-10 | **1.2%** |
| top-20 | 0.23% |

`time_s` accounts for per-edge slope and so tracks DIN far more closely than raw distance does, but
"never" is clearly not the answer, and the denser access-point set multiplies candidates per group
by ~5×, which makes near-ties *more* common, not less.

*The decision.* **Over-select 20 per hut per source type**, and let `build_approach_table.py`
re-rank the materialized rows by `din_duration_h` exactly as today. 20 × 1,348 groups × 4 variants
is still ~4% of the pair set, so the safety margin is nearly free — there is no reason to shave it
to 10 and buy a measurable divergence.

*The exact alternative, if 4% of divergence risk is still unwanted.* Run a **scalars-only path
walk** in the distance pass: `accumulate_path` minus `trail_coords`. The coordinate list is the
entire memory and I/O problem (A6); the walk itself is O(edges traversed) and yields true
`ascent_m`/`descent_m`, making the selection exactly equal to today's by construction and retiring
this question permanently. Cost is roughly the current `paths` step scaled up — order 25 min wall on
12 workers. Recommendation: ship the over-selection, and keep this in reserve if validation shows
the divergence is not where the measurement predicts. Written up as its own follow-up item,
`docs/backlog/exact-approach-selection-scalars-only-path-walk.md` — deliberately **out of scope
here**, so this spec's plan does not carry an optional 25-minute pass it probably does not need.

**B5 — what `build_access_edges` materializes.** The union of:

- (a) the over-selected top-K pairs, and
- (b) the reverse-index closure over the over-selected start ids — **every variant** of every
  `(hut, start)` pair for those starts, not just FAST_ANY. `build_tables` loops records with no
  variant filter, so restricting (b) to FAST_ANY would silently truncate the loop-closure index.

30,934 pairs today, low tens of thousands after densification. It re-runs one Dijkstra per (hut,
variant) — ~1,300 CPU-s after A, cheap enough that caching the first pass's Dijkstras across tasks
is not worth the complexity — and calls `get_shortest_paths` only for that cell's selected target
list.

**B6 — expected sizes.** Geometry for ~60k pairs instead of ~1M. `start_edges/geometry.npy` goes
from a projected ~14 GB to **under 1 GB**, `paths` drops by the same factor, and every row of P3's
shipped-payload table drops with it — `start-edge-geometry.bin` to well under 50 MB,
`start-edge-geometry.json` back to tens of KB, `start-edges.pmtiles` to a fraction of its 102 MB.

**B7 — `build_approach_table.py` after this.** Its selection half becomes a re-rank over an already
short candidate list; its reverse-index half is unchanged (it still reads `start_edges/records.npy`,
which now only contains materialized pairs — a superset of what the closure needs by construction).
Note that its `edge_id` column is a *row index* into `start_edges/records.npy`
(`for edge_id, r in enumerate(records)`) and the client resolves it against
`start-edge-geometry.bin`; that stays internally consistent because both are rebuilt from the same
narrowed record set, but it does mean `approaches.bin` is not byte-comparable across the change.

---

## C. Prefiltering `start_points.npy`

Secondary to A and B — none of these change the asymptotics — but each is small and independently
worthwhile.

**C1 — `filter_to_hut_range` is wrong in longitude (a bug, not an optimization).**
`filter_start_points.py:51-61` builds a `cKDTree` over raw `(lon, lat)` degrees and thresholds at
`max_edge_km * (1/111.320)` degrees. That constant is the km-per-degree of *latitude*. At 47.5°N a
degree of longitude is ~75.2 km, so a point exactly 30 km due east sits 30/75.2 = 0.399° from the
hut and is tested against a 0.269° threshold — and is **dropped**. The filter is an ellipse
squashed east-west, not a circle.

The error is one-sided: a point at exactly the 0.269° threshold due east is only 20.3 km away, well
inside the cap, so the filter never admits a point it should reject — it only silently discards
valid trailheads. Fix: multiply longitude by `cos(mid_lat)` (or the per-point `cos(lat)`) before
building the tree, matching `lib/grid.py`'s `km_per_deg_lng`.

This makes the kept set **larger**, on top of the 4.9× already banked, which is an argument for A
and B rather than against them — and it must land after them, or it makes the current runtime
worse. **The growth factor is currently unmeasured**, and it re-sizes §B. Measure the corrected
kept-set size *before* fixing B's over-selection and payload arithmetic, even though the fix itself
ships last.

**C2 — batch the KD-tree query.** The same function loops `hut_tree.query(...)` once per point over
122k+ points in Python. One `hut_tree.query(coords_array, k=1)` instead. Note this buys **no
measurable time**: `filter_start_points` runs in 3.48 s end to end (`data/timings.jsonl`,
2026-09-02). Do it because C1 forces the tree to be rebuilt in projected coordinates anyway, not on
performance grounds.

**C3 — cluster co-located stations.** Deduping `stations.geojson` on `(name, ~100 m)` collapses
122,567 features to 92,727 (−24%); `Bahnhof Amberg` alone appears 12× inside 100 m, `Hauptbahnhof`
9×. A 200–300 m radius keyed on name would do better. Two open questions for the plan: whether the
representative keeps its own `osm_id` (simplest, and the client only ever renders the retained
approach) or carries a member-id list, and whether clustering belongs in
`fetch_stations_parking.py` (at import, one place) or `filter_start_points.py` (alongside the other
filters). Note that A's snap-vertex dedup already collapses much of this for free — bus stops
within `maxSnapM` of the same road node land on one igraph vertex, and `sorted(set(target_vs))`
already dedups them — so C3's remaining value is mostly in `snap_hubs` cost and in
`start_points.npy` size, not in routing.

**C4 — a separate `graph.maxApproachKm` is REJECTED.** Tempting, and it looked like the biggest
single lever: only 7.6% of FAST_ANY access records are ≤ 10 km, so a 10 km approach cap would drop
92% of them. But the *retained* approaches genuinely use the long tail — measured over the 1,829
rows in `approaches.bin`: p50 **8.95 km**, p75 14.16 km, p90 **21.34 km**, p99 29.24 km. A hard
global cap strands exactly the remote huts whose only trailhead is far away. B's per-hut top-K is
the adaptive version of the same idea and has no such failure mode. If a cap is ever wanted anyway,
it belongs on the *selection* (B4) as a soft preference, never as a hard prefilter.

---

## D. `snap_hubs` is the next bottleneck

**D1.** `hub_snap` went from 180 s wall / 1,768 CPU-s to **846 s wall / 8,722 CPU-s** with the
larger hub set (`data/timings.jsonl`, 2026-08-31). It is linear in hub count and will be the
largest remaining cost once A and B land — after which `hub_edge_query` is minutes, so this is not
a distant "next", it is immediately the top line.

**D2 — cause.** `snap_hub_to_subgraph` (`lib/hub_snap.py:169-181`) opens with a full
`_haversine_m_vec` over **every node in the subgraph** to find the nearest existing graph node, once
per hub — O(hubs × nodes). The subgraph in question is `snap_hubs.py`'s own gather: a 60 km cell
padded by `_buffer_km_for(max_snap_m)` = 1 km (**not** `build_hub_edges`' 30 km-padded one), which
is still hundreds of thousands of nodes. The *edge* candidate search below it is already indexed
(`_candidate_edges_near` → a cached per-subgraph `cKDTree`, `_build_edge_spatial_index`); the node
search simply never got the same treatment.

**D3 — fix.** Build one `cKDTree` over `local_nodes` per subgraph, cached on the subgraph exactly
the way `_edge_spatial_index` already is, and query it instead of scanning. Same
projected-metres coordinate space as the edge index so the two agree. Expected 10–50× on the `snap`
step, for a change contained to `lib/hub_snap.py`. The `SnapRejection` fallback path
(`node_dists` reused at line 210 to report the nearest-node distance even when nothing qualified)
needs the KD-tree's own nearest-distance instead of the full vector. Note the tie-break changes
subtly: today's `argmin` is over exact haversine, the KD-tree's is over projected metres, so two
nodes equidistant to within projection error could swap. Irrelevant to output quality, but it means
snap results are not guaranteed bit-identical across this change either.

---

## Expected outcome

| | today (projected at 76,669 access points) | after A+B (+D) |
| --- | --- | --- |
| Dijkstras | 310,060 | 3,384 (+ ~3,384 in the geometry pass) |
| `hub_edge_query` wall | ~3.5 h (would OOM first) | under 10 min |
| parent-process peak RSS | ~80 GB → OOM | bounded by the selected pair set |
| `start_edges/geometry.npy` | ~14 GB | < 1 GB |
| `start-edge-geometry.bin` (shipped) | ~720 MB | < 50 MB |
| `start-edge-geometry.json` (shipped, fetched whole) | ~3.5 MB | tens of KB |
| `start-edges.pmtiles` (shipped) | ~500 MB | a fraction of today's 102 MB |
| `hub_snap` wall | 846 s | ~30–90 s |

Shipped outputs unchanged in shape; `approaches.bin` gains genuinely closer trailheads because the
access-point set is denser, which is the point of having added bus stations in the first place.

## Open questions

1. ~~B4's over-selection factor.~~ **Answered** — measured above. Use 20; the scalars-only path
   walk that would make the selection exact is parked as
   `docs/backlog/exact-approach-selection-scalars-only-path-walk.md`, not carried by this spec.
2. **C3's placement and id semantics** — `fetch_stations_parking.py` vs. `filter_start_points.py`,
   and representative-only vs. member-id list. Still open.
3. ~~Whether `build_hub_edges` should keep emitting access records during the transition.~~
   **Answered** — no. A-only OOMs the parent process (A6), so A and B ship together, or A lands with
   the access emit switched off behind a flag.
4. **Validation strategy.** A full rerun is hours even after the fix, and `build_base_graph` must
   not be disturbed. Proposal: run A and B against a single cell (a `--only-cell` flag, or an
   `analysis/` script calling `compute_hub_edges_for_cell` directly, per `pipeline/analysis/`'s
   existing conventions) and diff the resulting records against the current
   `start_edges/records.npy` restricted to that cell, before any full run is requested. Per A2b and
   D3 the diff will not be empty: define the expected tolerance up front — the **pair set** must
   match exactly, while per-record polylines and scalars may differ for the small number of legs
   whose time-shortest route is clipped differently by the two padded boxes.
5. **New:** what the per-cell `build_base_igraph_arrays` cost actually is at 5–12k snaps per cell
   (A4). It is unmeasurable until a timer step is added, and it is the term most likely to make the
   "under 10 min" figure wrong.

## Verified figures

Everything numeric above was checked against the repo on 2026-09-02 rather than carried over from
the draft. Exact matches: 212,862 `start_edges` records / 74,616 FAST_ANY / 8,237 hut records;
`geometry.npy` 2,908,573,408 B; `geom_count.mean()` = 1087.45; 1,829 approach rows over 610 huts;
30,934 reverse-index pairs; 76,669 `start_points` (65,810 / 10,749 / 110); 122,567 station and
27,316 parking features; the `hub_edge_query` and `hub_snap` step splits in `data/timings.jsonl`;
C4's percentiles and the 7.6% ≤10 km share. Newly measured for this revision: per-padded-cell
candidate counts (A4), per-cell hut distribution (A5), the over-selection table (B4), and the
`huts/public/data/` sizes (P3).
