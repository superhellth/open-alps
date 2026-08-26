# Hub-range trail/DEM coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make trail extraction (`filter_trails.py`) and Bavaria DEM fetch (`bavaria-dgm5`)
derive their geographic bound from the exact same "within `graph.maxEdgeKm` of some hut" shape, so
`add_base_elevation` can never again find a base-graph node with zero DEM coverage (the bug that
crashed a real Task 9 rebuild — `rasterio.errors.WindowError: Intersection is empty`), and add
Copernicus GLO-30 as a low-priority floor for the one residual gap no bbox/radius tuning can close
(a hut near a border whose range dips into a third country).

**Architecture:** Replace the rectangular `hub_range` bbox (committed `fb34f4e`, insufficient —
see spec) with a real union-of-circles polygon computed once (`compute_hub_range.py`), consumed by
`filter_trails.py` via `osmium extract --polygon` and by `composite.py`'s `bavaria-dgm5` region via
the same radius value fed into its existing `tiles_for_points()` per-hut buffering. A single
`HUB_RANGE_SAFETY_MARGIN` constant in `lib/pipeline.py` is the one place either side's radius is
derived from, so they cannot independently drift the way the old `bufferKm`/`bufferDeg` mismatch
did.

**Tech Stack:** Python 3.11 (`alpen-osm` conda env), `shapely` (new dependency — geometry union),
`osmium-tool` CLI (`extract --polygon`, GeoJSON format — verified empirically in this environment,
see Task 4), `doit` task DAG (`pipeline/dodo.py`), `pytest`.

**Spec:** `docs/superpowers/specs/2026-08-22-hub-range-dem-coverage.md`

## Global Constraints

- No graceful "skip and flag missing elevation" fallback anywhere in `add_base_elevation.py` —
  every real gap must be closed by coverage, not tolerated by degrading data (explicit user
  constraint from the spec's design discussion).
- `graph.maxEdgeKm` (`pipeline.config.json`, currently `30`) is the one true radius — never
  hand-copy a derived number into config; compute it from `maxEdgeKm` at the point of use.
- `osmium extract --polygon` in this environment accepts GeoJSON `Polygon`/`MultiPolygon` files
  directly (verified empirically with a throwaway sample: a way fully outside the polygon is
  dropped, a way inside is kept, both single-`Polygon` and `MultiPolygon` GeoJSON work) — use
  GeoJSON, not the Osmosis `.poly` text format, even though that also works, since it's what
  `shapely.geometry.mapping()` already produces with no hand-formatting.
- `osmium extract`'s default `--strategy` is `complete_ways` — already relied on by
  `filter_trails.py`; nothing in this plan changes it.
- `bavaria_dgm.tiles_for_points(points, buffer_km)` buffers each point with a **square** window of
  half-width `buffer_km` (in real UTM metres, via `rasterio.warp.transform`) — a square of
  half-width R strictly contains a circle of radius R centered at the same point. This is why
  using the *same* radius value on both sides is sufficient once the circle math is done in real
  distance terms; no extra multiplier is needed for the square-vs-circle relationship itself (only
  for polygon-approximation/discretization error — see Task 2).
- `tiles_for_utm_bounds` (`bavaria_dgm.py:132`) always rounds outward (`floor(min/1000)` to
  `floor(max/1000)` inclusive) — tile quantization only ever adds coverage, never removes it.

---

### Task 1: Add `shapely` to the pipeline environment

**Files:**
- Modify: `pipeline/README.md:104-105` (Setup section's `conda create` command)

**Interfaces:**
- Produces: `shapely` importable from the `alpen-osm` conda env for every later task in this plan.

- [ ] **Step 1: Install shapely into the `alpen-osm` env**

```bash
conda install -n alpen-osm -c conda-forge shapely
```

- [ ] **Step 2: Verify the import works**

```bash
conda run -n alpen-osm python -c "import shapely; from shapely.geometry import Point, Polygon, MultiPolygon, mapping; from shapely.ops import unary_union; print(shapely.__version__)"
```

Expected: prints a version string (e.g. `2.0.x`), no `ModuleNotFoundError`.

- [ ] **Step 3: Document it in the README**

`pipeline/README.md:104-105` currently reads:

```
conda create -n alpen-osm -c conda-forge \
  python=3.11 osmium-tool pyosmium scipy numpy python-igraph gdal rasterio orjson psutil
```

Change to:

```
conda create -n alpen-osm -c conda-forge \
  python=3.11 osmium-tool pyosmium scipy numpy python-igraph gdal rasterio orjson psutil shapely
```

- [ ] **Step 4: Commit**

```bash
git add pipeline/README.md
git commit -m "docs(pipeline): add shapely to the alpen-osm env setup"
```

---

### Task 2: `circle_polygon()` / `hub_range_polygon()` in `lib/pipeline.py`

**Files:**
- Modify: `pipeline/lib/pipeline.py` (add near `bbox_from_huts`, which this supersedes but does not
  yet remove — removal is Task 5)
- Test: `pipeline/tests/test_hub_range_polygon.py` (new file)

**Interfaces:**
- Consumes: `hut_points(huts_path, filter_bbox=None)` — already in `lib/pipeline.py`, returns
  `list[[lng, lat]]`.
- Produces: `HUB_RANGE_SAFETY_MARGIN: float` (module-level constant), `circle_polygon(lng: float,
  lat: float, radius_km: float, n_points: int = 32) -> shapely.geometry.Polygon`,
  `hub_range_polygon(huts_path, radius_km: float, n_points: int = 32) ->
  shapely.geometry.base.BaseGeometry` (a `Polygon` or `MultiPolygon` depending on whether hut
  circles overlap). Task 3 (`compute_hub_range.py`) and Task 6 (`composite.py`) both import
  `HUB_RANGE_SAFETY_MARGIN`; Task 3 also imports `hub_range_polygon`.

- [ ] **Step 1: Write the failing tests**

```python
# pipeline/tests/test_hub_range_polygon.py
import json
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shapely.geometry import MultiPolygon, Point, Polygon  # noqa: E402

from lib.pipeline import circle_polygon, hub_range_polygon  # noqa: E402


def _write_huts(tmp_path, coords):
    fc = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": c}}
            for c in coords
        ],
    }
    path = tmp_path / "huts.geojson"
    path.write_text(json.dumps(fc), encoding="utf-8")
    return path


def test_circle_polygon_at_equator_has_equal_lat_lng_extent():
    # At lat=0, one degree of longitude and one degree of latitude are both ~111.32km - no
    # cos(lat) distortion, so the polygon's bounding box should be (near-)square in degrees.
    poly = circle_polygon(0.0, 0.0, radius_km=10.0, n_points=64)
    minx, miny, maxx, maxy = poly.bounds
    lng_extent = maxx - minx
    lat_extent = maxy - miny
    assert lng_extent == pytest.approx(lat_extent, rel=0.01)


def test_circle_polygon_compensates_longitude_shrinkage_at_high_latitude():
    # At lat=60, one degree of longitude is only cos(60)=0.5x as many real km as one degree of
    # latitude - a real-world-radius circle must therefore span MORE degrees of longitude than
    # latitude, by exactly 1/cos(lat), or it under-covers east-west (the wrong direction for a
    # bound meant to be a safe over-approximation).
    lat = 60.0
    poly = circle_polygon(0.0, lat, radius_km=10.0, n_points=64)
    minx, miny, maxx, maxy = poly.bounds
    lng_extent = maxx - minx
    lat_extent = maxy - miny
    expected_ratio = 1 / math.cos(math.radians(lat))
    assert (lng_extent / lat_extent) == pytest.approx(expected_ratio, rel=0.01)


def test_circle_polygon_contains_center_point():
    poly = circle_polygon(11.0, 47.0, radius_km=5.0)
    assert poly.contains(Point(11.0, 47.0))


def test_circle_polygon_does_not_reach_a_point_well_outside_the_radius():
    # ~0.5 deg lat is ~55km, well past a 5km radius - sanity check the shape isn't accidentally
    # unbounded (e.g. a sign error turning the ring inside out).
    poly = circle_polygon(11.0, 47.0, radius_km=5.0)
    assert not poly.contains(Point(11.0, 47.5))


def test_hub_range_polygon_contains_every_hut(tmp_path):
    huts_path = _write_huts(tmp_path, [(11.0, 47.0), (11.2, 47.1), (13.0, 50.0)])
    polygon = hub_range_polygon(huts_path, radius_km=30.0)
    for lng, lat in [(11.0, 47.0), (11.2, 47.1), (13.0, 50.0)]:
        assert polygon.contains(Point(lng, lat))


def test_hub_range_polygon_unions_overlapping_circles_into_one_polygon(tmp_path):
    # Two huts 5km apart, both with a 30km radius - the circles overlap, so the union should
    # merge into a single connected shape, not a MultiPolygon of two near-identical circles.
    huts_path = _write_huts(tmp_path, [(11.0, 47.0), (11.05, 47.0)])
    polygon = hub_range_polygon(huts_path, radius_km=30.0)
    assert isinstance(polygon, Polygon)


def test_hub_range_polygon_keeps_disjoint_circles_separate(tmp_path):
    # Two huts far enough apart that 30km circles never touch - the real case this whole spec is
    # about (an Alpine hut cluster plus one outlying hut in the Bavarian Forest). Must stay a
    # MultiPolygon, not silently balloon into one bounding shape covering the empty terrain
    # between them (that over-inclusion is exactly what the old rectangular hub_range did wrong).
    huts_path = _write_huts(tmp_path, [(11.0, 47.0), (16.0, 50.5)])
    polygon = hub_range_polygon(huts_path, radius_km=30.0)
    assert isinstance(polygon, MultiPolygon)
    assert len(polygon.geoms) == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
conda run -n alpen-osm python -m pytest pipeline/tests/test_hub_range_polygon.py -v
```

Expected: every test fails with `ImportError: cannot import name 'circle_polygon'`.

- [ ] **Step 3: Write the implementation**

Add to `pipeline/lib/pipeline.py`, right after `bbox_from_huts` (around line 235):

```python
from shapely.geometry import Polygon  # add to the top-of-file imports
from shapely.ops import unary_union  # add to the top-of-file imports

# Safety margin applied by callers ON TOP OF graph.maxEdgeKm before passing radius_km to
# circle_polygon()/hub_range_polygon() (Task 3's compute_hub_range.py) and into
# bavaria-dgm5's per-hut tile buffer (Task 6's composite.py) - the ONE place both sides' radius
# is derived from, so they cannot independently drift the way the old bufferKm/bufferDeg mismatch
# did (docs/superpowers/specs/2026-08-22-hub-range-dem-coverage.md). Covers circle_polygon's
# n_points=32 polygon-approximation shortfall at the flat spots between vertices
# (cos(pi/32) ~= 0.9952, ~0.5% under the true radius there) plus a little headroom - tile-grid
# quantization (bavaria_dgm.tiles_for_utm_bounds) already rounds outward and needs no
# compensation.
HUB_RANGE_SAFETY_MARGIN = 1.01


def circle_polygon(lng: float, lat: float, radius_km: float, n_points: int = 32) -> Polygon:
    """Approximates a real-world radius_km circle around (lng, lat) as an n_points-vertex
    polygon, using per-point local flat-earth trig rather than shapely's Point.buffer() (which
    operates in raw degree space). One degree of longitude is only cos(lat) as many real km as
    one degree of latitude away from the equator, so a naive degree-radius buffer becomes an
    ellipse that UNDER-covers east-west at any latitude away from the equator - exactly the wrong
    direction for a bound meant to be a safe over-approximation. Flat-earth error at
    graph.maxEdgeKm's ~30km scale is negligible, and this is computed per-hut-locally (using that
    hut's own latitude), not from one global scale factor, so it stays accurate everywhere in the
    pipeline's scope."""
    deg_per_km_lat = 1 / 111.320
    deg_per_km_lng = 1 / (111.320 * math.cos(math.radians(lat)))
    ring = [
        (
            lng + radius_km * math.sin(theta) * deg_per_km_lng,
            lat + radius_km * math.cos(theta) * deg_per_km_lat,
        )
        for theta in (2 * math.pi * i / n_points for i in range(n_points))
    ]
    ring.append(ring[0])
    return Polygon(ring)


def hub_range_polygon(huts_path, radius_km: float, n_points: int = 32):
    """Unions a circle_polygon() (real-world radius_km) around every hut in huts_path into one
    (Multi)Polygon - the shape filter_trails.py clips trail extraction to, and (via the same
    radius_km) what bavaria-dgm5's per-hut DEM tile buffer must at least match. Returns a Polygon
    when hut circles overlap enough to merge, a MultiPolygon otherwise - callers must handle
    both (shapely.geometry.mapping() does, transparently)."""
    points = hut_points(huts_path)
    circles = [circle_polygon(lng, lat, radius_km, n_points) for lng, lat in points]
    return unary_union(circles)
```

`math` is already imported at the top of `lib/pipeline.py` (used elsewhere in the file) - no new
import needed for it.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
conda run -n alpen-osm python -m pytest pipeline/tests/test_hub_range_polygon.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Run the full suite**

```bash
conda run -n alpen-osm python -m pytest pipeline -q
```

Expected: all tests pass (previous count + 7).

- [ ] **Step 6: Commit**

```bash
git add pipeline/lib/pipeline.py pipeline/tests/test_hub_range_polygon.py
git commit -m "feat(pipeline): circle_polygon/hub_range_polygon - union-of-circles hub range"
```

---

### Task 3: `compute_hub_range.py` emits a GeoJSON polygon, not a bbox

**Files:**
- Modify: `pipeline/phases/preprocessing/compute_hub_range.py` (full rewrite)
- Modify: `pipeline/dodo.py` (`task_compute_hub_range`'s target)
- Test: `pipeline/tests/test_compute_hub_range_cli.py` (new file — a thin CLI smoke test, since the
  real geometry logic is already covered by Task 2's tests)

**Interfaces:**
- Consumes: `hub_range_polygon`, `HUB_RANGE_SAFETY_MARGIN` (Task 2, `lib.pipeline`).
- Produces: `data/osm/hub_range.geojson` (replaces `data/osm/hub_range.json` — the file Task 4's
  `filter_trails.py` reads).

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/test_compute_hub_range_cli.py
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "phases" / "preprocessing" / "compute_hub_range.py"


def _write_huts(path, coords):
    fc = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": c}}
            for c in coords
        ],
    }
    path.write_text(json.dumps(fc), encoding="utf-8")


def test_compute_hub_range_writes_geojson_polygon_containing_every_hut(tmp_path):
    osm_dir = tmp_path / "data" / "osm"
    osm_dir.mkdir(parents=True)
    _write_huts(osm_dir / "huts.geojson", [(11.0, 47.0), (11.2, 47.1)])

    # No PYTHONPATH setup needed - the script inserts its own sys.path entry (pipeline root)
    # before importing lib.pipeline, same as every other phases/ script in this codebase.
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--max-edge-km", "30",
         "--osm-dir", str(osm_dir)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr

    out_path = osm_dir / "hub_range.geojson"
    assert out_path.exists()
    with open(out_path, encoding="utf-8") as f:
        geojson = json.load(f)
    assert geojson["type"] in ("Polygon", "MultiPolygon")
```

This test needs `compute_hub_range.py` to accept an `--osm-dir` override so it doesn't depend on
the real `data/osm/` - add that flag in Step 3 alongside the rewrite (it defaults to the real
`OSM_DIR` so `dodo.py`'s invocation is unaffected).

- [ ] **Step 2: Run to verify it fails**

```bash
conda run -n alpen-osm python -m pytest pipeline/tests/test_compute_hub_range_cli.py -v
```

Expected: FAIL - `error: unrecognized arguments: --osm-dir ...` (the flag doesn't exist yet).

- [ ] **Step 3: Rewrite `compute_hub_range.py`**

```python
#!/usr/bin/env python3
"""Computes the "hub range" - the union of a graph.maxEdgeKm-radius circle around every hut in
huts.geojson - and writes it as a GeoJSON Polygon/MultiPolygon to data/osm/hub_range.geojson.
filter_trails.py clips each region's trail extract to this shape via `osmium extract --polygon`:
no trail farther than maxEdgeKm beeline from every hut can ever appear on a valid hut-to-hut/
hut-to-start edge (build_hub_edges.py's real-distance cutoff can only be >= beeline distance) -
the same bound filter_start_points.py already applies to station/parking points.

The radius includes HUB_RANGE_SAFETY_MARGIN (lib.pipeline) so this shape and bavaria-dgm5's
per-hut DEM tile buffer (dem_providers/composite.py) are guaranteed to agree - see
docs/superpowers/specs/2026-08-22-hub-range-dem-coverage.md.

Usage: python pipeline/phases/preprocessing/compute_hub_range.py
"""

import argparse
import json
import sys
from pathlib import Path

from shapely.geometry import mapping

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib.pipeline import HUB_RANGE_SAFETY_MARGIN, OSM_DIR, hub_range_polygon, load_config  # noqa: E402

config = load_config()

parser = argparse.ArgumentParser()
parser.add_argument("--max-edge-km", type=float, default=config["graph"]["maxEdgeKm"])
parser.add_argument("--osm-dir", type=Path, default=OSM_DIR)
args = parser.parse_args()

radius_km = args.max_edge_km * HUB_RANGE_SAFETY_MARGIN
polygon = hub_range_polygon(args.osm_dir / "huts.geojson", radius_km)

out_path = args.osm_dir / "hub_range.geojson"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(mapping(polygon), f)
print(f"hub range (maxEdgeKm={args.max_edge_km} -> {radius_km:.3f} km radius, "
      f"{'MultiPolygon' if polygon.geom_type == 'MultiPolygon' else 'Polygon'}): "
      f"{len(polygon.geoms) if polygon.geom_type == 'MultiPolygon' else 1} piece(s)")
print(f"written {out_path}")
```

- [ ] **Step 4: Run to verify it passes**

```bash
conda run -n alpen-osm python -m pytest pipeline/tests/test_compute_hub_range_cli.py -v
```

Expected: PASS.

- [ ] **Step 5: Update `dodo.py`'s target**

`pipeline/dodo.py`'s `task_compute_hub_range` (around line 188) currently has:

```python
        "targets": [str(OSM_DIR / "hub_range.json")],
```

Change to:

```python
        "targets": [str(OSM_DIR / "hub_range.geojson")],
```

- [ ] **Step 6: Run the full suite**

```bash
conda run -n alpen-osm python -m pytest pipeline -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add pipeline/phases/preprocessing/compute_hub_range.py pipeline/dodo.py pipeline/tests/test_compute_hub_range_cli.py
git commit -m "feat(pipeline): compute_hub_range emits a union-of-circles GeoJSON polygon"
```

---

### Task 4: `filter_trails.py` clips with `--polygon` instead of `--bbox`

**Files:**
- Modify: `pipeline/phases/preprocessing/filter_trails.py`
- Modify: `pipeline/dodo.py` (`task_filter_trails`'s `file_dep`)

**Interfaces:**
- Consumes: `data/osm/hub_range.geojson` (Task 3's output) - a file path, read directly by
  `osmium`, not parsed in Python (unlike the old bbox version, which had to parse it to build a
  `--bbox` string argument).

- [ ] **Step 1: Edit `filter_trails.py`**

Current (lines 1-56, from the earlier bbox-based commit `fb34f4e`):

```python
#!/usr/bin/env python3
"""
Filters each raw region extract down to hiking-relevant ways, using the tag filter from
pipeline.config.json, then clips to the hub range (data/osm/hub_range.json,
compute_hub_range.py's output - every hut's bbox padded by graph.maxEdgeKm). No trail farther
than that from every hut can ever appear on a valid hut-to-hut/hut-to-start edge (see
compute_hub_range.py's docstring), so dropping it here means stream_osm/contract_structural in
build_base_graph.py never have to process it, and add_base_elevation.py never needs DEM coverage
for it either.

Preserves full node/way topology at both steps (osmium tags-filter keeps referenced nodes by
default; `osmium extract`'s default "complete_ways" strategy keeps a way whole if any of its nodes
falls inside the bbox, rather than cutting through it) - required for graph-building later.
Requires osmium-tool installed natively (conda install -c conda-forge osmium-tool) and on PATH -
no Docker.

Usage: python pipeline/phases/preprocessing/filter_trails.py
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib.pipeline import OSM_DIR, load_config  # noqa: E402

config = load_config()

parser = argparse.ArgumentParser()
parser.add_argument("--tag-filter", default=config["trailTagFilter"])
args = parser.parse_args()

with open(OSM_DIR / "hub_range.json", encoding="utf-8") as f:
    hub_range = json.load(f)
bbox_arg = f"{hub_range['minLng']},{hub_range['minLat']},{hub_range['maxLng']},{hub_range['maxLat']}"

for region in config["regions"]:
    name = region["name"]
    src = OSM_DIR / "raw" / f"{name}-latest.osm.pbf"
    tag_filtered = OSM_DIR / f"{name}-tag-filtered.osm.pbf"
    dst = OSM_DIR / f"{name}-trails.osm.pbf"

    print(f"tag-filtering {src} -> {tag_filtered}")
    subprocess.run(
        ["osmium", "tags-filter", str(src), args.tag_filter, "-o", str(tag_filtered), "--overwrite"],
        check=True,
    )

    print(f"clipping {tag_filtered} to hub range {bbox_arg} -> {dst}")
    subprocess.run(
        ["osmium", "extract", "--bbox", bbox_arg, str(tag_filtered), "-o", str(dst), "--overwrite"],
        check=True,
    )
    tag_filtered.unlink()
```

Replace with:

```python
#!/usr/bin/env python3
"""
Filters each raw region extract down to hiking-relevant ways, using the tag filter from
pipeline.config.json, then clips to the hub range (data/osm/hub_range.geojson,
compute_hub_range.py's output - the union of a graph.maxEdgeKm-radius circle around every hut).
No trail farther than that from every hut can ever appear on a valid hut-to-hut/hut-to-start edge
(see compute_hub_range.py's docstring), so dropping it here means stream_osm/contract_structural
in build_base_graph.py never have to process it, and add_base_elevation.py never needs DEM
coverage for it either.

Preserves full node/way topology at both steps (osmium tags-filter keeps referenced nodes by
default; `osmium extract`'s default "complete_ways" strategy keeps a way whole if any of its nodes
falls inside the polygon, rather than cutting through it) - required for graph-building later.
Requires osmium-tool installed natively (conda install -c conda-forge osmium-tool) and on PATH -
no Docker.

Usage: python pipeline/phases/preprocessing/filter_trails.py
"""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib.pipeline import OSM_DIR, load_config  # noqa: E402

config = load_config()

parser = argparse.ArgumentParser()
parser.add_argument("--tag-filter", default=config["trailTagFilter"])
args = parser.parse_args()

hub_range_path = OSM_DIR / "hub_range.geojson"

for region in config["regions"]:
    name = region["name"]
    src = OSM_DIR / "raw" / f"{name}-latest.osm.pbf"
    tag_filtered = OSM_DIR / f"{name}-tag-filtered.osm.pbf"
    dst = OSM_DIR / f"{name}-trails.osm.pbf"

    print(f"tag-filtering {src} -> {tag_filtered}")
    subprocess.run(
        ["osmium", "tags-filter", str(src), args.tag_filter, "-o", str(tag_filtered), "--overwrite"],
        check=True,
    )

    print(f"clipping {tag_filtered} to hub range {hub_range_path} -> {dst}")
    subprocess.run(
        ["osmium", "extract", "--polygon", str(hub_range_path), str(tag_filtered),
         "-o", str(dst), "--overwrite"],
        check=True,
    )
    tag_filtered.unlink()
```

- [ ] **Step 2: Update `dodo.py`'s `file_dep`**

`pipeline/dodo.py`'s `task_filter_trails` (around line 137-138) currently has:

```python
        "file_dep": [str(OSM_DIR / "raw" / f"{n}-latest.osm.pbf") for n in REGION_NAMES]
        + [str(OSM_DIR / "hub_range.json")],
```

Change to:

```python
        "file_dep": [str(OSM_DIR / "raw" / f"{n}-latest.osm.pbf") for n in REGION_NAMES]
        + [str(OSM_DIR / "hub_range.geojson")],
```

- [ ] **Step 3: Manual smoke test (no automated test - this is a subprocess call to a native CLI
  tool, already covered structurally by Task 1's empirical verification)**

```bash
cd pipeline
conda run -n alpen-osm python -c "
import json
from shapely.geometry import Point, mapping
poly = Point(11.0, 47.0).buffer(0.01)
json.dump(mapping(poly), open('/tmp/test_hub_range.geojson', 'w'))
"
osmium extract --polygon /tmp/test_hub_range.geojson --help 2>&1 | head -1
```

Expected: no error (confirms the polygon file arg is accepted; full integration is Task 8).

- [ ] **Step 4: Run the full suite**

```bash
conda run -n alpen-osm python -m pytest pipeline -q
```

Expected: all tests pass (no test currently exercises `filter_trails.py`'s subprocess calls
directly - it's a thin orchestration script over `osmium`, matching this codebase's existing
convention for `merge_trails.py`/`verify_trails.py`, neither of which has a unit test either).

- [ ] **Step 5: Commit**

```bash
git add pipeline/phases/preprocessing/filter_trails.py pipeline/dodo.py
git commit -m "feat(pipeline): filter_trails clips with osmium extract --polygon"
```

---

### Task 5: Remove dead `bbox_from_huts`

**Files:**
- Modify: `pipeline/lib/pipeline.py` (delete `bbox_from_huts`)
- Delete: `pipeline/tests/test_bbox_from_huts.py`

**Interfaces:**
- None - `bbox_from_huts` has no remaining callers after Task 3's rewrite (its only caller,
  `compute_hub_range.py`, now uses `hub_range_polygon` instead; `composite.py` stopped calling it
  when `_resolve_region_bbox` was removed, commit `e8202df`).

- [ ] **Step 1: Confirm no remaining callers**

```bash
grep -rn "bbox_from_huts" pipeline --include=*.py
```

Expected output: only `pipeline/lib/pipeline.py` (the definition) and
`pipeline/tests/test_bbox_from_huts.py` (its test). If anything else appears, stop - something
still depends on it and this task needs re-scoping.

- [ ] **Step 2: Delete the function and its test**

Remove `bbox_from_huts` (the whole function, `pipeline/lib/pipeline.py:206-231` per this plan's
earlier reads - confirm exact lines before deleting, since Task 2 inserted new code above it and
shifted line numbers) and delete `pipeline/tests/test_bbox_from_huts.py` entirely:

```bash
git rm pipeline/tests/test_bbox_from_huts.py
```

- [ ] **Step 3: Run the full suite**

```bash
conda run -n alpen-osm python -m pytest pipeline -q
```

Expected: all tests pass (minus the 3 deleted `test_bbox_from_huts.py` tests).

- [ ] **Step 4: Commit**

```bash
git add pipeline/lib/pipeline.py
git commit -m "refactor(pipeline): remove bbox_from_huts, superseded by hub_range_polygon"
```

---

### Task 6: `bavaria-dgm5`'s DEM buffer is derived from `maxEdgeKm`, not a static config number

**Files:**
- Modify: `pipeline/phases/downloads/dem_providers/composite.py` (`fetch_regions` signature)
- Modify: `pipeline/phases/downloads/fetch_dem.py` (pass `max_edge_km` through)
- Modify: `pipeline/dodo.py` (`task_fetch_dem` gains a `max_edge_km` param, tracked)
- Modify: `pipeline/pipeline.config.json` (remove now-superseded `"bufferKm": 1.5`)
- Modify: `pipeline/tests/test_composite_region_merge.py` (existing test's call signature)

**Interfaces:**
- Consumes: `HUB_RANGE_SAFETY_MARGIN` (Task 2, `lib.pipeline`).
- Produces: `fetch_regions(provider_config: dict, dem_dir: Path, max_edge_km: float) ->
  list[dict]` - signature gains a required third parameter (was `fetch_regions(provider_config,
  dem_dir)`); every caller in this codebase is `fetch_dem.py` and the test file, both updated in
  this task.

- [ ] **Step 1: Write the failing tests**

Add to `pipeline/tests/test_composite_region_merge.py` (after the existing imports):

```python
from lib.pipeline import HUB_RANGE_SAFETY_MARGIN  # noqa: E402
```

Update the existing test's call (it currently has no `bboxFromHuts` region, so behavior is
unchanged except the new required argument):

```python
    manifest = composite.fetch_regions(provider_config, tmp_path, max_edge_km=30.0)
```

Add two new tests:

```python
def test_fetch_regions_computes_bufferkm_from_max_edge_km_for_bboxfromhuts_region(
    tmp_path, monkeypatch
):
    calls = []
    fake_provider = MagicMock()
    fake_provider.fetch.side_effect = lambda cfg, raw_dir: calls.append(cfg) or [
        raw_dir / "tile.tif"
    ]
    monkeypatch.setattr(composite, "get_provider", lambda name: fake_provider)
    monkeypatch.setattr(composite, "_points_for_region", lambda bbox: [[11.0, 47.0]])

    provider_config = {
        "regions": [
            {"provider": "bavaria-dgm5",
             "bbox": {"minLng": 0, "maxLng": 1, "minLat": 0, "maxLat": 1},
             "bboxFromHuts": True},
        ]
    }

    composite.fetch_regions(provider_config, tmp_path, max_edge_km=30.0)

    assert calls[0]["bufferKm"] == pytest.approx(30.0 * HUB_RANGE_SAFETY_MARGIN)


def test_fetch_regions_preserves_region_order_for_gdalbuildvrt_priority(tmp_path, monkeypatch):
    calls = []
    fake_provider = MagicMock()
    fake_provider.fetch.side_effect = lambda cfg, raw_dir: calls.append(cfg["provider"]) or [
        raw_dir / "tile.tif"
    ]
    monkeypatch.setattr(composite, "get_provider", lambda name: fake_provider)
    monkeypatch.setattr(composite, "_points_for_region", lambda bbox: [[11.0, 47.0]])

    provider_config = {
        "regions": [
            {"provider": "copernicus-glo-30", "bbox": {"minLng": 0, "maxLng": 1, "minLat": 0, "maxLat": 1}},
            {"provider": "bavaria-dgm5",
             "bbox": {"minLng": 0, "maxLng": 1, "minLat": 0, "maxLat": 1}, "bboxFromHuts": True},
            {"provider": "at-bev-dgm", "bbox": {"minLng": 0, "maxLng": 1, "minLat": 0, "maxLat": 1}},
        ]
    }

    manifest = composite.fetch_regions(provider_config, tmp_path, max_edge_km=30.0)

    assert [m["provider"] for m in manifest] == ["copernicus-glo-30", "bavaria-dgm5", "at-bev-dgm"]
    assert calls == ["copernicus-glo-30", "bavaria-dgm5", "at-bev-dgm"]
```

`pytest` needs importing at the top of this test file if not already present - check first:

```bash
grep -n "^import pytest" pipeline/tests/test_composite_region_merge.py
```

If missing, add `import pytest` alongside the existing imports.

- [ ] **Step 2: Run to verify they fail**

```bash
conda run -n alpen-osm python -m pytest pipeline/tests/test_composite_region_merge.py -v
```

Expected: the updated existing test fails with `TypeError: fetch_regions() missing 1 required
positional argument: 'max_edge_km'`; the two new tests fail the same way.

- [ ] **Step 3: Implement**

`pipeline/phases/downloads/dem_providers/composite.py` - update the import line and
`fetch_regions`:

```python
from lib.pipeline import HUB_RANGE_SAFETY_MARGIN, OSM_DIR, edge_points, hut_points  # noqa: E402
```

```python
def fetch_regions(provider_config: dict, dem_dir: Path, max_edge_km: float) -> list[dict]:
    """Resolves each configured region's bbox/points and downloads its raw tiles, returning a
    JSON-serializable manifest ([{"provider", "raw_dir", "region_vrt", "tile_paths"}, ...]) -
    lib.pipeline.build_dem_vrt() consumes this to do the actual reprojection/merge, with no
    network access of its own. max_edge_km (graph.maxEdgeKm) sizes any bboxFromHuts region's
    per-hut buffer - see HUB_RANGE_SAFETY_MARGIN's docstring for why this must be the same value
    compute_hub_range.py uses for filter_trails.py's clip, not an independently-set number. See
    module docstring for why fetch and build are separate scripts."""
    manifest = []
    for i, region_config in enumerate(provider_config["regions"]):
        if region_config.get("bboxFromHuts"):
            region_config = {
                **region_config,
                "points": _points_for_region(region_config["bbox"]),
                "bufferKm": max_edge_km * HUB_RANGE_SAFETY_MARGIN,
            }
        provider = get_provider(region_config["provider"])
        raw_dir = dem_dir / "raw" / f"region_{i}_{region_config['provider']}"
        region_vrt = dem_dir / f"region_{i}_{region_config['provider']}.vrt"

        print(f"composite region {i}: {region_config['provider']} ...")
        tile_paths = provider.fetch(region_config, raw_dir)
        manifest.append({
            "provider": region_config["provider"],
            "raw_dir": str(raw_dir),
            "region_vrt": str(region_vrt),
            "tile_paths": [str(p) for p in tile_paths],
        })
    return manifest
```

`pipeline/phases/downloads/fetch_dem.py` - add the CLI flag and pass it through:

```python
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dem_providers import get_provider  # noqa: E402
from lib.pipeline import DEM_DIR, load_config  # noqa: E402

config = load_config()

parser = argparse.ArgumentParser()
parser.add_argument("--max-edge-km", type=float, default=config["graph"]["maxEdgeKm"])
args = parser.parse_args()

dem_config = config["dem"]
provider_name = dem_config.get("provider", "copernicus-glo-30")

provider_config = dict(dem_config.get("providerConfig", {}))
provider_config.setdefault("bbox", config["bbox"])

DEM_DIR.mkdir(parents=True, exist_ok=True)

if provider_name == "composite":
    from dem_providers.composite import fetch_regions  # noqa: E402
    manifest = fetch_regions(provider_config, DEM_DIR, max_edge_km=args.max_edge_km)
else:
    print(f"fetching DEM tiles via provider {provider_name!r} ...")
    provider = get_provider(provider_name)
    raw_dir = DEM_DIR / "raw"
    tile_paths = provider.fetch(provider_config, raw_dir)
    print(f"{len(tile_paths)} tiles present")
    manifest = [{
        "provider": provider_name,
        "raw_dir": str(raw_dir),
        "region_vrt": str(DEM_DIR / f"region_0_{provider_name}.vrt"),
        "tile_paths": [str(p) for p in tile_paths],
    }]

manifest_path = DEM_DIR / "fetch_manifest.json"
with open(manifest_path, "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2)
n_tiles = sum(len(r["tile_paths"]) for r in manifest)
print(f"written {manifest_path} ({n_tiles} tiles across {len(manifest)} region(s))")
```

`pipeline/dodo.py`'s `task_fetch_dem` - it must now track `max_edge_km` too, since changing
`graph.maxEdgeKm` changes what Bavaria's DEM fetch actually does (the exact class of caching bug
this whole investigation started from - a value a task's *behavior* depends on must be in its
tracked `params`, never left implicit). Current (around line 232):

```python
def task_fetch_dem():
    return {
        "actions": [py("phases/downloads/fetch_dem.py")],
        # fetch_dem.py reads config["dem"] (provider name + provider-specific nested config) and
        # config["bbox"] directly - neither is a sensible CLI flag, so these params exist only to
        # track them via TaskOptionsChanged instead of the whole pipeline.config.json file - keep
        # the key paths here in sync with what the script actually reads.
        "params": [
            {"name": "dem_json", "long": "dem-json", "type": str,
             "default": json.dumps(CONFIG["dem"], sort_keys=True)},
            {"name": "bbox_json", "long": "bbox-json", "type": str,
             "default": json.dumps(CONFIG["bbox"], sort_keys=True)},
        ],
        "targets": [str(DEM_DIR / "fetch_manifest.json")],
        "uptodate": [TaskOptionsChanged()],
    }
```

Change to:

```python
def task_fetch_dem():
    return {
        "actions": [
            f'"{sys.executable}" "{SCRIPT_DIR / "phases" / "downloads" / "fetch_dem.py"}"'
            " --max-edge-km %(max_edge_km)s"
        ],
        # fetch_dem.py reads config["dem"] (provider name + provider-specific nested config) and
        # config["bbox"] directly - neither is a sensible CLI flag, so these params exist only to
        # track them via TaskOptionsChanged instead of the whole pipeline.config.json file - keep
        # the key paths here in sync with what the script actually reads. max_edge_km IS a real
        # flag (unlike the two above) - it sizes bavaria-dgm5's per-hut buffer (see
        # dem_providers/composite.py's fetch_regions), so a maxEdgeKm change must invalidate this
        # task too, not just compute_hub_range/filter_trails.
        "params": [
            {"name": "dem_json", "long": "dem-json", "type": str,
             "default": json.dumps(CONFIG["dem"], sort_keys=True)},
            {"name": "bbox_json", "long": "bbox-json", "type": str,
             "default": json.dumps(CONFIG["bbox"], sort_keys=True)},
            {"name": "max_edge_km", "long": "max-edge-km", "type": float,
             "default": CONFIG["graph"]["maxEdgeKm"]},
        ],
        "targets": [str(DEM_DIR / "fetch_manifest.json")],
        "uptodate": [TaskOptionsChanged()],
    }
```

`pipeline/pipeline.config.json` - remove the now-superseded static buffer (it would otherwise sit
there unused and misleading, since `fetch_regions` always overwrites `bufferKm` for a
`bboxFromHuts` region):

```jsonc
        {
          "provider": "bavaria-dgm5",
          "bbox": { "minLng": 8.9, "maxLng": 13.9, "minLat": 47.2, "maxLat": 50.6 },
          "bboxFromHuts": true
        },
```

(drops the `"bufferKm": 1.5,` line - remember to remove the now-dangling comma from the previous
line if editing by hand).

- [ ] **Step 4: Run the full suite**

```bash
conda run -n alpen-osm python -m pytest pipeline -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add pipeline/phases/downloads/dem_providers/composite.py pipeline/phases/downloads/fetch_dem.py pipeline/dodo.py pipeline/pipeline.config.json pipeline/tests/test_composite_region_merge.py
git commit -m "feat(pipeline): bavaria-dgm5's DEM buffer derives from graph.maxEdgeKm"
```

---

### Task 7: Copernicus GLO-30 as a low-priority coverage floor

**Files:**
- Modify: `pipeline/pipeline.config.json` (`dem.providerConfig.regions` gains a third, first-listed
  entry)

**Interfaces:**
- None new - `copernicus.py` already implements the standard provider contract
  (`fetch(provider_config, raw_dir)`, `to_4326_vrt(tile_paths, out_vrt_path)`) and is already
  registered in `dem_providers/__init__.py`'s `_REGISTRY`. `fetch_regions` (Task 6) already
  iterates any number of regions generically - Task 6's
  `test_fetch_regions_preserves_region_order_for_gdalbuildvrt_priority` already covers a 3-region
  case with Copernicus listed first, so this task is config-only.

- [ ] **Step 1: Edit `pipeline.config.json`**

Current `dem.providerConfig.regions` (lines 19-31, after Task 6's edit removes `bufferKm`):

```jsonc
      "regions": [
        {
          "provider": "bavaria-dgm5",
          "bbox": { "minLng": 8.9, "maxLng": 13.9, "minLat": 47.2, "maxLat": 50.6 },
          "bboxFromHuts": true
        },
        {
          "provider": "at-bev-dgm",
          "bbox": { "minLng": 9.5, "maxLng": 17.2, "minLat": 46.3, "maxLat": 49.0 },
          "downloadUrl": "https://gis.ktn.gv.at/OGD/Geographie_Planung/ogd-10m-at.zip"
        }
      ]
```

Change to:

```jsonc
      "regions": [
        {
          "provider": "copernicus-glo-30",
          "bbox": { "minLng": 8.9, "maxLng": 17.2, "minLat": 46.3, "maxLat": 50.6 }
        },
        {
          "provider": "bavaria-dgm5",
          "bbox": { "minLng": 8.9, "maxLng": 13.9, "minLat": 47.2, "maxLat": 50.6 },
          "bboxFromHuts": true
        },
        {
          "provider": "at-bev-dgm",
          "bbox": { "minLng": 9.5, "maxLng": 17.2, "minLat": 46.3, "maxLat": 49.0 },
          "downloadUrl": "https://gis.ktn.gv.at/OGD/Geographie_Planung/ogd-10m-at.zip"
        }
      ]
```

Copernicus is listed **first**: `composite.py`'s module docstring documents that `gdalbuildvrt`
takes the **last**-listed source for overlapping pixels, so this makes it lowest-priority -
painted over by both national sources wherever they have real data, visible only in gaps neither
reaches (a border-adjacent hut's range dipping into a third country). Its `bbox` is the full
nominal bbox (`config["bbox"]`, copied here explicitly for clarity, not `bboxFromHuts` - it's the
floor, not a targeted per-hut fetch).

- [ ] **Step 2: Run the full suite**

```bash
conda run -n alpen-osm python -m pytest pipeline -q
```

Expected: all tests pass (this task adds no new code, only config - Task 6's new tests already
cover the 3-region ordering behavior this config change exercises for real).

- [ ] **Step 3: Commit**

```bash
git add pipeline/pipeline.config.json
git commit -m "feat(pipeline): add Copernicus GLO-30 as a low-priority DEM coverage floor"
```

---

### Task 8: Rebuild and verify - the real test

**Files:** none - this is a run plus verification, like the existing plan's Task 9/24 pattern.

- [ ] **Step 1: Show the user the cost, and get confirmation** **[ASK FIRST]**

This reruns the DAG from `compute_hub_range` through `add_base_elevation` - `filter_trails`'s
output genuinely changes (new polygon clip), so `merge_trails`/`build_base_graph` cascade too
(~18-25 min for `build_base_graph` alone, per `data/timings.jsonl`), plus a **new** Copernicus
GLO-30 fetch (first time this provider has ever been fetched - whole-degree tiles over the full
bbox, expect on the order of 10-15 tiles based on the bbox's degree-span, each a few hundred MB -
budget for this being the single most expensive part of the DEM refetch, more than the incremental
Bavaria/Austria re-verification).

```bash
doit info compute_hub_range filter_trails merge_trails build_base_graph fetch_dem build_dem_vrt add_base_elevation
```

Confirm nothing unexpected shows `up-to-date` that should be stale, or vice versa, before running.

- [ ] **Step 2: Run** **[ASK FIRST]**

```bash
doit build_base_graph add_base_elevation
```

(Same target list as the previous attempt - `compute_hub_range`/`filter_trails`/`merge_trails`/
`fetch_dem`/`build_dem_vrt` are all upstream file_dep of these two and will be pulled in
automatically, per this session's earlier finding that doit resolves `file_dep` to its producing
task's target transitively.)

- [ ] **Step 3: Verify no `WindowError`, and real coverage**

```bash
python -c "
import numpy as np
e = np.load('data/osm/base_graph/edges.npy', mmap_mode='r')
print(len(e), 'edges')
for f in ('time_s', 'ascent_m', 'descent_m'):
    col = np.asarray(e[f]); print(f, 'min', float(col.min()), 'max', float(col.max()))
"
```

Expected: the run completes without a `rasterio.errors.WindowError` traceback (the original
crash), and no field is still sitting at its `UNSET`/`-1.0` sentinel value anywhere.

- [ ] **Step 4: Record the timing and Copernicus tile count in the findings doc**

```bash
tail -10 data/timings.jsonl
```

Append a short note to `docs/superpowers/specs/2026-08-22-tour-suggestion-findings.md` (the
existing findings doc from the parent plan) recording: `add_base_elevation`'s wall time on this
run, and how many Copernicus tiles were fetched (`data/dem/fetch_manifest.json`'s first region
entry's `tile_paths` length) - both feed later cost estimates for `graph.maxEdgeKm` retuning.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-08-22-tour-suggestion-findings.md
git commit -m "docs: record hub-range/DEM-coverage rebuild timing"
```
