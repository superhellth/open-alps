# phases/elevation/ — DEM mosaic + ascent/descent/profiles

Turns a raw elevation raster into a single sampleable GeoTIFF, then samples it along every edge
polyline `graph_building/build_hub_edges.py` computed, filling in the `ascent_m`/`descent_m`/
`profile_*` fields that were left `UNSET` there.

## `build_dem_vrt.py`

- Reads `data/dem/fetch_manifest.json` (written by `phases/downloads/fetch_dem.py`).
- For each manifest region, calls that region's provider's `to_4326_vrt(tile_paths, region_vrt)`
  (reprojects into EPSG:4326), then `lib/pipeline.py`'s `normalize_colorinterp()` (forces
  `ColorInterp=Gray` on every region VRT so a mismatched interpretation isn't silently dropped by
  the final merge), then merges all region VRTs with `gdalbuildvrt -overwrite dem.vrt
  <region_vrts...>`.
- **`materialize_geotiff`** step: bakes the (lazily-reprojecting) `dem.vrt` into a real,
  tiled/DEFLATE-compressed `dem.tif` via `gdal_translate` (`PREDICTOR=3`, `-a_nodata` copied
  explicitly). This exists because reading `dem.vrt` directly re-runs per-pixel reprojection on
  *every* read — measured ~750s for one AT+Bavaria window (`data/timings.jsonl`) — so
  materializing once here means `add_elevation.py` (rerun often, to retune the noise threshold)
  never re-pays that cost.
- **doit wiring**: `file_dep=[fetch_manifest.json]`, `targets=[dem.vrt, dem.tif]`.

## `add_elevation.py` — always reruns when selected (`uptodate: [False]`; cheap, ~90–100s)

Params: `--ele-noise-threshold-m` (default `config.dem.eleNoiseThresholdM`), `--profile-points`
(default `config.dem.profilePoints`, 30).

Processes `data/osm/hut_edges/` and `data/osm/start_edges/` together in one run, each via
`_process_edge_set()`: reads that edge set's `records.npy`/`geometry.npy`, samples the DEM, writes
back updated `records.npy` plus a new `profiles.npy`.

**`read_dem_window` step**: opens `dem.tif`, computes row/col indices directly from the raster's
affine transform (rasterio's `rowcol()` crashes on arrays with more than one element on this
build), reads just the bounding window covering all of this edge set's vertices — not the whole
multi-GB mosaic — and fancy-indexes every sample point out of that one window read.

**`per_edge_ascent_profile` step**, per edge (`fill_elevation_records()` — a pure function
decoupled from the `rasterio` DEM I/O above, so it's directly unit-testable without a raster
fixture):

- **`ascent_descent()`** — a threshold-hysteresis filter over the per-vertex elevation samples: a
  direction change (ascending→descending or vice versa) is only counted once cumulative drift
  since the *last counted* turning point exceeds `--ele-noise-threshold-m`. Without this, raw
  per-sample DEM noise (a few meters of jitter between adjacent pixels) would register as
  thousands of spurious micro up/down segments and massively inflate total ascent/descent.
- **`elevation_profile()`** — downsamples the (irregularly spaced, per-vertex) DEM samples to a
  fixed `--profile-points` count, evenly spaced by *cumulative trail distance* (`np.interp`),
  skipping nodata samples. Produces a fixed-size series regardless of the source polyline's
  original vertex density, so every edge's profile is directly comparable/plottable without
  per-edge-length-aware UI code.
- Fills each record's `ascent_m`, `descent_m`, `profile_offset`, `profile_count`, and appends the
  profile's sampled values to a new packed `profiles.npy` (`binfmt.PROFILE_DTYPE = f4`), sliced
  per-edge the same offset/count way as `geometry.npy`.

- **doit wiring**: `task_dep=[build_hub_edges]` (same-file dependency, not just mtime),
  `file_dep=[dem.tif]`, `targets=[hut_edges/records.npy, hut_edges/profiles.npy,
  start_edges/records.npy, start_edges/profiles.npy]`.

## Timing instrumentation

Both scripts use `lib/timing.py`'s `phase(script, name, **meta)` context manager to append one
JSON line to `data/timings.jsonl` per completed phase (skipped on exception, so a failed run never
leaves a misleading partial record) — `build_dem_vrt.py`'s `materialize_geotiff` and
`add_elevation.py`'s `read_dem_window`/`per_edge_ascent_profile` are wrapped this way. This is how
the `read_dem_window` regression above was actually caught and fixed, rather than guessed at.
