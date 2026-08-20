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
downloads/       → preprocessing/  → graph_building/ → elevation/ → postprocessing/
  raw .osm.pbf      trails.osm.pbf    base_graph/,      +ascent_m/    .pmtiles + stats
  huts/stations/    start_points.npy  hut_edges/,        descent_m/    for the app
  parking geojson                    start_edges/        profiles.npy
  dem tiles
```

## 1. `downloads/` — fetch raw data, no filtering/interpretation

Geofabrik OSM extracts, Alpenverein hut points, OSM stations/parking, and DEM elevation tiles.
Nothing here reads another phase's output. See `phases/downloads/README.md`.

## 2. `preprocessing/` — filter and merge into the pipeline's working inputs

Turns raw OSM extracts into one merged hiking-ways network (`trails.osm.pbf`), and filters
stations/parking down to the ones close enough to a hut to ever matter. See
`phases/preprocessing/README.md`.

## 3. `graph_building/` — the expensive step: OSM ways → hut-to-hut trail edges

Streams `trails.osm.pbf` into a persisted, hub-agnostic base graph, then queries it per hub
(hut/station/parking) to compute real-distance, road-penalized shortest paths between huts. See
`phases/graph_building/README.md`.

## 4. `elevation/` — DEM sampling: ascent/descent + elevation profiles per edge

Fetches/mosaics a DEM raster and samples it along each edge polyline computed in
`graph_building/`, filling in `ascent_m`/`descent_m`/`profile_*` fields in place. See
`phases/elevation/README.md`.

## 5. `postprocessing/` — package everything for the browser app

Builds static vector tiles (PMTiles) from the raw trail network and from the computed edges, plus
JSON stat sidecars for hover UI. See `phases/postprocessing/README.md`.

## Not a phase directory: `copy_public_data`

Defined inline in `pipeline/dodo.py`, not under `phases/` — copies every app-facing output
(`huts.geojson`, `hut-edges.pmtiles`, `hut-edge-stats.json`, `start-edges.pmtiles`,
`start-edge-stats.json`, `trails.pmtiles`, `stations.geojson`, `parking.geojson`) from `data/osm/`
into `huts/public/data/`. Included in the default `doit` run; run `doit copy_public_data` alone to
re-sync after hand-running individual scripts.

## Shared library code (`pipeline/lib/`)

Not a phase — code imported across phases:

- **`pipeline.py`** — `load_config()`, path constants (`OSM_DIR`, `DEM_DIR`, `PUBLIC_DATA_DIR`,
  ...), `materialize_geotiff()`, `normalize_colorinterp()`, `build_dem_vrt()`, `run_tippecanoe()`
  (native-or-WSL dispatch), `hut_points()` / `edge_points()` / `bbox_from_huts()`.
- **`timing.py`** — `phase(script, name, **meta)` context manager, appends one JSON line to
  `data/timings.jsonl` per completed phase. Used by `graph_building/build_base_graph.py` and
  `elevation/build_dem_vrt.py`/`add_elevation.py` to track which step stops scaling first as
  regional scope grows past AT+Bayern.
- **`grid.py`** — `Grid`, the row-major spatial grid `graph_building/` partitions the bbox into.
- **`binfmt.py`** — shared binary array formats (dtypes, `save_array()`/`load_array()`,
  `save_manifest()`/`load_manifest()`, `build_csr_index()`).
- **`contraction.py`** — `contract_structural()`, chain-contraction used by `build_base_graph.py`.
- **`edge_split.py`** — mid-chain edge splitting for snapping a hub onto a trail's interior.
- **`subgraph.py`** — `gather_padded_subgraph()`, the padded-region mmap gather used by
  `build_hub_edges.py`'s per-cell workers.

Full config reference, environment setup, and "reproducing from scratch" commands:
**`pipeline/README.md`**. Design rationale for the graph-building rewrite:
**`docs/osm-trail-pipeline.md`** and `docs/superpowers/specs/2026-08-19-pipeline-v2-design.md`.
