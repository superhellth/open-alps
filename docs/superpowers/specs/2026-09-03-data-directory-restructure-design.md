# `data/` directory restructure

## Problem

`data/osm/` is a flat dumping ground: raw OSM downloads, DEM-adjacent snapping arrays, build
intermediates (`base_graph/`, `hut_edges/`, `start_edges/`, `tour_edges/`, `route_subgraphs/`),
final public outputs (`huts.geojson`, `*.pmtiles`, payload bins), and scratch files all sit at the
same top level with inconsistent hyphen/underscore naming (`hut-edge-payload.bin` next to
`hut_edges/`). `data/dem/` mixes raw provider tiles, warped intermediates, and the final merged DEM
the same way. Nine files in `data/osm/` (`oa_tours_cache.json`, `tour_oa_traces.json`,
`tour_traces.json`, `oa_id_homepage_scan.json`, `oa_corridor_spike.json`,
`austria-parking.osm.pbf`, `austria-stations.osm.pbf`, `bayern-parking.osm.pbf`,
`bayern-stations.osm.pbf`) are orphaned — not a `file_dep`/target of any current doit task, not
referenced by any script — leftovers from an abandoned OA-scraping approach to official-tour
ingestion, superseded by the hand-curated GPX tour-folder approach (see
[Tour Folder Ingestion](2026-08-30-tour-folder-ingestion-design.md)).

`data/analysis/` is already a clean, consistently-used tier (every `pipeline/analysis/*.py` script
writes there) and is out of scope for this restructure.

## Goals

- Two top-level tiers under `data/`: `raw/` (fetched, external) and `build/` (computed,
  pipeline-internal), leaving `data/analysis/`, `data/timings.jsonl`, `data/.doit.json.db`
  untouched at the top level.
- Inside `data/build/`, one subdirectory per graph component, grouping files by what they *are*
  (e.g. everything about hut-edges together) rather than by which pipeline stage produced them —
  today's `postprocessing.py` writes `hut-edges.pmtiles`/`hut-edge-payload.bin`/etc. while
  `graph_building.py` writes `hut_edges/records.npy`, and those belong together.
- A consistent naming convention inside `data/build/`, enforced by this document and code review
  (no automated check — see "Non-goals").
- Delete the nine orphaned files.
- Zero change to `huts/public/data/` file names — the public contract (`docs/tour-suggestion-payload.md`,
  everything `huts/src/` fetches by literal path) is unaffected. `copy_public_data` becomes an
  explicit `(build-relative source path, public filename)` table instead of a name-preserving copy.
- Preserve doit's dependency cache across the move — see "Migration mechanics". This is the
  highest-risk part of the change: getting it wrong makes doit believe `build_base_graph` (~4h,
  see `data/timings.jsonl`) and everything downstream needs to rerun.

## Non-goals

- No `data/output/` tier distinct from `data/build/`. Final artifacts already get copied out to
  `huts/public/data/`; a third tier would just duplicate disk usage for no benefit.
- No automated structure enforcement (lint rule, doit-level path guard). Convention + this spec is
  enough; revisit only if the mess recurs.
- No renaming inside `data/raw/` — fetched file names (`huts.geojson`, `stations.geojson`,
  `parking.geojson`, `partner_betriebe.geojson`, `austria-latest.osm.pbf`, `dem/` internals) stay
  exactly as fetched. The hyphen convention below applies only within `data/build/`.
- No changes to `data/analysis/` layout, `pipeline/tours/` (already tracked in git, not part of
  this gitignored-data reorg), or any code outside `pipeline/`.
- Historical docs (`docs/superpowers/specs/*`, `docs/superpowers/plans/*`) are not rewritten to
  match new paths — they're a dated record of decisions at the time, not live documentation.

## New layout

```
data/
  raw/                        # output of pipeline/dag/downloads.py tasks only
    osm/
      austria-latest.osm.pbf
      bayern-latest.osm.pbf
    dem/                      # unchanged internally, moved wholesale under raw/
      fetch_manifest.json
      raw/
      at_bev_warped/
      bavaria_dgm_warped/
      region_0_copernicus-glo-30.vrt
      region_0_copernicus-glo-30_normalized.tif
      region_0_copernicus-glo-30_normalized.vrt
      region_1_bavaria-dgm5.vrt (+ _normalized.tif/.vrt)
      region_2_at-bev-dgm.vrt (+ _normalized.tif/.vrt)
      dem.tif
      dem.vrt
    huts.geojson
    partner_betriebe.geojson
    stations.geojson
    parking.geojson

  build/                      # everything computed, by graph component
    trails/
      austria-trails.osm.pbf
      bayern-trails.osm.pbf
      trails.osm.pbf
      verify-trails.stamp
      trails.pmtiles
    hub-range/
      hub-range.geojson
    start-points/
      start-points.npy
      start-points-id-table.json
    base-graph/
      manifest.json
      nodes.npy
      edges.npy
      cell-index.npy
      interior.npy
      interior-ele.npy
      node-ele.npy
      node-edge-ids.npy
      node-edge-index.npy
      edge-profiles.stamp
    snapping/
      hub-snaps.npy
      hub-snap-interior.npy
      unsnapped-huts.json
    route-subgraphs/
      manifest.json
      <per-hub shards, unchanged internal naming>
    access-edges/
      access-distances.npy
      selected-access-pairs.npy
    hut-edges/
      records.npy
      profiles.npy
      geometry.npy
      edge-ids.npy
      pmtiles
      stats.json
      geometry.bin
      geometry.json
      payload.bin
      payload.json
      ids.bin
      ids.json
    start-edges/
      records.npy
      profiles.npy
      geometry.npy
      pmtiles
      stats.json
      geometry.bin
      geometry.json
      approaches.bin
      approaches.json
    tour-edges/
      records.npy
      profiles.npy
      geometry.npy
      tour-meta.npy
      pmtiles
      stats.json
      geometry.bin
      geometry.json
      payload.bin
      payload.json
      tours.json
      tour-match-gaps.json

  analysis/                   # unchanged
  timings.jsonl                # unchanged
  .doit.json.db                # unchanged location, contents migrated (see below)
```

## Naming convention (scoped to `data/build/`)

- Hyphens, not underscores, for multi-word names (`hub-range.geojson`, not `hub_range.geojson`).
- Drop the redundant entity-name prefix on a file inside its own component directory: the
  directory already supplies that context, so `hut-edges/pmtiles` and `hut-edges/stats.json`, not
  `hut-edges/hut-edges.pmtiles` and `hut-edges/hut-edge-stats.json`. This only applies to files
  that were previously prefixed with the component name at the flat `data/osm/` level — internal
  array files that were already unprefixed (`records.npy`, `profiles.npy`, `geometry.npy`) keep
  their names.
- `data/raw/` is exempt — see "Non-goals".

## Full path mapping

| Old path (`data/osm/...` unless noted) | New path (`data/...`) |
|---|---|
| `raw/austria-latest.osm.pbf` | `raw/osm/austria-latest.osm.pbf` |
| `raw/bayern-latest.osm.pbf` | `raw/osm/bayern-latest.osm.pbf` |
| `huts.geojson` | `raw/huts.geojson` |
| `partner_betriebe.geojson` | `raw/partner_betriebe.geojson` |
| `stations.geojson` | `raw/stations.geojson` |
| `parking.geojson` | `raw/parking.geojson` |
| `dem/` (whole subtree, unchanged internally) | `raw/dem/` |
| `austria-trails.osm.pbf` | `build/trails/austria-trails.osm.pbf` |
| `bayern-trails.osm.pbf` | `build/trails/bayern-trails.osm.pbf` |
| `trails.osm.pbf` | `build/trails/trails.osm.pbf` |
| `verify_trails.stamp` | `build/trails/verify-trails.stamp` |
| `trails.pmtiles` | `build/trails/trails.pmtiles` |
| `hub_range.geojson` | `build/hub-range/hub-range.geojson` |
| `start_points.npy` | `build/start-points/start-points.npy` |
| `start_points_id_table.json` | `build/start-points/start-points-id-table.json` |
| `base_graph/*` (all 10 files, names unchanged apart from underscore→hyphen) | `build/base-graph/*` |
| `hub_snaps.npy` | `build/snapping/hub-snaps.npy` |
| `hub_snap_interior.npy` | `build/snapping/hub-snap-interior.npy` |
| `unsnapped_huts.json` | `build/snapping/unsnapped-huts.json` |
| `route_subgraphs/*` | `build/route-subgraphs/*` (unchanged internally) |
| `access_distances.npy` | `build/access-edges/access-distances.npy` |
| `selected_access_pairs.npy` | `build/access-edges/selected-access-pairs.npy` |
| `hut_edges/records.npy`, `profiles.npy`, `geometry.npy`, `edge_ids.npy` | `build/hut-edges/records.npy`, `profiles.npy`, `geometry.npy`, `edge-ids.npy` |
| `hut-edges.pmtiles` | `build/hut-edges/pmtiles` |
| `hut-edge-stats.json` | `build/hut-edges/stats.json` |
| `hut-edge-geometry.bin` / `.json` | `build/hut-edges/geometry.bin` / `.json` |
| `hut-edge-payload.bin` / `.json` | `build/hut-edges/payload.bin` / `.json` |
| `hut-edge-ids.bin` / `.json` | `build/hut-edges/ids.bin` / `.json` |
| `start_edges/records.npy`, `profiles.npy`, `geometry.npy` | `build/start-edges/records.npy`, `profiles.npy`, `geometry.npy` |
| `start-edges.pmtiles` | `build/start-edges/pmtiles` |
| `start-edge-stats.json` | `build/start-edges/stats.json` |
| `start-edge-geometry.bin` / `.json` | `build/start-edges/geometry.bin` / `.json` |
| `approaches.bin` / `.json` | `build/start-edges/approaches.bin` / `.json` |
| `tour_edges/records.npy`, `profiles.npy`, `geometry.npy`, `tour_meta.npy` | `build/tour-edges/records.npy`, `profiles.npy`, `geometry.npy`, `tour-meta.npy` |
| `tour-edges.pmtiles` | `build/tour-edges/pmtiles` |
| `tour-edge-stats.json` | `build/tour-edges/stats.json` |
| `tour-edge-geometry.bin` / `.json` | `build/tour-edges/geometry.bin` / `.json` |
| `tour-edge-payload.bin` / `.json` | `build/tour-edges/payload.bin` / `.json` |
| `tours.json` | `build/tour-edges/tours.json` |
| `tour-match-gaps.json` | `build/tour-edges/tour-match-gaps.json` |
| `oa_tours_cache.json`, `tour_oa_traces.json`, `tour_traces.json`, `oa_id_homepage_scan.json`, `oa_corridor_spike.json` | **deleted** (orphaned) |
| `austria-parking.osm.pbf`, `austria-stations.osm.pbf`, `bayern-parking.osm.pbf`, `bayern-stations.osm.pbf` | **deleted** (orphaned) |

`data/analysis/*`, `data/timings.jsonl` unchanged.

## Code changes

- `pipeline/lib/pipeline.py`: replace `OSM_DIR`/`DEM_DIR` with `RAW_DIR = DATA_DIR / "raw"`,
  `BUILD_DIR = DATA_DIR / "build"`, plus the per-component constants each `dag/*.py` file needs
  (`RAW_OSM_DIR`, `RAW_DEM_DIR`, `TRAILS_DIR`, `BASE_GRAPH_DIR`, `HUT_EDGES_DIR`, etc. — exact set
  decided during implementation, mirroring today's single-constant-per-file pattern).
- Every `pipeline/dag/*.py` (`downloads.py`, `preprocessing.py`, `elevation.py`,
  `graph_building.py`, `postprocessing.py`) and `pipeline/analysis/*.py`: update `file_dep`/
  `targets`/default-arg paths to the new constants and mapping table above.
- `pipeline/dodo.py`: `PUBLIC_FILES` becomes a list of `(build_path: Path, public_name: str)`
  pairs; `copy_public_data` copies `BUILD_DIR / build_path` (or `RAW_DIR / build_path` for the
  four fetched geojson files) to `PUBLIC_DATA_DIR / public_name`.
- `pipeline/tests/test_dodo_wiring.py`, `pipeline/tests/test_match_tour_edges.py`: update any
  hardcoded old-style paths.
- Docs: update `CLAUDE.md` (root), `pipeline/CLAUDE.md`, `docs/tour-suggestion-payload.md` — the
  three living docs with hardcoded `data/osm/...`/`data/dem/...` paths.

## Migration mechanics

This is the part most likely to go wrong, so it gets its own section.

`data/.doit.json.db` is a JSON file keyed by task name; each task's entry maps every tracked
relative path string (e.g. `"../data/osm/huts.geojson"`) to `[mtime, size, checksum]` plus a
`"deps:"` list of those same path strings. doit's `MD5Checker` considers a task up to date only if
every dep/target path in the *current* `dodo.py` run resolves to an entry with a matching checksum
in this db. If a task's target path changes but the db isn't updated to match, doit sees "no record
for this path" and reruns the task — for `build_base_graph` and friends that's hours, cascading to
everything downstream.

A pure filesystem move (`os.rename`/`shutil.move` on the same filesystem) preserves both mtime and
content (hence checksum), so the fix is a single migration script, run once, that in one pass:

1. Creates the new `data/raw/`, `data/build/` tree.
2. Moves every file per the mapping table above (`os.rename`, not copy — cheap, no need to touch
   58GB+ of data twice).
3. Deletes the nine orphaned files.
4. Rewrites `data/.doit.json.db`: for every task entry, for every key/`"deps:"` entry that matches
   an old path in the mapping table, replace the string with the new path, keeping the
   `[mtime, size, checksum]` value untouched.
5. Removes the now-empty `data/osm/` and `data/dem/` directories.

This script must land in the **same commit** as the `dodo.py`/`dag/*.py` path constant changes —
the physical layout and doit's declared targets must agree at every commit, since `data/` isn't
tracked in git and there's no way to "check out" a prior physical layout to match an older commit.

**Verification, before treating the migration as done:** run `doit list` and a dry-run (`doit -n`
or equivalent — never bare `doit`, per root `CLAUDE.md`'s pipeline-task warning) and confirm zero
tasks are reported as needing to run. If any task shows as stale, stop and fix the db rewrite before
touching anything else — do not let a stale-task report trigger an actual `doit` run to "see what
happens."

**Rollback safety:** back up `data/.doit.json.db` before step 4 (it's 20KB, trivial). If the moves
in steps 2-3 fail partway, they're individually resumable/idempotent (re-run only moves files still
at their old path); the risk is entirely in step 4's db rewrite, which is why it's backed up
separately and verified before anything is deleted.

## Testing

- `pipeline/tests/test_dodo_wiring.py` (and any other test asserting on `dodo.py` task
  paths/targets) updated to the new paths — this is the automated check that the new layout stays
  wired correctly, even though there's no separate structure-enforcement mechanism per "Non-goals."
- After migration, `doit list`/dry-run showing zero stale tasks (see above) is the acceptance test
  for the migration itself — no pipeline task is run as part of verifying this change.
