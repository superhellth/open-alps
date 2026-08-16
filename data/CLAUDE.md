# data/ — hut-to-hut routing graph pipeline

A hut-to-hut trail graph (nodes = huts, edges = real trail paths/distances) so route planning
isn't limited to the Alpenverein's 26 predefined tours (`toursearchApi` /
`AVT_CAA_TOUR_View_L`, see `docs/alpenverein-api.md` §3). Edges are derived from OSM hiking ways,
not the Alpenverein data.

This is entirely an offline precompute pipeline living under `data/` — it doesn't change the
app's backend-free architecture; outputs are static files (GeoJSON + PMTiles vector tiles), hand-
copied into `huts/public/data/` for the app to fetch (see the root `CLAUDE.md`'s "App structure").
Full reproduction steps and scripts: **`data/README.md`**. Design rationale for the OSM
extract/filter/merge steps: **`docs/osm-trail-pipeline.md`**.

Pipeline is plain Python, no bash/Node/Docker: config-driven — every hyperparameter (region list,
hut bbox, trail tag filter, max-edge-km / max-snap-m, DEM provider) lives in
`data/pipeline.config.json` — and `data/scripts/run_all.py` runs all 11 steps end to end,
idempotently (skips a step whose output is newer than the config, unless named via `--only`),
inside the `alpen-osm` conda env (see `data/README.md` "Setup" for how that env was created — via
`micromamba`, not `conda create`, since this machine's `base` conda env hangs solving
`-c conda-forge` specs). Current status: built and up to date for Austria+Bavaria, outputs
hand-copied into `huts/public/data/` and rendered by the app (`GraphPage.jsx`'s `#graph` route
for the raw network, `App.jsx` for stations/parking) — see the root `CLAUDE.md`'s "App structure"
section. Not done: extending scope past AT+Bayern, and automating the hand-copy into a build step.

## Timing pipeline phases

`data/scripts/lib/timing.py`'s `phase(script, name, **meta)` context manager appends one JSON
line to `data/timings.jsonl` per completed phase (`{ts, script, phase, seconds, meta?}`) — skipped
entirely if the block raises, so a failed run never leaves a misleading partial record. Used by
`run_all.py` (one record per step, keyed `"NN-<step name>"`), and internally by the two steps
expensive enough to want phase-level breakdown: `06-build-hut-graph.py` (`stream_osm`,
`build_igraph`, `build_kdtree`, `connected_components`, `pass1_distances`, `pass2_paths`) and
`08-add-elevation.py` (`read_dem_window`, `per_edge_ascent_profile`). This exists because scope is
expected to grow past AT+Bayern — `timings.jsonl` is the real-numbers record for seeing which
phase stops scaling first, instead of guessing. Wrap a new expensive block in `with
phase(SCRIPT_NAME, "phase_name", **any_size_metadata):` rather than ad hoc `print`/`time.time()`
timing to keep it queryable the same way.
