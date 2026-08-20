# pipeline/ — hut-to-hut routing graph pipeline

A hut-to-hut trail graph (nodes = huts, edges = real trail paths/distances) so route planning
isn't limited to the Alpenverein's 26 predefined tours (`toursearchApi` /
`AVT_CAA_TOUR_View_L`, see `docs/alpenverein-api.md` §3). Edges are derived from OSM hiking ways,
not the Alpenverein data.

This is entirely an offline precompute pipeline living under `pipeline/` — it doesn't change the
app's backend-free architecture; outputs are static files (GeoJSON + PMTiles vector tiles), copied
into `huts/public/data/` for the app to fetch (see the root `CLAUDE.md`'s "App structure"). Raw
downloads and generated pipeline outputs live in the sibling `data/` dir (gitignored — `pipeline/`
is the only tracked half). Full reproduction steps and scripts: **`pipeline/README.md`**. Design
rationale for the OSM extract/filter/merge steps: **`docs/osm-trail-pipeline.md`**.

Pipeline is plain Python, no bash/Node/Docker: config-driven — every hyperparameter (region list,
hut bbox, trail tag filter, max-edge-km / max-snap-m, DEM provider) lives in
`pipeline/pipeline.config.json` — and `pipeline/dodo.py` runs the whole thing as a
[doit](https://pydoit.org) task DAG (one task per script, wired by `file_dep`/`targets` rather than
a numbered run order), idempotently (`doit` skips a task whose targets are already up to date;
`doit <task>` reruns just that task and any stale deps), inside the `alpen-osm` conda env (see
`pipeline/README.md` "Setup" for how that env was created — via `micromamba`, not `conda create`,
since this machine's `base` conda env hangs solving `-c conda-forge` specs). The last task,
`copy_public_data`, copies every output into `huts/public/data/` — no separate hand-copy step.

**V2 architecture** (`docs/superpowers/specs/2026-08-19-pipeline-v2-design.md`): a persisted,
hub-agnostic base graph (`graph_building/build_base_graph.py`, streams+contracts `trails.osm.pbf` once into
`data/osm/base_graph/`'s plain `.npy` structured arrays, `lib/binfmt.py`) is decoupled from the
hub-edge query (`graph_building/build_hub_edges.py`), which partitions the bbox into `lib/grid.py` cells and
runs one worker process per cell (`ProcessPoolExecutor`), each mmap-slicing only its own padded
region of the base graph (`lib/subgraph.py`) rather than sharing one big in-process graph. This
means the expensive stream+contract step is cached across hub-set changes and hyperparameter
retuning, and station/parking routing edges (filtered to hub range by
`preprocessing/filter_start_points.py`, snapped mid-chain via `lib/edge_split.py` where needed) are now
first-class alongside hut-hut edges — both live in the same `records.npy`/`geometry.npy` binary
format (`hut_edges/`, `start_edges/`), tiled by the same generalized `graph_building/build_edge_tiles.py`.

Current status: built and up to date for Austria+Bavaria, outputs rendered by the app
(`GraphPage.jsx`'s `#graph` route for the raw network + hut/start edges, `App.jsx` for
stations/parking markers) — see the root `CLAUDE.md`'s "App structure" section. Not done:
extending scope past AT+Bayern; the diverse-paths (multiple route variants per pair,
`RECORD_DTYPE`'s `variant` field) extensibility hook exists but no second variant is computed yet.

## Timing pipeline phases

`pipeline/lib/timing.py`'s `phase(script, name, **meta)` context manager appends one JSON
line to `data/timings.jsonl` per completed phase (`{ts, script, phase, seconds, meta?}`) — skipped
entirely if the block raises, so a failed run never leaves a misleading partial record. Used
internally by the scripts expensive enough to want phase-level breakdown: `graph_building/build_base_graph.py`
(`stream_osm`, `contract_structural`), `graph_building/build_dem_vrt.py` (`materialize_geotiff`) and
`graph_building/add_elevation.py` (`read_dem_window`, `per_edge_ascent_profile`). This exists because scope is
expected to grow past AT+Bayern — `timings.jsonl` is the real-numbers record for seeing which
phase stops scaling first, instead of guessing. It already caught one: `read_dem_window` timed at
~750s (`data/timings.jsonl`), because `graph_building/add_elevation.py` used to sample `graph_building/build_dem_vrt.py`'s
`dem.vrt` directly - a VRT chain that lazily reprojects every region's tiles into EPSG:4326 on
read, so a window covering AT+Bavaria re-ran that reprojection on every `graph_building/add_elevation.py` run
(the script people rerun most, to retune `--ele-noise-threshold-m`). Fixed by having
`graph_building/build_dem_vrt.py` materialize the VRT into a real, tiled/compressed GeoTIFF once
(`pipeline/lib/pipeline.py`'s `materialize_geotiff()`, `data/dem/dem.tif`) that `graph_building/add_elevation.py`
reads instead - see that function's docstring. Wrap a new expensive block in `with
phase(SCRIPT_NAME, "phase_name", **any_size_metadata):` rather than ad hoc `print`/`time.time()`
timing to keep it queryable the same way.
