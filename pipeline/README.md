# pipeline/

Offline precompute pipeline for the hut-to-hut trail graph. This directory (`pipeline.config.json`,
scripts, this file) is the tracked source; its raw/generated inputs and outputs live in the
sibling `data/` dir (`data/osm/`, `data/dem/`), which is entirely gitignored — regenerate it via
`doit` (see "Reproducing from scratch" below) rather than expecting it to be present after a fresh
clone. Rationale for the pipeline's design choices lives in `docs/osm-trail-pipeline.md`; this file
is the practical "how to reproduce it" index. For what each script actually does — data structures,
algorithms — see `phases/README.md` and each phase subdirectory's own `README.md`.

## Config

All hyperparameters live in one place: **`pipeline/pipeline.config.json`**.

```json
{
  "bbox": { "minLng": 8.9, "maxLng": 17.2, "minLat": 46.3, "maxLat": 50.6 },
  "regions": [
    { "name": "austria", "url": "https://download.geofabrik.de/europe/austria-latest.osm.pbf" },
    { "name": "bayern", "url": "https://download.geofabrik.de/europe/germany/bayern-latest.osm.pbf" }
  ],
  "trailTagFilter": "w/highway=path,footway,track,steps,residential,service,unclassified,tertiary",
  "graph": { "maxEdgeKm": 10, "maxSnapM": 200, "tileSizeKm": 60 },
  "dem": { "provider": "composite", "providerConfig": { "regions": [ ... ] }, "eleNoiseThresholdM": 4 },
  "trailTiles": { "minZoom": 6, "maxZoom": 14 }
}
```

(`dem.providerConfig.regions` elided above for brevity — see the `dem` bullet below and the real
`pipeline.config.json` for the full shape.)

- `bbox` — filters the ArcGIS hut pull (`fetch_huts.py`) to the pipeline's current scope.
- `regions` — one Geofabrik extract per entry; `download_extracts.py`/`filter_trails.py`/
  `merge_trails.py` loop over this list, so adding a region (e.g. Switzerland) is just adding
  `{ "name": "switzerland", "url": "..." }` here.
- `trailTagFilter` — the `osmium tags-filter` expression `filter_trails.py` applies.
- `graph.maxEdgeKm` / `graph.maxSnapM` — defaults for `build_hub_edges.py`'s `--max-edge-km` /
  `--max-snap-m`; still overridable per-run via those flags. What they actually control:
  - **`maxSnapM`** (meters, default 200) — how far a hub may be from the nearest OSM trail node
    to count as "on the trail network" at all. `build_hub_edges.py` snaps each hub to its closest
    trail node via a KDTree; if that nearest node is farther than `maxSnapM`, the hub is skipped
    entirely (no edges computed for it) rather than force-matched to a trail it isn't really on.
    Raising this includes more hubs (e.g. huts set back from the mapped path) at the cost of
    snapping some to a trail node that isn't really their access point.
  - **`maxEdgeKm`** (kilometers, default 10) — the longest hut-to-hut trail distance (walking
    distance along the graph, not beeline) that's kept as an edge. It's a deliberate cutoff, not
    just a performance knob: a hut-to-hut edge is meant to represent one day-hike leg, so anything
    longer should be multiple hops through intermediate huts, not one edge (see `docs/
    osm-trail-pipeline.md` for why). It also bounds the search — each hub's shortest-path query is
    capped at this distance, so raising it increases both edge count and runtime.
  - **`tileSizeKm`** (kilometers, default 60) — the cell size `build_hub_edges.py`'s `Grid`
    (`lib/grid.py`) partitions the bbox into; one worker process handles one cell, each mmap-
    slicing only its own padded region (cell + `maxEdgeKm` buffer) of the persisted base graph
    (`lib/subgraph.py`). 60km ≈ 2× `maxEdgeKm`, giving each tile a core-to-buffer area ratio that
    keeps per-tile work non-trivial relative to the fixed buffer overhead. Also read by
    `build_base_graph.py`, which assigns every graph node to a cell at write time so
    `build_hub_edges.py` can look cells up identically at query time.
- `dem` — inputs to the elevation pass (`fetch_dem.py`/`build_dem_vrt.py`/`add_elevation.py`):
  - **`provider`** / **`providerConfig`** — which DEM source `fetch_dem.py` fetches from, and that
    provider's own config. Registered providers (`pipeline/phases/downloads/dem_providers/`):
    - **`copernicus-glo-30`** — global 30m coverage (AWS Open Data, no auth). `providerConfig: {}`
      (uses the top-level `bbox`). The safe default; systematically underestimates ascent/descent
      on switchback-heavy alpine trails because 30m can't resolve terrain that narrow (see
      `docs/osm-trail-pipeline.md`).
    - **`at-bev-dgm`** — Austria's national 10m DGM (data.gv.at, CC-BY-4.0, Lambert/EPSG:31287).
      `providerConfig: {"downloadUrl": "<confirmed direct .zip URL>"}` — single ~1.9GB national
      file, not tiled, so `bbox` in its config is unused metadata.
    - **`bavaria-dgm5`** — Bavaria's 5m DGM (geodaten.bayern.de, CC BY 4.0, UTM32N/EPSG:25832),
      served as one small (~200KB) direct-download zip per 1km tile; tile IDs are computed from
      `providerConfig.bbox` (no tile-index file needed), so keeping that bbox tight matters: see
      `bboxFromHuts` below.
    - **`composite`** — meta-provider stitching per-sub-region VRTs from *different* providers
      into one final `dem.vrt` (e.g. Austria via `at-bev-dgm`, Bavaria via `bavaria-dgm5`).
      `providerConfig: {"regions": [{"provider": "...", "bbox": {...}, ...that provider's own
      config keys}, ...]}`. Region order matters where two regions' bboxes overlap —
      `gdalbuildvrt` keeps the first-listed source's pixels.
  - **`bboxFromHuts`** (per-region, `composite` only, default false) — a region's `bbox` is
    normally just a coarse political-boundary filter used to pick out which huts belong to that
    region (`data/osm/huts.geojson` covers the pipeline's *whole* scope, both countries). Setting
    `bboxFromHuts: true` tightens the box actually fetched down to those huts' real extent (+
    `bufferDeg`, default 0.05°) instead of the full political box — matters for request-per-tile
    providers like `bavaria-dgm5`, whose full state bbox is ~80,000 1km tiles even though huts
    only exist in the southern Alpine strip near the Austrian border.
  - **`eleNoiseThresholdM`** (meters, default 2) — `add_elevation.py`'s threshold-hysteresis
    cutoff: a direction change only counts toward ascent/descent once cumulative drift since the
    last counted point exceeds this, so per-sample DEM noise doesn't inflate totals. Lower = more
    sensitive to real short climbs but noisier; higher = smoother but can flatten genuinely short
    steep sections. Still overridable per-run via `--ele-noise-threshold-m`.
- `trailTiles.minZoom` / `trailTiles.maxZoom` — defaults for `build_trail_tiles.py`'s `--min-zoom`
  / `--max-zoom`, the zoom range `tippecanoe` builds vector tiles for. Below `minZoom` the layer
  just isn't rendered; above `maxZoom` Leaflet oversamples the highest tile that exists (standard
  vector-tile overzoom), so raising `maxZoom` mainly costs build time/tile count, not correctness.

Every script reads this file (via `pipeline/lib/pipeline.py`'s `load_config()`) instead of
hardcoding these values — change the config, not the scripts.

## Setup: the `alpen-osm` conda env

The pipeline needs a real `osmium-tool` binary (`tags-filter`/`merge`/`fileinfo`) plus a handful
of Python packages with native extensions (`pyosmium`, `scipy`, `numpy`, `python-igraph`). None of
that is on PyPI in CLI form, so it's a conda-forge env, not `pip`/`uv`. `psutil` is in the
list too: `lib/memtrace.py` imports it at module level and `build_base_graph.py` imports
memtrace, so an env without it fails the phase at import time, not at first use.

```bash
conda create -n alpen-osm -c conda-forge \
  python=3.11 osmium-tool pyosmium scipy numpy python-igraph gdal rasterio orjson psutil
conda activate alpen-osm
osmium --version   # sanity check: should print "osmium version ..."
pip install pmtiles doit   # pmtiles + doit aren't on conda-forge
```

`tippecanoe` (needed by `build_trail_tiles.py`/`build_edge_tiles.py`) has no Windows build on
conda-forge — only linux-64/osx-64. On Windows, set up a one-time WSL micromamba env instead:

```bash
# inside WSL
curl -sSL -o micromamba.tar.bz2 "https://micro.mamba.pm/api/micromamba/linux-64/latest"
mkdir -p mm && tar -xjf micromamba.tar.bz2 -C mm
./mm/bin/micromamba create -y -r ~/micromamba -n tippecanoe -c conda-forge tippecanoe
```

`build_trail_tiles.py` detects Windows and falls back to invoking `tippecanoe` through WSL
automatically (`lib.pipeline.run_tippecanoe()`) — see `phases/postprocessing/README.md` for how.
On Linux/macOS, just `conda install -c conda-forge tippecanoe` into `alpen-osm` and skip this.

## Reproducing from scratch

The pipeline is orchestrated by [doit](https://pydoit.org) — `pipeline/dodo.py` declares one task
per script, wired by `file_dep`/`targets` (doit derives run order and staleness from that graph).

```bash
conda activate alpen-osm
doit                                    # run everything that's stale, in dependency order
doit build_base_graph build_hub_edges   # run just these tasks (+ stale deps)
doit build_base_graph --tile-size-km 60 # override a task's own param
doit list                               # see every task + up-to-date status
doit info <task>                        # see why a task would (not) run
```

`doit` skips any task whose `targets` already exist and whose `file_dep` (including
`pipeline.config.json`) haven't changed. Delete an output file (or edit the config) to force that
task and everything downstream to rerun. `add_elevation` always reruns when selected (cheap,
~90-100s — usually run to retune `--ele-noise-threshold-m`). `build_base_graph`/`build_hub_edges`
are freshness-checked normally (`build_base_graph` alone measured ~4.1h — see `pipeline/CLAUDE.md`
for why you must ask before running it), but still pick up a changed `--tile-size-km`/
`--max-edge-km`/`--max-snap-m` automatically.

`doit copy_public_data` (included in the default run) copies every output the app reads into
`huts/public/data/` — run it alone to re-sync after hand-running individual scripts.

## Rejected: buffer-clip + OSMnx

An earlier version of graph-building buffered every hut by a radius, unioned the buffers, and
clipped `trails.osm.pbf` to that polygon before loading it into NetworkX/OSMnx — the idea being to
shrink the graph enough to fit in memory. It didn't work: Alpine huts are packed densely enough
that even a 15km buffer only cut node count in half (26.5M → 13.5M), still too large to load. The
actual problem was never the input size — it was NetworkX/OSMnx's per-node/edge Python object
overhead (dict-of-dicts + shapely geometry per edge). Shrinking the *area* never fixed that. Those
scripts have been removed; `build_base_graph.py`/`build_hub_edges.py` (see
`phases/graph_building/README.md`) replaced the whole approach — full design rationale in
`docs/superpowers/specs/2026-08-19-pipeline-v2-design.md`.
