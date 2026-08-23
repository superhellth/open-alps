# phases/elevation/ — DEM mosaic + ascent/descent/profiles

Turns a raw elevation raster into a single sampleable GeoTIFF, then samples it along every edge
polyline `graph_building/build_hub_edges.py` computed, filling in the `ascent_m`/`descent_m`/
`profile_*` fields that were left `UNSET` there.

## `build_dem_vrt.py`

- Reads `data/dem/fetch_manifest.json` (written by `phases/downloads/fetch_dem.py`).
- For each manifest region, calls that region's provider's `to_4326_vrt(tile_paths, region_vrt)`
  (reprojects into EPSG:4326), then `lib/pipeline.py`'s `normalize_colorinterp()` (forces
  `ColorInterp=Gray` on every region VRT so a mismatched interpretation isn't silently dropped by
  the final merge).
- **Per-region materialize, in parallel**: `lib/pipeline.py`'s `build_dem_vrt()` then bakes each
  region's (possibly still-lazily-reprojecting) VRT into a real GeoTIFF via `materialize_geotiff()`,
  one call per region under a `ThreadPoolExecutor` (one OS `gdal_translate` process per provider,
  running concurrently — real parallelism, unlike GDAL's own `NUM_THREADS`, which only threads the
  compression step, never the warp/resample read path). Only then are the (now-real) region
  GeoTIFFs merged with `gdalbuildvrt -overwrite dem.vrt <region_tifs...>` — cheap mosaic
  bookkeeping, no more resampling.
- **`materialize_geotiff`** step (final, on the merged `dem.vrt`): with every region already real
  pixels, this is now just a compress+copy, not a reprojection. It exists at all — as a step
  distinct from just reading `dem.vrt` on demand — because reading a lazily-reprojecting VRT
  directly re-runs per-pixel reprojection on *every* read; materializing once here means
  `compute_edge_profiles.py` (rerun often, to retune `--smoothing-kernel-m`) never re-pays that
  cost. The *per-region* parallel materialize above is what actually keeps the reprojection cost
  itself off one core — see `lib/pipeline.py`'s `build_dem_vrt()`/`materialize_geotiff()`
  docstrings for the measured numbers (a single combined-VRT materialize pegged one core at ~99%
  for 8462s, `data/timings.jsonl` 2026-08-23, after Copernicus GLO-30 was added as a full-bbox
  coverage floor).
- **doit wiring**: `file_dep=[fetch_manifest.json]`, `targets=[dem.vrt, dem.tif]`.

## `sample_base_elevation.py` (base-graph Phase A — DEM sampling)

No params besides `--base-graph-dir`/`--dem`. Reads `dem.tif` and the base graph's
`nodes.npy`/`cell_index.npy`/`interior.npy`, writes `node_ele.npy`/`interior_ele.npy`.

Loops **per grid cell** (`lib/grid.py`), not per edge and never as one whole-raster window: reads
one windowed `dem.tif` slice per cell (buffered 0.2km for bilinear's 1-pixel neighbourhood), then
bilinear-samples every node/interior point that falls in that cell (`sample_bilinear()` — pixel
*centres*, not corners). Interior points carry no `cell_id` of their own, so their per-cell
grouping is computed here via `grid.cell_ids_for_points()` + `binfmt.build_csr_index()`, the same
CSR convention `nodes.npy` is already sorted by.

Split out from what used to be one `add_base_elevation.py` script specifically because this half
never reads `--smoothing-kernel-m` — see `compute_edge_profiles.py` below.

- **doit wiring**: `file_dep=[base_graph/manifest.json, dem.tif]`,
  `targets=[base_graph/node_ele.npy, base_graph/interior_ele.npy]`. No `TaskOptionsChanged` needed
  (no params to track).

## `compute_edge_profiles.py` (base-graph Phase B — per-edge smoothing/time_s/ascent-descent)

Params: `--smoothing-kernel-m` (default `config.dem.smoothingKernelM`). Reads
`node_ele.npy`/`interior_ele.npy` (Phase A's output) plus `nodes.npy`/`interior.npy`/`edges.npy`,
rewrites `edges.npy` in place with `time_s`/`ascent_m`/`descent_m` filled in.

Per base-graph edge (Python loop — smoothing is an inherently per-edge local operation, a global
vectorised pass would leak across edge boundaries): reconstructs the edge's full point sequence
(`u` → interior slice → `v`), smooths the elevation profile with a distance-weighted triangular
kernel (`smooth_profile()` — metres, not points, since point spacing varies ~7x across base
edges), and sums `time_s` from the smoothed profile (`lib/speed.py`'s `edge_time_s()`).
`ascent_m`/`descent_m` are filled afterwards in ONE vectorised batch call
(`edge_ascent_descent()` — plain signed-delta sums via `np.diff` + `np.bincount`, no threshold, no
hysteresis; `eleNoiseThresholdM` is retired, the kernel width is the replacement tunable) over
every edge's smoothed profile at once.

`edges.npy` can't be this task's declared `doit` target (`build_base_graph` already owns it, and
`doit` forbids two tasks sharing a target) — `base_graph/edge_profiles.stamp` is the completion
signal instead, same pattern `build_hub_edges` uses `node_ele.npy` for its `task_dep` on this task.

- **doit wiring**: `task_dep=[sample_base_elevation]`,
  `file_dep=[base_graph/node_ele.npy, base_graph/interior_ele.npy]`,
  `targets=[base_graph/edge_profiles.stamp]`, `uptodate=[TaskOptionsChanged()]` — a
  `--smoothing-kernel-m` retune reruns this task alone, never `sample_base_elevation`.

## Timing instrumentation

Every script under `phases/elevation/` uses `lib/timing.py`'s `phase(script, name, **meta)`
context manager to append one JSON line to `data/timings.jsonl` per completed phase (skipped on
exception, so a failed run never leaves a misleading partial record), plus `StepTimer` for the
sub-phase breakdown printed as a `step totals:` line at the end of each run. This is how the
`read_dem_window` regression (see `lib/pipeline.py`'s `materialize_geotiff()` docstring) and the
Copernicus-floor materialize slowdown (`build_dem_vrt.py`'s `materialize_geotiff` phase, 8462s on
2026-08-23) were actually caught and diagnosed with real numbers, rather than guessed at.
