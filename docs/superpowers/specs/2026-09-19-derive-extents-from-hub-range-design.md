# Derive every spatial extent from the hub range — drop the hand-typed `bbox`

Date: 2026-09-19
Status: draft, for planning

## Problem

`pipeline.config.json` carries hand-typed rectangles that stand in for "the area we care about":

- top-level `bbox` (`8.9–17.2 E, 46.3–50.6 N`), and one copy per DEM region under
  `dem.providerConfig.regions[]` (`copernicus-glo-30`, `bavaria-dgm5`, `at-bev-dgm`).

These rectangles duplicate information the pipeline already has, and they are only loosely
consistent with it:

| Consumer | What it uses the rectangle for | Real requirement |
|---|---|---|
| `build_base_graph.py:254` → `Grid` | origin + extent of the tile grid, persisted in `base-graph/manifest.json` | any box that contains every base-graph node |
| `fetch_dem.py:40` `setdefault("bbox", …)` | default region bbox | never read: `fetch_regions()` only reads each region's own `bbox` |
| `copernicus-glo-30` region | 1°×1° tile list to download | tiles covering the area trails can exist in |
| `bavaria-dgm5` region + `bboxFromHuts` | rough "Bavarian huts" filter → per-hut DGM5 tile squares | tiles covering hub range ∩ Bavaria |
| `at-bev-dgm` region | nothing (`at_bev.py` reads only `downloadUrl`) | none |
| `check_start_point_integrity` | "outside_bbox" sanity check | inside the AT+Bavaria coverage |
| `dag/downloads.py:56`, `dag/graph_building.py:48` | `bbox_json` tracking param | none (only exists to track the number) |

The area that actually matters is already computed: `compute_hub_range.py` writes
`data/build/hub-range/hub-range.geojson`, the union of a
`graph.maxEdgeKm × HUB_RANGE_SAFETY_MARGIN` circle around every hut. `filter_trails.py` clips
every trail to it, so no base-graph node exists outside it. The regions themselves are already
defined by the `.poly` files of `config["regions"]` (used by `fetch_huts.py` for the hut catalog).

Two hand-typed rectangles next to these two real definitions can silently drift from them: the
Bavaria rectangle pulls in Austrian huts (extra DGM5 requests for tiles that do not exist), and
adding a region to `config["regions"]` does not extend any of them.

## Goals

1. Remove the top-level `bbox` and every per-region `bbox` / `bboxFromHuts` from the config.
2. One definition of "the area": `hub-range.geojson` for what has to be covered, the OSM `.poly`
   files for which country a DEM source applies to.
3. DEM coverage of every base-graph node is guaranteed by construction, not by matching numbers
   (`docs/superpowers/specs/2026-08-22-hub-range-dem-coverage.md`: no graceful "skip missing
   elevation" fallback).
4. The start-point quality check tests real coverage (inside the region polygons) instead of a
   rectangle.

## Non-goals

- Changing the hub-range polygon itself (radius, `n_points`, `HUB_RANGE_SAFETY_MARGIN`). It stays
  as `compute_hub_range.py` builds it; this spec only reads it.
- Extending scope past AT + Bayern.
- Changing DEM providers or their resolution/priority order (copernicus < bavaria < at-bev).
- The hut-catalog filter in `fetch_huts.py` (already polygon-based).

## Design

### 1. `hub-range.geojson` is the single source of "area to cover"

`fetch_dem` takes `data/build/hub-range/hub-range.geojson` as a `file_dep`. The DAG stays acyclic
(`fetch_huts → compute_hub_range → fetch_dem`; the same "diamond" shape `filter_trails` already
has, `dag/preprocessing.py:15`). `fetch_dem` no longer needs `--max-edge-km` or
`HUB_RANGE_SAFETY_MARGIN`: the polygon already carries them, and `fetch_dem` cannot drift from
`filter_trails`.

### 2. DEM fetch (`phases/downloads/`)

Layer order is unchanged (last-listed wins in `gdalbuildvrt`): copernicus, bavaria-dgm5, at-bev.

- **`copernicus-glo-30`** — tiles = every 1°×1° tile whose box intersects the hub-range polygon.
  Iterate the tiles inside `polygon.bounds`, keep those with `box(tile).intersects(polygon)`.
  Whole-tile rounding gives all the slack needed, so no extra buffer.
- **`bavaria-dgm5`** — region polygon `= hub_range ∩ bayern_polygon`, transformed to EPSG:25832.
  Tiles = every 1 km DGM5 tile intersecting it (prepared-geometry tests over the polygon's
  bounds), then the existing `existing_tile_ids()` WMS coverage check. Replaces
  `_points_for_region()`, `bboxFromHuts`, `bufferKm`, and `tiles_for_points`' per-hut squares. An
  Austrian hut near the border is covered because its circle intersects Bavaria, with no special
  case. `hut_points()` keeps working for its other callers but loses `filter_bbox`.
- **`at-bev-dgm`** — unchanged: one national zip, no extent needed.

`bayern.poly` becomes a `file_dep` of `fetch_dem`. Fail loud on an empty intersection (as
`hut_points` does today for an empty selection).

Config shape: keep `dem.providerConfig.regions[]`, drop `bbox` and `bboxFromHuts`, add an
optional `"boundary": "<name of an entry in config.regions>"` on regions that apply only inside one
country (`bavaria-dgm5` → `"bayern"`). No `boundary` = whole hub range. Renaming the list to
`layers[]` is out of scope.

### 3. Base-graph grid derived from the data

`pack_and_write()` builds `Grid` from `contracted.coords`' min/max lon/lat instead of a config
bbox, and still writes the result to `manifest.json` as `bbox`. Every consumer already reads
`manifest["bbox"]` (`snap_hubs`, `build_hub_edges`, `build_access_edges`, `gather_route_subgraphs`,
`sample_base_elevation`, `analysis/*`), so none of them change. `build_base_graph.py` loses its
`config["bbox"]` argument; `dag/graph_building.py` drops the `bbox_json` tracking param.

Origin/extent: the node min/max snapped outward to whole degrees (`floor` of the minima, `ceil` of
the maxima). The origin then only moves when the data crosses a whole-degree line, so cell IDs stay
as stable across rebuilds as the fixed config bbox made them. The extra empty edge cells are
harmless (`Grid` clamps points to the last row/column).

### 4. Quality check: polygon containment

`check_start_point_integrity` replaces the rectangle test with point-in-polygon against
`region_boundary(all configured .poly files)` (`lib/poly.py`, vectorised with
`shapely.contains_xy`). Reason string: `outside_region`. `non_finite` and `duplicate` stay.
`check_preprocessing` takes the `.poly` files as `file_dep`. Huts and partner businesses are
already filtered by `prep(region_boundary(...)).contains` in `fetch_huts.py` and pass by
construction. Stations and parking come from `osmium export` of the Geofabrik extracts, which keep
whole ways crossing the boundary, and parking areas are reduced to a centroid (`_area_to_point`), so
a few of them can lie just outside the polygon. Measure the flagged count on the current data
first; if any are flagged, fix it at the root in `fetch_stations_parking.py` by filtering to the
region boundary the way `fetch_huts.py` does, rather than adding a tolerance to the check. This also answers the open backlog
question "are hubs outside the AT + Bavaria polygon filtered, and does a check cover it": start
points include huts (`_TYPE_NAMES`), so the same check covers them.

### 5. Config, DAG and docs

- `pipeline.config.json`: delete top-level `bbox`; delete `bbox`/`bboxFromHuts` from the three DEM
  regions; add `boundary` where needed.
- `dag/downloads.py`: `fetch_dem` gains `file_dep` (hub-range, `bayern.poly`), loses the
  `bbox_json` tracking param and the `max_edge_km` cli param.
- `fetch_dem.py`: drop `setdefault("bbox", …)`; `bavaria_dgm.py` module docstring loses the
  top-level-bbox fallback line.
- `pipeline/pixi.toml`: pin `shapely = ">=2.0"` (`contains_xy` and prepared-geometry batch tests;
  the lock already resolves 2.1.2).
- Docs to update: `pipeline/README.md` (config table + DEM section), `pipeline/CLAUDE.md`
  ("hut bbox" wording), `phases/downloads/README.md`, `phases/graph_building/README.md`
  ("partitions the bbox"), `phases/README.md` (`bbox_from_huts()`), root `CLAUDE.md` if it
  mentions the bbox.

## Edge cases

- **Austrian hut with routes into Bavaria** — its hub-range circle intersects `bayern.poly`, so
  the intersection polygon contains that strip and its DGM5 tiles are fetched.
- **Hut near a non-configured border (Italy, Switzerland, Czechia)** — no OSM trails exist outside
  the extracts, so no DEM is needed there; Copernicus tiles cover the area anyway.
- **Outlying Bavarian Forest huts** — hub-range pieces far north; the Copernicus tile test skips
  the empty tiles between, unlike a bounding box.
- **Border-line tiles** — the intersect tests include touching tiles, so a node exactly on the
  hub-range boundary is covered.
- **Empty Bavaria intersection** (no huts near Bavaria) — raise, do not silently fetch nothing.
- **Grid extent differs from today's bbox** — cell count may change; `Grid.n_cols/n_rows` are
  persisted in the manifest, so consumers pick this up without change.

## Cost and rerun impact

This is a one-time rebuild; nothing here runs unattended (project rule: no `doit` without
explicit confirmation).

- `fetch_dem`: reruns, downloads only tiles not already cached in `data/raw/dem/`.
- `build_dem_vrt` / `materialize_regions` (~14 min) and `materialize_geotiff`: rerun with the new
  tile set.
- `build_base_graph` (~6 min): reruns because the grid origin changes, which changes every
  `cell_id`; everything downstream then reruns, including `hub_snap` (~60 min) and
  `sample_base_elevation`.
- `check_preprocessing`: reruns (new dependencies).

## Testing

- Copernicus tile selection: polygon with a hole and a distant island → only intersecting tiles.
- Bavaria tile selection: hub-range piece straddling the Bavaria/Austria border → only tiles inside
  Bavaria; Austrian-hut circle overlapping Bavaria → included; empty intersection → raises.
- `pack_and_write` with a derived extent: every node gets a valid cell ID; manifest `bbox` equals
  the data extent snapped outward to whole degrees.
- Quality check: point outside the polygon → `outside_region`; point inside → not flagged.
- Update `test_dodo_wiring.py` (`bbox_json` no longer tracked), `test_composite_region_merge.py`
  (no `bboxFromHuts`), `test_check_preprocessing.py`, `test_build_base_graph.py`.

## Decisions

1. **Region config shape:** `boundary` field on the existing `dem.providerConfig.regions[]`
   entries; no rename to `layers[]`.
2. **Border-adjacent start points:** measure the flagged count of the polygon check on the current
   data first. If stations/parking are flagged, filter them to the region boundary at fetch time
   (`fetch_stations_parking.py`) instead of loosening the check.
3. **Grid origin:** node extent snapped outward to whole degrees.
4. **shapely:** the lock resolves 2.1.2, so no risk; add the `>=2.0` pin.

## Open questions

None.
