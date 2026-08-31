# phases/preprocessing/ — filter and merge raw downloads

Turns `phases/downloads/`'s raw pulls into the pipeline's actual working inputs: one merged
hiking-ways network, and a bounded set of station/parking "hub" candidates.

## `filter_trails.py`

- Reads `config["trailTagFilter"]` — an `osmium tags-filter` expression, e.g.
  `w/highway=path,footway,track,steps,residential,service,unclassified,tertiary,via_ferrata`.
- Per region: shells out to
  `osmium tags-filter <raw> <filter> -o <name>-trails.osm.pbf --overwrite`.
- `osmium tags-filter` keeps every node referenced by a kept way by default, so way topology
  (shared endpoints between adjacent ways) is preserved for `graph_building/` even though most
  standalone POI nodes are dropped.
- Requires the `osmium-tool` native binary on PATH (`alpen-osm` conda env).
- **doit wiring**: `file_dep=[raw/<region>-latest.osm.pbf, ..., config]`,
  `targets=[<region>-trails.osm.pbf, ...]`.

## `merge_trails.py`

- `osmium merge <region1-trails.osm.pbf> <region2-trails.osm.pbf> ... -o trails.osm.pbf --overwrite`.
- Combines all per-region filtered extracts into one merged hiking network — the single input
  `graph_building/build_base_graph.py` streams.
- **doit wiring**: `file_dep=[<region>-trails.osm.pbf, ...]`, `targets=[trails.osm.pbf]`.

## `verify_trails.py` — gate

- Checks `trails.osm.pbf` exists and is non-empty; exits nonzero otherwise, failing the doit run
  before anything downstream starts on a bad/missing input.
- Runs `osmium fileinfo -e trails.osm.pbf` to print bbox/node/way/relation counts for a quick
  sanity read.
- Targets `verify_trails.stamp`, so an unchanged `trails.osm.pbf` (content hash) skips the rescan
  instead of forcing a rerun on every `doit` invocation — the check result isn't itself cacheable,
  but "did the input change" is, via the normal `file_dep` hash.
- **doit wiring**: `file_dep=[trails.osm.pbf]`, `targets=[verify_trails.stamp]`.

## `filter_start_points.py`

Reduces station/parking candidates to the ones that can possibly matter, using a provably correct
(not approximate) geometric filter, before they ever reach the expensive graph query.

- **Usability filter**: before the beeline filter runs, `is_usable()` hard-drops candidates that
  can never be a real trailhead — `access`/`motor_vehicle` of `private`/`no`, a `barrier` of
  `gate`/`lift_gate`, or a station/bus-stop tagged `disused=yes`/`abandoned=yes` (the
  `disused:railway=*` lifecycle prefix is already excluded on import by
  `fetch_stations_parking.py`'s tag filter). This is a hard drop, not a preference — it runs before
  the expensive graph query, not just at final table-selection time
  (`postprocessing/build_approach_table.py`), so `build_hub_edges.py` never wastes work routing to
  a point that could never ship anyway.
- **Algorithm**: builds a `scipy.spatial.cKDTree` over all hut coordinates (`hut_points()` from
  `huts.geojson`), then for each usable station/parking candidate does a 1-nearest-neighbor query
  against that tree and keeps the point only if the beeline distance to its nearest hut is
  `<= config["graph"]["maxEdgeKm"]` (converted from km via `1 / 111.320` deg/km).
- **Why this bound is correct, not heuristic**: `graph_building/build_hub_edges.py` only ever
  keeps a hut-to-hut/hub-to-hut path whose real (trail-network) walking distance is
  `<= maxEdgeKm`. Real walking distance is always `>=` beeline distance, so any point farther than
  `maxEdgeKm` beeline from every hut *cannot* produce a kept edge under any possible trail routing
  — the kd-tree prefilter can never discard a point that would otherwise have survived.
- **Why this filter is needed at all**: `trailTagFilter` (see `filter_trails.py` above) includes
  `residential`/`service`/`unclassified`/`tertiary` roads across the whole Austria+Bavaria extract,
  so proximity to *some* trail-tagged way doesn't bound the candidate count — most of two
  countries' urban road networks would otherwise pass through. The beeline-to-hut filter is what
  actually bounds hub count before `build_hub_edges.py`'s per-hub shortest-path search runs.
- **Output**:
  - `data/osm/start_points.npy` — structured array `(lon: f8, lat: f8, osm_id: i8, type: u1)`,
    `type` is `binfmt.TYPE_STATION` (1) / `binfmt.TYPE_PARKING` (2) / `binfmt.TYPE_PARTNER` (3,
    Bergsteigerdörfer partner businesses from `partner_betriebe.geojson` — `docs/superpowers/specs/
    2026-08-28-hut-classification-design.md`). For `TYPE_PARTNER`, `osm_id` holds the ArcGIS
    layer's `OBJECTID`, not a real OSM id.
  - `data/osm/start_points_id_table.json` — `{"station:<osm_id>": <osm_id>, "parking:<osm_id>":
    <osm_id>}`, kept for symmetry/debuggability; downstream code addresses points by the
    `(osm_id, type)` pair directly rather than through this table.
- **doit wiring**: `file_dep=[huts.geojson, stations.geojson, parking.geojson, config]`,
  `targets=[start_points.npy, start_points_id_table.json]`.
