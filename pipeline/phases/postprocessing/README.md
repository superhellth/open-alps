# phases/postprocessing/ — package for the browser app

Builds the static assets `huts/`'s `GraphPage.jsx`/`App.jsx` actually fetch: vector tiles (too
large to ship as plain GeoJSON) plus small JSON sidecars for hover/UI data that PMTiles can't
serve on its own.

## `build_trail_tiles.py` — the raw trail network as vector tiles

Ships the *full* raw OSM trail network (26.5M nodes for AT+Bayern — the reason this can't be
plain GeoJSON) as one static PMTiles archive, rendered client-side via `protomaps-leaflet` behind
an opt-in toggle in `GraphPage.jsx` (`TrailTilesLayer`).

1. `osmium export trails.osm.pbf --geometry-types=linestring -f geojsonseq -o -` piped directly
   (no intermediate file) into a Python filter loop.
2. The filter loop (using `orjson` — the one pure-Python bottleneck in this script, everything
   else is C/C++) strips every feature's properties down to just `highway`, streaming
   `data/osm/trails.geojsons` (newline-delimited GeoJSON).
3. `tippecanoe -o trails.mbtiles -l trails -Z<min> -z<max> --drop-densest-as-needed --force
   trails.geojsons` (zoom range from `config.trailTiles.minZoom/maxZoom`) — builds a standard
   zoom-pyramid MBTiles archive, `--drop-densest-as-needed` thinning dense areas at low zoom
   rather than failing on tile-size limits.
4. `pmtiles.convert.mbtiles_to_pmtiles(trails.mbtiles, trails.pmtiles, max_zoom)` — repacks the
   sqlite-based MBTiles into a single flat-file PMTiles archive, readable via HTTP range requests
   with no server-side logic (no tile server needed — see "Rejected" note below).
5. Deletes the intermediate `.geojsons`/`.mbtiles` files.

On Windows, `tippecanoe` (no conda-forge win-64 build) runs via `lib.pipeline.run_tippecanoe()`,
which shells out through WSL to a separate linux-64 micromamba env (see `pipeline/README.md`
"tippecanoe on Windows").

- **doit wiring**: `file_dep=[trails.osm.pbf]`, `targets=[trails.pmtiles]`.

### Rejected: a dynamic tile server

A dynamic tile server (martin, tegola, tileserver-gl) was considered for serving `trails.osm.pbf`
and rejected: this project has no backend by design (see root `CLAUDE.md`), and standing one up
means new hosting/TLS/uptime to maintain, not just a build step. A static PMTiles file served
alongside the rest of the app, with zoom-dependent detail via the tile pyramid, gets the same
effective result with zero extra infrastructure.

## `build_edge_tiles.py` — hut/start edges as tiles + stats

One script, invoked twice by `dodo.py` (`--edges-dir`/`--layer-name` swapped) — once over
`hut_edges/`, once over `start_edges/` — splitting each edge set's `records.npy`/`geometry.npy`/
`profiles.npy` (post-`add_elevation.py`) into two smaller app-facing assets instead of shipping the
raw binary arrays directly.

- **Per edge** (`edge_id` = array index into `records.npy`): writes a tiling-input feature
  stripped to just `{edge_id}` properties, plus computes an iterative/vectorized
  Ramer-Douglas-Peucker simplification (`rdp_keep_indices()`, tolerance =
  `config.hutEdgeTiles.hoverSimplifyToleranceDeg`, default ~0.0003° / ~11m) — a much smaller
  geometry used only for hover hit-testing, kept separate from the full-resolution tile geometry.
- **`build_stats()`** — writes one JSON array indexed by `edge_id`, holding everything
  non-geometric the app's hover UI needs: `from_hut_id, to_hut_id, distance_m, road_m, ascent_m,
  descent_m, elevation_profile, sac_scale, via_ferrata`, plus the RDP-simplified `positions`
  (`[lng, lat]` pairs). This exists because PMTiles has no feature-level query API — a rendered
  tile can be drawn, but there's no "give me properties for edge N" lookup, so the app needs this
  separate flat JSON copy for hover. `from_hut_id`/`to_hut_id` are resolved from the numeric
  `(type, id)` pair stored in `records.npy` back to their original string/OSM id via
  `start_points_id_table.json` (huts pass through as-is — `huts.geojson` never needed a separate
  id table since hut ids are already strings).
- **`*-edges.pmtiles`** — full-resolution edge geometry, `{edge_id}`-only properties, built via the
  same tippecanoe → pmtiles-convert pipeline as `build_trail_tiles.py` above (`-l hut_edges`/`-l
  start_edges`, same `min-zoom`/`max-zoom`/`--drop-densest-as-needed`).
- Deletes intermediate `.geojsonseq`/`.mbtiles` files.
- **doit wiring**: `file_dep=[hut_edges/records.npy]` (resp. `start_edges/records.npy`),
  `targets=[hut-edges.pmtiles, hut-edge-stats.json]` (resp. `start-edges.pmtiles`,
  `start-edge-stats.json`).

## Timing

`build_edge_tiles.py` and `build_trail_tiles.py` each write one `lib/timing.py` `phase()` record
per run (`build_edge_tiles`, keyed by `layer` so the hut and access runs stay apart; and
`build_trail_tiles`), with a `StepTimer` split in the meta and a `step totals:` line at the end.
The steps separate our own Python work from the external tools: `write_tiling_input` /
`build_stats` / `write_stats` (resp. `osmium_export_filter`) vs. `tippecanoe` vs.
`mbtiles_to_pmtiles` — so a slower run says which of the three grew.
