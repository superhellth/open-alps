# phases/postprocessing/ — package for the browser app

Builds the static assets `huts/`'s `AdminPage.tsx`/`TourSearchPage.tsx` actually fetch: vector tiles (too
large to ship as plain GeoJSON) plus small JSON sidecars for hover/UI data that PMTiles can't
serve on its own.

## `build_trail_tiles.py` — the raw trail network as vector tiles

Ships the *full* raw OSM trail network (26.5M nodes for AT+Bayern — the reason this can't be
plain GeoJSON) as one static PMTiles archive, rendered client-side via `protomaps-leaflet` behind
an opt-in toggle in `AdminPage.tsx` (`TrailTilesLayer`).

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

## `build_edge_tiles.py` — hut/start/tour edges as tiles + stats

One script, invoked three times by `dodo.py` (`--edges-dir`/`--layer-name` swapped) — once over
`hut_edges/`, once over `start_edges/`, once over `tour_edges/` — splitting each edge set's
`records.npy`/`geometry.npy`/`profiles.npy` (post-`elevation/compute_edge_profiles.py`+
`build_profiles.py`) into three smaller app-facing assets instead of shipping the raw binary arrays
directly.

- **Per edge** (`edge_id` = array index into `records.npy`): writes a tiling-input feature
  stripped to just `{edge_id}` properties, plus computes an iterative/vectorized
  Ramer-Douglas-Peucker simplification (`rdp_keep_indices()`, tolerance =
  `config.hutEdgeTiles.hoverSimplifyToleranceDeg`, default ~0.0003° / ~11m) — a much smaller
  geometry used only for hover hit-testing, kept separate from the full-resolution tile geometry.
- **`build_stats()`** — writes one JSON array indexed by `edge_id`, holding everything
  non-geometric, non-elevation the app's hover UI needs: `from_hut_id, to_hut_id, distance_m,
  road_m, ascent_m, descent_m, sac_scale, via_ferrata`. This exists because PMTiles has no
  feature-level query API — a rendered tile can be drawn, but there's no "give me properties for
  edge N" lookup, so the app needs this separate flat JSON copy for hover. `from_hut_id`/
  `to_hut_id` are resolved from the numeric `(type, id)` pair stored in `records.npy` back to
  their original string/OSM id via `start_points_id_table.json` (huts pass through as-is —
  `huts.geojson` never needed a separate id table since hut ids are already strings). The
  RDP-simplified hover geometry and the elevation profile are both written separately (below), not
  inlined into this JSON.
- **`*-edge-geometry.bin`/`*-edge-geometry.json`** — the RDP-simplified `positions` per edge,
  split out of `build_stats()`'s output into their own byte-packed sidecar: a flat `f4` `[lng,
  lat]` array (`.bin`) plus a `point_counts` array (`.json`) giving each edge's slice length in
  order, since a plain JSON array of coordinate pairs per edge would repeat the same nesting
  overhead `hut-edge-stats.json` was designed to avoid.
- **`*-edge-elevation.bin`/`*-edge-elevation.json`** — the point-by-point elevation profile per
  edge, split out of `build_stats()`'s output the same way `positions` is: a flat `f4` array of
  every edge's elevation values back to back in `edge_id` order (`.bin`) plus a `profile_counts`
  array giving each edge's slice length in order (`.json`) — same prefix-sum-offset shape as
  `point_counts`, kept as a separately-named field since geometry point count (RDP-simplified) and
  elevation sample count (fixed at `config.dem.profilePoints`, 0 for a degenerate edge) are
  different quantities.
- **`*-edges.pmtiles`** — full-resolution edge geometry, `{edge_id}`-only properties, built via the
  same tippecanoe → pmtiles-convert pipeline as `build_trail_tiles.py` above (`-l hut_edges`/`-l
  start_edges`, same `min-zoom`/`max-zoom`/`--drop-densest-as-needed`).
- Deletes intermediate `.geojsonseq`/`.mbtiles` files.
- **doit wiring**: `file_dep=[hut_edges/records.npy]` (resp. `start_edges/records.npy`,
  `tour_edges/records.npy`), `targets=[hut-edges.pmtiles, hut-edge-stats.json,
  hut-edge-geometry.bin, hut-edge-geometry.json, hut-edge-elevation.bin, hut-edge-elevation.json]`
  (resp. `start-edge-*`, `tour-edge-*`).

## `build_approach_table.py` — approach/exit table + loop-closure reverse index

Reduces `start_edges/records.npy` (92,426 records over 27,261 parkings + 3,025 stations for
AT+Bayern — neither shippable nor seedable as-is) to two things, written into `approaches.bin`/
`approaches.json`:

1. **Duration/source-type/variant matrix** (`--duration-buckets-h`/`--variants`, default
   `config.approach.durationBucketsH`/`config.approach.variants`) — every candidate is bucketed
   into a `(source_type, variant, duration_bucket)` cell and the fastest candidate per non-empty
   cell is kept; no top-k, no reserved-slot overwrite. `maxApproachTime` is not reintroduced (root
   `CLAUDE.md`) — an approach is bounded by the same `maxEdgeKm` range cap as any hut-hut edge,
   filtered client-side.
2. **Loop-closure reverse index** — the client's car mode requires exit start-point == entry
   start-point, and a tour's first and last hut's approach-table rows essentially never share a
   start id, so a post-filter would annihilate the result set. Every `start_edges` record whose
   start point appears in *any* hut's retained approach ships too (all variants, since closure
   needs whatever the client already has open), keyed both hut→starts and start→huts.

- **doit wiring**: `file_dep=[start_edges/records.npy, start_points_id_table.json]`,
  `targets=[approaches.bin, approaches.json]`.

## `build_edge_payload.py` — pack + ship the hut-edge payload

Packs `hut_edges/records.npy` into the columnar binary the client loads once, up front (never
per-edge, unlike geometry — that stays lazily fetched from `hut-edges.pmtiles`, and no duration
column ships: the client computes DIN itself at load from `distance_m`/`ascent_m`/`descent_m`,
spec D3). Columns laid out per-column, not interleaved, so gzip sees each column's own byte
pattern uninterrupted; hut ids narrow `RECORD_DTYPE`'s `i8` down to `u2` (well under 65,536 huts).
Measured, not assumed (`data/analysis/payload_sizing.json`): 3 variants × 6,067 edges × 13 columns
= 693 KB raw, 43.4 KB gzipped — a byte-shuffle filter made it *worse* (46.4 KB), so this doesn't
add one; quantisation is out of scope on the same measurement.

- **doit wiring**: `task_dep=[build_profiles]` (records.npy's `profile_offset`/`profile_count` are
  rewritten in place, not a declared target — see `build_edge_tiles.py`'s comment above),
  `file_dep=[hut_edges/records.npy, huts.geojson]`,
  `targets=[hut-edge-payload.bin, hut-edge-payload.json]`.

## Timing

`build_edge_tiles.py` and `build_trail_tiles.py` each write one `lib/timing.py` `phase()` record
per run (`build_edge_tiles`, keyed by `layer` so the hut and access runs stay apart; and
`build_trail_tiles`), with a `StepTimer` split in the meta and a `step totals:` line at the end.
The steps separate our own Python work from the external tools: `write_tiling_input` /
`build_stats` / `write_stats` (resp. `osmium_export_filter`) vs. `tippecanoe` vs.
`mbtiles_to_pmtiles` — so a slower run says which of the three grew.
