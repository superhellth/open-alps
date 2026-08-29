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
  "trailTagFilter": "w/highway=path,footway,track,steps,residential,service,unclassified,tertiary,via_ferrata",
  "graph": {
    "maxEdgeKm": 30, "maxSnapM": 100, "maxSnapAscentM": 25,
    "roadHighwayTags": ["residential", "service", "unclassified", "tertiary"],
    "tileSizeKm": 60,
    "speedModel": { "v0": 4.013, "k": 3.5, "s0": 0.05 },
    "variants": ["FAST_ANY", "FAST_T2", "FAST_T3", "FAST_T3_UNGRADED"]
  },
  "dem": { "providerConfig": { "regions": [ ... ] }, "smoothingKernelM": 30, "profilePoints": 30 },
  "approach": { "k": 3 },
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
- `graph.maxEdgeKm` / `graph.maxSnapM` / `graph.maxSnapAscentM` — defaults for
  `build_hub_edges.py`'s `--max-edge-km` / `--max-snap-m` / `--max-snap-ascent-m`; still
  overridable per-run via those flags. What they actually control:
  - **`maxSnapM`** (meters, default 100) — how far a hub may be from the nearest OSM trail node
    to count as "on the trail network" at all. `build_hub_edges.py` snaps each hub to its closest
    trail node via a KDTree; if that nearest node is farther than `maxSnapM`, the hub is skipped
    entirely (no edges computed for it) rather than force-matched to a trail it isn't really on.
    Raising this includes more hubs (e.g. huts set back from the mapped path) at the cost of
    snapping some to a trail node that isn't really their access point.
  - **`maxSnapAscentM`** (meters, default 25) — a second, vertical check on top of `maxSnapM`'s
    horizontal one: a candidate snap point is also rejected if it sits more than this far above or
    below the hub's own DEM elevation, since a horizontally-close trail node can still be on a
    different terrace/switchback. Every rejection is reported, not silently dropped — see
    `unsnapped_huts.json`.
  - **`maxEdgeKm`** (kilometers, default 30) — the longest hut-to-hut trail distance (walking
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
  - **`speedModel`** (`{v0, k, s0}`) — the pointwise Tobler-shaped routing weight
    (`lib/speed.py`'s `edge_time_s()`), calibrated against DIN 33466 by
    `analysis/routing_probe.py`, not inherited as-is from the textbook Tobler constants. Read
    directly by `compute_edge_profiles.py`; every value here is its own tracked `dodo.py` param
    (`--speed-v0`/`--speed-k`/`--speed-s0`) so a retune reruns that task.
  - **`variants`** — the `graph.variants` row list `build_hub_edges.py` routes
    (`lib/variants.py`), e.g. `["FAST_ANY", "FAST_T2", "FAST_T3", "FAST_T3_UNGRADED"]`. Tracked as
    a tracking-only `dodo.py` param (`variants_json`, no CLI flag) so a grid edit is seen even
    though the script reads this straight from config.
- `approach.k` — how many best approach edges `build_approach_table.py` keeps per hut (see
  `phases/postprocessing/README.md`).
- `dem` — inputs to the elevation pass (`fetch_dem.py`/`build_dem_vrt.py`/
  `sample_base_elevation.py`/`compute_edge_profiles.py`):
  - **`providerConfig.regions`** — `fetch_dem.py` always fetches through the `composite`
    meta-provider (`dem_providers/composite.py`), which resolves each configured region's own
    provider and stitches their per-region VRTs into one final `dem.vrt` — even a one-region scope
    is just `regions` with a single entry, so there's no separate single-provider code path or
    config field. Region order matters where two regions' bboxes overlap — see `composite.py`'s
    own docstring for which one wins. Each region is `{"provider": "...", "bbox": {...}, ...that
    provider's own config keys}`. Registered providers (`pipeline/phases/downloads/dem_providers/`):
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
  - **`bboxFromHuts`** (per-region, `composite` only, default false) — a region's `bbox` is
    normally just a coarse political-boundary filter used to pick out which huts belong to that
    region (`data/osm/huts.geojson` covers the pipeline's *whole* scope, both countries). Setting
    `bboxFromHuts: true` tightens the box actually fetched down to those huts' real extent (+
    `bufferDeg`, default 0.05°) instead of the full political box — matters for request-per-tile
    providers like `bavaria-dgm5`, whose full state bbox is ~80,000 1km tiles even though huts
    only exist in the southern Alpine strip near the Austrian border.
  - **`smoothingKernelM`** (meters, default 30) — `compute_edge_profiles.py`'s
    distance-weighted triangular smoothing kernel width applied to each base edge's elevation
    profile before summing `ascent_m`/`descent_m` as plain signed-delta sums. Replaces the old
    `eleNoiseThresholdM` threshold-hysteresis cutoff (retired — no threshold, no hysteresis loop
    any more): metres, not points, since point spacing varies ~7x across base edges. Lower = more
    sensitive to real short climbs but noisier; higher = smoother but can flatten genuinely short
    steep sections. Still overridable per-run via `--smoothing-kernel-m`.
  - **`profilePoints`** (default 30) — how many evenly-spaced distance points
    `build_profiles.py` interpolates each record's display elevation profile onto. Cheap to retune
    (seconds, never reopens the DEM) — see `phases/elevation/README.md`.
- `trailTiles.minZoom` / `trailTiles.maxZoom` — defaults for `build_trail_tiles.py`'s `--min-zoom`
  / `--max-zoom`, the zoom range `tippecanoe` builds vector tiles for. Below `minZoom` the layer
  just isn't rendered; above `maxZoom` Leaflet oversamples the highest tile that exists (standard
  vector-tile overzoom), so raising `maxZoom` mainly costs build time/tile count, not correctness.

Every script reads this file (via `pipeline/lib/pipeline.py`'s `load_config()`) instead of
hardcoding these values — change the config, not the scripts.

## Setup: the `alpen-osm` pixi env

The pipeline needs a real `osmium-tool` binary (`tags-filter`/`merge`/`fileinfo`) plus a handful
of Python packages with native extensions (`pyosmium`, `scipy`, `numpy`, `python-igraph`). None of
that is on PyPI in CLI form, so it's a conda-forge env, managed here via
[pixi](https://pixi.sh) rather than `pip`/`uv`. `pixi.toml` (this directory) is the tracked
manifest — its dependency list plus `pixi.lock` (also tracked) is the whole env spec, so
`pixi install` reproduces exactly the same env everyone else has, not just "python=3.11 and
whatever conda-forge resolves today." `psutil` is in the list too: `lib/memtrace.py` imports it
at module level and `build_base_graph.py` imports memtrace, so an env without it fails the phase
at import time, not at first use.

```bash
curl -fsSL https://pixi.sh/install.sh | sh   # one-time, installs the pixi CLI itself
cd pipeline
pixi install                                  # reads pixi.toml/pixi.lock, builds the env
pixi run osmium --version   # sanity check: should print "osmium version ..."
```

`pixi run <cmd>` runs `<cmd>` inside the env without a separate activate step (`pixi shell` drops
you into an activated shell instead, if you'd rather not prefix every command). `tippecanoe`
(needed by `build_trail_tiles.py`/`build_edge_tiles.py`) is in `pixi.toml`'s dependency list too —
it has conda-forge builds for linux-64/osx-64/osx-arm64 (this project's `pixi.toml` only declares
those platforms), so on Linux, macOS, or WSL it's just another package in the same env, no extra
step. It has **no Windows conda-forge build**, so native Windows (not WSL) isn't a supported pixi
platform here — set up a one-time WSL micromamba env just for `tippecanoe` instead:

```bash
# inside WSL
curl -sSL -o micromamba.tar.bz2 "https://micro.mamba.pm/api/micromamba/linux-64/latest"
mkdir -p mm && tar -xjf micromamba.tar.bz2 -C mm
./mm/bin/micromamba create -y -r ~/micromamba -n tippecanoe -c conda-forge tippecanoe
```

`build_trail_tiles.py` detects Windows and falls back to invoking `tippecanoe` through WSL
automatically (`lib.pipeline.run_tippecanoe()`) — see `phases/postprocessing/README.md` for how.
If you're already working from inside WSL (as this setup is), ignore the Windows path entirely —
`pixi install` above covers `tippecanoe` too.

## Reproducing from scratch

The pipeline is orchestrated by [doit](https://pydoit.org) — one task per script, wired by
`file_dep`/`targets` (doit derives run order and staleness from that graph). Task wiring lives in
`pipeline/dag/` (one module per `phases/` subdirectory); `pipeline/dodo.py` just assembles them
plus the pipeline-wide `copy_public_data` finalize step.

```bash
pixi run doit                                    # run everything that's stale, in dependency order
pixi run doit build_base_graph build_hub_edges   # run just these tasks (+ stale deps)
pixi run doit build_base_graph --tile-size-km 60 # override a task's own param
pixi run doit list                               # see every task + up-to-date status
pixi run doit info <task>                        # see why a task would (not) run
```

(Or `pixi shell` once, then drop the `pixi run` prefix for the rest of the session.)

`doit` skips any task whose `targets` already exist and whose own tracked params (each task's
`TaskOptionsChanged()` check, `lib/doit_support.py`) haven't changed since its last successful run — not a
whole-config-file hash, so an edit to an unrelated `pipeline.config.json` key doesn't invalidate
every task downstream of it. `build_profiles` always reruns when selected (cheap, seconds — never
reopens the DEM, usually run to retune `--profile-points`). `build_base_graph`/`build_hub_edges`
are freshness-checked normally (`build_base_graph` alone measured ~4.1h — see `pipeline/CLAUDE.md`
for why you must ask before running it), but still pick up a changed `--tile-size-km`/
`--max-edge-km`/`--max-snap-m`/`--max-snap-ascent-m`, a `graph.variants` grid edit, or a bumped
`binfmt.SCHEMA_VERSION` automatically. `sample_base_elevation`/`compute_edge_profiles` are the
elevation-pass split of the old `add_elevation` — freshness-checked the same way, with
`compute_edge_profiles` also tracking every `speedModel` constant so a routing-probe recalibration
reruns it.

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
