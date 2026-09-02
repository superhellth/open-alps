# Scaling `build_hub_edges` to a bus-stop-sized access-point set

Date: 2026-09-02
Status: draft, not yet approved for planning

Follows on from `docs/superpowers/specs/2026-08-19-pipeline-v2-design.md`, whose per-cell
tiled/multiprocess restructuring of the hub-edge query is still the right shape. Nothing in the
V2 output contract (`RECORD_DTYPE`, `hut_edges/` + `start_edges/`, the access→hut storage
direction, the variant grid) is changed by this spec — only how those records are computed, and
how many of them get full geometry materialized.

## Problem

Commits `c572e47`/`5601f86` extended `fetch_stations_parking.py` to bus stations. `start_points.npy`
now holds **76,669** access points (65,810 station, 10,749 parking, 110 partner) against the
**15,674** the last full run used — 4.9×. Two things break at that multiplier, and only the first
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
(`build_hub_edges.py:171`). igraph runs a **full single-source Dijkstra over the entire masked cell
subgraph** for that call: it does not early-exit once the target list is settled, and there is no
distance cutoff. A route subgraph is a 60 km cell padded by `maxEdgeKm` = 30 km, i.e. ~120×120 km —
`cell_0/local_edges.npy` is 90 MB, ~940k edges over ~800k nodes.

So the cost model is:

```
distances_cost  =  n_hubs x n_variants x O(E_cell log V_cell)
```

Target count is **free**; source count is **linear**. Back-solving from the measurement:
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

## Non-goals

- Changing `RECORD_DTYPE`, the `hut_edges/`/`start_edges/` directory layout, the access→hut storage
  convention, or `approaches.bin`/`approaches.json`'s shape. The shipped payload should be
  bit-identical modulo the denser access-point set.
- Changing the variant grid, the speed model, or `maxEdgeKm` as the hut↔hut leg cap.
- Anything in `huts/`. This is entirely a `pipeline/` problem (bad/oversized emitted data), and
  per the root `CLAUDE.md`'s "Fix problems at their root layer" it must not be papered over with a
  client-side filter.
- Extending scope past AT+Bayern.

---

## A. Invert the routing direction — huts become the sources

**A1.** `compute_hub_edges_for_cell` already only ever routes *to* huts (`hut_targets`, line 123),
and `build_igraph_from_base` builds the graph `directed=False` (`lib/cell_igraph.py:221`). The
source/target roles are therefore free to swap, and the current assignment is the expensive one.

Change the per-cell loop to:

- **sources** = `[h for h in core_hubs if h["type"] == binfmt.TYPE_HUT]` — the huts whose cell this
  is (~14 per cell, 846 total).
- **targets** = every candidate hub in the padded bounds — huts *and* access points.

One Dijkstra per (hut, variant) yields the distance to every access point in range at once.
Dijkstra count drops from 310,060 to **3,384**: a ~90× cut on the step that is 85% of the run, and
`distances` becomes **independent of access-point count**. Adding another 60k bus stops after this
costs nothing in this step.

**A2 — correctness.** The padded-bounds argument is symmetric, so no pair is lost or duplicated:

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

**A3 — record orientation.** Records are stored access→hut by convention. A hut-sourced path must
be reversed before being written as an access record: reverse `path.coords`, and **swap
`ascent_m`/`descent_m`** (the base graph stores them in a fixed u→v direction and `accumulate_path`
already swaps per traversed edge, so the swap at record level is the exact inverse). `distance_m`,
`road_m`, `max_ele_m`, `ungraded_m`, `inferred_m`, `sac_rank`, `via_ferrata` are direction-free.
`fold_endpoint_snaps` takes `(src_snap, tgt_snap)` and must be handed them in the stored order.
Hut↔hut records need no reorientation.

**A4 — igraph size.** Every candidate access point in the padded region now needs a snap vertex in
the cell igraph, not just the core ones. That is roughly 5–10k mid-chain snaps per cell instead of
~1.3k, each adding one vertex and two synthetic edges while removing one — ~+20k edges on a 940k
edge graph, under 3%. `build_igraph` is 2% of the run, so this is noise. It is worth re-measuring
rather than assuming, since `build_base_igraph_arrays` does Python-level per-snap work.

**A5 — sequencing.** A is independently landable and is the whole 90×. B (below) should not block
it.

---

## B. Split "distance" from "geometry", and select before materializing

Even with A, `paths` and the ~14 GB write remain, both proportional to the pair count rather than
to what ships. The fix is to move the k-selection out of `build_approach_table.py` and into the
DAG, so geometry is only ever built for records that survive.

**B1 — new task DAG shape.**

```
gather_route_subgraphs
  ├─ build_hut_edges           hut <-> hut only, with geometry     (~8k records today)
  └─ build_access_distances    hut -> access, distance/time ONLY   (compact table, no geometry)
        └─ select_approach_pairs   NEW: global, pure numpy, seconds
              └─ build_access_edges   geometry for the selected pairs only
```

`build_hut_edges` keeps its current name and semantics, narrowed to hut↔hut — it is small (8,237
records, 130 MB geometry) and unaffected by access-point growth. Splitting it out also makes the
half that feeds the tour-search payload independently rerunnable from the half that feeds
approaches.

**B2 — why a separate global step is needed at all.** Top-K-per-hut is **cell-local**: every
candidate for a hut lies inside its own cell's padded set, so a worker can already rank them. But
the loop-closure reverse index (E2 in `build_approach_table.py` — every hut reachable from a
*retained* start id) is not: a retained start point may be reachable from huts in a neighbouring
cell. That closure is what forces one global round trip, hence `select_approach_pairs` as its own
task rather than in-worker selection.

**B3 — intermediate contract.** `build_access_distances` writes one compact row per
`(hut_id, start_id, start_type, variant)`: `distance_m f4`, `time_s f4`, no coords, no profile.
~1M rows × ~24 B = **~24 MB**. This is also a genuinely useful artifact on its own — it is the
first cheap, complete answer to "which trailheads can reach which hut", queryable without touching
geometry.

**B4 — ranking without a path walk.** `build_approach_table.py` ranks candidates by
`speed.din_duration_h(distance_m, ascent_m, descent_m)`, which needs the routed path. The Dijkstra
already yields the path's `time_s` for free (it is the routing objective). Rank on `time_s` and
**over-select** — top ~10 per hut per source type instead of `approach.k` = 3 — then let
`build_approach_table.py` re-rank the materialized rows by `din_duration_h` exactly as today. The
shipped selection is then identical to the current output as long as the true k-best is inside the
over-selected 10, which time-ranking makes overwhelmingly likely; the over-selection factor is the
tunable safety margin.

**B5 — what `build_access_edges` materializes.** The union of (a) the over-selected top-K pairs and
(b) the reverse-index closure over retained start ids (30,934 pairs today, low tens of thousands
after densification). It re-runs one Dijkstra per (hut, variant) — ~1,300 CPU-s after A, cheap
enough that caching the first pass's Dijkstras across tasks is not worth the complexity — and calls
`get_shortest_paths` only for that cell's selected target list.

**B6 — expected sizes.** Geometry for ~60k pairs instead of ~1M: `start_edges/` goes from a
projected ~14 GB to **under 1 GB**, and `paths` drops by the same factor.

**B7 — `build_approach_table.py` after this.** Its selection half becomes a re-rank over an already
short candidate list; its reverse-index half is unchanged (it still reads `start_edges/records.npy`,
which now only contains materialized pairs — a superset of what the closure needs by construction).

---

## C. Prefiltering `start_points.npy`

Secondary to A and B — none of these change the asymptotics — but each is small and independently
worthwhile.

**C1 — `filter_to_hut_range` is wrong in longitude (a bug, not an optimization).**
`filter_start_points.py:51-61` builds a `cKDTree` over raw `(lon, lat)` degrees and thresholds at
`max_edge_km * (1/111.320)` degrees. That constant is the km-per-degree of *latitude*. At 47.5°N a
degree of longitude is ~75.2 km, so a point exactly 30 km due east sits 30/75.2 = 0.399° from the
hut and is tested against a 0.269° threshold — and is **dropped**. The filter is an ellipse
squashed east-west, not a circle, so it is too *strict* in longitude and is currently discarding
valid trailheads. Fix: multiply longitude by `cos(mid_lat)` (or the per-point `cos(lat)`) before
building the tree, matching `lib/grid.py`'s `km_per_deg_lng`. Note this makes the kept set
**larger**, which is an argument for A and B, not against them — and it must land after them, or it
makes the current runtime worse.

**C2 — batch the KD-tree query.** The same function loops `hut_tree.query(...)` once per point over
122k+ points in Python. One `hut_tree.query(coords_array, k=1)` instead.

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
rows in `approaches.bin`: p50 **9.0 km**, p75 14.2 km, p90 **21.3 km**, p99 29.2 km. A hard global
cap strands exactly the remote huts whose only trailhead is far away. B's per-hut top-K is the
adaptive version of the same idea and has no such failure mode. If a cap is ever wanted anyway, it
belongs on the *selection* (B4) as a soft preference, never as a hard prefilter.

---

## D. `snap_hubs` is the next bottleneck

**D1.** `hub_snap` went from 180 s wall / 1,768 CPU-s to **846 s wall / 8,722 CPU-s** with the
larger hub set (`data/timings.jsonl`, 2026-08-31). It is linear in hub count and will stay the
largest remaining cost once A and B land.

**D2 — cause.** `snap_hub_to_subgraph` (`lib/hub_snap.py:169-181`) opens with a full
`_haversine_m_vec` over **every node in the cell subgraph** to find the nearest existing graph node,
once per hub — O(hubs × nodes), ~77k × several hundred thousand. The *edge* candidate search below
it is already indexed (`_candidate_edges_near` → a cached per-subgraph `cKDTree`,
`_build_edge_spatial_index`); the node search simply never got the same treatment.

**D3 — fix.** Build one `cKDTree` over `local_nodes` per subgraph, cached on the subgraph exactly
the way `_edge_spatial_index` already is, and query it instead of scanning. Same
projected-metres coordinate space as the edge index so the two agree. Expected 10–50× on the `snap`
step, for a change contained to `lib/hub_snap.py`. The `SnapRejection` fallback path
(`node_dists` reused at line 210 to report the nearest-node distance even when nothing qualified)
needs the KD-tree's own nearest-distance instead of the full vector.

---

## Expected outcome

| | today (projected at 76,669 access points) | after A+B |
| --- | --- | --- |
| Dijkstras | 310,060 | 3,384 (+ ~3,384 in the geometry pass) |
| `hub_edge_query` wall | ~3.5 h | under 10 min |
| `start_edges/geometry.npy` | ~14 GB | < 1 GB |
| `hub_snap` wall | 846 s | ~30–90 s (with D) |

Shipped outputs unchanged in shape; `approaches.bin` gains genuinely closer trailheads because the
access-point set is denser, which is the point of having added bus stations in the first place.

## Open questions

1. **B4's over-selection factor.** 10 per hut per source type is a guess. It should be validated
   against the current run by re-ranking the existing `start_edges/records.npy`: how often does the
   `din_duration_h`-best row fall outside the `time_s`-top-10? If the answer is "never", the factor
   can drop.
2. **C3's placement and id semantics** — `fetch_stations_parking.py` vs. `filter_start_points.py`,
   and representative-only vs. member-id list.
3. **Whether `build_hut_edges` should keep emitting access records at all** during the transition,
   or whether A and B land together. A-only is a valid intermediate state that already gets the
   90×, at the cost of still writing ~14 GB — which may be unacceptable on disk even for one run,
   in which case A and B have to ship together.
4. **Validation strategy.** A full rerun is hours even after the fix, and `build_base_graph` must
   not be disturbed. Proposal: run A and B against a single cell (a `--only-cell` flag, or an
   `analysis/` script calling `compute_hub_edges_for_cell` directly, per `pipeline/analysis/`'s
   existing conventions) and diff the resulting records against the current
   `start_edges/records.npy` restricted to that cell, before any full run is requested.
