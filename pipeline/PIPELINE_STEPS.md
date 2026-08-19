# Pipeline steps — detailed

Generated from reading `pipeline/dodo.py` and each script. Orchestration is a
[doit](https://pydoit.org) task DAG (`pipeline/dodo.py`), not a numbered sequence — task order
below follows the DAG's dependency order (`file_dep`/`targets`), which matches
`DOIT_CONFIG["default_tasks"]`. All hyperparameters come from `pipeline/pipeline.config.json`
via `lib/pipeline.py`'s `load_config()`.

**Never run any of this without asking the user first** — `build_base_graph` alone measured
~4.1 hours as part of its predecessor `build_hut_graph` (`data/timings.jsonl`) and is part of the
default `doit` run.

---

## 1. `download_extracts` — `download_extracts.py`

- Reads `config["regions"]` (name + Geofabrik URL, e.g. austria/bayern).
- For each region: `urllib.request.urlretrieve(url, data/osm/raw/<name>-latest.osm.pbf)`.
- Prints final file sizes. No pinning — Geofabrik extracts regenerate daily, rerun to refresh.
- **doit wiring**: `file_dep=[pipeline.config.json]`, `targets=[raw/<region>-latest.osm.pbf, ...]`.

## 2. `filter_trails` — `filter_trails.py`

- Reads `config["trailTagFilter"]` (an `osmium tags-filter` expression, e.g.
  `w/highway=path,footway,track,steps,residential,service,unclassified,tertiary,via_ferrata`).
- Per region: shells out to `osmium tags-filter <raw> <filter> -o <name>-trails.osm.pbf --overwrite`.
- `osmium tags-filter` keeps referenced nodes by default, preserving topology for graph-building.
- Requires `osmium-tool` native binary on PATH (conda-forge, `alpen-osm` env).
- **doit wiring**: `file_dep=[raw/<region>-latest.osm.pbf,... , config]`, `targets=[<region>-trails.osm.pbf,...]`.

## 3. `merge_trails` — `merge_trails.py`

- `osmium merge <region1-trails.osm.pbf> <region2-trails.osm.pbf> ... -o trails.osm.pbf --overwrite`.
- Combines all per-region filtered extracts into one merged hiking network.
- **doit wiring**: `file_dep=[<region>-trails.osm.pbf, ...]`, `targets=[trails.osm.pbf]`.

## 4. `verify_trails` — `verify_trails.py`  (gate, always reruns — `uptodate: [False]`)

- Checks `trails.osm.pbf` exists and is non-empty; exits nonzero otherwise (fails the doit run).
- Runs `osmium fileinfo -e trails.osm.pbf` to print bbox/node/way/relation counts.
- No target — it's a sanity gate, not a cacheable build step.

## 5. `fetch_huts` — `fetch_huts.py`

- Reads `config["bbox"]`.
- `GET` the Alpenverein ArcGIS layer (`AVT_GEO_CAA_HUETTEN_View_P/FeatureServer/0/query`,
  `outFields=id,name`, `outSR=4326`, `resultRecordCount=8000`, no auth).
- Filters returned features to those with geometry inside `bbox`.
- Writes `data/osm/huts.geojson`: FeatureCollection of Points, `properties={id, name}`.
- **doit wiring**: `file_dep=[config]`, `targets=[huts.geojson]`.

## 5b. `fetch_stations_parking` — `fetch_stations_parking.py`

- Two layers, each processed per region (reusing the raw extracts from step 1, no new download):
  - **stations**: `osmium tags-filter n/railway=station,halt` → `osmium export --geometry-types point`
    → keep only `name, network, operator` properties.
  - **parking**: `osmium tags-filter nwr/amenity=parking` → `osmium export --geometry-types point`
    (polygons exported as centroids) → keep only `name, capacity, fee, access` properties.
- Concatenates each layer's per-region features and writes `data/osm/stations.geojson` and
  `data/osm/parking.geojson`.
- **doit wiring**: `file_dep=[raw/<region>-latest.osm.pbf, ...]`, `targets=[stations.geojson, parking.geojson]`.

## 5c. `filter_start_points` — `filter_start_points.py`

- Reads `huts.geojson`, `stations.geojson`, `parking.geojson`.
- `filter_to_hut_range()`: a correct (not approximate) filter — drops every station/parking point
  farther than `config.graph.maxEdgeKm` beeline from every hut, via a `scipy.spatial.cKDTree`
  over hut coords. No point farther than that can ever produce a kept edge under
  `build_hub_edges.py`'s real-distance cutoff, regardless of how the trail actually routes — this
  is what bounds the hub count before it reaches the expensive graph query (`trailTagFilter`
  already includes residential/service/unclassified/tertiary roads across the whole
  Austria+Bavaria extract, so trail-snap distance alone wouldn't exclude urban parking).
- Writes `data/osm/start_points.npy` (`lon, lat, osm_id, type` — `type` is
  `binfmt.TYPE_STATION`/`TYPE_PARKING`) and `data/osm/start_points_id_table.json`
  (`{"station:<osm_id>": ..., "parking:<osm_id>": ...}`, kept for symmetry/debuggability —
  downstream code uses the `(osm_id, type)` pair directly).
- **doit wiring**: `file_dep=[huts.geojson, stations.geojson, parking.geojson, config]`,
  `targets=[start_points.npy, start_points_id_table.json]`.

## 6a. `build_base_graph` — `build_base_graph.py`  (the expensive step, ~4.1h for AT+Bayern)

Replaces the old buffer-clip + OSMnx/NetworkX approach (rejected — object overhead, not input
size, was the memory problem; see `pipeline/README.md`). Params: `--tile-size-km` (default
`config.graph.tileSizeKm`). Depends only on `trails.osm.pbf` — not on any hub set — so it's
cached across hub-set changes and downstream hyperparameter retuning; `build_hub_edges.py` (which
does depend on hub sets) loads this output instead of re-streaming/re-contracting every run.

1. **stream_osm** — streams `trails.osm.pbf` once via `pyosmium` (`osmium.SimpleHandler`) into
   flat numpy arrays: node coords, edge endpoint indices, per-edge haversine distance, a
   road-penalized routing "weight" (real distance × `roadPenaltyFactor` if `highway` is in
   `config.graph.roadHighwayTags`), a road bool, a ranked `sac_scale` value (via
   `SAC_SCALE_RANK`, easiest→hardest), and a `via_ferrata` bool (`highway=via_ferrata` or
   `via_ferrata_scale` tag present).
2. **contract_structural** (`lib/contraction.py`) — collapses every run of degree-2 nodes (pure
   pass-through, no junction) into one chain edge. Unlike the old script, this is **structural
   only** — no hub-snap-point exception, since hub sets aren't known at this point in V2; mid-chain
   hub snapping is deferred to `lib/edge_split.py` at `build_hub_edges.py` time. Built via
   CSR-style adjacency (one sort over doubled endpoint arrays, no Python dict-of-lists). Each
   chain edge carries summed distance/weight, summed road length, the max `sac_scale` rank
   walked, whether any via-ferrata segment was crossed, and the full interior polyline. Lossless
   — a degree-2 node has no alternate route, so summing costs along the chain preserves
   shortest-path costs exactly, while shrinking node/edge count by (expected) an order of
   magnitude or more (measured ~40M raw nodes/edges for AT+Bavaria).
3. Nodes are assigned a `lib/grid.py` `Grid` cell id (`config.graph.tileSizeKm`) and re-sorted by
   cell so `cell_index.npy` addresses a contiguous slice per cell — this is what lets
   `build_hub_edges.py`'s workers mmap-slice just their own region instead of loading everything.
- **Output**: `data/osm/base_graph/{nodes.npy, cell_index.npy, node_edge_index.npy,
  node_edge_ids.npy, edges.npy, interior.npy, manifest.json}` — plain `.npy` structured arrays
  (see `lib/binfmt.py`), memory-mappable, one file per array.
- **doit wiring**: `file_dep=[trails.osm.pbf]`, `targets=[base_graph/manifest.json]`.
  `uptodate` uses `config_changed` over the task's own params, so a changed `--tile-size-km`
  triggers a rerun without `doit forget`. NOT force-rerun (unlike `add_elevation`) —
  freshness-checked normally given its ~4.1h cost.

## 6b. `build_hub_edges` — `build_hub_edges.py`  (tiled, multiprocess)

Replaces the old script's pass1/pass2. Params: `--max-edge-km` (default `config.graph.maxEdgeKm`),
`--max-snap-m` (`maxSnapM`), `--workers` (default `os.cpu_count()`).

1. Loads `base_graph/manifest.json` + reconstructs its `Grid`, loads `huts.geojson` +
   `start_points.npy` (the combined hub set), and assigns each hub to a grid cell.
2. Runs one worker process per cell via `ProcessPoolExecutor` (guarded behind
   `if __name__ == "__main__":` — required on Windows, where the `spawn` start method re-imports
   the worker module in each child). Each worker:
   - Gathers its **padded region** (`lib/subgraph.py`'s `gather_padded_subgraph`) — a
     cell-union-then-edge-incidence-closure mmap slice of the base graph, buffered by
     `max-edge-km` so a hub near a cell boundary still sees every trail within range.
   - **Snaps** each hub in its region to the subgraph (`snap_hub_to_subgraph`): an existing graph
     node within `max-snap-m` always wins; otherwise the nearest mid-chain point on an edge is
     found (`lib/edge_split.py`'s `nearest_point_on_polyline`) and the edge is split there
     (`split_edge_at_point`), inserting a virtual vertex.
   - Builds an in-process `igraph.Graph` over the region (base + virtual vertices), computes
     real-distance (`weights="dist"`) cutoff distances from each core hub to every other hub in
     range (mirrors the old pass1), then — for pairs that pass the cutoff — fetches the
     road-penalized (`weights="weight"`) shortest path (`get_shortest_paths(..., output="epath")`,
     mirrors the old pass2) and walks it to build the full path geometry, summing real `dist`/
     `road_m`, tracking max `sac_rank` and any `via_ferrata` crossing.
3. `merge_and_dedup()` combines every worker's records: hut↔hut pairs are deduplicated
   (unordered, keyed on `(type, id)` since ids alone can collide across hut/station/parking id
   spaces); directional start→hut records are kept as-is.
- **Output**: `data/osm/hut_edges/{records.npy, geometry.npy}` and
  `data/osm/start_edges/{records.npy, geometry.npy}` (`binfmt.RECORD_DTYPE` +
  `binfmt.COORD_DTYPE`; `ascent_m`/`descent_m`/`profile_*` left `UNSET`/`0` here — filled by
  `add_elevation.py`).
- **doit wiring**: `file_dep=[base_graph/manifest.json, huts.geojson, start_points.npy]`,
  `targets=[hut_edges/records.npy, start_edges/records.npy]`. `uptodate` uses `config_changed`
  over the task's own params.

## 7. `fetch_dem` — `fetch_dem.py`

- Reads `config["dem"]` (`provider`, `providerConfig`, with `bbox` defaulted from top-level
  `config["bbox"]`).
- If `provider == "composite"`: delegates to `dem_providers.composite.fetch_regions()`, which
  runs each sub-region's own provider's `fetch()` and returns one manifest entry per sub-region
  (`{provider, raw_dir, region_vrt, tile_paths}`).
- Otherwise: calls `dem_providers.get_provider(name).fetch(config, raw_dir)` directly (single
  manifest entry).
- Every provider's `fetch()` skips tiles already on disk. Does **not** reproject/merge/materialize
  — that's step 7b, split out so retuning reprojection or rerunning after tile downloads never
  re-triggers Bavaria's coverage-grid WMS tile-existence check.
- Writes `data/dem/fetch_manifest.json`.
- **doit wiring**: `file_dep=[config]`, `targets=[fetch_manifest.json]`.
- Providers (`pipeline/dem_providers/`):
  - `copernicus-glo-30` — global 30m, AWS Open Data, no auth, `providerConfig: {}` (uses top bbox).
  - `at-bev-dgm` — Austria 10m DGM, one ~1.9GB national zip (`downloadUrl`), bbox unused.
  - `bavaria-dgm5` — Bavaria 5m DGM, one ~200KB zip per 1km tile computed from `providerConfig.bbox`;
    `bboxFromHuts: true` (used here) shrinks that bbox to actual hut extent + `bufferKm`
    (via `lib/pipeline.py`'s `bbox_from_huts`) instead of the full political box.
  - `composite` — stitches per-sub-region VRTs from different providers; region order matters
    where bboxes overlap (`gdalbuildvrt` keeps the first-listed source).

## 7b. `build_dem_vrt` — `build_dem_vrt.py`

- Reads `fetch_manifest.json`.
- `lib.pipeline.build_dem_vrt(manifest, DEM_DIR)`: for each manifest region, calls that
  provider's `to_4326_vrt(tile_paths, region_vrt)` (reprojects into EPSG:4326), then
  `normalize_colorinterp()` (forces `ColorInterp=Gray` so a mismatched region isn't silently
  dropped by the final `gdalbuildvrt` merge), then merges all region VRTs via
  `gdalbuildvrt -overwrite dem.vrt <region_vrts...>`.
- **materialize_geotiff** phase: bakes the (lazily-reprojecting) `dem.vrt` into a real
  tiled/DEFLATE-compressed `dem.tif` via `gdal_translate` (`PREDICTOR=3`, `-a_nodata` copied
  explicitly). This exists because reading `dem.vrt` directly re-runs per-pixel reprojection on
  every read — timed at ~750s for one AT+Bavaria window — so materializing once here means
  `add_elevation.py` (rerun often, to retune noise threshold) doesn't keep re-paying that cost.
- **doit wiring**: `file_dep=[fetch_manifest.json]`, `targets=[dem.vrt, dem.tif]`.

## 8. `add_elevation` — `add_elevation.py`  (always reruns when selected, `uptodate: [False]`; cheap, ~90–100s)

- Params: `--ele-noise-threshold-m` (default `config.dem.eleNoiseThresholdM`), `--profile-points`
  (default `config.dem.profilePoints`, 30).
- Processes `data/osm/hut_edges/` and `data/osm/start_edges/` together in one run, each via
  `_process_edge_set()`: reads that edge set's `records.npy`/`geometry.npy`, samples the DEM, and
  writes back updated `records.npy` plus a new `profiles.npy`.
- **read_dem_window** phase: opens `dem.tif`, computes row/col indices directly from the affine
  transform (rasterio's `rowcol()` crashes on arrays >1 element on this build), reads just the
  bounding window covering all edge-set vertices (not the whole multi-GB mosaic), and
  fancy-indexes all sample points from that one window read.
- **per_edge_ascent_profile** phase, per edge (`fill_elevation_records()`, a pure function
  decoupled from the `rasterio` DEM I/O above so it's directly unit-testable):
  - `ascent_descent()`: threshold-hysteresis filter — only counts a direction change once
    cumulative drift since the last counted point exceeds `--ele-noise-threshold-m`, so per-sample
    DEM noise doesn't inflate ascent/descent totals.
  - `elevation_profile()`: downsamples DEM samples to `--profile-points` values evenly spaced by
    cumulative trail distance (`np.interp`), skipping nodata samples — a fixed-size series
    regardless of the polyline's original (irregular) vertex spacing.
  - Fills each record's `ascent_m`, `descent_m`, `profile_offset`, `profile_count`, and appends
    the profile values to a new packed `profiles.npy` (`binfmt.PROFILE_DTYPE`).
- **doit wiring**: `task_dep=[build_hub_edges]` (same file, not just mtime), `file_dep=[dem.tif]`,
  `targets=[hut_edges/records.npy, hut_edges/profiles.npy, start_edges/records.npy,
  start_edges/profiles.npy]`.

## 9. `build_trail_tiles` — `build_trail_tiles.py`

Builds the *raw* trail network into static vector tiles (too large — 26.5M nodes — to ship as
plain GeoJSON).

1. `osmium export trails.osm.pbf --geometry-types=linestring -f geojsonseq -o -` piped directly
   (no intermediate file) into a Python filter loop.
2. The filter loop (using `orjson`, the one pure-Python bottleneck in this script — everything
   else is C/C++) strips every property down to just `highway`, writing
   `data/osm/trails.geojsons`.
3. `tippecanoe -o trails.mbtiles -l trails -Z<min> -z<max> --drop-densest-as-needed --force
   trails.geojsons` (params default from `config.trailTiles.minZoom/maxZoom`).
4. `pmtiles.convert.mbtiles_to_pmtiles(trails.mbtiles, trails.pmtiles, max_zoom)`.
5. Deletes the intermediate `.geojsons`/`.mbtiles` files.
- On Windows, `tippecanoe` (no conda-forge win-64 build) runs via `lib.pipeline.run_tippecanoe()`,
  which shells out through WSL to a separate linux-64 micromamba env there.
- **doit wiring**: `file_dep=[trails.osm.pbf]`, `targets=[trails.pmtiles]`.

## 11. `build_hut_edge_tiles` / `build_start_edge_tiles` — `build_edge_tiles.py`

Generalized from the old `build_hut_edge_tiles.py`: same script, run twice by `dodo.py` (once per
`--edges-dir`/`--layer-name`) — once over `hut_edges/`, once over `start_edges/` — splitting each
edge set's `records.npy`/`geometry.npy`/`profiles.npy` (post step 8) into two smaller static
assets instead of shipping the arrays directly.

- For each edge (`edge_id` = array index): writes a tiling-input feature stripped to just
  `{edge_id}` properties, and computes an iterative/vectorized Ramer-Douglas-Peucker
  simplification (`rdp_keep_indices`, tolerance = `config.hutEdgeTiles.hoverSimplifyToleranceDeg`,
  default ~0.0003° / ~11m) for a much smaller hover-hit-test geometry.
- **`build_stats()`**: one JSON array, index = `edge_id`, holding everything non-geometric
  (`from_hut_id, to_hut_id, distance_m, road_m, ascent_m, descent_m, elevation_profile,
  sac_scale, via_ferrata`) plus the simplified `positions` ([lng, lat] pairs) for hover hit-testing
  (PMTiles has no feature-level query API, hence this separate copy). `from_hut_id`/`to_hut_id`
  are resolved from numeric `(type, id)` back to their original string/OSM id via
  `start_points_id_table.json` (huts pass through as-is, since `huts.geojson` never had a
  separate id table).
- **`*-edges.pmtiles`**: full-resolution edge geometry, `{edge_id}`-only properties, built the
  same tippecanoe → pmtiles-convert pipeline as step 9 (`-l hut_edges`/`-l start_edges`, same
  `min-zoom/max-zoom`/`--drop-densest-as-needed`).
- Deletes intermediate `.geojsonseq`/`.mbtiles` files.
- **doit wiring**: `file_dep=[hut_edges/records.npy]` (resp. `start_edges/records.npy`),
  `targets=[hut-edges.pmtiles, hut-edge-stats.json]` (resp. `start-edges.pmtiles`,
  `start-edge-stats.json`).

## 12. `copy_public_data` — inline in `dodo.py`

- Copies `PUBLIC_FILES` (`huts.geojson, hut-edges.pmtiles, hut-edge-stats.json,
  start-edges.pmtiles, start-edge-stats.json, trails.pmtiles, stations.geojson, parking.geojson`)
  from `data/osm/` into `huts/public/data/`, creating the target dir if needed. Skips + prints a
  message for any not-yet-built file rather than failing.
- This is the only sync step into the app's public data dir — no separate hand-copy needed.
- **doit wiring**: `file_dep`/`targets` = the `PUBLIC_FILES` list (source/dest respectively).

---

## Shared library code

- **`lib/pipeline.py`** — `load_config()`, path constants (`OSM_DIR`, `DEM_DIR`,
  `PUBLIC_DATA_DIR`, ...), `materialize_geotiff()`, `normalize_colorinterp()`, `build_dem_vrt()`,
  `run_tippecanoe()` (native-or-WSL dispatch), `hut_points()` / `edge_points()` /
  `bbox_from_huts()` (used by DEM providers to derive fetch extents from real hut/edge locations).
- **`lib/timing.py`** — `phase(script, name, **meta)` context manager, appends one JSON line to
  `data/timings.jsonl` per completed phase (skipped on exception, so failed runs leave no
  misleading partial record). Used by the expensive scripts (`build_base_graph.py`,
  `build_dem_vrt.py`, `add_elevation.py`) to track which phase stops scaling first as regional
  scope grows past AT+Bayern.
- **`lib/grid.py`** — `Grid`, a row-major spatial grid partitioning a bbox into
  `tileSizeKm` cells; `cell_id` is fully determined by `(bbox, tile_size_km)` so it's
  re-derivable identically at both `build_base_graph.py` write time and `build_hub_edges.py`
  query time, with no lookup table needed.
- **`lib/binfmt.py`** — the shared binary array formats: dtypes (`NODE_DTYPE`, `EDGE_DTYPE`,
  `RECORD_DTYPE`, `COORD_DTYPE`, ...), type constants (`TYPE_HUT`/`TYPE_STATION`/`TYPE_PARKING`),
  `save_array()`/`load_array()` (plain `.npy`, memory-mappable via `mmap_mode="r"`),
  `save_manifest()`/`load_manifest()`, and `build_csr_index()` (the shared "sort once,
  bincount+cumsum for offsets" CSR-adjacency helper used for both nodes-by-cell and
  edges-by-node indexing).
- **`lib/contraction.py`** — `contract_structural()`, the pure structural (no hub-snap exception)
  chain-contraction function `build_base_graph.py` calls.
- **`lib/edge_split.py`** — `nearest_point_on_polyline()`/`split_edge_at_point()`, mid-chain edge
  splitting for snapping a hub to the interior of a chain edge rather than an existing node.
- **`lib/subgraph.py`** — `gather_padded_subgraph()`, the padded-region (cell + buffer) mmap
  gather `build_hub_edges.py`'s per-cell workers use to slice the persisted base graph.
