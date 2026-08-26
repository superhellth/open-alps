# OSM trail data pipeline

How `data/osm/trails.osm.pbf` is produced. This is the raw hiking-trail input for the planned
hut-to-hut routing graph (nodes = huts from `AVT_GEO_CAA_HUETTEN_View_P`, edges = derived from
this file). Everything here is an offline, rerunnable precompute step — the app itself stays
backend-free per the project's architecture.

This covers the rationale for steps 1-4 (download → filter → merge → verify). For the runnable
scripts, the hyperparameter config (`pipeline.config.json`), and the exact reproduction commands,
see `pipeline/README.md`. For why the graph-build step (5-6) is a streamed pyosmium+igraph build and
not an OSMnx buffer-clip, see the "Rejected" section of that same README.

## Why this shape

- **Scope: Austria + Bavaria only, for now.** Hut coordinates span ~9 countries (DE 323, AT ~237,
  Slovenia 179, South Tyrol/IT ~89, CH 10, LI 2 — checked via the ArcGIS hut layer, see
  `docs/alpenverein-api.md`), but AT+DE alone already cover the majority of huts. Extending to
  CH/IT/SI later just means adding a `regions` entry per country to `pipeline.config.json` (see
  `pipeline/README.md`) — steps 1–3 already loop over that list, nothing to edit in the scripts.
- **Geofabrik `.osm.pbf` extracts, not live Overpass queries.** Overpass is fine for prototyping a
  small bbox but has query size/time limits and shouldn't be hit repeatedly for a full-region
  pull. A one-time download processed locally is more robust and repeatable.
- **`osmium tags-filter`, not `osmtogeojson`.** The eventual graph-build step needs shared OSM
  node IDs at trail junctions (two ways crossing = same node ID). GeoJSON export flattens every
  way into an independent `LineString` and loses that. `tags-filter` keeps full node/way topology
  by default (no `-R`/`--omit-referenced` flag used) while still shrinking the file drastically by
  dropping everything that isn't a trail.
- **`osmium-tool` via a native conda-forge binary, not Docker.** An earlier version of this
  pipeline shelled out to `stefda/osmium-tool` over Docker because `osmium-tool` wasn't installed
  natively. That's gone — the whole pipeline is plain Python now (`subprocess` calls to a native
  `osmium` binary), no Docker/bash/Node dependency. See `pipeline/README.md` "Setup" for how the
  `alpen-osm` conda env is created (via `micromamba`, since this machine's `base` conda env can't
  solve `-c conda-forge` specs in reasonable time).

## Prerequisites

- The `alpen-osm` conda env active (`conda activate alpen-osm`) — see `pipeline/README.md` "Setup".
- ~2GB free disk for raw extracts + filtered output.

## Directory layout

```
data/osm/
  raw/
    austria-latest.osm.pbf     # untouched Geofabrik download
    bayern-latest.osm.pbf      # untouched Geofabrik download
  austria-trails.osm.pbf       # filtered to hiking ways only
  bayern-trails.osm.pbf        # filtered to hiking ways only
  trails.osm.pbf               # merged, final output of this pipeline
```

Not committed to version control (no `.gitignore` exists yet since this repo has no git — add
`data/osm/` to one if/when git is initialized). ~1.6GB raw in, ~264MB final output.

## Steps

### 1. Download raw extracts

```bash
conda activate alpen-osm
python pipeline/download_extracts.py
```

Sizes at time of writing: Austria ~807MB, Bavaria ~849MB. Geofabrik regenerates these regularly
(daily); re-running gets the current snapshot, not a pinned version — acceptable since trail
geometry changes rarely, but note this if exact reproducibility across time matters later.

### 2. Filter each extract to hiking-relevant ways

```bash
python pipeline/filter_trails.py
```

Runs `osmium tags-filter` (native binary, via `subprocess`) once per region in
`pipeline.config.json`, with the tag filter expression from `trailTagFilter` in that same config.

Result: 807MB → 134MB (Austria), 849MB → 131MB (Bavaria). The `highway` filter keeps
`path|footway|track|steps` ways only; tags like `sac_scale`, `trail_visibility`, `surface`,
`name`, `ref` ride along automatically since `tags-filter` keeps whole matched objects, not just
selected tags.

### 3. Merge into one file

```bash
python pipeline/merge_trails.py
```

Result: `data/osm/trails.osm.pbf`, 264MB.

### 4. Sanity-check

```bash
python pipeline/verify_trails.py
```

Exits nonzero if the file is missing or empty (so pipeline's doit task can gate on it), then prints
`osmium fileinfo -e`. Expected at time of writing: bbox lon 8.97–17.17 / lat 46.37–50.57
(AT+Bayern), ~2.78M ways, ~26.5M nodes, 0 relations (route relations weren't pulled — only raw
`highway=*` ways; add `r/route=hiking` to `trailTagFilter` later if named-route relations like
E4/E5 are wanted as an overlay).

## DEM provider: why it's pluggable

Step 08's `ascent_m`/`descent_m` are sampled from a DEM (`data/dem/dem.vrt`, built by step 07)
along each edge's trail polyline. Copernicus GLO-30 — the default provider — is a 30m grid;
alpine trails climb via switchbacks that are often narrower than 30m apart, so the DEM can't
resolve them as distinct terrain and the sampled elevation profile comes out smoother than the
real trail, undercounting ascent/descent versus sources like alpenvereinaktiv that use
finer-grained regional DEMs or actual recorded GPS/barometric tracks.

Austria's BEV DGM (10m, `at-bev-dgm`) and Bavaria's DGM5 (5m, `bavaria-dgm5`) are the regional
fix — both resolve switchback-scale terrain, at the cost of being regional rather than global (no
single provider covers this pipeline's whole AT+Bayern scope) and needing more
download/storage/runtime than Copernicus's one flat global tileset. The `composite` meta-provider
exists to combine them per sub-region without forcing one DEM source on the whole bbox — see
`pipeline/dem_providers/base.py` for the provider contract every source implements, and
`pipeline/README.md`'s Config section for the registered providers and how to select them via
`pipeline.config.json`'s `dem.providerConfig.regions`.

## Not done yet

- Route-relation (`r/route=hiking`) pull for the named-trail overlay layer (E4/E5, Karnischer
  Höhenweg-style routes), separate from the Alpenverein `toursearchApi` catalogue (see
  `docs/alpenverein-api.md` §3 for that one — 26 predefined tours, not a general trail network).
- Everything else tracked in `pipeline/README.md`'s own "Not done yet" (scope beyond AT+Bayern, and
  wiring `hut-edges.geojson` into the `huts/` app).
