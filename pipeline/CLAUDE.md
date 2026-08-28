# pipeline/ — hut-to-hut routing graph pipeline

A hut-to-hut trail graph (nodes = huts, edges = real trail paths/distances) so route planning
isn't limited to the Alpenverein's 26 predefined tours (`toursearchApi` /
`AVT_CAA_TOUR_View_L`, see `docs/alpenverein-api.md` §3). Edges are derived from OSM hiking ways,
not the Alpenverein data.

This is entirely an offline precompute pipeline living under `pipeline/` — it doesn't change the
app's backend-free architecture; outputs are static files (GeoJSON + PMTiles vector tiles), copied
into `huts/public/data/` for the app to fetch (see the root `CLAUDE.md`'s "App structure"). Raw
downloads and generated pipeline outputs live in the sibling `data/` dir (gitignored — `pipeline/`
is the only tracked half). Full reproduction steps and scripts: **`pipeline/README.md`**. Per-script
data structures and algorithms: **`pipeline/phases/README.md`** (high-level DAG map) and each
`phases/<phase>/README.md` (detailed). Design rationale for the OSM extract/filter/merge steps:
**`docs/osm-trail-pipeline.md`**.

Pipeline is plain Python, no bash/Node/Docker: config-driven — every hyperparameter (region list,
hut bbox, trail tag filter, max-edge-km / max-snap-m, DEM provider) lives in
`pipeline/pipeline.config.json` — and `pipeline/dodo.py` runs the whole thing as a
[doit](https://pydoit.org) task DAG (one task per script, wired by `file_dep`/`targets` rather than
a numbered run order), idempotently (`doit` skips a task whose targets are already up to date;
`doit <task>` reruns just that task and any stale deps), inside the `alpen-osm` pixi env (see
`pipeline/README.md` "Setup"). The last task, `copy_public_data`, copies every output into
`huts/public/data/` — no separate hand-copy step.

`dodo.py` itself only assembles the DAG (`DOIT_CONFIG`, `copy_public_data`) — the `task_*`
functions live in `pipeline/dag/`, one module per `phases/` subdirectory (`dag/downloads.py`,
`dag/preprocessing.py`, `dag/graph_building.py`, `dag/elevation.py`, `dag/postprocessing.py`), so a
task's wiring sits next to the phase it wires, and no single file grows to hold the whole DAG.
`lib/doit_support.py` holds the plumbing every `task_*` function needs: `pipeline_task()` builds
the action command line + `file_dep`/`targets` (via `rel()`) + `params`/`uptodate` in one call
instead of each task hand-rolling them; `cli_param()` is a param that's both a real `--flag` on the
action line and part of the tracked cache key, `tracking_param()` is one that's tracked but has no
corresponding flag (the script reads that config value directly); `TaskOptionsChanged` is the
`uptodate` check both rely on — see its docstring for the two doit bugs it works around, which is
why it exists as real code instead of `doit`'s built-in `config_changed`.

### Keep task-wiring rationale short-lived

A `dag/*.py` comment should state *why the wiring is what it is now* (e.g. "not force-rerun: ~4h
rebuild", "split from X because Y only needs Z") in one or two lines — not the history of what used
to be wrong and how it got fixed. `dodo.py` grew past 700 lines mostly from that narrative form
repeated per task; it's real information, but it belongs in the commit that made the change (or
`pipeline/README.md`/a linked spec under `docs/superpowers/`) so it can be found by `git blame`
without inflating the file everyone reads to understand the DAG. When editing a task's wiring,
prefer trimming an existing comment down to its current rationale over appending another paragraph
explaining what changed and why the old approach was wrong.

`pipeline/analysis/` holds standalone, read-only analysis/benchmark scripts (e.g. `snap_stats.py`)
that are **not** part of the `dodo.py` task DAG and never modify `phases/` scripts — they import and
call the real phase functions directly (e.g. `build_hub_edges.py`'s `snap_hub_to_subgraph()`) against
already-persisted `data/` outputs, to get hard numbers on where a phase's complexity/cost actually
goes, without touching production code. Run by hand: `python pipeline/analysis/<script>.py`.
Per-script purpose, requirements and outputs, plus the rules a new script here has to follow:
**`pipeline/analysis/README.md`**.

**V2 architecture** (`docs/superpowers/specs/2026-08-19-pipeline-v2-design.md`): a persisted,
hub-agnostic base graph (`phases/graph_building/build_base_graph.py`, streams+contracts `trails.osm.pbf` once into
`data/osm/base_graph/`'s plain `.npy` structured arrays, `lib/binfmt.py`) is decoupled from the
hub-edge query (`phases/graph_building/build_hub_edges.py`), which partitions the bbox into `lib/grid.py` cells and
runs one worker process per cell (`ProcessPoolExecutor`), each mmap-slicing only its own padded
region of the base graph (`lib/subgraph.py`) rather than sharing one big in-process graph. This
means the expensive stream+contract step is cached across hub-set changes and hyperparameter
retuning, and station/parking routing edges (filtered to hub range by
`phases/preprocessing/filter_start_points.py`, snapped mid-chain via `lib/edge_split.py` where needed) are now
first-class alongside hut-hut edges — both live in the same `records.npy`/`geometry.npy` binary
format (`hut_edges/`, `start_edges/`), tiled by the same generalized `phases/postprocessing/build_edge_tiles.py`.

Current status: outputs rendered by the app (`GraphPage.jsx`'s `#graph` route for the raw network +
hut/start edges, `App.jsx` for stations/parking markers) — see the root `CLAUDE.md`'s "App
structure" section. The graph now routes on a time cost (`lib/speed.py`'s pointwise Tobler model,
calibrated against DIN 33466 by `analysis/routing_probe.py`) rather than a road-penalized distance,
and the diverse-paths hook (`RECORD_DTYPE`'s `variant` field) is in active use: `build_hub_edges.py`
routes every hub pair over `pipeline.config.json`'s `graph.variants` grid — `FAST_ANY`, `FAST_T2`,
`FAST_T3`, `FAST_T3_UNGRADED` (`lib/variants.py`, `lib/binfmt.py`'s `VARIANT_*` constants) — each row
a differently-filtered subgraph over the same base graph, not a repeated full rebuild. Not done:
extending scope past AT+Bayern; the full four-variant rebuild under the new cost model is the
pending run (`docs/superpowers/plans/2026-08-22-tour-suggestion-backend.md` Task 24) — until it
lands, the shipped `huts/public/data/` outputs still reflect the old road-penalized single-variant
graph.

## Timing pipeline phases

`pipeline/lib/timing.py`'s `phase(script, name, **meta)` context manager appends one JSON
line to `data/timings.jsonl` per completed phase (`{ts, script, phase, seconds, meta?}`) — skipped
entirely if the block raises, so a failed run never leaves a misleading partial record. Used
internally by the scripts expensive enough to want phase-level breakdown: `phases/graph_building/build_base_graph.py`
(`stream_osm`, `contract_structural`), `phases/elevation/build_dem_vrt.py` (`materialize_geotiff`) and,
historically (V1, before the split into `sample_base_elevation.py`/`compute_edge_profiles.py`),
`add_elevation.py` (`read_dem_window`, `per_edge_ascent_profile`) — that script is deleted, but its
`phase()` records remain in `data/timings.jsonl` as history. This exists because scope is
expected to grow past AT+Bayern — `timings.jsonl` is the real-numbers record for seeing which
phase stops scaling first, instead of guessing. It already caught one: `read_dem_window` timed at
~750s (`data/timings.jsonl`), because the old `add_elevation.py` sampled `phases/elevation/build_dem_vrt.py`'s
`dem.vrt` directly - a VRT chain that lazily reprojects every region's tiles into EPSG:4326 on
read, so a window covering AT+Bavaria re-ran that reprojection on every `add_elevation.py` run
(the script people reran most, to retune the now-retired `--ele-noise-threshold-m`). Fixed by having
`phases/elevation/build_dem_vrt.py` materialize the VRT into a real, tiled/compressed GeoTIFF once
(`pipeline/lib/pipeline.py`'s `materialize_geotiff()`, `data/dem/dem.tif`) that
`phases/elevation/sample_base_elevation.py` reads instead - see that function's docstring. Wrap a
new expensive block in `with
phase(SCRIPT_NAME, "phase_name", **any_size_metadata):` rather than ad hoc `print`/`time.time()`
timing to keep it queryable the same way.

`lib/timing.py`'s `StepTimer` is the sub-phase counterpart: it sums seconds + call counts per
step name in memory and lands them as `<step>_s`/`<step>_calls` meta on ONE `phase(...)` record,
for steps that repeat inside a phase or run in worker processes (where concurrent `phase()` calls
would interleave lines in the single `timings.jsonl`). Steps must not nest, or the percentages
stop being a split. Every long script now ends with a `step totals: ...` line:

| script | phase record | steps |
| --- | --- | --- |
| `graph_building/snap_hubs.py` | `hub_snap` | `gather_subgraph`, `snap` (per worker, merged in the parent) |
| `graph_building/gather_route_subgraphs.py` | `gather_route_subgraphs` | single-process, no StepTimer split (one `phase()` per whole run) |
| `graph_building/build_hub_edges.py` | `hub_edge_query` | `gather_subgraph` (now a cache reload, not a fresh gather), `snap` (now a dict lookup against snap_hubs.py's cache, not a geometric search), `build_igraph`, `distances`, `paths` (per worker, merged in the parent; also printed per cell in the progress line) |
| `graph_building/build_base_graph.py` | `build_base_graph` | `stream_osm`, `handler_to_arrays`, `contract`, `pack_nodes`, `pack_interior`, `pack_edges`, `write_arrays` |
| `elevation/add_elevation.py` (removed, V1) | `add_elevation` | `load_arrays`, `dem_index_math`, `read_dem_window`, `sample_elevations`, `per_edge_ascent_profile`, `save_arrays` |
| `elevation/sample_base_elevation.py` | `sample_base_elevation` | `load_arrays`, `read_dem`, `sample`, `write` |
| `elevation/compute_edge_profiles.py` | `compute_edge_profiles` | `load_arrays`, `smooth`, `ascent_descent`, `write` |
| `postprocessing/build_edge_tiles.py` | `build_edge_tiles` | `load_arrays`, `write_tiling_input`, `build_stats`, `write_stats`, `tippecanoe`, `mbtiles_to_pmtiles` |
| `postprocessing/build_trail_tiles.py` | `build_trail_tiles` | `osmium_export_filter`, `tippecanoe`, `mbtiles_to_pmtiles` |
| `downloads/download_extracts.py` | `download_extracts` | `download` (per region) |
| `preprocessing/filter_trails.py` | `filter_trails` | `tag_filter`, `clip` (per region) |
| `downloads/fetch_stations_parking.py` | `fetch_stations_parking` | `<layer>_tag_filter`, `<layer>_export` (per layer x region) |

Every other DAG task (`preprocessing/merge_trails.py`, `preprocessing/verify_trails.py`,
`downloads/fetch_huts.py`, `preprocessing/compute_hub_range.py`,
`preprocessing/filter_start_points.py`, `downloads/fetch_dem.py`,
`elevation/build_profiles.py`, `postprocessing/build_approach_table.py`,
`postprocessing/build_edge_payload.py`, and `copy_public_data`'s inline action in `dodo.py`) now
records a plain `phase(...)` per run too (no StepTimer split - either genuinely one unit of work,
or not yet worth breaking down further) - so every task in the DAG has at least whole-task timing
in `data/timings.jsonl`, even the ones not listed in this table.
`elevation/build_dem_vrt.py` already did this before this pass, with two separate phase records
(`materialize_regions`, `materialize_geotiff`) rather than one.

The pre-existing `stream_osm` / `contract_structural` / `read_dem_window` /
`per_edge_ascent_profile` `phase()` records are deliberately kept alongside the StepTimer steps
of the same name - they are the historical series in `data/timings.jsonl` (and carry the
`rss_sampler` memory meta), so queries over them keep working. `build_hub_edges.py`'s step
seconds are summed across parallel workers and therefore exceed its wall clock - read the ratios
between steps there, not the absolute numbers.

## Progress logging

Every script under `phases/` or `analysis/` must print progress as it runs — never go silent for
more than a few seconds on a real-size run. `build_hub_edges.py`'s per-cell loop is the model:
print one line per unit of work as it completes (`[completed/total] ... -> N records | elapsed Xm,
~Ym remaining`), with `flush=True` so it's visible immediately even when stdout is piped/redirected.
A script that only prints a final summary is unreviewable while it runs and looks hung on a slow
box — this applies equally to `analysis/` scripts, which are run by hand and read interactively.
