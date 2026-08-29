# phases/graph_building/ — OSM ways → hut-to-hut trail edges

The expensive phase (`build_base_graph` alone measured ~4.1h for AT+Bayern —
`data/timings.jsonl`). Split into four scripts so each hyperparameter only forces a rerun of the
work that actually depends on it: `build_base_graph.py` (hub-agnostic, depends only on the OSM
extract), `snap_hubs.py` (depends only on `--max-snap-m`/`--max-snap-ascent-m`),
`gather_route_subgraphs.py` (depends only on `--max-edge-km`), and `build_hub_edges.py` (the actual
per-variant routing, depends on both `--max-edge-km` and `graph.variants` — see
`docs/superpowers/plans/2026-08-23-split-build-hub-edges.md` for why the last three were split out
of what was originally one `build_hub_edges.py`).

Replaces an earlier buffer-clip + OSMnx/NetworkX approach — rejected because the bottleneck was
never input size but per-node/edge Python object overhead (dict-of-dicts + shapely geometry per
edge); see "Rejected: buffer-clip + OSMnx" in `pipeline/README.md`.

## `build_base_graph.py` — hub-agnostic base graph (~4.1h for AT+Bayern)

Depends only on `trails.osm.pbf`, not on any hub set, so it's cached across hub-set changes and
downstream hyperparameter retuning — `build_hub_edges.py` loads this output instead of
re-streaming/re-contracting the OSM extract every run. Params: `--tile-size-km` (default
`config.graph.tileSizeKm`).

**Algorithm, in three passes:**

1. **`stream_osm`** — streams `trails.osm.pbf` once via `pyosmium` (`osmium.SimpleHandler`) into
   flat numpy arrays: node coordinates, edge endpoint indices, per-edge haversine distance, a road
   boolean (`highway` in `config.graph.roadHighwayTags`), per-way passability grading
   (`lib/grading.py`'s `classify_way()` — `sac_rank` plus `ungraded_m`/`inferred_m` metres, so an
   edge's ungraded terrain is a summable fact rather than lost under `sac_rank`'s max), a
   `constrained_ok` boolean (`excluded_from_constrained() OR via_ferrata OR ungraded`, precomputed
   once here so Task 13's filtered-graph build per variant per cell is a boolean mask, not a
   re-derivation), and a `via_ferrata` boolean (`highway=via_ferrata` or a `via_ferrata_scale` tag
   present). `time_s`/`ascent_m`/`descent_m` are left at `binfmt.UNSET` here — they're filled later,
   per base edge, by `phases/elevation/compute_edge_profiles.py` (see that phase's README), not by
   this streaming pass. There is no routing "weight" column any more (spec A3): a road is no longer
   penalized inside a distance the client displays — if `ROAD_*` is ever built (deferred pending
   Task 24's post-rebuild road-share measurement) it will be a separate objective column, not a
   revived penalty.
2. **`contract_structural`** (`lib/contraction.py`) — collapses every maximal run of degree-2
   nodes (a pure pass-through chain, no junction) into a single chain edge. This is a lossless
   transform: a degree-2 node has no alternate route, so summing distance/road-length/`ungraded_m`/
   `inferred_m` along the chain, AND-folding `constrained_ok`, and taking the max `sac_rank` walked
   preserves every shortest-path cost *exactly*, while shrinking node/edge count by (measured) an
   order of magnitude or more (~40M raw nodes/edges → far fewer chain edges for AT+Bavaria). Unlike
   an earlier version, contraction here is **structural only** — no hub-snap-point exception, since
   hub sets aren't known yet at this stage; mid-chain hub snapping is deferred to
   `lib/edge_split.py`, invoked at `build_hub_edges.py` query time. Built via CSR-style adjacency
   (`lib/binfmt.py`'s `build_csr_index()` — one stable sort over doubled endpoint arrays plus
   bincount/cumsum for offsets, no Python dict-of-lists), so it scales without per-node Python
   object overhead.
3. **Spatial indexing** — every surviving node is assigned a `lib/grid.py` `Grid` cell id
   (row-major partition of the bbox into `config.graph.tileSizeKm` cells), and nodes are re-sorted
   by cell so `cell_index.npy` addresses one contiguous slice per cell. This is what lets
   `build_hub_edges.py`'s per-cell workers mmap-slice just their own region instead of loading the
   whole graph into memory.

**Output** (`data/osm/base_graph/`, plain `.npy` structured arrays, `lib/binfmt.py`, all
memory-mappable via `np.load(..., mmap_mode="r")`):

| file | dtype (`binfmt.py`) | contents |
|---|---|---|
| `nodes.npy` | `NODE_DTYPE = (lon f8, lat f8, cell_id i4)` | every surviving node, sorted by cell |
| `cell_index.npy` | `CELL_INDEX_DTYPE = (start_offset i8, count i4)` | one entry per grid cell → slice into `nodes.npy` |
| `node_edge_index.npy` | `NODE_EDGE_INDEX_DTYPE = (start_offset i8, count i4)` | one entry per node → slice into `node_edge_ids.npy` (adjacency) |
| `node_edge_ids.npy` | `i8` | flat adjacency list, CSR-indexed by `node_edge_index.npy` |
| `edges.npy` | `EDGE_DTYPE = (u i8, v i8, dist f8, road_m f8, ungraded_m f8, inferred_m f8, time_s f8, ascent_m f4, descent_m f4, sac_rank i1, via_ferrata bool, constrained_ok bool, interior_offset i8, interior_count i4, edge_id i8)` | one contracted chain edge per row. `time_s`/`ascent_m`/`descent_m` sit at `binfmt.UNSET` until `phases/elevation/compute_edge_profiles.py` runs |
| `interior.npy` | `COORD_DTYPE = (lon f8, lat f8)` | flat polyline vertex pool for every chain edge's interior geometry, sliced via `interior_offset`/`interior_count` |
| `manifest.json` | — | grid params (bbox, `tileSizeKm`) needed to reconstruct the same `Grid` at query time, plus array shapes |

- **doit wiring**: `file_dep=[trails.osm.pbf]`, `targets=[base_graph/manifest.json]`. `uptodate`
  uses `TaskOptionsChanged()` over the task's own params (`--tile-size-km` plus a tracking-only
  `schema_version`, `dodo.py`'s `binfmt.SCHEMA_VERSION` — bumped on any `EDGE_DTYPE` change so a
  code-only dtype edit still forces a rerun), so a changed param triggers a rerun without `doit
  forget`. **Not** force-rerun (unlike the deleted V1 `add_elevation.py`) — freshness-checked
  normally given its ~4.1h cost.

## Shared hub-loading + per-cell-pool infra

`snap_hubs.py`, `gather_route_subgraphs.py` and `build_hub_edges.py` each need the same combined
hub set (huts + stations/parking/partner access points) loaded and cell-bucketed against the base
graph's `Grid`, and each runs its own cell-by-cell loop that must print
`pipeline/CLAUDE.md`'s progress-logging convention. Rather than each script hand-rolling both:

- **`lib/hubs.py`** — `load_all_hubs(osm_dir)` joins `huts.geojson` + `start_points.npy` into one
  flat `[{id, type, lon, lat, name}, ...]` list (`type` is `binfmt.TYPE_*`); `bucket_by_cell(hubs,
  grid)` buckets it into `{cell_id: [hub, ...]}`. One place to extend when a new hub type joins
  `TYPE_HUT`/`TYPE_STATION`/`TYPE_PARKING`/`TYPE_PARTNER`.
- **`lib/progress.py`** — `run_pool(tasks, worker_fn, workers)` wraps the
  `ProcessPoolExecutor`/`as_completed` submit loop `snap_hubs.py` and `build_hub_edges.py` both
  need (guarded behind `if __name__ == "__main__":` in each — required on Windows, where the
  `spawn` start method re-imports the worker module in each child); `gather_route_subgraphs.py`
  runs single-process and doesn't need it. `ProgressTracker` tracks completed/total/elapsed and
  formats the `"elapsed Xm, ~Ym remaining"` suffix every per-cell progress line ends with.

## `snap_hubs.py` — snap every hub onto the base graph, once

Params: `--max-snap-m` (default `config.graph.maxSnapM`), `--max-snap-ascent-m`
(`maxSnapAscentM`), `--workers`.

Snaps every hub (independent of `--max-edge-km` and `graph.variants` — a hub's snap point is a
fact about its own location, not about any routing constraint) onto the persisted base graph and
persists the result to `hub_snaps.npy`/`hub_snap_interior.npy` (`lib/hub_snap.py`'s
`PersistedSnap`, keyed by globally-stable node/edge ids) for `build_hub_edges.py` to reuse. One
worker process per grid cell; each worker gathers a small `lib/subgraph.py` region (buffered off
`--max-snap-m`, not `--max-edge-km` — a few hundred metres, not tens of km) and calls
`lib/hub_snap.py`'s `snap_hub_to_subgraph()` per hub: an existing graph node within `--max-snap-m`
always wins; otherwise the nearest mid-chain point on a chain edge's interior polyline is found
(`lib/edge_split.py`'s `nearest_point_on_polyline()`) and the edge is split there
(`split_edge_at_point()`). A hub with no node within `--max-snap-m`, or whose vertical offset
exceeds `--max-snap-ascent-m`, is rejected — recorded in `unsnapped_huts.json`, never
force-matched. Writes `hub_snaps.npy`, `hub_snap_interior.npy`, `unsnapped_huts.json`.

## `gather_route_subgraphs.py` — cache each hub cell's routing region

Params: `--max-edge-km` (default `config.graph.maxEdgeKm`).

For every hub-bearing cell, gathers and persists the `--max-edge-km`-padded `LocalSubgraph`
(`lib/subgraph.py`'s `gather_padded_subgraph()` — a cell-union-then-edge-incidence-closure mmap
slice of the base graph) that `build_hub_edges.py`'s routing pass needs, under
`data/osm/route_subgraphs/cell_<id>/`. Depends only on `--max-edge-km` and the base graph — not on
`graph.variants` — so retuning the variant grid alone leaves this cache untouched. Single-process,
sequential over cells (the expensive part is the mmap slice + array copy per cell, not something
that benefits from cross-cell parallelism the way per-hub snapping/routing do).

## `build_hub_edges.py` — per-hub shortest paths, tiled + multiprocess

Params: `--max-edge-km` (default `config.graph.maxEdgeKm`), `--workers` (default
`os.cpu_count()`).

Reloads `snap_hubs.py`'s persisted snaps and `gather_route_subgraphs.py`'s cached per-cell
subgraphs instead of recomputing either — this script's own cost is now just the routing pass,
the one stage that genuinely scales with the variant grid. One worker process per grid cell; each
worker (`_run_cell`) reloads its cached subgraph, looks up its hubs' precomputed snaps
(`lib/hub_snap.py`'s `reconstruct_local_snaps()`), and calls `compute_hub_edges_for_cell()`:

1. **Routes each enabled variant row** (`pipeline.config.json`'s `graph.variants`, `lib/variants.py`
   — currently `FAST_ANY`, `FAST_T2`, `FAST_T3`, `FAST_T3_UNGRADED`) separately over the same
   snapped hubs: `lib/variants.py`'s `edge_mask()` turns the row's constraint (max `sac_rank`,
   whether ungraded terrain is admitted) into a boolean mask over the region's edges, and
   `lib/cell_igraph.py`'s `build_igraph_from_base()` builds one `igraph.Graph` per row from only
   the unmasked edges (base nodes + virtual snap vertices) — the variant-independent
   column/interior/max_ele_m work is built once per cell by `build_base_igraph_arrays()` and
   reused across every row. `lib/cell_igraph.py` holds this igraph-building/path-walking engine
   (also used directly by `analysis/routing_probe.py`) as reusable, subgraph+snaps-only plumbing
   with no dependency on this script's own routing loop or output packing — see its module
   docstring. For each core hub: computes real-distance shortest-path *distances* (`weights="dist"`,
   on that row's masked graph) to every *hut* in range and discards any pair over `--max-edge-km` (mirrors an
   "all-pairs cutoff" pass), then for surviving pairs fetches the *time*-shortest path
   (`weights="weight"` == `time_s`, spec A3 — never the road-penalized distance the pre-V2
   pipeline used) and walks its edge list to build full path geometry, summing real `dist`/`road_m`
   and tracking max `sac_rank` and any `via_ferrata` crossing along the path. The routed path's own
   `distance_m` is re-checked against `--max-edge-km` after the fact (spec C8): the cutoff above
   ran on the *unconstrained* shortest distance, which the time-shortest path can exceed. A row
   with no legal path for a pair emits nothing for it — never a silent fallback to a laxer row.
   Only huts are ever routed *to*: the two shipped edge sets are hut-hut and access-point-to-hut,
   so a station↔parking pair is work nothing consumes, and a hut→access-point pair would just
   duplicate the access→hut record the access point's own cell already emits.
2. **`merge_and_dedup()`** combines every worker's records: undirected hut↔hut pairs are
   deduplicated on `(variant, type, id)` (not id alone — hut/station/parking id spaces can
   collide, and two variant rows for the same pair are two distinct records, not duplicates),
   while directional access→hut records are kept as-is (a station/parking point is always stored
   as the origin, never merged symmetrically with a hut).

`compute_hub_edges_for_cell()` always takes an already-computed `snaps` dict (from
`reconstruct_local_snaps()` in production); `snap_hubs_for_cell()` is a standalone self-snapping
convenience for callers without that cache (tests, `analysis/` scripts) — production never calls
it, since a hub only ever needs to snap once, pipeline-wide, in `snap_hubs.py`.

**Output** (`lib/binfmt.py`'s `RECORD_DTYPE`/`COORD_DTYPE`). `distance_m`/`road_m`/`ascent_m`/
`descent_m`/`max_ele_m`/`ungraded_m`/`inferred_m`/`sac_rank`/`via_ferrata` are all accumulated
directly off the SAME base-graph edges the router walked (`_path_for()`'s `PathResult`, spec B3 -
routing and display can't disagree because they're the same numbers), so they're only meaningful
once `phases/elevation/compute_edge_profiles.py` has already filled `ascent_m`/`descent_m` on the
base graph and `phases/elevation/sample_base_elevation.py` has filled `node_ele.npy`/
`interior_ele.npy` (`lib/subgraph.py`'s `gather_padded_subgraph()` reads both, defaulting to zeros
if they don't exist yet - a base graph without an elevation pass still gets valid `dist`/`road_m`/
`ungraded_m`/`inferred_m` records, just with `ascent_m`/`descent_m`/`max_ele_m` at 0). `ascent_m`/
`descent_m` swap per edge when a path traverses it v→u instead of u→v, since the base graph stores
them in a fixed direction. `max_ele_m` is a per-edge max over both endpoints' and every interior
point's absolute elevation, not a delta, so a col strictly inside one contracted base-graph edge
(not itself a graph vertex) is still caught; a mid-chain hub snap inherits its parent edge's
`max_ele_m` on both synthetic halves rather than re-deriving one per half (same limitation
`ascent_m`/`descent_m`/`sac_rank`/`via_ferrata` already accept there, spec C9). `snap_m` and
`profile_offset`/`profile_count` are left at `0`/`UNSET`, filled in by a later pass.

- `data/osm/hut_edges/{records.npy, geometry.npy}` — hut-to-hut edges, one record per
  `(pair, variant)`.
- `data/osm/start_edges/{records.npy, geometry.npy}` — access edges (station/parking ↔ hut), same
  shape. Named "start" for historical reasons; the edge is undirected — the same record serves a
  trip that *starts* at the station and one that *ends* there. It is only stored access→hut.

`RECORD_DTYPE = (from_id i8, to_id i8, from_type u1, to_type u1, variant u1, distance_m f4,
road_m f4, ascent_m f4, descent_m f4, max_ele_m f4, ungraded_m f4, inferred_m f4, snap_m f4,
sac_rank i1, via_ferrata bool, geom_offset i8, geom_count i4, profile_offset i8, profile_count
i4)` — `from_type`/`to_type` are `binfmt.TYPE_HUT` (0) / `TYPE_STATION` (1) / `TYPE_PARKING` (2) /
`TYPE_PARTNER` (3, added `docs/superpowers/specs/2026-08-28-hut-classification-design.md` —
Bergsteigerdörfer partner businesses, routed one-directionally to huts exactly like
stations/parking, never hut↔hut);
`variant` is one of `binfmt.VARIANT_*` (`lib/variants.py`'s `VARIANTS` dict has the per-row
definitions). `geom_offset`/`geom_count` slice into the sibling `geometry.npy` (`COORD_DTYPE`), a
flat polyline vertex pool exactly like `base_graph/interior.npy`.

**Timing**: the whole cell-pool loop is one `lib/timing.py` `phase("build_hub_edges.py",
"hub_edge_query", ...)` record. Each worker fills a `StepTimer` with its own
`gather_subgraph`/`snap`/`build_igraph`/`distances`/`paths` split and returns it with its records;
the parent merges them all into the phase meta (`<step>_s`, `<step>_calls`) and prints a final
`step totals` line, with the same split per cell in the progress line. Summed across workers, so
the columns exceed wall clock — read the ratios.

- **doit wiring** (`dag/graph_building.py`, split three ways so retuning one knob doesn't force the
  other two to rerun — see each task's own comment there): `task_snap_hubs` depends only on
  `--max-snap-m`/`--max-snap-ascent-m` (`file_dep=[base_graph/manifest.json,
  base_graph/node_ele.npy, huts.geojson, start_points.npy, dem.tif]`,
  `targets=[hub_snaps.npy, hub_snap_interior.npy, unsnapped_huts.json]`); `task_gather_route_subgraphs`
  depends only on `--max-edge-km` (same `file_dep` minus `dem.tif`,
  `targets=[route_subgraphs/manifest.json]`); `task_build_hub_edges` depends on both
  (`task_dep=[snap_hubs, gather_route_subgraphs]`, `file_dep=[base_graph/manifest.json,
  huts.geojson, start_points.npy, hub_snaps.npy, hub_snap_interior.npy,
  route_subgraphs/manifest.json]`, `targets=[hut_edges/records.npy, start_edges/records.npy]`) plus
  a tracking-only `variants_json` param (`config.graph.variants`, read straight from config so a
  grid edit wouldn't otherwise be seen as a param change). All three depend on `compute_edge_profiles`
  as a `task_dep` (edges.npy's `time_s`/`ascent_m`/`descent_m` are rewritten in place by that task
  but aren't one of its declared targets, so `node_ele.npy`'s file-hash freshness alone wouldn't
  guarantee ordering) and carry the tracking-only `schema_version` param
  (`binfmt.SCHEMA_VERSION`). `uptodate` uses `TaskOptionsChanged()` over each task's own params, so
  a flag retune reruns just the task(s) that actually depend on it, without `doit forget`.
