# Pipeline V2: faster build + parking/station routing edges

Date: 2026-08-19
Status: approved for planning

Supersedes the *mechanism* of `docs/superpowers/specs/2026-08-18-start-locations-design.md`
(which bolted station/parking snap+query onto the existing monolithic `build_hut_graph.py` run).
That spec's **output contract** — `start-edges.geojson`/`start-edges.pmtiles`/
`start-edge-stats.json` shape, `station:<osm_id>`/`parking:<osm_id>` id scheme, directional
start→hut edges with no dedup — is kept as-is; only how it's computed changes.

## Goal

`build_hut_graph.py` alone measured ~4.1h for AT+Bayern (`data/timings.jsonl`). Adding
parking-lot/station start points as new graph query sources (per the superseded spec) would
multiply the number of snap+shortest-path queries by an order of magnitude if done naively
(every OSM `amenity=parking` node and `railway=station,halt` point across all of Austria+Bavaria
— tens of thousands of points, not ~1173 huts), pushing an already-multi-hour build into a
multi-day one.

V2's goal: cut build time by (a) filtering parking/station candidates down to the ones that
could plausibly be trailhead-relevant before they ever reach the expensive graph query, and
(b) restructuring the graph-build itself so the expensive, hub-agnostic part (streaming
`trails.osm.pbf` + structural contraction) is computed once and cached, decoupled from
per-hub-type snapping/querying, which itself moves from a single-process thread pool to real
multi-core (and future multi-machine) parallelism via geographic tiling.

Scope also covers DEM/elevation and tile-building steps, since the new binary intermediate
format (replacing GeoJSON) touches `add_elevation.py` and the tile-build scripts even though
they aren't the current bottleneck.

## Why build time is the right target (not runtime)

The shipped routing graph stays small regardless (huts + filtered parking/stations — low
thousands of nodes at most); a Dijkstra/A* over that in-browser is sub-100ms in any reasonable
format. The cost lives entirely in offline construction: computing edges from thousands of
source points against the ~40M-node raw OSM graph.

## Non-goals / future work

- **Diverse route variants** (multiple paths per hut pair with different elevation/path-type
  characteristics, not just the shortest) — not built in V2. Two hooks are included so it isn't
  foreclosed:
  - Every contracted base-graph edge gets a stable, persistent `edge_id`, so a future pass can
    attach new per-edge cost columns (e.g. an ascent-cost weight) and re-query the *same* cached
    base graph without re-streaming/re-contracting `trails.osm.pbf`.
  - The edge output schema's `variant` field allows multiple stored paths per (from, to) pair;
    V2 populates only `variant=0` ("shortest").
  - Actual diverse-path algorithms (e.g. Yen's k-shortest-paths with a dissimilarity check) and
    elevation-aware route weighting (which requires moving DEM sampling from "after pathfinding,
    on the ~hundreds/thousands of output paths" to "on the base graph's edges before
    pathfinding" — a materially larger DEM workload) are explicitly deferred to a future
    iteration, enabled but not implemented here.
- App/UI wiring (start-point picker, rendering start→hut legs, multi-hop route search chaining
  start-edges with hut-edges) — same non-goal as the superseded spec, still out of scope.
- Non-hut destinations (viewpoints, etc.) — out of scope entirely.

## Pipeline shape (new task DAG)

Steps 1–5b (`download_extracts` → `filter_trails` → `merge_trails` → `verify_trails` →
`fetch_huts` → `fetch_stations_parking`) are unchanged — the blowup isn't there.

### 5c. `filter_start_points` (new)

Cheap, pure-Python, runs before any graph is touched:

1. Load `huts.geojson` into a KDTree.
2. For each point in `stations.geojson`/`parking.geojson`, find distance to nearest hut.
3. Keep only points within `graph.maxEdgeKm` beeline of some hut — a correct filter (not an
   approximation), since no point farther than that can produce an edge under the existing
   real-distance cutoff regardless of how the trail actually routes.
4. Assign each surviving point a numeric id (offset past the hut id range), write
   `start_points.bin` (`lon, lat, numeric_id, type`) and append `id_table.json` entries
   (`station:<osm_id>` / `parking:<osm_id>`).

`trailTagFilter` already includes `residential/service/unclassified/tertiary` roads across the
*entire* Austria+Bavaria extract (added for road-bias routing), so trail-snap distance alone
would not exclude urban parking — this beeline-to-hut filter is what actually bounds the hub
count, likely cutting tens of thousands of OSM points down to a low-thousands trailhead-relevant
subset.

**doit wiring**: `file_dep=[huts.geojson, stations.geojson, parking.geojson, config]`,
`targets=[start_points.bin, id_table fragment]`.

### 6. `build_base_graph` (new, replaces the stream/snap/contract/build-igraph part of today's `build_hut_graph.py`)

Streams `trails.osm.pbf` once (same `pyosmium` streaming as today), contracts **purely
structurally** — keep-node = degree ≠ 2 only, with no dependency on which points will later be
snapped to it (today's contraction forces hut-snap points to be keep-nodes too; V2 drops that,
see "Mid-chain edge splitting" below) — builds the node/edge arrays, and persists them to the
custom mmap binary format described below.

Depends only on `trails.osm.pbf` (+ config) — **not** on huts/start-points — so it's cached
across hub-set changes and downstream hyperparameter retuning. This is the chunk that ate most
of the historical 4.1h (`stream_osm` + `contract_chains` phases in `data/timings.jsonl`).

**doit wiring**: `file_dep=[trails.osm.pbf, config]`, `targets=[base_graph/manifest.json,
nodes.bin, edges.bin, interior.bin, cell_index.bin, node_edge_csr.bin]`. New `--tile-size-km`
param. Not force-rerun — freshness-checked normally like today's `build_hut_graph`, but expected
to be substantially cheaper given it's now hub-agnostic; the actual number needs benchmarking
post-implementation, not assumed here.

### 7. `build_hub_edges` (new, replaces pass1/pass2)

Loads the mmap base graph + combined hub list (huts + `start_points.bin`), partitions the bbox
into a grid of overlapping tiles, and runs a `ProcessPoolExecutor` pool, one task per tile:

1. **Grid setup**: cells of `tile-size-km` (sized so one cell's node/edge slice comfortably fits
   a worker's RAM — this is the knob that scales to future regions: more area means more cells,
   not bigger ones). Each cell's **padded region** = cell bounds + `maxEdgeKm` buffer.
2. **Correctness argument**: a real trail path of length ≤ `maxEdgeKm` can end at most
   `maxEdgeKm` beeline from its start (path length ≥ beeline distance between endpoints,
   trivially). So any hub reachable from a core-cell hub is guaranteed to lie inside that cell's
   padded region — a worker never needs data outside its own padded slice to correctly answer
   queries for hubs in its core. (Testable directly, not just argued — see Validation below.)
3. **Per-worker**:
   - mmap-slice `nodes.bin`/`edges.bin`/`interior.bin` to the padded region via
     `cell_index.bin` + `node_edge_csr.bin` (index arithmetic, no data copy until read).
   - Build a small local `igraph.Graph` from that slice.
   - Snap every hub whose coordinate falls in the cell's **core** to the local graph, including
     **mid-chain-edge splitting**: since the base graph contracted structurally only, a hub may
     snap partway along a chain edge instead of at an existing node. Splitting inserts a virtual
     node at the snap fraction along that edge's interior polyline, dividing `dist`/`weight`/
     `road_m` proportionally — purely local to the worker's copy of that one edge.
   - Run pass1 (candidates via local hub KDTree + `graph.distances`, cutoff `maxEdgeKm`) and
     pass2 (`get_shortest_paths` for kept pairs) exactly as today's per-hut loop, scoped to this
     cell's core hubs against this cell's padded subgraph.
   - Write a shard file (same `records.bin`/`geometry.bin` shape as the final output).
4. **Merge**: concatenate shards. A hut↔hut pair may be computed independently from both
   endpoints' cells (harmless redundancy — both should yield the same physical path); a final
   pass dedups hut↔hut pairs by `(min(from_id,to_id), max(from_id,to_id))`. Start→hut pairs are
   directional with no dedup concept, same as the superseded spec.

**doit wiring**: `file_dep=[base_graph outputs, huts.geojson, start_points.bin, config]`,
`targets=[hut-edges.bin, start-edges.bin]`. Params: `--max-edge-km`, `--max-snap-m`,
`--road-penalty-factor`, `--workers` (now process count). Same `config_changed`-on-own-params
uptodate pattern as today's `build_hut_graph`. Not force-rerun.

### 8. `fetch_dem` / `build_dem_vrt` — unchanged

### 9. `add_elevation` (reworked)

Reads/writes the binary edge format directly (no JSON parsing of a 184MB+ file). Processes
`hut-edges.bin` **and** `start-edges.bin` together in one combined batched DEM window read (same
technique as today, just fed more points at once) — a single task, replacing the superseded
spec's separate `add_start_elevation`. Same threshold-hysteresis ascent/descent algorithm,
unchanged.

**doit wiring**: `uptodate: [False]` (cheap, always reruns), `task_dep=[build_hub_edges]`,
`file_dep=[dem.tif]`, `targets=[hut-edges.bin, start-edges.bin]` (edited in place).

### 10. `build_trail_tiles` — unchanged

Streams straight from `trails.osm.pbf` via pipe; never touches hut-edges data at all.

### 11. `build_edge_tiles` (generalized from `build_hut_edge_tiles`)

Same tippecanoe → pmtiles pipeline, now reading the binary format instead of GeoJSON. One
shared script, still two doit tasks (`build_hut_edge_tiles`, `build_start_edge_tiles`), each
pointed at its respective `.bin` file. **Output stays JSON**
(`hut-edge-stats.json`/`start-edge-stats.json`) — that's the app-facing contract, unchanged.

### 12. `copy_public_data`

`PUBLIC_FILES` gains `start-edges.pmtiles`/`start-edge-stats.json` (per the superseded spec).
`stations.geojson`/`parking.geojson` stay **unfiltered** in this list — the app's map markers
should keep showing every station/parking lot; the `maxEdgeKm`-to-hut filter only narrows the
internal candidate set used for routing-edge computation (`start_points.bin`, never shipped to
the app).

## Binary formats

Both formats reuse the CSR/ragged-array pattern already used in `build_hut_graph.py`'s
adjacency-via-sorted-endpoints code — flat `numpy` arrays, memory-mappable via `np.load(...,
mmap_mode="r")` or raw `numpy.memmap`, zero new dependencies.

### Base graph (`data/osm/base_graph/`)

| file | contents |
|---|---|
| `nodes.bin` | `(lon, lat, cell_id)` per node, **sorted by `cell_id`** (row-major grid over the bbox at `tile_size_km`) so a cell's nodes are a contiguous slice |
| `cell_index.bin` | `(start_offset, count)` per `cell_id` — O(1) lookup of a cell's node range |
| `node_edge_csr.bin` | each node's incident edge ids (same technique as today's `contract_chains` adjacency) — turns "all edges touching this node set" into a cheap gather |
| `edges.bin` | `(u, v, dist, weight, road_m, sac_rank, via_ferrata, interior_offset, interior_count, edge_id)`. `edge_id` is stable and persisted — the future-diverse-paths hook |
| `interior.bin` | packed `(lon, lat)` pairs per edge's interior polyline, CSR-addressed via `interior_offset`/`interior_count` |
| `manifest.json` | bbox, `cell_size_km`, dtypes, schema version, counts — human-checkable, mirrors what `verify_trails.py` already prints for the raw pbf |

### Edge outputs (`hut-edges.bin`, `start-edges.bin`)

| file | contents |
|---|---|
| `records.bin` | `(from_id, to_id, from_type, to_type, variant, distance_m, road_m, ascent_m, descent_m, sac_rank, via_ferrata, geom_offset, geom_count, profile_offset, profile_count)`. `ascent_m`/`descent_m`/`profile_*` start unset, filled in-place by `add_elevation` |
| `geometry.bin` | packed `(lon, lat)` path polyline per record, CSR-addressed |
| `profiles.bin` | packed elevation-profile floats per record, CSR-addressed, filled by `add_elevation` |
| `id_table.json` | numeric id → real string id (hut ids, `station:<osm_id>`, `parking:<osm_id>`) — only needed at the final stats/tiles step |

Numeric ids throughout (not strings) keep every array fixed-width and directly memmap-able.

## Validation strategy

Following the existing `pipeline/tests/` style (plain `pytest`, small pure-function fixtures, no
network access, no full-scale OSM files — see `test_bbox_from_huts.py`,
`test_bavaria_tile_grid.py`):

- **Buffer correctness**: a synthetic small graph with a hub near a cell boundary, computed once
  tiled and once as a single reference (non-tiled) cell, must produce identical edges.
- **Mid-chain-edge splitting**: a synthetic chain edge with a known interior polyline, snapped
  at a known fraction — assert the two split segments' distances sum back to the original.
- **CSR slicing** (`cell_index.bin`/`node_edge_csr.bin`): small fixture graph, assert a
  cell+buffer query returns exactly the expected node/edge set.
- **End-to-end parity** (manual, one-time, before switchover — not a pytest unit test): run V1
  and V2 against the same small real region, diff `distance_m`/`road_m`/`sac_scale` per matching
  hut pair.

## Retired / new scripts

- Retired: `build_hut_graph.py` (its logic splits into the two scripts below).
- New: `filter_start_points.py`, `build_base_graph.py`, `build_hub_edges.py`.
- Generalized (shared script, called twice): `build_hut_edge_tiles.py` → `build_edge_tiles.py`.
- Reworked in place: `add_elevation.py` (binary I/O, dual edge-set input).
- Unchanged: `download_extracts.py`, `filter_trails.py`, `merge_trails.py`, `verify_trails.py`,
  `fetch_huts.py`, `fetch_stations_parking.py`, `fetch_dem.py`, `build_dem_vrt.py`,
  `build_trail_tiles.py`.
