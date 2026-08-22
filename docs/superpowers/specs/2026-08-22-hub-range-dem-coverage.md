# Hub-range trail/DEM coverage spec

Date: 2026-08-22
Status: draft, for planning
Trigger: `add_base_elevation` crashed (`rasterio.errors.WindowError: Intersection is empty`) on a
real Task 9 rebuild — a base-graph cell near an outlying hut in the Bavarian Forest had trail nodes
but zero DEM coverage. Root-caused during that debugging session; this spec is the fix.

## Problem

`build_base_graph` (V2 architecture, `pipeline/CLAUDE.md`) streams and contracts the **entire**
AT+Bayern trail network from the raw OSM extract, independent of any hub set. `add_base_elevation`
then needs real elevation everywhere that graph has nodes. But DEM coverage is fetched separately,
per `dem.provider` in `pipeline.config.json`:

- `at-bev-dgm` downloads one fixed nationwide Austria GeoTIFF — always full coverage, `bbox`/
  `points` config is inert for it (`at_bev.py`'s `fetch()` ignores both).
- `bavaria-dgm5` (`bavaria_dgm.py`) is tile-per-request. `composite.py`'s `bboxFromHuts: true`
  narrows its fetch to `_points_for_region()`'s huts (or trail-edge vertices, when available) plus
  a small `bufferKm` (config: `1.5`, read correctly by `bavaria_dgm.fetch()` — an earlier
  suspicion that a `bufferDeg`/`bufferKm` key mismatch was in play turned out to be dead code for
  this path, since `points` takes priority over `bbox` in `fetch()`).

`bboxFromHuts` predates the V2 base graph. It was sized for a world where DEM sampling only needed
to cover per-hub query ranges (originally: real trail-edge vertices from a prior hub-edge pass,
buffered by ~1.5km for "trail wanders a bit past a sampled vertex"). V2's base graph has trail data
everywhere in both countries, regardless of hut proximity, and `_points_for_region()`'s fallback to
bare hut points (since `hut-edges.geojson`, the V1 artifact it prefers, no longer exists) leaves a
1.5km buffer around isolated hut markers — nowhere near enough for trails tens of km away, which is
routine (AVT huts cluster in the Alps; the base graph also includes non-alpine trail networks like
the Bavarian Forest).

**Constraint (stated by the user during design):** no graceful "skip and flag missing elevation"
fallback. Every trail edge the base graph keeps must get real elevation from a configured source.
Coverage must be arranged so gaps don't occur, not tolerated when they do.

## Already done (this session, committed `fb34f4e`)

`compute_hub_range` (new task) computes a **rectangular bbox** — every hut's bounding box padded
by `graph.maxEdgeKm` (30km) — and `filter_trails.py` clips each region's tag-filtered extract to it
via `osmium extract --bbox` before `merge_trails`. Rationale for the bound itself (not the shape):
no trail farther than `maxEdgeKm` beeline from every hut can ever appear on a valid hut-to-hut/
hut-to-start edge, since `build_hub_edges`'s real-distance cutoff is always ≥ beeline distance —
the same argument `filter_start_points.py` already applies to station/parking points.

**This alone is insufficient.** A rectangle is a *looser* test than "within `maxEdgeKm` of some
hut": corners and gaps between hut clusters can be farther from any single hut than `maxEdgeKm`
while still sitting inside the rectangle. If `bavaria-dgm5`'s DEM fetch used a tighter per-hut
circle buffer (even one sized to `maxEdgeKm`), some rectangle-admitted trail nodes could still fall
outside it — the same class of crash, rarer but not gone. The trail-side shape and the DEM-side
shape must be the *same* test, not independently-sized approximations of it.

## Design

Replace the rectangle on both sides with the same shape: **the union of a `maxEdgeKm`-radius
circle around every hut.** Same underlying math as `filter_start_points.py`, applied as a shape
instead of a per-point predicate.

### C1. `compute_hub_range` emits a polygon, not a bbox

- New dependency: `shapely` (not currently installed in the `alpen-osm` env — add via
  `conda install -c conda-forge shapely`, document in `pipeline/README.md`'s Setup section).
- For every hut point, `shapely.geometry.Point(lng, lat).buffer(radius_deg)`; `radius_deg =
  maxEdgeKm * safety_margin * deg_per_km` (see C4 for `safety_margin`). `shapely.unary_union` the
  circles into one (Multi)Polygon.
- Write it in a format `osmium extract --polygon` accepts. **Open question, verify before
  committing to it:** osmium-tool's `--polygon` supports the Osmosis `.poly` text format, GeoJSON,
  and WKT depending on version/build — confirm which one this environment's `osmium` reads
  correctly with a throwaway smoke test before wiring it into `dodo.py`. `data/osm/hub_range.json`
  (current bbox artifact) becomes `data/osm/hub_range.poly` or `.geojson` accordingly.
- Buffering in degrees (not metres) distorts circles into ellipses away from the equator (lng
  degrees shrink with `cos(lat)`) — at ~47-50°N this flattens the "circle" noticeably
  east-west. Over-inclusion (a fatter shape than intended) is harmless here — it only means
  keeping a few more trail nodes/DEM tiles than strictly required, never dropping ones that
  should stay in. **Do not equal-area-project to fix this** - it's extra complexity for a
  direction that fails safe.

### C2. `filter_trails.py`: `--polygon` instead of `--bbox`

One-line change to the existing `osmium extract` call (`-p <file>` instead of `-b <bbox>`).
`--strategy complete_ways` (osmium's default, already relied on) still applies — a way with any
node inside the polygon is kept whole, never cut through.

### C3. `bavaria-dgm5`: buffer radius matches, `bufferKm` config value updated

`bavaria_dgm.fetch()`'s points-based path (`tiles_for_points(points, buffer_km)`) already does
per-point circular buffering — it's the *right* mechanism, just the wrong radius. Change
`pipeline.config.json`'s `dem.providerConfig.regions[bavaria-dgm5].bufferKm` from `1.5` to
`maxEdgeKm * safety_margin` (see C4), computed the same way `compute_hub_range` computes its
polygon radius so the two can't drift apart independently (ideally: both read the same config
value/derivation, not two hand-typed numbers — ties into F below).

`composite.py`'s `_points_for_region()` still prefers `hut-edges.geojson` (doesn't exist in V2,
falls back to bare hut points) - unaffected by this change, already correct for the fallback case.

### C4. Safety margin

`compute_hub_range`'s polygon radius and `bavaria-dgm5`'s tile buffer must use the **same or a
larger** radius than the trail-inclusion test, never smaller, or C1-vs-C3 reintroduces exactly the
mismatch this spec exists to close. Recommend a small multiplicative margin (e.g. `1.05`x) on the
DEM-fetch side specifically, absorbing:
- degrees-vs-metres distortion (C1) if the two radii are computed independently rather than shared,
- floating-point/geodesic approximation error in `deg_per_km`,
- `tiles_for_points`'s own tile-grid quantization (whole 1km tiles - a hut circle's edge can fall
  mid-tile; the tile is either fully in or fully out).

Exact numeric margin is an implementation-time judgment call, not fixed by this spec — pick a value
and confirm empirically (rerun `add_base_elevation` clean afterward - the only real test).

### D. Residual cross-border gap: Copernicus GLO-30 as a floor

A hut close enough to a border that its `maxEdgeKm` circle crosses into a third country neither
`at-bev-dgm` nor `bavaria-dgm5` covers is not fixed by any bbox/radius tuning on either of those
two national sources - it's a genuine data-source gap. `copernicus.py` (30m global, AWS Open Data,
`dem_providers/__init__.py`'s registry already has it as `"copernicus-glo-30"`) is already a
complete, working provider — `dem.source` in `pipeline.config.json` even still names it, vestigial
from before `composite` existed.

Add it as a **third composite region**, full nominal `bbox` (not hut-buffered - it's the floor, not
a targeted fetch), listed **first** in `providerConfig.regions`:

```jsonc
"regions": [
  { "provider": "copernicus-glo-30", "bbox": { /* full nominal bbox */ } },
  { "provider": "bavaria-dgm5", "bbox": {...}, "bboxFromHuts": true, "bufferKm": <maxEdgeKm * margin> },
  { "provider": "at-bev-dgm", "bbox": {...} }
]
```

`composite.py`'s module docstring: `gdalbuildvrt` takes the **last**-listed source for overlapping
pixels. Listing Copernicus first makes it lowest-priority - painted over by both national sources
wherever they have real data, visible only in gaps neither reaches. Resolution drops to 30m only in
that thin residual sliver, never a crash.

Cost: one more full-bbox fetch (whole-degree tiles, `~9-12` tiles for this bbox based on its
degree-span - cheap relative to the two national sources already being fetched).

## Non-goals

- No graceful `add_base_elevation` fallback for zero-DEM-coverage cells (explicit user constraint -
  every real gap must be closed by coverage, not tolerated by degrading data).
- No change to `at-bev-dgm` - already unconditional/full-country, already a superset of anything
  hub-range-shaped on the Austria side.
- Not narrowing `hub_range`/the base graph down to whatever DEM already happens to cover - that
  direction was considered and rejected (it silently drops real, routable trail data instead of
  fixing coverage; see conversation leading to this spec).

## Open questions / verify during implementation

1. Exact `osmium extract --polygon` file format this environment's osmium-tool version reads
   (poly/GeoJSON/WKT) - smoke-test before wiring into `dodo.py`.
2. `shapely` needs adding to the `alpen-osm` conda env and `pipeline/README.md`'s Setup section.
3. Exact safety-margin multiplier for C4 (start at 1.05x, confirm empirically against a clean
   `add_base_elevation` run - no `WindowError`, and no or negligible new node/interior-point misses
   at the very edge of the shape).
4. Whether `compute_hub_range`'s polygon radius and `bavaria-dgm5`'s `bufferKm` should be unified
   into one config-derived value rather than two independently-set numbers that happen to agree
   today - recommended, not required by this spec; flagged so implementation doesn't reintroduce
   the "two numbers, one drifts" failure mode this whole investigation started from.
5. `composite.py`'s `_resolve_region_bbox`/`bufferDeg` path is dead code for any region using
   `bboxFromHuts` (points always wins in `bavaria_dgm.fetch()`) - worth a cleanup pass, out of
   scope for this spec.
