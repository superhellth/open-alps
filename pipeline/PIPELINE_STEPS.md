# Pipeline steps — detailed

Generated from reading `pipeline/dodo.py` and each script. Orchestration is a
[doit](https://pydoit.org) task DAG (`pipeline/dodo.py`), not a numbered sequence — task order
below follows the DAG's dependency order (`file_dep`/`targets`), which matches
`DOIT_CONFIG["default_tasks"]`. All hyperparameters come from `pipeline/pipeline.config.json`
via `lib/pipeline.py`'s `load_config()`.

**Never run any of this without asking the user first** — `build_hut_graph` alone measured
~4.1 hours (`data/timings.jsonl`) and is part of the default `doit` run.

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

## 6. `build_hut_graph` — `build_hut_graph.py`  (the expensive step, ~4.1h for AT+Bayern)

Replaces the old buffer-clip + OSMnx/NetworkX approach (rejected — object overhead, not input
size, was the memory problem; see `pipeline/README.md`). Params: `--max-edge-km` (default
`config.graph.maxEdgeKm`), `--max-snap-m` (`maxSnapM`), `--road-penalty-factor`
(`roadPenaltyFactor`), `--workers` (default `os.cpu_count()`).

1. **stream_osm** — streams `trails.osm.pbf` once via `pyosmium` (`osmium.SimpleHandler`) into
   flat numpy arrays: node coords, edge endpoint indices, per-edge haversine distance, a
   road-penalized routing "weight" (real distance × `roadPenaltyFactor` if `highway` is in
   `config.graph.roadHighwayTags`), a road bool, a ranked `sac_scale` value (via
   `SAC_SCALE_RANK`, easiest→hardest), and a `via_ferrata` bool (`highway=via_ferrata` or
   `via_ferrata_scale` tag present).
2. **build_kdtree** — builds a `scipy.spatial.cKDTree` over raw node coords, used to snap each hut
   to its nearest trail node (query capped at `--max-snap-m`, converted from meters to degrees,
   then re-verified with real haversine distance). Huts with no trail node within `max-snap-m`
   are skipped entirely (no edges computed for them) — this is how direct-booking-only /
   off-network huts are handled.
3. **contract_chains** — collapses every run of degree-2 nodes (pure pass-through, no junction)
   between two "keep" nodes (real junctions/dead-ends, degree ≠ 2, or a hut-snap point) into one
   chain edge. Built via CSR-style adjacency (one sort over doubled endpoint arrays, no Python
   dict-of-lists). Each chain edge carries summed distance/weight, summed road length, the max
   `sac_scale` rank walked, whether any via-ferrata segment was crossed, and the full interior
   polyline. Lossless — a degree-2 node has no alternate route, so summing costs along the chain
   preserves shortest-path costs exactly, while shrinking node/edge count by (expected) an order
   of magnitude or more (measured ~40M raw nodes/edges for AT+Bavaria).
4. **build_igraph** — builds an `igraph.Graph` (undirected) over the *contracted* nodes/edges,
   with edge attrs `weight, dist, road_m, sac_rank, via_ferrata, interior_coords`.
5. **connected_components** — computes component membership once, so pass 1 can filter
   candidate pairs to the same component in O(1) instead of Dijkstra exhausting an unreachable
   component per query.
6. **pass1_distances** — for each snapped hut, finds candidate huts within a beeline radius of
   `3 × max-edge-km` via a hut-coordinate KDTree, restricted to the same connected component.
   Runs `graph.distances(source=[node], target=candidates, weights="dist")` per hut (target-limited,
   unlike scipy's `dijkstra(..., limit=)` which still allocates a full-graph-sized array every
   call) across a `ThreadPoolExecutor` (igraph's C calls release the GIL, so real thread
   parallelism, no process-pool pickling of the graph). Keeps a pair (dedup'd, unordered) if its
   real distance is finite and ≤ `max-edge-km`. Distance filtering uses real `dist`, not the
   road-penalized `weight`, so the length guarantee is unaffected by the road penalty.
7. **pass2_paths** — for each kept pair only, calls `graph.get_shortest_paths(src, tgt,
   weights="weight", output="epath")` (Dijkstra over the *penalized* weight, so it prefers
   trail-type ways over a comparably-short road alternative) — also thread-pooled. Walks the
   returned edge path, concatenating each contracted edge's interior polyline (reversed if
   traversed backward) into the full hut→trail-node→...→trail-node→hut geometry, summing real
   `dist` (→ `distance_m`) and `road_m`, tracking the max `sac_rank` walked and whether any
   via-ferrata edge was crossed.
- **Output**: `data/osm/hut-edges.geojson` — FeatureCollection of LineStrings, one per kept
  unordered hut pair, `properties={from_hut_id, to_hut_id, distance_m, road_m, sac_scale,
  via_ferrata, source: "osm"}`.
- **doit wiring**: `file_dep=[trails.osm.pbf, huts.geojson]`, `targets=[hut-edges.geojson]`.
  `uptodate` uses `config_changed` over the task's own params, so a changed `--max-edge-km` /
  `--max-snap-m` / `--road-penalty-factor` triggers a rerun without `doit forget`. NOT
  force-rerun (unlike `add_elevation`) — freshness-checked normally given its ~4.1h cost.

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
- Reads all polyline vertices across every edge in `hut-edges.geojson` in one batch.
- **read_dem_window** phase: opens `dem.tif`, computes row/col indices directly from the affine
  transform (rasterio's `rowcol()` crashes on arrays >1 element on this build), reads just the
  bounding window covering all edge vertices (not the whole multi-GB mosaic), and fancy-indexes
  all sample points from that one window read.
- **per_edge_ascent_profile** phase, per edge:
  - `ascent_descent()`: threshold-hysteresis filter — only counts a direction change once
    cumulative drift since the last counted point exceeds `--ele-noise-threshold-m`, so per-sample
    DEM noise doesn't inflate ascent/descent totals.
  - `elevation_profile()`: downsamples DEM samples to `--profile-points` values evenly spaced by
    cumulative trail distance (`np.interp`), skipping nodata samples — a fixed-size series
    regardless of the polyline's original (irregular) vertex spacing.
  - Writes `ascent_m`, `descent_m`, `elevation_profile` into each feature's properties, in place.
- Writes back to `data/osm/hut-edges.geojson` (same file, now with elevation properties added).
- **doit wiring**: `task_dep=[build_hut_graph]` (same file, not just mtime), `file_dep=[dem.tif]`,
  `targets=[hut-edges.geojson]`.

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

## 11. `build_hut_edge_tiles` — `build_hut_edge_tiles.py`

Splits `hut-edges.geojson` (post step 8, ~184MB at full resolution/properties) into two smaller
static assets instead of shipping it directly.

- For each edge (`edge_id` = array index): writes a tiling-input feature stripped to just
  `{edge_id}` properties, and computes an iterative/vectorized Ramer-Douglas-Peucker
  simplification (`rdp_keep_indices`, tolerance = `config.hutEdgeTiles.hoverSimplifyToleranceDeg`,
  default ~0.0003° / ~11m) for a much smaller hover-hit-test geometry.
- **hut-edge-stats.json**: one JSON array, index = `edge_id`, holding everything non-geometric
  (`from_hut_id, to_hut_id, distance_m, road_m, ascent_m, descent_m, elevation_profile,
  sac_scale, via_ferrata`) plus the simplified `positions` ([lng, lat] pairs) for hover hit-testing
  (PMTiles has no feature-level query API, hence this separate copy).
- **hut-edges.pmtiles**: full-resolution edge geometry, `{edge_id}`-only properties, built the
  same tippecanoe → pmtiles-convert pipeline as step 9 (`-l hut_edges`, same
  `min-zoom/max-zoom`/`--drop-densest-as-needed`).
- Deletes intermediate `.geojsonseq`/`.mbtiles` files.
- **doit wiring**: `file_dep=[hut-edges.geojson]`, `targets=[hut-edges.pmtiles, hut-edge-stats.json]`.

## 12. `copy_public_data` — inline in `dodo.py`

- Copies `PUBLIC_FILES` (`huts.geojson, hut-edges.pmtiles, hut-edge-stats.json, trails.pmtiles,
  stations.geojson, parking.geojson`) from `data/osm/` into `huts/public/data/`, creating the
  target dir if needed. Skips + prints a message for any not-yet-built file rather than failing.
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
  misleading partial record). Used by the expensive scripts (`build_hut_graph.py`,
  `build_dem_vrt.py`, `add_elevation.py`) to track which phase stops scaling first as regional
  scope grows past AT+Bayern.
