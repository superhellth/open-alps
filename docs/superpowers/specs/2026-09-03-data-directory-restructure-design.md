# `data/` directory restructure

## Problem

`data/osm/` is a flat dumping ground: raw OSM downloads, DEM-adjacent snapping arrays, build
intermediates (`base_graph/`, `hut_edges/`, `start_edges/`, `tour_edges/`, `route_subgraphs/`),
final public outputs (`huts.geojson`, `*.pmtiles`, payload bins), and scratch files all sit at the
same top level with inconsistent hyphen/underscore naming (`hut-edge-payload.bin` next to
`hut_edges/`). `data/dem/` mixes raw provider tiles, warped intermediates, and the final merged DEM
the same way. Orphaned files — not a `file_dep`/target of any current doit task, not referenced by
any script — sit among them (listed under "Deleted files").

`data/analysis/` is already a clean, consistently-used tier (every `pipeline/analysis/*.py` script
writes there) and `data/quality/` is the output tier of `dag/quality.py` (`QUALITY_DIR`); both are
out of scope for this restructure.

## Goals

- Two top-level tiers under `data/`: `raw/` (fetched, external) and `build/` (computed,
  pipeline-internal), leaving `data/analysis/`, `data/quality/`, `data/timings.jsonl`,
  `data/.doit.json.db` untouched at the top level.
- Inside `data/build/`, one subdirectory per graph component, grouping files by what they *are*
  (e.g. everything about hut-edges together) rather than by which pipeline stage produced them —
  today's `postprocessing.py` writes `hut-edges.pmtiles`/`hut-edge-payload.bin`/etc. while
  `graph_building.py` writes `hut_edges/records.npy`, and those belong together.
- A consistent naming convention inside `data/build/`, enforced by this document and code review
  (no automated check — see "Non-goals").
- Delete the orphaned files.
- Zero change to `huts/public/data/` file names — the public contract (`docs/tour-suggestion-payload.md`,
  everything `huts/src/` fetches by literal path) is unaffected. `copy_public_data` becomes an
  explicit `(source path, public filename)` table instead of a name-preserving copy.
- Preserve doit's dependency cache across the move — see "Migration mechanics". This is the
  highest-risk part of the change: getting it wrong makes doit believe `build_base_graph` (~4h,
  see `data/timings.jsonl`) and everything downstream needs to rerun.

## Non-goals

- No `data/output/` tier distinct from `data/build/`. Final artifacts already get copied out to
  `huts/public/data/`; a third tier would just duplicate disk usage for no benefit.
- No automated structure enforcement (lint rule, doit-level path guard). Convention + this spec is
  enough; revisit only if the mess recurs.
- No renaming inside `data/raw/` — fetched file names (`huts.geojson`, `stations.geojson`,
  `parking.geojson`, `partner_betriebe.geojson`, `austria-latest.osm.pbf`, `austria.poly`,
  `dem/` internals) stay exactly as fetched. The hyphen convention below applies only within
  `data/build/`.
- No changes to `data/analysis/` or `data/quality/` layout, `pipeline/tours/` (already tracked in
  git, not part of this gitignored-data reorg), or the public-data contract `huts/` consumes. The
  one exception is the dev-only GPX editor's direct `hubs.json` read (see "Code changes").
- Historical docs (`docs/superpowers/specs/*`, `docs/superpowers/plans/*`) are not rewritten to
  match new paths — they're a dated record of decisions at the time, not live documentation.
- Stale files in `huts/public/data/` (gitignored copies of files no longer in `PUBLIC_FILES`, e.g.
  `tour-edge-payload.*`, `tour-fetch-gaps.json`) are not touched by this change.

## New layout

```
data/
  raw/                        # output of pipeline/dag/downloads.py tasks only
    osm/
      austria-latest.osm.pbf
      austria.poly
      bayern-latest.osm.pbf
      bayern.poly
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
      edges.pmtiles
      stats.json
      geometry.bin
      geometry.json
      elevation.bin
      elevation.json
      payload.bin
      payload.json
      ids.bin
      ids.json
    start-edges/
      records.npy
      profiles.npy
      geometry.npy
      edge-ids.npy
      edges.pmtiles
      stats.json
      geometry.bin
      geometry.json
      elevation.bin
      elevation.json
      ids.bin
      ids.json
      approaches.bin
      approaches.json
    tour-edges/
      records.npy
      profiles.npy
      geometry.npy
      edges.pmtiles
      stats.json
      geometry.bin
      geometry.json
      elevation.bin
      elevation.json
      tours.json
      tour-match-gaps.json
      hubs.json

  analysis/                   # unchanged
  quality/                    # unchanged
  timings.jsonl                # unchanged
  .doit.json.db                # unchanged location, contents migrated (see below)
```

`route-subgraphs/` and `snapping/` hold intermediates shared across components (route subgraphs
feed hut/start edges; snaps feed edge building), so they stay separate rather than being folded
into one edge component.

## Naming convention (scoped to `data/build/`)

- Hyphens, not underscores, for multi-word names (`hub-range.geojson`, not `hub_range.geojson`).
- Drop the redundant entity-name prefix on a file inside its own component directory: the
  directory already supplies that context, so `hut-edges/stats.json` and `hut-edges/payload.bin`,
  not `hut-edges/hut-edge-stats.json`. This only applies to files that were previously prefixed
  with the component name at the flat `data/osm/` level — internal array files that were already
  unprefixed (`records.npy`, `profiles.npy`, `geometry.npy`) keep their names.
- Keep the file extension always: the tile archives are `edges.pmtiles`, never a bare `pmtiles`,
  so editors and tools detect the type.
- `data/raw/` is exempt — see "Non-goals".

## Full path mapping

| Old path (`data/osm/...` unless noted) | New path (`data/...`) |
|---|---|
| `raw/austria-latest.osm.pbf`, `raw/austria.poly` | `raw/osm/austria-latest.osm.pbf`, `raw/osm/austria.poly` |
| `raw/bayern-latest.osm.pbf`, `raw/bayern.poly` | `raw/osm/bayern-latest.osm.pbf`, `raw/osm/bayern.poly` |
| `huts.geojson` | `raw/huts.geojson` |
| `partner_betriebe.geojson` | `raw/partner_betriebe.geojson` |
| `stations.geojson` | `raw/stations.geojson` |
| `parking.geojson` | `raw/parking.geojson` |
| `data/dem/` (whole subtree, unchanged internally) | `raw/dem/` |
| `austria-trails.osm.pbf` | `build/trails/austria-trails.osm.pbf` |
| `bayern-trails.osm.pbf` | `build/trails/bayern-trails.osm.pbf` |
| `trails.osm.pbf` | `build/trails/trails.osm.pbf` |
| `verify_trails.stamp` | `build/trails/verify-trails.stamp` |
| `trails.pmtiles` | `build/trails/trails.pmtiles` |
| `hub_range.geojson` | `build/hub-range/hub-range.geojson` |
| `start_points.npy` | `build/start-points/start-points.npy` |
| `start_points_id_table.json` | `build/start-points/start-points-id-table.json` |
| `base_graph/*` (all 10 files, underscore→hyphen) | `build/base-graph/*` |
| `hub_snaps.npy` | `build/snapping/hub-snaps.npy` |
| `hub_snap_interior.npy` | `build/snapping/hub-snap-interior.npy` |
| `unsnapped_huts.json` | `build/snapping/unsnapped-huts.json` |
| `route_subgraphs/*` | `build/route-subgraphs/*` (unchanged internally) |
| `access_distances.npy` | `build/access-edges/access-distances.npy` |
| `selected_access_pairs.npy` | `build/access-edges/selected-access-pairs.npy` |
| `hut_edges/records.npy`, `profiles.npy`, `geometry.npy`, `edge_ids.npy` | `build/hut-edges/records.npy`, `profiles.npy`, `geometry.npy`, `edge-ids.npy` |
| `hut-edges.pmtiles` | `build/hut-edges/edges.pmtiles` |
| `hut-edge-stats.json` | `build/hut-edges/stats.json` |
| `hut-edge-geometry.bin` / `.json` | `build/hut-edges/geometry.bin` / `.json` |
| `hut-edge-elevation.bin` / `.json` | `build/hut-edges/elevation.bin` / `.json` |
| `hut-edge-payload.bin` / `.json` | `build/hut-edges/payload.bin` / `.json` |
| `hut-edge-ids.bin` / `.json` | `build/hut-edges/ids.bin` / `.json` |
| `start_edges/records.npy`, `profiles.npy`, `geometry.npy`, `edge_ids.npy` | `build/start-edges/records.npy`, `profiles.npy`, `geometry.npy`, `edge-ids.npy` |
| `start-edges.pmtiles` | `build/start-edges/edges.pmtiles` |
| `start-edge-stats.json` | `build/start-edges/stats.json` |
| `start-edge-geometry.bin` / `.json` | `build/start-edges/geometry.bin` / `.json` |
| `start-edge-elevation.bin` / `.json` | `build/start-edges/elevation.bin` / `.json` |
| `start-edge-ids.bin` / `.json` | `build/start-edges/ids.bin` / `.json` |
| `approaches.bin` / `.json` | `build/start-edges/approaches.bin` / `.json` |
| `tour_edges/records.npy`, `profiles.npy`, `geometry.npy` | `build/tour-edges/records.npy`, `profiles.npy`, `geometry.npy` |
| `tour-edges.pmtiles` | `build/tour-edges/edges.pmtiles` |
| `tour-edge-stats.json` | `build/tour-edges/stats.json` |
| `tour-edge-geometry.bin` / `.json` | `build/tour-edges/geometry.bin` / `.json` |
| `tour-edge-elevation.bin` / `.json` | `build/tour-edges/elevation.bin` / `.json` |
| `tours.json` | `build/tour-edges/tours.json` |
| `tour-match-gaps.json` | `build/tour-edges/tour-match-gaps.json` |
| `hubs.json` | `build/tour-edges/hubs.json` |

`data/analysis/*`, `data/quality/*`, `data/timings.jsonl` unchanged.

### Deleted files

Each is confirmed absent from every `dag/*.py` `file_dep`/`targets` and every `phases/`/`lib/`
script (re-verify with grep immediately before deleting):

- `austria-parking.osm.pbf`, `austria-stations.osm.pbf`, `bayern-parking.osm.pbf`,
  `bayern-stations.osm.pbf`
- `tour-fetch-gaps.json` (left over from the removed `fetch_tour_oa_geometry` task)
- `tour-edge-payload.bin` / `.json` (`build_tour_edge_payload` is gone; `test_dodo_wiring.py`
  asserts these are not in `PUBLIC_FILES`)
- `tour_edges/tour_meta.npy`, `tour_edges/edge_ids.npy` (no longer targets of
  `match_tour_edges`; `test_dodo_wiring.py:243` asserts this)

### `copy_public_data` source table

`PUBLIC_FILES` (33 entries, public name = today's name) becomes `(source, public_name)` pairs; the
public name is always the pre-restructure flat name, e.g.
`(BUILD_DIR/"hut-edges"/"edges.pmtiles", "hut-edges.pmtiles")`,
`(BUILD_DIR/"snapping"/"unsnapped-huts.json", "unsnapped_huts.json")`,
`(RAW_DIR/"huts.geojson", "huts.geojson")`. Sources for the four fetched geojson files resolve
under `RAW_DIR`, the rest under `BUILD_DIR`, per the mapping table above.

## Code changes

- `pipeline/lib/pipeline.py`: replace `OSM_DIR`/`DEM_DIR` with `RAW_DIR = DATA_DIR / "raw"`,
  `BUILD_DIR = DATA_DIR / "build"`, plus per-component constants (`RAW_OSM_DIR`, `RAW_DEM_DIR`,
  `TRAILS_DIR`, `BASE_GRAPH_DIR`, `HUT_EDGES_DIR`, etc. — exact set decided during implementation).
  `QUALITY_DIR` stays.
- `pipeline/dag/*.py` (`downloads.py`, `preprocessing.py`, `elevation.py`, `graph_building.py`,
  `postprocessing.py`, `quality.py`): update `file_dep`/`targets`/CLI args to the new constants.
- **`pipeline/phases/**` scripts (largest blast radius).** Roughly 35 scripts import
  `OSM_DIR`/`DEM_DIR` or take flat-layout CLI args (`--osm-dir`, `--edges-root`, `--dem-dir`,
  `--out-dir`, default paths, and hardcoded file names such as `base_graph/node_ele.npy`). Each
  moves from "one root dir + fixed relative names" to explicit per-component dirs. `dag/quality.py`
  passes `--osm-dir {OSM_DIR}` to all five `check_*` scripts, so those CLIs change too.
- `pipeline/lib/*` helpers that resolve paths under `OSM_DIR` (`hubs.py`, `hub_snap.py`,
  `grading.py`, `cell_igraph.py`, `doit_support.py` docstrings).
- `pipeline/analysis/*.py`: update paths/default args.
- `pipeline/dodo.py`: `PUBLIC_FILES` table and `copy_public_data` as described above.
- Tests: `test_dodo_wiring.py`, `test_match_tour_edges.py`, `test_build_profiles.py`,
  `test_check_postprocessing.py`, `test_compute_hub_range_cli.py`, `test_config.py`,
  `test_doit_support.py` — update every hardcoded old-style path.
- Docs and comments naming old paths: root `CLAUDE.md`, `pipeline/CLAUDE.md`, `pipeline/README.md`,
  `pipeline/phases/**/README.md`, `pipeline/analysis/README.md`, `docs/tour-suggestion-payload.md`,
  `docs/gpx-editor.md` (`data/osm/hubs.json` → `data/build/tour-edges/hubs.json`), and the stale
  path comments in `huts/src/adminPage/TrailLayers.tsx`.
- **`huts/tools/gpxEditorPlugin.ts` (dev-only GPX editor).** It reads `hubs.json` straight from the
  data dir: `hubsPath: path.join(repoRoot, 'data', 'osm', 'hubs.json')` (line 146) and the
  not-found error text `data/osm/hubs.json not found` (line 110). Both change to
  `data/build/tour-edges/hubs.json`, and `huts/tools/gpxEditorPlugin.test.ts:105` asserts on that
  error text. This is the only `huts/` code that reads `data/` directly; every other `huts/` read
  goes through `huts/public/data/`. Nothing else in `huts/` changes.
- Mechanically find leftovers with `grep -rn "OSM_DIR\|DEM_DIR\|data/osm\|data/dem\|base_graph\|hut_edges\|start_edges\|tour_edges" pipeline docs CLAUDE.md huts/src`.

## Migration mechanics

This is the part most likely to go wrong, so it gets its own section.

`data/.doit.json.db` is a JSON file (doit's `json` backend) keyed by task name. **Verified against
the live file:** each task's dict holds the tracked path strings as top-level keys, each mapping to
`[mtime, size, md5]`, plus a `"deps:"` list of the same path strings, plus `"_values_:"`,
`"result:"`, `"checker:"`. Path strings are **relative to `pipeline/`**, forward-slash, produced by
`rel()` (`lib/doit_support.py`) — e.g. `"../data/osm/trails.osm.pbf"`, not absolute. Paths outside
`data/` (e.g. `"tours/Kaisertour/1.gpx"`) are unaffected. `"_values_:"` holds only task options
(bbox, tile size, schema versions) and contains no paths, so it needs no rewrite. The db has 38
task entries and ~105 distinct path strings.

If a task's target path changes but the db isn't updated, doit sees no record for the new path and
reruns the task — for `build_base_graph` and friends that's hours, cascading downstream.

A pure same-filesystem move (`os.rename`) preserves mtime, size and content (hence md5), so one
migration script, run once, does the following in one pass:

1. Builds the old→new mapping from the table above, expanded per file (directory moves like
   `base_graph/*`, `dem/`, `route_subgraphs/*` expand by walking the old tree).
2. Reads `data/.doit.json.db` and prints the planned db rewrites and file moves. With `--dry-run`
   stops here.
3. Backs up `data/.doit.json.db` to `data/.doit.json.db.pre-restructure`.
4. Creates `data/raw/` and `data/build/` and moves every file per the mapping (`os.rename`, not
   copy — no reason to touch 58GB+ of data twice). Already-moved files are skipped, so a rerun
   after partial failure resumes.
5. Deletes the orphaned files listed under "Deleted files".
6. Rewrites the db: for every task, every top-level key and every `"deps:"` entry that equals an
   old `../data/...` path gets the new `../data/...` path; values (`[mtime, size, md5]`) are kept
   untouched. Keys not in the mapping are left alone. Entries for tasks no longer in `dodo.py`
   (`fetch_tour_oa_geometry`, `build_tour_edge_payload`) are inert and may be dropped.
7. Removes the now-empty `data/osm/` and `data/dem/` directories, but only if empty.

The script asserts before writing anything: every old-path source exists or was already moved, no
destination already exists with different content, and every path string in the db that starts
with `../data/osm/` or `../data/dem/` is covered by the mapping (else abort listing the strays).

The script lands in the **same commit** as the `dodo.py`/`dag/*.py` path changes — the physical
layout and doit's declared targets must agree at every commit, since `data/` isn't tracked in git
and no prior physical layout can be checked out. It lives in `pipeline/tools/` and is deleted in
a follow-up once run on all machines.

**Verification, before treating the migration as done:** with explicit user confirmation (root
`CLAUDE.md` forbids running pipeline tasks unasked), run the read-only status listing (the doit
DAG status CLI from spec 2026-09-01, or `doit list --all --status`) — never a bare `doit` — and
confirm zero tasks are reported as needing to run. Any stale task means stop and fix the db
rewrite; do not run `doit` "to see what happens." `build_profiles` is always-run by design and is
the one expected exception (cheap, seconds).

**Rollback:** the db backup restores step 6. File moves are reversible by running the mapping in
reverse; deletions in step 5 are not, so step 5 runs only after the dry-run output has been read
and the deletion list re-verified by grep.

## Testing

- `pipeline/tests/test_dodo_wiring.py` (and any other test asserting on `dodo.py` task
  paths/targets) updated to the new paths — the automated check that the new layout stays wired
  correctly, even without a structure-enforcement mechanism per "Non-goals."
- A unit test for the migration script on a `tmp_path` fixture: fake old tree plus a small
  `.doit.json.db`; assert files land at new paths, db keys and `deps:` are rewritten with values
  intact, unmapped keys are preserved, a second run is a no-op, and an uncovered `../data/osm/…`
  key aborts before any move.
- After migration, zero stale tasks in the status listing (see above) is the acceptance test for
  the migration itself — no pipeline task is run as part of verifying this change.
