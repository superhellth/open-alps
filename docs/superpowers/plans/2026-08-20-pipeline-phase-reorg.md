# Pipeline Phase Reorg Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `pipeline/`'s 17 flat top-level scripts into `downloads/`, `preprocessing/`,
`graph_building/` subpackages grouped by pipeline phase, with no behavior change.

**Architecture:** Pure file moves (`git mv`) plus the minimum import-path and doc-path fixes the
moves force: each moved script's `sys.path.insert` depth, `dodo.py`'s action strings, and the
handful of tests that import scripts directly by module name. `lib/`, `tests/`, `dodo.py`'s task
graph shape, and `pipeline.config.json` are untouched.

**Tech Stack:** Python, doit, pytest.

**Spec:** `docs/superpowers/specs/2026-08-20-pipeline-phase-reorg-design.md`

## Global Constraints

- No change to `dodo.py` task names, `file_dep`/`targets`, or freshness-check logic — only the
  script path inside each task's `actions` string.
- No change to any script's logic/behavior — only `sys.path.insert` depth and docstring `Usage:`
  lines.
- `lib/` stays flat and unmoved.
- `tests/` stays flat; only import statements inside test files change, never test logic.
- Do not run `doit <task>` or bare `doit` at any point in this plan (per root `CLAUDE.md` — a
  freshness check could kick off a multi-hour job). Verification uses `doit list` only, which
  does not execute any task.
- Each new package folder (`downloads/`, `preprocessing/`, `graph_building/`) gets an empty
  `__init__.py`, no per-folder README.

---

### Task 1: `downloads/` package

**Files:**
- Create: `pipeline/downloads/__init__.py` (empty)
- Move: `pipeline/download_extracts.py` → `pipeline/downloads/download_extracts.py`
- Move: `pipeline/fetch_huts.py` → `pipeline/downloads/fetch_huts.py`
- Move: `pipeline/fetch_stations_parking.py` → `pipeline/downloads/fetch_stations_parking.py`
- Move: `pipeline/fetch_dem.py` → `pipeline/downloads/fetch_dem.py`
- Move: `pipeline/dem_providers/` → `pipeline/downloads/dem_providers/` (all 6 files:
  `__init__.py`, `at_bev.py`, `base.py`, `bavaria_dgm.py`, `composite.py`, `copernicus.py`)
- Modify: `pipeline/dodo.py` (`task_download_extracts`, `task_fetch_huts`,
  `task_fetch_stations_parking`, `task_fetch_dem`)
- Modify: `pipeline/tests/test_at_bev_bbox.py`
- Modify: `pipeline/tests/test_bavaria_tile_grid.py`
- Modify: `pipeline/tests/test_copernicus_tile_naming.py`
- Modify: `pipeline/tests/test_dem_providers_registry.py`
- Modify: `pipeline/tests/test_composite_region_merge.py`
- Modify: `pipeline/README.md`

**Interfaces:**
- Produces: importable package `downloads` (and `downloads.dem_providers`) under `pipeline/`,
  consumed by `pipeline/tests/*` via `from downloads.dem_providers import ...` and by
  `pipeline/dodo.py` via the `downloads/<script>.py` action path. No other task depends on this
  one's internals.

- [ ] **Step 1: Create the package and move the four download scripts**

```bash
cd pipeline
mkdir -p downloads
touch downloads/__init__.py
git mv download_extracts.py downloads/download_extracts.py
git mv fetch_huts.py downloads/fetch_huts.py
git mv fetch_stations_parking.py downloads/fetch_stations_parking.py
git mv fetch_dem.py downloads/fetch_dem.py
git mv dem_providers downloads/dem_providers
git add downloads/__init__.py
```

- [ ] **Step 2: Fix `sys.path.insert` depth in the three scripts that only import `lib.*`**

In `downloads/download_extracts.py`, `downloads/fetch_huts.py`,
`downloads/fetch_stations_parking.py`, each has one line:

```python
sys.path.insert(0, str(Path(__file__).resolve().parent))
```

Change to:

```python
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

(They now live one level deeper than `lib/`, which stays at `pipeline/lib/`.)

- [ ] **Step 3: Fix `downloads/fetch_dem.py`'s sys.path (needs both `dem_providers` and `lib`)**

`fetch_dem.py` imports both `dem_providers` (now its sibling at `downloads/dem_providers/`) and
`lib.pipeline` (now two levels up at `pipeline/lib/`). Replace:

```python
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dem_providers import get_provider  # noqa: E402
from lib.pipeline import DEM_DIR, load_config  # noqa: E402
```

with:

```python
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dem_providers import get_provider  # noqa: E402
from lib.pipeline import DEM_DIR, load_config  # noqa: E402
```

- [ ] **Step 4: Fix `downloads/dem_providers/composite.py`'s sys.path**

It currently has:

```python
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.pipeline import OSM_DIR, bbox_from_huts, edge_points, hut_points  # noqa: E402
```

`parent.parent` used to land on `pipeline/` (from `pipeline/dem_providers/composite.py`); now
`composite.py` is one level deeper (`pipeline/downloads/dem_providers/composite.py`), so it needs
one more `.parent`:

```python
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib.pipeline import OSM_DIR, bbox_from_huts, edge_points, hut_points  # noqa: E402
```

- [ ] **Step 5: Update `Usage:` docstring lines in the four moved scripts**

- `downloads/download_extracts.py`: `Usage: python pipeline/download_extracts.py` →
  `Usage: python pipeline/downloads/download_extracts.py`
- `downloads/fetch_huts.py`: `Usage: python pipeline/fetch_huts.py` →
  `Usage: python pipeline/downloads/fetch_huts.py`
- `downloads/fetch_stations_parking.py`: `Usage: python pipeline/05b-fetch-stations-parking.py`
  → `Usage: python pipeline/downloads/fetch_stations_parking.py` (also fixes a stale filename
  left over from before the script was renamed)
- `downloads/fetch_dem.py`: `Usage: python pipeline/fetch_dem.py` →
  `Usage: python pipeline/downloads/fetch_dem.py`; also its docstring line referencing
  `pipeline/dem_providers/base.py` → `pipeline/downloads/dem_providers/base.py`

- [ ] **Step 6: Update `dodo.py`'s action paths for the four download tasks**

In `task_download_extracts`, `task_fetch_huts`, `task_fetch_stations_parking`, `task_fetch_dem`,
change the `py(...)` call's first argument:

```python
"actions": [py("download_extracts.py")],
```
→
```python
"actions": [py("downloads/download_extracts.py")],
```

```python
"actions": [py("fetch_huts.py")],
```
→
```python
"actions": [py("downloads/fetch_huts.py")],
```

```python
"actions": [py("fetch_stations_parking.py")],
```
→
```python
"actions": [py("downloads/fetch_stations_parking.py")],
```

```python
"actions": [py("fetch_dem.py")],
```
→
```python
"actions": [py("downloads/fetch_dem.py")],
```

- [ ] **Step 7: Update the five test files that import `dem_providers` directly**

In `pipeline/tests/test_at_bev_bbox.py`:
```python
from dem_providers import at_bev  # noqa: E402
```
→
```python
from downloads.dem_providers import at_bev  # noqa: E402
```

In `pipeline/tests/test_bavaria_tile_grid.py`:
```python
from dem_providers import bavaria_dgm  # noqa: E402
```
→
```python
from downloads.dem_providers import bavaria_dgm  # noqa: E402
```

In `pipeline/tests/test_copernicus_tile_naming.py`:
```python
from dem_providers import copernicus  # noqa: E402
```
→
```python
from downloads.dem_providers import copernicus  # noqa: E402
```

In `pipeline/tests/test_dem_providers_registry.py`:
```python
from dem_providers import get_provider, PROVIDER_NAMES  # noqa: E402
```
→
```python
from downloads.dem_providers import get_provider, PROVIDER_NAMES  # noqa: E402
```

In `pipeline/tests/test_composite_region_merge.py`:
```python
import dem_providers  # noqa: E402
from dem_providers import composite  # noqa: E402
```
→
```python
import downloads.dem_providers as dem_providers  # noqa: E402
from downloads.dem_providers import composite  # noqa: E402
```

(This test uses the bare `dem_providers` name later in the file via `dem_providers.something` —
the `as dem_providers` alias keeps those references working unchanged. Verify this by grepping
the file for `dem_providers\.` after the edit.)

- [ ] **Step 8: Update path mentions in `pipeline/README.md`**

Lines currently reading:
```
python pipeline/download_extracts.py      # ~1.6GB, Geofabrik extracts from pipeline.config.json
```
```
python pipeline/fetch_huts.py              # -> data/osm/huts.geojson
python pipeline/fetch_stations_parking.py  # -> data/osm/stations.geojson, parking.geojson
```
```
python pipeline/fetch_dem.py               # -> data/dem/fetch_manifest.json, via dem.provider (see Config)
```
and the mention of `` `pipeline/dem_providers/base.py` `` (`fetch()` + `to_4326_vrt()`) — prefix
each script path with `downloads/` and the `dem_providers` path with `downloads/dem_providers/`.

- [ ] **Step 9: Run the affected tests**

```bash
cd pipeline
pytest tests/test_at_bev_bbox.py tests/test_bavaria_tile_grid.py tests/test_copernicus_tile_naming.py tests/test_dem_providers_registry.py tests/test_composite_region_merge.py -v
```
Expected: all PASS, same count as before the move.

- [ ] **Step 10: Run `doit list` to confirm the DAG still resolves**

```bash
cd pipeline
doit list
```
Expected: same task names and up-to-date status as before this task's changes (this does not
execute any task — see Global Constraints).

- [ ] **Step 11: Commit**

```bash
git add pipeline/downloads pipeline/dodo.py pipeline/tests/test_at_bev_bbox.py \
  pipeline/tests/test_bavaria_tile_grid.py pipeline/tests/test_copernicus_tile_naming.py \
  pipeline/tests/test_dem_providers_registry.py pipeline/tests/test_composite_region_merge.py \
  pipeline/README.md
git commit -m "refactor(pipeline): move download scripts into downloads/"
```

---

### Task 2: `preprocessing/` package

**Files:**
- Create: `pipeline/preprocessing/__init__.py` (empty)
- Move: `pipeline/filter_trails.py` → `pipeline/preprocessing/filter_trails.py`
- Move: `pipeline/merge_trails.py` → `pipeline/preprocessing/merge_trails.py`
- Move: `pipeline/verify_trails.py` → `pipeline/preprocessing/verify_trails.py`
- Move: `pipeline/filter_start_points.py` → `pipeline/preprocessing/filter_start_points.py`
- Modify: `pipeline/dodo.py` (`task_filter_trails`, `task_merge_trails`, `task_verify_trails`,
  `task_filter_start_points`)
- Modify: `pipeline/tests/test_filter_start_points.py`
- Modify: `pipeline/README.md`

**Interfaces:**
- Produces: importable package `preprocessing` under `pipeline/`, consumed by
  `pipeline/tests/test_filter_start_points.py` via
  `from preprocessing.filter_start_points import filter_to_hut_range` and by `pipeline/dodo.py`
  via the `preprocessing/<script>.py` action path.

- [ ] **Step 1: Create the package and move the four scripts**

```bash
cd pipeline
mkdir -p preprocessing
touch preprocessing/__init__.py
git mv filter_trails.py preprocessing/filter_trails.py
git mv merge_trails.py preprocessing/merge_trails.py
git mv verify_trails.py preprocessing/verify_trails.py
git mv filter_start_points.py preprocessing/filter_start_points.py
git add preprocessing/__init__.py
```

- [ ] **Step 2: Fix `sys.path.insert` depth in all four scripts**

Each has one line:
```python
sys.path.insert(0, str(Path(__file__).resolve().parent))
```
Change to:
```python
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```
in `preprocessing/filter_trails.py`, `preprocessing/merge_trails.py`,
`preprocessing/verify_trails.py`, `preprocessing/filter_start_points.py`.

- [ ] **Step 3: Update `Usage:` docstring lines**

- `preprocessing/filter_trails.py`: `Usage: python pipeline/filter_trails.py` →
  `Usage: python pipeline/preprocessing/filter_trails.py`
- `preprocessing/merge_trails.py`: `Usage: python pipeline/merge_trails.py` →
  `Usage: python pipeline/preprocessing/merge_trails.py`
- `preprocessing/verify_trails.py`:
  `Usage: python pipeline/verify_trails.py [filename]   (default: trails.osm.pbf)` →
  `Usage: python pipeline/preprocessing/verify_trails.py [filename]   (default: trails.osm.pbf)`
- `preprocessing/filter_start_points.py`: `Usage: python pipeline/filter_start_points.py` →
  `Usage: python pipeline/preprocessing/filter_start_points.py`

- [ ] **Step 4: Update `dodo.py`'s action paths for the four preprocessing tasks**

```python
"actions": [py("filter_trails.py")],
```
→
```python
"actions": [py("preprocessing/filter_trails.py")],
```

```python
"actions": [py("merge_trails.py")],
```
→
```python
"actions": [py("preprocessing/merge_trails.py")],
```

```python
"actions": [py("verify_trails.py")],
```
→
```python
"actions": [py("preprocessing/verify_trails.py")],
```

```python
"actions": [py("filter_start_points.py")],
```
→
```python
"actions": [py("preprocessing/filter_start_points.py")],
```

- [ ] **Step 5: Update `pipeline/tests/test_filter_start_points.py`**

```python
from filter_start_points import filter_to_hut_range  # noqa: E402
```
→
```python
from preprocessing.filter_start_points import filter_to_hut_range  # noqa: E402
```

- [ ] **Step 6: Update path mentions in `pipeline/README.md`**

```
python pipeline/filter_trails.py           # -> ~264MB combined, hiking ways only
python pipeline/merge_trails.py            # -> data/osm/trails.osm.pbf
python pipeline/verify_trails.py           # gate: fails if trails.osm.pbf is missing/empty
```
and
```
python pipeline/filter_start_points.py     # -> data/osm/start_points.npy, start_points_id_table.json
```
prefix each with `preprocessing/`.

- [ ] **Step 7: Run the affected test**

```bash
cd pipeline
pytest tests/test_filter_start_points.py -v
```
Expected: PASS, same count as before the move.

- [ ] **Step 8: Run `doit list`**

```bash
cd pipeline
doit list
```
Expected: same task names and up-to-date status as before.

- [ ] **Step 9: Commit**

```bash
git add pipeline/preprocessing pipeline/dodo.py pipeline/tests/test_filter_start_points.py pipeline/README.md
git commit -m "refactor(pipeline): move OSM filter/merge scripts into preprocessing/"
```

---

### Task 3: `graph_building/` package

**Files:**
- Create: `pipeline/graph_building/__init__.py` (empty)
- Move: `pipeline/build_base_graph.py` → `pipeline/graph_building/build_base_graph.py`
- Move: `pipeline/build_hub_edges.py` → `pipeline/graph_building/build_hub_edges.py`
- Move: `pipeline/add_elevation.py` → `pipeline/graph_building/add_elevation.py`
- Move: `pipeline/build_dem_vrt.py` → `pipeline/graph_building/build_dem_vrt.py`
- Move: `pipeline/build_trail_tiles.py` → `pipeline/graph_building/build_trail_tiles.py`
- Move: `pipeline/build_edge_tiles.py` → `pipeline/graph_building/build_edge_tiles.py`
- Modify: `pipeline/dodo.py` (`task_build_base_graph`, `task_build_hub_edges`,
  `task_build_dem_vrt`, `task_add_elevation`, `task_build_trail_tiles`,
  `task_build_hut_edge_tiles`, `task_build_start_edge_tiles`)
- Modify: `pipeline/tests/test_add_elevation.py`
- Modify: `pipeline/tests/test_build_edge_tiles.py`
- Modify: `pipeline/tests/test_build_hub_edges.py`
- Modify: `pipeline/README.md`
- Modify: `pipeline/PIPELINE_STEPS.md`
- Modify: `pipeline/CLAUDE.md` (root pipeline doc's mentions of these script paths)

**Interfaces:**
- Produces: importable package `graph_building` under `pipeline/`, consumed by
  `pipeline/tests/test_add_elevation.py`, `test_build_edge_tiles.py`, `test_build_hub_edges.py`
  via `from graph_building.<script> import ...`, and by `pipeline/dodo.py` via the
  `graph_building/<script>.py` action path (both `py()`-wrapped and the two direct
  `SCRIPT_DIR / "..."` f-string actions).

- [ ] **Step 1: Create the package and move the six scripts**

```bash
cd pipeline
mkdir -p graph_building
touch graph_building/__init__.py
git mv build_base_graph.py graph_building/build_base_graph.py
git mv build_hub_edges.py graph_building/build_hub_edges.py
git mv add_elevation.py graph_building/add_elevation.py
git mv build_dem_vrt.py graph_building/build_dem_vrt.py
git mv build_trail_tiles.py graph_building/build_trail_tiles.py
git mv build_edge_tiles.py graph_building/build_edge_tiles.py
git add graph_building/__init__.py
```

- [ ] **Step 2: Fix `sys.path.insert` depth in all six scripts**

Each has one line:
```python
sys.path.insert(0, str(Path(__file__).resolve().parent))
```
Change to:
```python
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```
in `graph_building/build_base_graph.py`, `graph_building/build_hub_edges.py`,
`graph_building/add_elevation.py`, `graph_building/build_dem_vrt.py`,
`graph_building/build_trail_tiles.py`, `graph_building/build_edge_tiles.py`.

- [ ] **Step 3: Update `Usage:` docstring lines**

- `graph_building/build_base_graph.py`:
  `Usage: python pipeline/build_base_graph.py [--tile-size-km 60]` →
  `Usage: python pipeline/graph_building/build_base_graph.py [--tile-size-km 60]`
- `graph_building/build_hub_edges.py`:
  `Usage: python pipeline/build_hub_edges.py [--max-edge-km 30] [--max-snap-m 100] [--workers N]`
  → `Usage: python pipeline/graph_building/build_hub_edges.py [--max-edge-km 30] [--max-snap-m 100] [--workers N]`
- `graph_building/add_elevation.py`:
  ```
  python pipeline/add_elevation.py
  python pipeline/add_elevation.py --ele-noise-threshold-m 3
  ```
  →
  ```
  python pipeline/graph_building/add_elevation.py
  python pipeline/graph_building/add_elevation.py --ele-noise-threshold-m 3
  ```
- `graph_building/build_dem_vrt.py`: `Usage: python pipeline/build_dem_vrt.py` →
  `Usage: python pipeline/graph_building/build_dem_vrt.py`
- `graph_building/build_trail_tiles.py`:
  ```
  python pipeline/build_trail_tiles.py
  python pipeline/build_trail_tiles.py --min-zoom 6 --max-zoom 14
  ```
  →
  ```
  python pipeline/graph_building/build_trail_tiles.py
  python pipeline/graph_building/build_trail_tiles.py --min-zoom 6 --max-zoom 14
  ```
- `graph_building/build_edge_tiles.py`:
  `python pipeline/build_edge_tiles.py --edges-dir data/osm/hut_edges --layer-name hut_edges \` →
  `python pipeline/graph_building/build_edge_tiles.py --edges-dir data/osm/hut_edges --layer-name hut_edges \`

- [ ] **Step 4: Update `dodo.py`'s action paths for the six graph-building tasks**

`task_build_base_graph` and `task_build_hub_edges` build their action with an f-string, not
`py()`:
```python
f'"{sys.executable}" "{SCRIPT_DIR / "build_base_graph.py"}"'
" --tile-size-km %(tile_size_km)s"
```
→
```python
f'"{sys.executable}" "{SCRIPT_DIR / "graph_building" / "build_base_graph.py"}"'
" --tile-size-km %(tile_size_km)s"
```
and
```python
f'"{sys.executable}" "{SCRIPT_DIR / "build_hub_edges.py"}"'
" --max-edge-km %(max_edge_km)s --max-snap-m %(max_snap_m)s"
```
→
```python
f'"{sys.executable}" "{SCRIPT_DIR / "graph_building" / "build_hub_edges.py"}"'
" --max-edge-km %(max_edge_km)s --max-snap-m %(max_snap_m)s"
```

`task_add_elevation` also uses the direct f-string form:
```python
f'"{sys.executable}" "{SCRIPT_DIR / "add_elevation.py"}"'
" --ele-noise-threshold-m %(ele_noise_threshold_m)s"
" --profile-points %(profile_points)s"
```
→
```python
f'"{sys.executable}" "{SCRIPT_DIR / "graph_building" / "add_elevation.py"}"'
" --ele-noise-threshold-m %(ele_noise_threshold_m)s"
" --profile-points %(profile_points)s"
```

`task_build_dem_vrt` uses `py()`:
```python
"actions": [py("build_dem_vrt.py")],
```
→
```python
"actions": [py("graph_building/build_dem_vrt.py")],
```

`task_build_trail_tiles` uses `py()` with extra args:
```python
py(
    "build_trail_tiles.py",
    f"--min-zoom {tiles_cfg.get('minZoom', 6)}",
    f"--max-zoom {tiles_cfg.get('maxZoom', 14)}",
)
```
→
```python
py(
    "graph_building/build_trail_tiles.py",
    f"--min-zoom {tiles_cfg.get('minZoom', 6)}",
    f"--max-zoom {tiles_cfg.get('maxZoom', 14)}",
)
```

`task_build_hut_edge_tiles` and `task_build_start_edge_tiles` both use `py()`:
```python
py(
    "build_edge_tiles.py",
    ...
)
```
→ (in both tasks)
```python
py(
    "graph_building/build_edge_tiles.py",
    ...
)
```

- [ ] **Step 5: Update the three test files that import moved scripts directly**

`pipeline/tests/test_add_elevation.py`:
```python
from add_elevation import fill_elevation_records  # noqa: E402
```
→
```python
from graph_building.add_elevation import fill_elevation_records  # noqa: E402
```

`pipeline/tests/test_build_edge_tiles.py`:
```python
from build_edge_tiles import build_stats, rdp_keep_indices  # noqa: E402
```
→
```python
from graph_building.build_edge_tiles import build_stats, rdp_keep_indices  # noqa: E402
```

`pipeline/tests/test_build_hub_edges.py`:
```python
from build_hub_edges import (  # noqa: E402
```
→
```python
from graph_building.build_hub_edges import (  # noqa: E402
```
(keep the rest of that multi-line import unchanged — only the module path on this line changes)

- [ ] **Step 6: Update path mentions in `pipeline/README.md`**

```
python pipeline/build_base_graph.py        # -> data/osm/base_graph/ (hub-agnostic, cached trail graph)
python pipeline/build_hub_edges.py         # -> data/osm/hut_edges/, start_edges/ (records.npy, geometry.npy)
```
```
python pipeline/build_dem_vrt.py          # -> data/dem/dem.tif; rerun alone after tweaking a provider, no re-fetch
python pipeline/add_elevation.py           # adds ascent_m/descent_m/profiles.npy to hut_edges/, start_edges/ in place
```
```
python pipeline/build_trail_tiles.py       # -> data/osm/trails.pmtiles
python pipeline/build_edge_tiles.py --edges-dir data/osm/hut_edges --id-table data/osm/start_points_id_table.json \
python pipeline/build_edge_tiles.py --edges-dir data/osm/start_edges --id-table data/osm/start_points_id_table.json \
```
prefix each script path with `graph_building/`.

- [ ] **Step 7: Update `pipeline/PIPELINE_STEPS.md`**

This file references every moved script by bare filename, both in step headers (e.g.
`` ## 1. `download_extracts` — `download_extracts.py` ``) and inline in the narrative text (e.g.
"`build_hub_edges.py`'s workers mmap-slice..."). Apply this exact mapping everywhere the bare
filename appears in the file (do not touch `lib/*.py` mentions — those are unaffected, `lib/`
didn't move — and do not touch the historical mention of `` `build_hut_edge_tiles.py` `` on the
`build_hut_edge_tiles` / `build_start_edge_tiles` line, which names an old pre-generalization
script, not a current file):

| bare filename | replace with |
|---|---|
| `download_extracts.py` | `downloads/download_extracts.py` |
| `fetch_huts.py` | `downloads/fetch_huts.py` |
| `fetch_stations_parking.py` | `downloads/fetch_stations_parking.py` |
| `fetch_dem.py` | `downloads/fetch_dem.py` |
| `filter_trails.py` | `preprocessing/filter_trails.py` |
| `merge_trails.py` | `preprocessing/merge_trails.py` |
| `verify_trails.py` | `preprocessing/verify_trails.py` |
| `filter_start_points.py` | `preprocessing/filter_start_points.py` |
| `build_base_graph.py` | `graph_building/build_base_graph.py` |
| `build_hub_edges.py` | `graph_building/build_hub_edges.py` |
| `add_elevation.py` | `graph_building/add_elevation.py` |
| `build_dem_vrt.py` | `graph_building/build_dem_vrt.py` |
| `build_trail_tiles.py` | `graph_building/build_trail_tiles.py` |
| `build_edge_tiles.py` | `graph_building/build_edge_tiles.py` |
| `pipeline/dem_providers/` | `pipeline/downloads/dem_providers/` |

Run as a script rather than by hand, to guarantee every occurrence is caught and none are
double-prefixed:

```python
import pathlib
path = pathlib.Path("pipeline/PIPELINE_STEPS.md")
text = path.read_text(encoding="utf-8")
mapping = {
    "download_extracts.py": "downloads/download_extracts.py",
    "fetch_huts.py": "downloads/fetch_huts.py",
    "fetch_stations_parking.py": "downloads/fetch_stations_parking.py",
    "fetch_dem.py": "downloads/fetch_dem.py",
    "filter_trails.py": "preprocessing/filter_trails.py",
    "merge_trails.py": "preprocessing/merge_trails.py",
    "verify_trails.py": "preprocessing/verify_trails.py",
    "filter_start_points.py": "preprocessing/filter_start_points.py",
    "build_base_graph.py": "graph_building/build_base_graph.py",
    "build_hub_edges.py": "graph_building/build_hub_edges.py",
    "add_elevation.py": "graph_building/add_elevation.py",
    "build_dem_vrt.py": "graph_building/build_dem_vrt.py",
    "build_trail_tiles.py": "graph_building/build_trail_tiles.py",
    "build_edge_tiles.py": "graph_building/build_edge_tiles.py",
    "pipeline/dem_providers/": "pipeline/downloads/dem_providers/",
}
# build_hut_edge_tiles.py (historical name) must survive untouched - protect it first
text = text.replace("build_hut_edge_tiles.py", "\x00PROTECTED\x00")
for old, new in mapping.items():
    text = text.replace(old, new)
text = text.replace("\x00PROTECTED\x00", "build_hut_edge_tiles.py")
path.write_text(text, encoding="utf-8")
```

After running it, read the file's diff and confirm nothing got double-prefixed (e.g. no
`graph_building/graph_building/...` or `downloads/downloads/...`) and that
`build_hut_edge_tiles.py` on the `build_hut_edge_tiles` / `build_start_edge_tiles` line is
unchanged.

- [ ] **Step 8: Update `pipeline/CLAUDE.md`**

It references `build_base_graph.py`, `build_hub_edges.py`, `filter_start_points.py`,
`build_edge_tiles.py`, `build_dem_vrt.py`, `add_elevation.py` (bare, no `lib/` mentions moved —
`lib/edge_split.py`, `lib/grid.py`, `lib/subgraph.py`, `lib/timing.py`, `lib/pipeline.py`,
`lib/binfmt.py` stay untouched). Run the same substitution approach as Step 7, using the same
mapping table but scoped to `pipeline/CLAUDE.md` and dropping the `build_hut_edge_tiles.py` /
`pipeline/dem_providers/` protection lines (neither string appears in this file — verify that
with a quick grep before running, and skip the protect/restore step if so).

- [ ] **Step 9: Run the affected tests**

```bash
cd pipeline
pytest tests/test_add_elevation.py tests/test_build_edge_tiles.py tests/test_build_hub_edges.py -v
```
Expected: all PASS, same count as before the move.

- [ ] **Step 10: Run `doit list`**

```bash
cd pipeline
doit list
```
Expected: same task names and up-to-date status as before.

- [ ] **Step 11: Commit**

```bash
git add pipeline/graph_building pipeline/dodo.py pipeline/tests/test_add_elevation.py \
  pipeline/tests/test_build_edge_tiles.py pipeline/tests/test_build_hub_edges.py \
  pipeline/README.md pipeline/PIPELINE_STEPS.md pipeline/CLAUDE.md
git commit -m "refactor(pipeline): move graph-building/tiling scripts into graph_building/"
```

---

### Task 4: Full-suite verification

**Files:** none (verification only, no source changes expected)

**Interfaces:**
- Consumes: the final state of `pipeline/downloads/`, `pipeline/preprocessing/`,
  `pipeline/graph_building/`, `pipeline/dodo.py`, `pipeline/tests/*` from Tasks 1-3.

- [ ] **Step 1: Run the full pipeline test suite**

```bash
cd pipeline
pytest tests -v
```
Expected: same total pass count as `git stash` + `pytest tests -v` on the pre-reorg tree (no
test added, removed, or skipped by this plan — only import lines changed).

- [ ] **Step 2: Run `doit list` one more time from the final tree**

```bash
cd pipeline
doit list
```
Expected: identical task list/status to the pre-reorg baseline.

- [ ] **Step 3: Confirm no stray flat-file references remain**

```bash
cd pipeline
grep -rn "pipeline/download_extracts\.py\|pipeline/fetch_huts\.py\|pipeline/fetch_stations_parking\.py\|pipeline/fetch_dem\.py\|pipeline/filter_trails\.py\|pipeline/merge_trails\.py\|pipeline/verify_trails\.py\|pipeline/filter_start_points\.py\|pipeline/build_base_graph\.py\|pipeline/build_hub_edges\.py\|pipeline/add_elevation\.py\|pipeline/build_dem_vrt\.py\|pipeline/build_trail_tiles\.py\|pipeline/build_edge_tiles\.py\|pipeline/dem_providers/" . --include=*.py --include=*.md
```
Expected: no matches outside of this plan/spec doc's own text (the grep is against the working
tree, not `docs/`, so it should be empty). If anything turns up, fix the path there before
proceeding.

- [ ] **Step 4: Confirm no old top-level files remain untracked/orphaned**

```bash
cd pipeline
ls *.py 2>/dev/null
```
Expected: no output (all 14 moved scripts are gone from `pipeline/` root; `dodo.py` and
`pipeline.config.json` are not `.py` glob matches for scripts... note `dodo.py` itself *is* a
`.py` file and is expected to still be listed here — that's correct, it stays at the root).

- [ ] **Step 5: Final commit if Step 3 turned up any fixes**

```bash
git add -A
git commit -m "refactor(pipeline): fix remaining stray path references from phase reorg"
```

(Skip this step if Step 3 found nothing to fix.)
