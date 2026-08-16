# pipeline/

Offline precompute pipeline for the hut-to-hut trail graph. This directory (`pipeline.config.json`,
scripts, this file) is the tracked source; its raw/generated inputs and outputs live in the
sibling `data/` dir (`data/osm/`, `data/dem/`), which is entirely gitignored — regenerate it via
`pipeline/run_all.py` rather than expecting it to be present after a fresh clone. Rationale for the
pipeline's design choices lives in `docs/osm-trail-pipeline.md`; this file is the practical "how to
reproduce it" index.

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
  "graph": { "maxEdgeKm": 10, "maxSnapM": 200 },
  "dem": { "provider": "composite", "providerConfig": { "regions": [ ... ] }, "eleNoiseThresholdM": 4 },
  "trailTiles": { "minZoom": 6, "maxZoom": 14 }
}
```

(`dem.providerConfig.regions` elided above for brevity — see the `dem` bullet below and the real
`pipeline.config.json` for the full shape.)

- `bbox` — filters the ArcGIS hut pull (script 05) to the pipeline's current scope.
- `regions` — one Geofabrik extract per entry; scripts 01-03 loop over this list, so adding a
  region (e.g. Switzerland) is just adding `{ "name": "switzerland", "url": "..." }` here.
- `trailTagFilter` — the `osmium tags-filter` expression script 02 applies.
- `graph.maxEdgeKm` / `graph.maxSnapM` — defaults for script 06's `--max-edge-km` /
  `--max-snap-m`; still overridable per-run via those flags. What they actually control:
  - **`maxSnapM`** (meters, default 200) — how far a hut may be from the nearest OSM trail node
    to count as "on the trail network" at all. Script 06 snaps each hut to its closest trail node
    via a KDTree; if that nearest node is farther than `maxSnapM`, the hut is skipped entirely
    (no edges computed for it) rather than force-matched to a trail it isn't really on. Raising
    this includes more huts (e.g. ones set back from the mapped path) at the cost of snapping some
    to a trail node that isn't really their access point.
  - **`maxEdgeKm`** (kilometers, default 10) — the longest hut-to-hut trail distance (walking
    distance along the graph, not beeline) that's kept as an edge. It's a deliberate cutoff, not
    just a performance knob: a hut-to-hut edge is meant to represent one day-hike leg, so anything
    longer should be multiple hops through intermediate huts, not one edge (see `docs/
    osm-trail-pipeline.md` for why). It also bounds the search — each hut's shortest-path query is
    capped at this distance, and candidate huts beyond `3 × maxEdgeKm` beeline are never queried at
    all, so raising it increases both edge count and runtime.
- `dem` — inputs to step 07/08's elevation pass:
  - **`source`** — vestigial, no longer read by any script; `provider` is what actually selects
    the DEM source now (kept only so old configs don't error on an unrecognized key).
  - **`provider`** / **`providerConfig`** — which DEM source step 07 fetches from, and that
    provider's own config. Every provider implements the contract in
    `pipeline/dem_providers/base.py` (`fetch()` + `to_4326_vrt()`); `07-fetch-dem.py` is a
    thin dispatcher over `dem_providers.get_provider(name)` that only calls `fetch()` and writes
    `data/dem/fetch_manifest.json` — `07b-build-dem-vrt.py` reads that manifest and calls
    `to_4326_vrt()` + materializes `dem.tif`, with no network access of its own, so retuning a
    provider's reprojection (e.g. a NoData-handling fix) is a rerun of 07b alone, never a
    re-fetch. Registered providers:
    - **`copernicus-glo-30`** — global 30m coverage (AWS Open Data, no auth). `providerConfig: {}`
      (uses the top-level `bbox`). The safe default; systematically underestimates ascent/descent
      on switchback-heavy alpine trails because 30m can't resolve terrain that narrow (see
      `docs/osm-trail-pipeline.md`).
    - **`at-bev-dgm`** — Austria's national 10m DGM (data.gv.at, CC-BY-4.0, Lambert/EPSG:31287).
      `providerConfig: {"downloadUrl": "<confirmed direct .zip URL>"}` — single ~1.9GB national
      file, not tiled, so `bbox` in its config is unused metadata (the whole file downloads
      regardless).
    - **`bavaria-dgm5`** — Bavaria's 5m DGM (geodaten.bayern.de, CC BY 4.0, UTM32N/EPSG:25832),
      served as one small (~200KB) direct-download zip per 1km tile
      (`https://download1.bayernwolke.de/a/dgm/dgm5xyz/{easting_km}_{northing_km}.zip`) - tile IDs
      are computed from `providerConfig.bbox` (no tile-index file needed), so keeping that bbox
      tight matters: see `bboxFromHuts` below.
    - **`composite`** — meta-provider stitching per-sub-region VRTs from *different* providers
      into one final `dem.vrt` (e.g. Austria via `at-bev-dgm`, Bavaria via `bavaria-dgm5`).
      `providerConfig: {"regions": [{"provider": "...", "bbox": {...}, ...that provider's own
      config keys}, ...]}`. Region order matters where two regions' bboxes overlap -
      `gdalbuildvrt` keeps the first-listed source's pixels.
  - **`bboxFromHuts`** (per-region, `composite` only, default false) — a region's `bbox` is
    normally just a coarse political-boundary filter used to pick out which huts belong to that
    region (`data/osm/huts.geojson` covers the pipeline's *whole* scope, both countries). Setting
    `bboxFromHuts: true` tightens the box actually fetched down to those huts' real extent (+
    `bufferDeg`, default 0.05°) instead of the full political box. This matters for
    request-per-tile providers like `bavaria-dgm5`: Bavaria's full state bbox is ~80,000 1km
    tiles, but huts only exist in the southern Alpine strip near the Austrian border - deriving
    the fetch bbox from actual hut locations (`lib/pipeline.py`'s `bbox_from_huts`) cuts that down
    to only the area the pipeline actually needs, without hand-tuning a smaller political box that
    would go stale as huts are added/removed. Providers whose `fetch()` ignores `bbox` entirely
    (e.g. `at-bev-dgm`'s single national file) are unaffected either way.
  - **`eleNoiseThresholdM`** (meters, default 2) — step 08's threshold-hysteresis cutoff: a
    direction change only counts toward ascent/descent once cumulative drift since the last
    counted point exceeds this, so per-sample DEM noise doesn't inflate totals. Lower = more
    sensitive to real short climbs but noisier; higher = smoother but can flatten genuinely short
    steep sections. Still overridable per-run via step 08's `--ele-noise-threshold-m`.
- `trailTiles.minZoom` / `trailTiles.maxZoom` — defaults for step 09's `--min-zoom` / `--max-zoom`,
  the zoom range `tippecanoe` builds vector tiles for. Below `minZoom` the layer just isn't
  rendered; above `maxZoom` Leaflet oversamples the highest tile that exists (standard vector-tile
  overzoom), so raising `maxZoom` mainly costs build time/tile count, not correctness.

Every script reads this file (via `pipeline/lib/pipeline.py`'s `load_config()`) instead of
hardcoding these values — change the config, not the scripts.

## Layout

```
pipeline/                          # tracked source
  pipeline.config.json            # single source of truth for hyperparameters, above
  lib/pipeline.py                  # shared config reader + path constants
  run_all.py                       # runs everything below in order, idempotently
  01-11                            # individual steps, in run order — plain Python scripts
data/                               # gitignored raw/generated inputs+outputs, regenerated by the above
  osm/
    raw/
      <region>-latest.osm.pbf     # untouched Geofabrik download, one per pipeline.config.json region
    <region>-trails.osm.pbf       # filtered to hiking ways (script 02), one per region
    trails.osm.pbf                # merged hiking network across all regions (script 03)
    huts.geojson                  # hut points in scope, from ArcGIS (script 05)
    hut-edges.geojson             # derived hut-to-hut trail edges (script 06), gains
                                   # ascent_m/descent_m properties per feature after script 08
    trails.pmtiles                 # raw trail network as static vector tiles (script 09)
  dem/
    raw/
      <TileName>.tif               # untouched Copernicus GLO-30 tiles, one per bbox degree cell
    dem.vrt                        # GDAL mosaic index over raw/ (script 07) - lazily reprojecting,
                                    # not read directly by script 08 (see dem.tif)
    dem.tif                        # dem.vrt materialized into a real, tiled/compressed GeoTIFF
                                    # (script 07) - this is what script 08 actually samples, so
                                    # reruns of 08 (e.g. to retune --ele-noise-threshold-m) don't
                                    # keep re-paying dem.vrt's reprojection cost
```

Everything is plain Python (stdlib `urllib`/`subprocess` + the `osmium`/`scipy`/`numpy`/`igraph`/
`rasterio`/GDAL libs) — no bash, no Node, no Docker. `osmium-tool` (the CLI, called via
`subprocess`) and `pyosmium` (the Python bindings, imported directly in script 06) are two
different packages that happen to share a name upstream; both come from the conda env below, as
is `gdalbuildvrt` (the CLI script 07 shells out to) and `rasterio` (script 08's DEM reader).

## Setup: the `alpen-osm` conda env

The pipeline needs a real `osmium-tool` binary (`tags-filter`/`merge`/`fileinfo`) plus a handful
of Python packages with native extensions (`pyosmium`, `scipy`, `numpy`, `python-igraph`). None of
that is on PyPI in CLI form, so it's a conda-forge env, not `pip`/`uv`.

**Use `micromamba` to create it, not `conda create` directly.** This machine's `base` conda env
only has `defaults` in its channel list (`conda config --show channels`); solving a `-c
conda-forge` spec against that with conda's classic solver cross-checks builds across both
channels and can hang for 10+ minutes or spin forever in "Solving environment" / "retrying with
next repodata source". `micromamba` is a fast, standalone solver binary — no install step, no
touching your existing conda setup — that solves the same spec in seconds.

```bash
# one-time: fetch the micromamba binary (~4.5MB, no install)
curl -sSL -o micromamba.tar.bz2 "https://micro.mamba.pm/api/micromamba/win-64/latest"
mkdir mm && tar -xjf micromamba.tar.bz2 -C mm
# mm/Library/bin/micromamba.exe is now a standalone executable

# create the env inside your existing conda envs dir, so `conda activate` finds it too
mm/Library/bin/micromamba.exe create -y -r "$CONDA_ROOT" -n alpen-osm -c conda-forge \
  python=3.11 osmium-tool pyosmium scipy numpy python-igraph gdal rasterio orjson
```

(`$CONDA_ROOT` is wherever your miniconda/anaconda lives, e.g. `C:/Users/<you>/miniconda3` —
same value `conda info` reports as "base environment".)

`tippecanoe` is **not** installable into this env — conda-forge only ships it for linux-64/osx-64,
not win-64. Step 09 needs it separately; see "Displaying the raw OSM trails" below for how that's
set up on Windows (a WSL micromamba env, one-time).

Once created, use it like any normal conda env — `micromamba` was only needed to get past the
solve; the env itself is a regular conda env with no lingering micromamba dependency:

```bash
conda activate alpen-osm
osmium --version   # sanity check: should print "osmium version ..."
```

Step 09 also needs the `pmtiles` package, which isn't on conda-forge — install it with `pip`
inside the same env (fine to mix; only the packages with native extensions above need conda). It
has no CLI despite the name, script 09 imports `pmtiles.convert.mbtiles_to_pmtiles` directly:

```bash
conda activate alpen-osm
pip install pmtiles
```

## Reproducing from scratch

```bash
conda activate alpen-osm
python pipeline/run_all.py
```

Runs steps 01-09 in order, skipping any step whose output already exists and is newer than
`pipeline.config.json`. Delete an output file (or edit the config, which invalidates everything
downstream of it) to force a rebuild. Steps 06 and 08 always run when selected (cheap, and
usually run precisely to pick up a new hyperparameter) rather than being freshness-checked.

Run a subset with `--only` (comma list and/or ranges) — steps passed this way always run,
skipping the freshness check, since naming a step explicitly means you want it to run now:

```bash
python pipeline/run_all.py --only 6           # just rebuild the graph
python pipeline/run_all.py --only 5,6          # re-fetch huts + rebuild graph
python pipeline/run_all.py --only 3-6          # merge onward
python pipeline/run_all.py --only 7,8          # DEM + elevation only
python pipeline/run_all.py --only 9            # just rebuild the raw-trail vector tiles
```

Args after a literal `--` are passed through to script 06, e.g. to sweep `--max-edge-km` without
re-running anything upstream:

```bash
python pipeline/run_all.py --only 6 -- --max-edge-km 15
```

Step 08's own flag (`--ele-noise-threshold-m`) isn't forwarded through `run_all.py`'s `--`
passthrough (that's reserved for script 06) — run it directly for that:

```bash
python pipeline/08-add-elevation.py --ele-noise-threshold-m 3
```

To run a single step by hand (e.g. while tuning a script), invoke it directly — each one is still
a plain, independently runnable script (all from within the `alpen-osm` env):

```bash
python pipeline/01-download-extracts.py      # ~1.6GB, Geofabrik extracts from pipeline.config.json
python pipeline/02-filter-trails.py           # -> ~264MB combined, hiking ways only
python pipeline/03-merge-trails.py            # -> data/osm/trails.osm.pbf
python pipeline/04-verify-trails.py           # gate: fails if trails.osm.pbf is missing/empty

python pipeline/05-fetch-huts.py              # -> data/osm/huts.geojson

python pipeline/06-build-hut-graph.py         # -> data/osm/hut-edges.geojson

python pipeline/07-fetch-dem.py               # -> data/dem/fetch_manifest.json, via dem.provider (see Config)
python pipeline/07b-build-dem-vrt.py          # -> data/dem/dem.tif; rerun alone after tweaking a provider, no re-fetch
python pipeline/08-add-elevation.py           # adds ascent_m/descent_m to data/osm/hut-edges.geojson in place

python pipeline/09-build-trail-tiles.py       # -> data/osm/trails.pmtiles
```

After step 09, copy `data/osm/trails.pmtiles` to `huts/public/data/trails.pmtiles` (same manual
copy step used for `hut-edges.geojson`/`huts.geojson`) for the app's raw-trails toggle layer
(`GraphPage.jsx`'s `TrailTilesLayer`, `#graph` route) to pick it up.

## Rejected: buffer-clip + OSMnx

An earlier version of step 6 buffered every hut by a radius, unioned the buffers, and clipped
`trails.osm.pbf` to that polygon before loading it into NetworkX/OSMnx — the idea being to shrink
the graph enough to fit in memory. It didn't work: Alpine huts are packed densely enough that even
a 15km buffer only cut node count in half (26.5M → 13.5M), still too large to load. The actual
problem was never the input size — it was NetworkX/OSMnx's per-node/edge Python object overhead
(dict-of-dicts + shapely geometry per edge). Shrinking the *area* never fixed that. Those scripts
have been removed; `06-build-hut-graph.py` (below) replaced the whole approach.

`06-build-hut-graph.py` skips the buffer clip and OSMnx entirely: it streams `trails.osm.pbf`
(the full, unclipped merge from step 3) once with `pyosmium` into flat numpy arrays, builds a
`scipy`-backed KDTree + `igraph` graph, snaps huts to their nearest trail node, and runs a
distance-capped shortest-path query per hut — cheap even against the full network because the
`--max-edge-km` cutoff (from `pipeline.config.json`) stops each search early. See the script's
docstring for details. Its two per-hut/per-edge query passes run across a `ThreadPoolExecutor`
(`--workers`, default all cores) since igraph's C routines release the GIL — no process-pool
pickling of the graph needed.

Step 08's elevation pass is a straight DEM sample-and-sum per edge polyline (rasterio + a
threshold-hysteresis filter, see the script's docstring) — cheap enough on the surviving edge set
that it hasn't needed the same treatment.

## Displaying the raw OSM trails

`hut-edges.geojson` only ships the ~600 derived hut-to-hut trail segments, not the full raw OSM
network they were computed from (`trails.osm.pbf`, 26.5M nodes) — far too large to ship as plain
GeoJSON to a browser. A dynamic tile server (martin, tegola, tileserver-gl) was considered and
rejected: this project has no backend by design, and standing one up means new hosting/TLS/uptime
to maintain, not just a build step.

Instead, step 09 pre-builds the raw network into a single static **PMTiles** vector-tile archive
(`trails.pmtiles`) — still just a file, read via HTTP range requests from whatever static host
serves the rest of the app, with zoom-dependent detail instead of one fixed simplification level.
`GraphPage.jsx` renders it client-side with `protomaps-leaflet`, toggleable via a checkbox so it's
opt-in (it's a lot of lines to draw at once).

### tippecanoe on Windows (WSL)

`tippecanoe` (the vector-tile builder step 09 shells out to) has no Windows build on
conda-forge — only linux-64/osx-64. It's also not packaged in Ubuntu's apt repos, so the fix is a
small linux-64 micromamba env inside WSL, one-time setup, independent of the Windows `alpen-osm`
env:

```bash
# inside WSL (wsl.exe from a Windows shell, or a WSL terminal directly)
cd ~
curl -sSL -o micromamba.tar.bz2 "https://micro.mamba.pm/api/micromamba/linux-64/latest"
mkdir -p mm && tar -xjf micromamba.tar.bz2 -C mm

./mm/bin/micromamba create -y -r ~/micromamba -n tippecanoe -c conda-forge tippecanoe
```

`09-build-trail-tiles.py` detects it's on Windows, checks for a native `tippecanoe` on PATH
first (absent), and falls back to invoking it through WSL — `wsl bash -lc "~/mm/bin/micromamba
run -r ~/micromamba -n tippecanoe tippecanoe ..."` — translating the Windows absolute paths it
passes (input `.geojsons`, output `.mbtiles`) to their `/mnt/<drive>/...` WSL-mount equivalents.
On Linux/macOS, install `tippecanoe` normally (conda-forge) and this fallback is never triggered.

## Not done yet

- Extending scope beyond AT+Bayern (Switzerland, Italy/South Tyrol, Slovenia, Liechtenstein) — add
  each as a `regions` entry in `pipeline.config.json`.
- All pipeline outputs (`hut-edges.geojson`, `huts.geojson`, `trails.pmtiles`) are still hand-copied
  into `huts/public/data/` after a pipeline run, not fetched from `data/` directly or wired into a
  build step.
- The Alpenverein `toursearchApi` 26-tour overlay (see `docs/alpenverein-api.md` §3) is a separate,
  already-understood data source — not part of this OSM pipeline.
