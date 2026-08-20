# phases/graph_building/ — OSM ways → hut-to-hut trail edges

The expensive phase (`build_base_graph` alone measured ~4.1h for AT+Bayern —
`data/timings.jsonl`). Split into two scripts so that the costly, hub-independent part is computed
and persisted once, and only the cheap, hub-dependent part reruns when the hub set or edge
hyperparameters change.

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
   flat numpy arrays: node coordinates, edge endpoint indices, per-edge haversine distance, a
   road-penalized routing "weight" (real distance × `roadPenaltyFactor` when `highway` is in
   `config.graph.roadHighwayTags`), a road boolean, a ranked `sac_scale` value
   (`SAC_SCALE_RANK`, easiest→hardest), and a `via_ferrata` boolean (`highway=via_ferrata` or a
   `via_ferrata_scale` tag present).
2. **`contract_structural`** (`lib/contraction.py`) — collapses every maximal run of degree-2
   nodes (a pure pass-through chain, no junction) into a single chain edge. This is a lossless
   transform: a degree-2 node has no alternate route, so summing distance/weight/road-length along
   the chain and taking the max `sac_scale` rank walked preserves every shortest-path cost
   *exactly*, while shrinking node/edge count by (measured) an order of magnitude or more (~40M
   raw nodes/edges → far fewer chain edges for AT+Bavaria). Unlike an earlier version, contraction
   here is **structural only** — no hub-snap-point exception, since hub sets aren't known yet at
   this stage; mid-chain hub snapping is deferred to `lib/edge_split.py`, invoked at
   `build_hub_edges.py` query time. Built via CSR-style adjacency (`lib/binfmt.py`'s
   `build_csr_index()` — one stable sort over doubled endpoint arrays plus bincount/cumsum for
   offsets, no Python dict-of-lists), so it scales without per-node Python object overhead.
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
| `edges.npy` | `EDGE_DTYPE = (u i8, v i8, dist f8, weight f8, road_m f8, sac_rank i1, via_ferrata bool, interior_offset i8, interior_count i4, edge_id i8)` | one contracted chain edge per row |
| `interior.npy` | `COORD_DTYPE = (lon f8, lat f8)` | flat polyline vertex pool for every chain edge's interior geometry, sliced via `interior_offset`/`interior_count` |
| `manifest.json` | — | grid params (bbox, `tileSizeKm`) needed to reconstruct the same `Grid` at query time, plus array shapes |

- **doit wiring**: `file_dep=[trails.osm.pbf]`, `targets=[base_graph/manifest.json]`. `uptodate`
  uses `config_changed` over the task's own params, so a changed `--tile-size-km` triggers a
  rerun without `doit forget`. **Not** force-rerun (unlike `add_elevation`) — freshness-checked
  normally given its ~4.1h cost.

## `build_hub_edges.py` — per-hub shortest paths, tiled + multiprocess

Params: `--max-edge-km` (default `config.graph.maxEdgeKm`), `--max-snap-m` (`maxSnapM`),
`--workers` (default `os.cpu_count()`).

**Setup**: loads `base_graph/manifest.json` and reconstructs its `Grid` (deterministic — `cell_id`
is fully determined by `(bbox, tile_size_km)`, so no lookup table is needed to re-derive it),
loads `huts.geojson` + `start_points.npy` (the combined hub set: huts + filtered
stations/parking), and assigns each hub to a grid cell by coordinate.

**Parallelism**: one worker process per grid cell, via `ProcessPoolExecutor` (guarded behind
`if __name__ == "__main__":` — required on Windows, where the `spawn` start method re-imports the
worker module in each child). Each worker, independently:

1. **Gathers a padded region** — `lib/subgraph.py`'s `gather_padded_subgraph()`: a
   cell-union-then-edge-incidence-closure mmap slice of the base graph, buffered by
   `--max-edge-km` so a hub near a cell boundary still sees every trail edge within range, without
   loading cells the worker doesn't need.
2. **Snaps** each hub in its region onto the subgraph (`snap_hub_to_subgraph()`): an existing
   graph node within `--max-snap-m` always wins; otherwise the nearest mid-chain point on a chain
   edge's interior polyline is found (`lib/edge_split.py`'s `nearest_point_on_polyline()`) and the
   edge is split there (`split_edge_at_point()`), inserting a virtual vertex. A hub with no node
   within `--max-snap-m` is skipped entirely — not force-matched to a distant trail.
3. **Builds an in-process `igraph.Graph`** over the region (base nodes + virtual snap vertices),
   then for each core hub in the region: computes real-distance shortest-path *distances*
   (`weights="dist"`) to every other hub in range and discards any pair over `--max-edge-km`
   (mirrors an "all-pairs cutoff" pass), then for surviving pairs fetches the road-penalized
   shortest *path* (`weights="weight"`, `get_shortest_paths(..., output="epath")`) and walks its
   edge list to build full path geometry, summing real `dist`/`road_m` and tracking max `sac_rank`
   and any `via_ferrata` crossing along the path.
4. **`merge_and_dedup()`** combines every worker's records: undirected hut↔hub pairs are
   deduplicated on `(type, id)` (not id alone — hut/station/parking id spaces can collide), while
   directional start→hut records are kept as-is (a station/parking point is always the origin,
   never merged symmetrically with a hut).

**Output** (`lib/binfmt.py`'s `RECORD_DTYPE`/`COORD_DTYPE`; `ascent_m`/`descent_m`/`profile_*`
left at `UNSET`(-1.0)/0 here, filled in by `phases/elevation/add_elevation.py`):

- `data/osm/hut_edges/{records.npy, geometry.npy}` — hut-to-hut edges.
- `data/osm/start_edges/{records.npy, geometry.npy}` — station/parking-to-hut edges, same shape.

`RECORD_DTYPE = (from_id i8, to_id i8, from_type u1, to_type u1, variant u1, distance_m f4,
road_m f4, ascent_m f4, descent_m f4, sac_rank i1, via_ferrata bool, geom_offset i8, geom_count
i4, profile_offset i8, profile_count i4)` — `from_type`/`to_type` are `binfmt.TYPE_HUT` (0) /
`TYPE_STATION` (1) / `TYPE_PARKING` (2); `variant` is currently always `VARIANT_SHORTEST` (0), a
reserved extensibility hook for a future second route variant per pair (not computed yet).
`geom_offset`/`geom_count` slice into the sibling `geometry.npy` (`COORD_DTYPE`), a flat polyline
vertex pool exactly like `base_graph/interior.npy`.

- **doit wiring**: `file_dep=[base_graph/manifest.json, huts.geojson, start_points.npy]`,
  `targets=[hut_edges/records.npy, start_edges/records.npy]`. `uptodate` uses `config_changed`
  over the task's own params, so `--max-edge-km`/`--max-snap-m` changes trigger a rerun
  automatically.
