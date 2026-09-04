# phases/downloads/ — fetch raw data

Four fetchers, mostly independent - each pulls from a remote source and writes into `data/osm/` or
`data/dem/`. All read `pipeline/pipeline.config.json` via `lib/pipeline.py`'s `load_config()`.
`fetch_huts.py` is the one exception: it depends on `download_extracts.py`'s `.poly` outputs (see
below) to filter to real AT+Bavaria coverage.

## `download_extracts.py` — Geofabrik OSM extracts

- Reads `config["regions"]` (name + Geofabrik `.osm.pbf` URL + `.poly` boundary-polygon URL, e.g.
  austria/bayern).
- For each region: `urllib.request.urlretrieve` the `.osm.pbf` to `data/osm/raw/<name>-latest.osm.pbf`
  and the `.poly` boundary to `data/osm/raw/<name>.poly` (the same admin-boundary shape Geofabrik
  clipped the extract to - `fetch_huts.py`'s real-coverage filter, see `lib/poly.py`).
- No pinning — Geofabrik extracts regenerate daily; rerun to refresh.
- **doit wiring**: `file_dep=[pipeline.config.json]`,
  `targets=[raw/<region>-latest.osm.pbf, raw/<region>.poly, ...]`.

## `fetch_huts.py` — Alpenverein hut points

- `GET` the Alpenverein ArcGIS feature layer
  (`AVT_GEO_CAA_HUETTEN_View_P/FeatureServer/0/query`, `outFields` per `OUT_FIELDS`, `outSR=4326`,
  `resultRecordCount=8000`, no auth).
- Filters returned features to those whose geometry falls inside the real AT+Bavaria boundary -
  the union of `download_extracts.py`'s per-region `.poly` files (`lib/poly.py`), not a rectangular
  bbox (a bbox also catches huts in neighboring countries with zero nearby trail data).
- Classifies and splits into `data/osm/huts.geojson` (real huts, `properties` includes
  `id/name/hutType/serviced/elevation/ohrsHutId/tenantCode`) and
  `data/osm/partner_betriebe.geojson` (Bergsteigerdörfer partner businesses, `properties = {id, name}`).
- **doit wiring**: `file_dep=[raw/<region>.poly, ...]`, `targets=[huts.geojson, partner_betriebe.geojson]`.

## `fetch_stations_parking.py` — OSM railway stations + parking

Two independent tag-filtered exports, reusing the raw extracts from `download_extracts.py` (no
new network download):

- **stations** — two node-only tag-filter pipelines, unioned (and re-sorted by ID) with
  `osmium sort`: rail is `n/railway=station,halt` → `n/name` (two AND stages); bus is three AND
  stages (`n/highway=bus_stop` → `n/public_transport=platform` → `n/name`) — each stage's output
  feeding the next, since `osmium tags-filter` only ORs the tags named in one call. Rail does
  **not** require `public_transport=platform` — that tag is essentially never present on
  `railway=station,halt` nodes in this data and would drop real stations, not filter noise. Bare
  `highway=bus_stop` alone matches ~5x as many nodes as the narrowed bus set, most unnamed
  poles/duplicates that add routing cost in `build_hub_edges.py` without real trailhead value.
  Both pipelines' final output is `osmium export --geometry-types point`'d, then properties pruned
  to `{name, access, motor_vehicle, barrier, disused, abandoned}` — the same usability-tag shape
  as parking below, so both layers are filterable the same way by `filter_start_points.py`'s
  `is_usable()`.
- **parking** — `osmium tags-filter nwr/amenity=parking` (nodes+ways+relations, since lots are
  usually mapped as polygons), `osmium export --geometry-types point` (so a polygon exports as its
  centroid, not its ring — keeps this a plain `Point` layer like everything else), properties
  pruned to `{name, capacity, fee, access, motor_vehicle, barrier}`.
- Per-layer features from every region are concatenated into one `FeatureCollection` each:
  `data/osm/stations.geojson`, `data/osm/parking.geojson`.
- **doit wiring**: `file_dep=[raw/<region>-latest.osm.pbf, ...]`,
  `targets=[stations.geojson, parking.geojson]`.

## `fetch_dem.py` — elevation raster tiles

- Reads `config["dem"]["providerConfig"]` (`bbox` defaulted from the top-level `config["bbox"]`)
  and always delegates to `dem_providers.composite.fetch_regions()`, which runs each configured
  sub-region's own provider's `fetch()` and returns one manifest entry per sub-region
  (`{provider, raw_dir, region_vrt, tile_paths}`) — even a single-region scope is just
  `providerConfig.regions` with one entry, so there is no separate single-provider code path.
- Every provider's `fetch()` skips tiles already on disk (idempotent). Does **not**
  reproject/merge/materialize — that's `phases/elevation/build_dem_vrt.py`, split out so retuning
  reprojection or rerunning after a fresh tile download never re-triggers a provider's own
  tile-existence check (Bavaria's is a per-1km-tile WMS coverage grid).
- Writes `data/dem/fetch_manifest.json`.
- **doit wiring**: `file_dep=[config]`, `targets=[fetch_manifest.json]`.

### Providers (`dem_providers/`)

Common contract: `dem_providers/base.py` defines `fetch(config, raw_dir) -> manifest_entry` and
`to_4326_vrt(tile_paths, out_vrt)`; every provider module implements both, `get_provider(name)`
looks one up by registry key.

- **`copernicus.py`** (`copernicus-glo-30`) — global 30m coverage, AWS Open Data, no auth.
  `providerConfig: {}` (uses the top-level `bbox`). The safe default; systematically underestimates
  ascent/descent on switchback-heavy alpine trails because 30m resolution can't resolve terrain
  that narrow (see `docs/osm-trail-pipeline.md`).
- **`at_bev.py`** (`at-bev-dgm`) — Austria's national 10m DGM (data.gv.at, CC-BY-4.0,
  Lambert/EPSG:31287). `providerConfig: {"downloadUrl": "<confirmed direct .zip URL>"}` — one
  ~1.9GB national file, not tiled, so `bbox` in its config is unused metadata.
- **`bavaria_dgm.py`** (`bavaria-dgm5`) — Bavaria's 5m DGM (geodaten.bayern.de, CC BY 4.0,
  UTM32N/EPSG:25832), served as one small (~200KB) direct-download zip per 1km tile; tile IDs are
  computed directly from `providerConfig.bbox` (no tile-index file needed). `bboxFromHuts: true`
  (used here) shrinks that bbox from the full political box down to actual hut extent +
  `bufferKm` (`lib/pipeline.py`'s `bbox_from_huts()`) — Bavaria's full state bbox is ~80,000 1km
  tiles, but huts only exist in the southern Alpine strip near the Austrian border.
- **`composite.py`** (`composite`) — meta-provider stitching per-sub-region VRTs from *different*
  providers into one final `dem.vrt` (e.g. Austria via `at-bev-dgm`, Bavaria via `bavaria-dgm5`).
  `providerConfig: {"regions": [{"provider": ..., "bbox": ..., ...that provider's own config
  keys}, ...]}`. Region order matters where two regions' bboxes overlap — `gdalbuildvrt` keeps the
  first-listed source's pixels.
