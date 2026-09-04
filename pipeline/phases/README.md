# pipeline/phases/ — task DAG overview

High-level map of the pipeline. Orchestration is a [doit](https://pydoit.org) task DAG
(`pipeline/dodo.py`), not a numbered sequence — the order below follows the DAG's dependency order
(`file_dep`/`targets`), which matches `DOIT_CONFIG["default_tasks"]`. All hyperparameters come from
`pipeline/pipeline.config.json` via `lib/pipeline.py`'s `load_config()`.

**Never run any of this without asking the user first** — `build_base_graph` alone measured
~4.1 hours as part of its predecessor `build_hut_graph` (`data/timings.jsonl`) and is part of the
default `doit` run.

Each subdirectory below is one phase of the DAG and has its own `README.md` with the actual data
structures and algorithms — this file only says what each phase is for and how they chain
together.

```
downloads/       → preprocessing/  → graph_building/  → elevation/           → graph_building/ → elevation/       → postprocessing/
  raw .osm.pbf      trails.osm.pbf    build_base_graph/   sample_base_        build_hub_edges/    build_profiles.py  .pmtiles + stats
  huts/stations/    start_points.npy  base_graph/edges.npy elevation.py+       hut_edges/,         profiles.npy       for the app
  parking geojson                    (time_s UNSET)       compute_edge_       start_edges/
  dem tiles                                               profiles.py
                                                            (fills time_s/
                                                            ascent_m/descent_m
                                                            on edges.npy)
```

Elevation is not one contiguous phase any more: the DEM-sampling half
(`sample_base_elevation.py`/`compute_edge_profiles.py`) has to run *before* `build_hub_edges.py`,
because `time_s` is the routing weight (spec A3) — a route can't be found before its cost exists.
Only the display-only half (`build_profiles.py`, interpolated point elevations for the hover
profile UI) runs after, since it reads `records.npy`'s already-routed geometry.

## 1. `downloads/` — fetch raw data, no filtering/interpretation

Geofabrik OSM extracts, Alpenverein hut points, OSM stations/parking, and DEM elevation tiles.
Nothing here reads another phase's output. See `phases/downloads/README.md`.

## 2. `preprocessing/` — filter and merge into the pipeline's working inputs

Turns raw OSM extracts into one merged hiking-ways network (`trails.osm.pbf`), and filters
stations/parking down to the ones close enough to a hut to ever matter. See
`phases/preprocessing/README.md`.

## 3. `graph_building/` — the expensive step: OSM ways → hut-to-hut trail edges

`build_base_graph.py` streams `trails.osm.pbf` into a persisted, hub-agnostic base graph
(distance, road/grading/ungraded-metre facts per edge; `time_s`/`ascent_m`/`descent_m` left
`UNSET` until `elevation/` fills them in — see below). `build_hub_edges.py` then queries that graph
per hub (hut/station/parking), routing each `pipeline.config.json` `graph.variants` row
(`FAST_ANY`/`FAST_T2`/`FAST_T3`/`FAST_T3_UNGRADED`, `lib/variants.py`) over a differently-filtered
subgraph on the *time* cost (`lib/speed.py`'s pointwise model), never a road-penalized distance
(spec A3). See `phases/graph_building/README.md`.

## 4. `elevation/` — DEM sampling: split around `graph_building/`'s hub-edge query

`build_dem_vrt.py` mosaics the DEM once. `sample_base_elevation.py` samples it per base-graph
point; `compute_edge_profiles.py` smooths those samples per base edge and fills `time_s`/
`ascent_m`/`descent_m` on `base_graph/edges.npy` in place — both run *before*
`build_hub_edges.py`, since `time_s` is the routing weight a route can't be found without.
`build_profiles.py` runs *after* `build_hub_edges.py`: it interpolates the same stored point
elevations onto each routed record's display profile (`profile_*` fields), never reopening the
DEM. See `phases/elevation/README.md`.

## 5. `postprocessing/` — package everything for the browser app

Builds static vector tiles (PMTiles) from the raw trail network and from the computed edges, JSON
stat sidecars for hover UI, the reduced approach/exit table (`build_approach_table.py`), and the
packed hut-edge payload the client loads up front (`build_edge_payload.py`). See
`phases/postprocessing/README.md`.

## Not a phase directory: `copy_public_data`

Defined inline in `pipeline/dodo.py`, not under `phases/` — copies every app-facing output
(`huts.geojson`, `hut-edges.pmtiles`, `hut-edge-stats.json`, `start-edges.pmtiles`,
`start-edge-stats.json`, `trails.pmtiles`, `stations.geojson`, `parking.geojson`,
`unsnapped_huts.json`, `approaches.bin`, `approaches.json`, `hut-edge-payload.bin`,
`hut-edge-payload.json` — `dodo.py`'s `PUBLIC_FILES`) from `data/osm/` into `huts/public/data/`.
Included in the default `doit` run; run `doit copy_public_data` alone to re-sync after
hand-running individual scripts.

## Shared library code (`pipeline/lib/`)

Not a phase — code imported across phases:

- **`pipeline.py`** — `load_config()`, path constants (`OSM_DIR`, `DEM_DIR`, `PUBLIC_DATA_DIR`,
  ...), `materialize_geotiff()`, `normalize_colorinterp()`, `build_dem_vrt()`, `run_tippecanoe()`
  (native-or-WSL dispatch), `hut_points()` / `edge_points()` / `bbox_from_huts()`.
- **`timing.py`** — `phase(script, name, **meta)` context manager, appends one JSON line to
  `data/timings.jsonl` per completed phase. Used by `graph_building/build_base_graph.py` and
  `elevation/build_dem_vrt.py`/`sample_base_elevation.py`/`compute_edge_profiles.py` to track
  which step stops scaling first as regional scope grows past AT+Bayern.
- **`grid.py`** — `Grid`, the row-major spatial grid `graph_building/` partitions the bbox into.
- **`binfmt.py`** — shared binary array formats (dtypes, `save_array()`/`load_array()`,
  `save_manifest()`/`load_manifest()`, `build_csr_index()`, `SCHEMA_VERSION`).
- **`grading.py`** — `classify_way()`/`excluded_from_constrained()`, per-way passability grading
  (`sac_rank` + `ungraded_m`/`inferred_m` tier) consumed by `build_base_graph.py`'s streaming pass.
- **`speed.py`** — `edge_time_s()`/`speed_kmh()` (the pointwise Tobler-shaped routing weight,
  calibrated by `analysis/routing_probe.py`) and `din_duration_h()` (the reported-duration formula
  the client applies — never stored, spec D3).
- **`variants.py`** — the `graph.variants` row definitions and `edge_mask()`, turning one row's
  constraint into a boolean mask over a subgraph's edges for `build_hub_edges.py`.
- **`contraction.py`** — `contract_structural()`, chain-contraction used by `build_base_graph.py`.
- **`edge_split.py`** — mid-chain edge splitting for snapping a hub onto a trail's interior.
- **`subgraph.py`** — `gather_padded_subgraph()`, the padded-region mmap gather used by
  `build_hub_edges.py`'s per-cell workers.
- **`geo.py`** — `hut_points()`/`circle_polygon()`/`hub_range_polygon()`, hub-range coverage
  geometry shared by `preprocessing/compute_hub_range.py` and
  `downloads/dem_providers/composite.py` (both must derive the same radius from
  `HUB_RANGE_SAFETY_MARGIN` or their coverage shapes silently drift apart).
- **`poly.py`** — `parse_poly_file()`/`region_boundary()`, parses Geofabrik's `.poly`
  admin-boundary files into shapely (Multi)Polygons; `downloads/fetch_huts.py` filters the AV hut
  catalog to the union of every configured region's boundary instead of a bbox.
- **`edge_output.py`** — `write_edge_records()`/`fold_endpoint_snaps()`, the record-packing shape
  (`binfmt.RECORD_DTYPE` + `geometry.npy`) shared by `build_hub_edges.py` and
  `match_tour_edges.py` so both emit identical on-disk edge records.

Full config reference, environment setup, and "reproducing from scratch" commands:
**`pipeline/README.md`**. Design rationale for the graph-building rewrite:
**`docs/osm-trail-pipeline.md`** and `docs/superpowers/specs/2026-08-19-pipeline-v2-design.md`.
