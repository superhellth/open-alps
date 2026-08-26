# pipeline/ phase reorg — design

## Problem

`pipeline/` is 17 top-level scripts in one flat directory with no grouping by pipeline phase.
The ordering/relationship between scripts is only discoverable by reading `dodo.py`'s task DAG or
`PIPELINE_STEPS.md`, not from the directory listing itself. This is a pure reorganization for
navigability — no behavior, task DAG shape, or config changes.

## Target layout

```
pipeline/
  downloads/        download_extracts.py, fetch_huts.py, fetch_stations_parking.py,
                     fetch_dem.py, dem_providers/ (moved from pipeline/dem_providers/)
  preprocessing/     filter_trails.py, merge_trails.py, verify_trails.py, filter_start_points.py
  graph_building/    build_base_graph.py, build_hub_edges.py, add_elevation.py,
                     build_dem_vrt.py, build_trail_tiles.py, build_edge_tiles.py
  lib/               unchanged, flat, shared (binfmt, contraction, edge_split, grid, pipeline, timing)
  tests/             unchanged, flat
  dodo.py, pipeline.config.json, README.md, CLAUDE.md, PIPELINE_STEPS.md  — stay at pipeline/ root
```

Each new folder (`downloads/`, `preprocessing/`, `graph_building/`) gets an empty `__init__.py`
so it's an importable package; no per-folder README (phase docs already live in `CLAUDE.md` /
`PIPELINE_STEPS.md`, avoid duplication).

### Grouping rationale (resolved during brainstorming)

- Tiling scripts (`build_trail_tiles.py`, `build_edge_tiles.py`) fold into `graph_building/`
  rather than getting a 5th folder — fewer top-level dirs, and they're the graph's rendering
  step.
- `fetch_dem.py` goes in `downloads/` (consistent "anything that hits the network lives here"
  rule) even though its only consumer is the elevation phase.
- `dem_providers/` (registry of DEM source backends, single consumer `fetch_dem.py`) moves with
  it into `downloads/dem_providers/`.
- `lib/` stays flat and shared rather than splitting graph-specific modules
  (`binfmt.py`/`contraction.py`/`edge_split.py`/`grid.py`) into `graph_building/lib/` — avoids
  guessing wrong about future reuse (e.g. `edge_split` could matter to tiling too).

## Mechanical fallout (not optional — the reorg breaks these if left alone)

1. **Script self-relative sys.path.** Every script currently does
   `sys.path.insert(0, str(Path(__file__).resolve().parent))` then `from lib.pipeline import ...`.
   Once a script lives one level deeper (e.g. `graph_building/build_hub_edges.py`), that must
   become `.parent.parent` to still resolve `pipeline/lib/`. `fetch_dem.py`'s own
   `from dem_providers import ...` stays a relative sibling import since `dem_providers/` moves
   with it into `downloads/`.

2. **dodo.py script paths.** `py()` calls currently reference scripts by flat filename (e.g.
   `"fetch_huts.py"`). All 17 need their new subpath (e.g. `"downloads/fetch_huts.py"`). No
   change to task names, `file_dep`/`targets`, or DAG structure — purely the action string.

3. **Test imports.** Tests do `sys.path.insert(0, str(Path(__file__).resolve().parent.parent))`
   (pointing at `pipeline/`) then import scripts directly by flat module name:
   `from build_hub_edges import ...`, `from add_elevation import ...`,
   `from build_edge_tiles import ...`, `from filter_start_points import ...`, plus 4 DEM-provider
   tests doing `from dem_providers import ...` / `import dem_providers`. These need updating to
   the new package-qualified path (e.g. `from graph_building.build_hub_edges import ...`,
   `from downloads.dem_providers import ...`) consistently across all affected test files.
   `lib`-only imports (`from lib.pipeline import ...`, `from lib import binfmt`, etc.) are
   unaffected since `lib/` doesn't move.

4. **Docs and docstrings.** Script docstring `Usage:` lines (e.g. `python pipeline/fetch_huts.py`)
   and path mentions in `README.md`, `PIPELINE_STEPS.md`, and `pipeline/CLAUDE.md` reference old
   flat paths — update to the new subpaths so they stay accurate.

## Explicitly not touched

- `lib/` internals and module boundaries.
- `dodo.py`'s task graph shape, task names, `file_dep`/`targets`, or freshness-check logic.
- `pipeline.config.json`.
- Any script's logic/behavior.
- `tests/` directory structure (stays flat, only import lines change).

## Verification

After the move: `pytest pipeline/tests` must pass unchanged, and `doit list` (from within
`pipeline/`, no task execution) must show the same task names/status as before the move — proof
the DAG wiring survived the path rewrite without needing `doit forget`.
