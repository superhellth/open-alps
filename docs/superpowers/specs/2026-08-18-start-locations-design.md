# Start locations (stations/parking) in the routing graph

Date: 2026-08-18
Status: approved for planning

## Goal

Route planning currently only knows hut-to-hut edges. To support "plan a route starting from a
train station or parking lot," the trail graph needs edges from every station/parking point to
every hut within routing range — not just station/parking markers on a map.

Scope: pipeline + data model only. App/UI wiring (start-point picker, rendering start→hut legs)
is a separate follow-up.

## Requirements

- For each station and parking point, find all huts reachable within the existing hut-hut edge
  radius (`graph.maxEdgeKm` — reused as-is, no new config value).
- Distance/path computed the same way as hut-hut edges: snap to nearest trail node, real trail
  path (not beeline), with road-penalty-aware routing and the same real-distance cutoff guarantee.
- Elevation (ascent/descent/profile) on start→hut edges, same treatment as hut-hut edges.
- Output kept separate from `hut-edges.geojson`/`hut-edges.pmtiles` (new files), not merged in.

## IDs for stations/parking

`fetch_stations_parking.py` currently keeps only `name`/`network`/`operator` (stations) and
`name`/`capacity`/`fee`/`access` (parking) — no id. Edges need a stable id to reference.

Add osmium's `@id` to each layer's `keep_fields`, prefixed by layer to avoid collisions with each
other and with hut ids (hut ids come from the Alpenverein ArcGIS layer, a disjoint id space):

- `station:<osm_id>`
- `parking:<osm_id>` (parking is exported as point-per-polygon-centroid already; the way id is
  stable per lot)

## Snap + edge computation

Extend `build_hut_graph.py` rather than writing a new script. Rationale: `stream_osm` /
`build_kdtree` / `contract_chains` / `build_igraph` build the trail network itself and are
independent of which points get snapped to it — they're also the ~4-hour part of the run
(`data/timings.jsonl`). A separate script would have to redo all of that just to snap a few
thousand station/parking points; extending the existing run reuses the graph, KDTree, and
component-membership arrays already held in memory.

Concretely, the existing hut snap→candidates→pass1(distances)→pass2(paths) sequence runs a
second time in the same process, against the same `raw_node_tree`/`graph`/`component_id`:

1. Load `stations.geojson` + `parking.geojson`, build a combined start-point list (id, type,
   lon/lat).
2. Snap each start point to `raw_node_tree` exactly like huts (`--max-snap-m`, reject if no trail
   node within range — a station/lot far from any mapped trail simply gets no edges, same
   "skipped, not force-matched" behavior as unsnapped huts).
3. Candidates = nearby huts via the existing `hut_tree` KDTree, beeline-prefiltered the same way
   (`max_edge_km * 3` radius) before the real igraph distance query.
4. Pass 1 (`graph.distances`, target-limited, `weights="dist"`) filtered by `--max-edge-km`
   (reused, not a new value) exactly as for hut-hut pairs.
5. Pass 2 (`graph.get_shortest_paths`, `weights="weight"`) fetches the real path, road_m,
   sac_scale rollup, via_ferrata flag — identical logic to the hut-hut pass 2.

Difference from hut-hut edges: this direction is inherently directional (start → hut) and has no
"unordered pair" concept to dedupe — there's no start↔start or hut→start edge to skip, so the
`seen_pairs` dedup logic from the hut-hut pass doesn't apply here.

Output: new `data/osm/start-edges.geojson`, FeatureCollection of LineStrings, one per
(start point, reachable hut) pair:

```json
{
  "type": "Feature",
  "properties": {
    "from_start_id": "station:123456",
    "from_start_type": "station",
    "to_hut_id": "<hut id>",
    "distance_m": 4210.5,
    "road_m": 300.0,
    "sac_scale": "mountain_hiking",
    "via_ferrata": false,
    "source": "osm"
  },
  "geometry": { "type": "LineString", "coordinates": [...] }
}
```

`build_hut_graph.py`'s module docstring and `--out`/new `--start-out` args get updated to
document the second output; a new `--stations`/`--parking` arg pair (defaulting to
`stations.geojson`/`parking.geojson` in `OSM_DIR`) feeds step 1.

## Elevation + tiles: no new code

`add_elevation.py` and `build_hut_edge_tiles.py` are already parameterized over
`--edges`/`--out` (elevation) and `--edges`/`--out-tiles`/`--out-stats` (tiles) — they don't know
or care that the input is hut-hut edges specifically. Both get a second invocation pointed at
`start-edges.geojson`:

- `add_elevation.py --edges start-edges.geojson --out start-edges.geojson`
- `build_hut_edge_tiles.py --edges start-edges.geojson --out-tiles start-edges.pmtiles --out-stats start-edge-stats.json`

## `dodo.py` wiring

- `task_build_hut_graph`: `file_dep` gains `stations.geojson`/`parking.geojson`; `targets` gains
  `start-edges.geojson`. Still gated by the existing `config_changed` uptodate check (graph
  hyperparams affect both outputs identically) and still NOT force-rerun — same ~4h cost profile
  applies regardless of how many outputs the run produces.
- New `task_add_start_elevation` (mirrors `task_add_elevation`: `uptodate: [False]`, cheap,
  depends on `dem.tif` + `task_build_hut_graph`).
- New `task_build_start_edge_tiles` (mirrors `task_build_hut_edge_tiles`).
- `copy_public_data`'s `PUBLIC_FILES` list gains `start-edges.pmtiles`, `start-edge-stats.json`.
- `default_tasks` list gains the two new task names, ordered after `add_elevation` /
  `build_hut_edge_tiles` respectively (mirrors existing hut-edge ordering).

## Out of scope (follow-up)

- `App.jsx`/`GraphPage.jsx` consuming `start-edges.pmtiles`/`start-edge-stats.json` — start-point
  picker UI, rendering start→hut legs, any multi-hop route search (start → hut → hut → ...) that
  would chain start-edges with hut-edges.
- Non-hut destinations (e.g. viewpoints) — out of scope entirely, not just deferred.
