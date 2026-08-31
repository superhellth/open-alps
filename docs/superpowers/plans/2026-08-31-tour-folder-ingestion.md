# Tour Folder Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the AV-ArcGIS-fragment/Outdooractive-fallback tour input with the reproducible
`pipeline/tours/<Name>/<N>.gpx` folder format, retarget `match_tour_edges.py` to consume it, and
delete the id-resolution/fragment-reassembly machinery it makes obsolete.

**Architecture:** A new `lib/tour_folder.py` parses one ordered `(lon, lat)` list per leg from each
tour folder's numbered GPX files. A new `nearest_hub_to_point` in `lib/hubs.py` snaps each leg's raw
GPX endpoints onto the existing `(type, id)` hub vocabulary, replacing the deleted
`lib/tour_geometry.py`'s chain-reassembly/hut-position logic. `match_tour_edges.py` keeps its
corridor/route/record core (`corridor_bounds`, `match_leg`, `_cached_gather_for_bounds`,
`write_edge_records`) untouched in shape, but drives it from GPX legs instead of reassembled AV
fragments, and its `build_tour_record` takes `(type, id)` endpoint pairs instead of bare hut
indices. `tours.json` becomes an index of per-leg endpoint intent, written directly by
`match_tour_edges.py` instead of by `fetch_tours.py`.

**Tech Stack:** Python 3.11, numpy structured arrays (`lib/binfmt.py`), `doit` task DAG, stdlib
`xml.etree.ElementTree` for GPX parsing (no new dependency), pytest.

**Spec:** `docs/superpowers/specs/2026-08-30-tour-folder-ingestion-design.md`

## Global Constraints

- Never run any `pipeline/` task (`doit <task>` or bare `doit`) without first asking the user and
  getting explicit confirmation — even a task that looks cheap or read-only (root `CLAUDE.md`).
- No new pipeline hyperparameters beyond what the spec names. Endpoint snapping reuses
  `pipeline.config.json`'s existing `graph.maxSnapM` (100 m) — never a new config field, never the
  old `tourMatch.maxHutTraceM` (250 m, deleted).
- Leg order comes from the filename's integer value, sorted numerically, never lexicographically,
  never `readdir` order. A non-numeric filename stem is a hard error naming the file.
- Every leg endpoint (including internal tour boundaries) is snapped independently — never assumed
  identical because two leg files were authored to touch.
- No `isLoop` field anywhere in the new code path — closed-tour ambiguity cannot exist once each
  leg is its own directed file.
- Fix defects at their root layer (root `CLAUDE.md`): this plan only touches `pipeline/`; nothing
  here papers over a `huts/` concern or vice versa.
- All docs/specs/plans this work produces live under `docs/superpowers/`; remove a completed
  backlog item's `.md` file and its `docs/backlog.md` entry together, if any exists for this work.

---

## Task 1: Config trim + `TOURS_DIR` constant

**Files:**
- Modify: `pipeline/pipeline.config.json`
- Modify: `pipeline/lib/pipeline.py`
- Modify: `pipeline/tests/test_config.py`
- Test: `pipeline/tests/test_config.py`, `pipeline/tests/test_pipeline_paths.py` (create if no such
  file exists for path constants; otherwise add to whichever test file already covers
  `lib/pipeline.py`'s constants — check with `grep -rl "OSM_DIR\b" pipeline/tests | xargs grep -l
  "DATA_DIR ="` before creating a new file)

**Interfaces:**
- Produces: `lib.pipeline.TOURS_DIR` (a `Path`, `pipeline/tours` resolved off `SCRIPTS_DIR` exactly
  like `DEM_DIR`/`OSM_DIR`), consumed by Task 4 (`match_tour_edges.py`) and Task 6
  (`dag/graph_building.py`).

- [ ] **Step 1: Trim `tourMatch` in `pipeline.config.json`**

Open `pipeline/pipeline.config.json` and change the `tourMatch` block from:
```json
"tourMatch": {
  "fragmentBreakM": 150.0,
  "corridorBufferM": 150.0,
  "maxHutTraceM": 250.0,
  "lengthDivergenceRatio": 2.0
}
```
to:
```json
"tourMatch": {
  "corridorBufferM": 150.0,
  "lengthDivergenceRatio": 2.0
}
```

- [ ] **Step 2: Update `test_config.py`**

Replace `test_tour_match_config_has_all_four_thresholds` in `pipeline/tests/test_config.py` with:
```python
def test_tour_match_config_has_the_two_kept_thresholds():
    config = load_config()
    tm = config["tourMatch"]
    assert set(tm.keys()) == {"corridorBufferM", "lengthDivergenceRatio"}
    assert tm["corridorBufferM"] == 150.0
    assert tm["lengthDivergenceRatio"] == 2.0
```

- [ ] **Step 3: Run the config test to verify it passes**

Run: `cd pipeline && .pixi/envs/default/bin/pytest tests/test_config.py -v`
Expected: PASS (2 tests: `test_config_has_no_road_penalty_factor`,
`test_tour_match_config_has_the_two_kept_thresholds`)

- [ ] **Step 4: Add `TOURS_DIR` to `lib/pipeline.py`**

In `pipeline/lib/pipeline.py`, next to the existing `DATA_DIR`/`OSM_DIR`/`DEM_DIR`/`CONFIG_PATH`/
`PUBLIC_DATA_DIR` constants, add:
```python
TOURS_DIR = SCRIPTS_DIR / "tours"
```
(`SCRIPTS_DIR` already resolves to `pipeline/`, so this is `pipeline/tours` — the tracked-in-git
tour-folder input directory, spec §1.)

- [ ] **Step 5: Write a test proving `TOURS_DIR` resolves correctly**

Add to whichever test file covers `lib/pipeline.py`'s path constants (or create
`pipeline/tests/test_pipeline_paths.py` if none does):
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.pipeline import TOURS_DIR  # noqa: E402


def test_tours_dir_is_pipeline_tours():
    assert TOURS_DIR.name == "tours"
    assert TOURS_DIR.parent.name == "pipeline"
    assert (TOURS_DIR / "Kaisertour").is_dir()
```

- [ ] **Step 6: Run it**

Run: `cd pipeline && .pixi/envs/default/bin/pytest tests/test_pipeline_paths.py -v` (or the file you
added to)
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add pipeline/pipeline.config.json pipeline/lib/pipeline.py pipeline/tests/test_config.py \
  pipeline/tests/test_pipeline_paths.py
git commit -m "pipeline: trim tourMatch config, add TOURS_DIR constant"
```
(Drop the `test_pipeline_paths.py` path from the `git add` if you added the test to an existing
file instead.)

---

## Task 2: `lib/tour_folder.py` — GPX leg parser

**Files:**
- Create: `pipeline/lib/tour_folder.py`
- Test: `pipeline/tests/test_tour_folder.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `parse_leg_gpx(path: Path) -> list[tuple[float, float]]`
  - `load_tour_folder(folder: Path) -> list[tuple[int, list[tuple[float, float]]]]` — `(leg_number,
    points)` pairs, numerically sorted by filename.
  - `load_all_tour_folders(tours_dir: Path) -> list[tuple[str, Path]]` — `(tour_name, folder_path)`
    pairs, sorted by folder name.

  Consumed by Task 4 (`match_tour_edges.py`).

- [ ] **Step 1: Write the fixture GPX files**

Create `pipeline/tests/fixtures/tour_folder/GoodTour/1.gpx`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><trkseg>
    <trkpt lat="47.1" lon="11.1"><ele>1000</ele></trkpt>
    <trkpt lat="47.2" lon="11.2"></trkpt>
  </trkseg></trk>
</gpx>
```
Create `pipeline/tests/fixtures/tour_folder/GoodTour/2.gpx`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><trkseg>
    <trkpt lat="47.2" lon="11.2"></trkpt>
    <trkpt lat="47.3" lon="11.3"></trkpt>
  </trkseg></trk>
</gpx>
```
Create `pipeline/tests/fixtures/tour_folder/NumericOrderTour/1.gpx` and `.../10.gpx` and
`.../2.gpx` (three files, each with the same two-point `<trkseg>` body as above but distinct
coordinates, e.g. `(0.0, 0.0)`/`(1.0, 1.0)` for `1.gpx`, `(2.0,2.0)`/`(3.0,3.0)` for `2.gpx`,
`(4.0,4.0)`/`(5.0,5.0)` for `10.gpx` — the point values don't matter, only which file's number
sorts where).
Create `pipeline/tests/fixtures/tour_folder/BadTour/leg-one.gpx` (any valid GPX body — the point is
the non-numeric filename stem).
Create `pipeline/tests/fixtures/tour_folder/GoodTour/readme.txt` with any content (proves non-.gpx
files are ignored).

- [ ] **Step 2: Write the failing tests**

Create `pipeline/tests/test_tour_folder.py`:
```python
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.tour_folder import (  # noqa: E402
    load_all_tour_folders, load_tour_folder, parse_leg_gpx,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "tour_folder"


def test_parse_leg_gpx_returns_ordered_lon_lat_ignoring_ele():
    points = parse_leg_gpx(FIXTURES / "GoodTour" / "1.gpx")
    assert points == [(11.1, 47.1), (11.2, 47.2)]


def test_load_tour_folder_orders_legs_by_filename_and_ignores_non_gpx():
    legs = load_tour_folder(FIXTURES / "GoodTour")
    assert [n for n, _ in legs] == [1, 2]
    assert legs[0][1] == [(11.1, 47.1), (11.2, 47.2)]


def test_load_tour_folder_sorts_numerically_not_lexicographically():
    legs = load_tour_folder(FIXTURES / "NumericOrderTour")
    assert [n for n, _ in legs] == [1, 2, 10]  # not [1, 10, 2]


def test_load_tour_folder_raises_on_non_numeric_stem():
    with pytest.raises(ValueError, match="leg-one.gpx"):
        load_tour_folder(FIXTURES / "BadTour")


def test_load_all_tour_folders_sorted_by_name():
    names = [name for name, _ in load_all_tour_folders(FIXTURES)]
    assert names == sorted(names)
    assert "GoodTour" in names
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd pipeline && .pixi/envs/default/bin/pytest tests/test_tour_folder.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lib.tour_folder'`

- [ ] **Step 4: Implement `lib/tour_folder.py`**

```python
"""Parses pipeline/tours/<TourName>/<N>.gpx folders into ordered per-leg point lists - the
reproducible-by-construction tour input format (docs/superpowers/specs/
2026-08-30-tour-folder-ingestion-design.md §1). One tour = one folder; one leg = one GPX file,
numbered by filename, sorted numerically - never lexicographically, never readdir order."""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

_GPX_NS = {"gpx": "http://www.topografix.com/GPX/1/1"}
_LEG_NUMBER_RE = re.compile(r"\d+")


def parse_leg_gpx(path: Path) -> list:
    """Ordered (lon, lat) list from a GPX file's <trk>/<trkseg>/<trkpt> points. <ele> and <wpt>
    are ignored - elevation comes from the graph's own profiles, like every other edge (spec §1)."""
    root = ET.parse(path).getroot()
    return [
        (float(pt.get("lon")), float(pt.get("lat")))
        for pt in root.findall(".//gpx:trk/gpx:trkseg/gpx:trkpt", _GPX_NS)
    ]


def _leg_number(path: Path) -> int:
    if not _LEG_NUMBER_RE.fullmatch(path.stem):
        raise ValueError(f"tour leg filename must be a plain integer, got: {path}")
    return int(path.stem)


def load_tour_folder(folder: Path) -> list:
    """[(leg_number, points), ...] for one tour folder, sorted numerically by filename (spec §1).
    leg_number is the raw integer from the filename; legIndex = leg_number - 1 (spec §4)."""
    numbered = [(_leg_number(f), f) for f in folder.glob("*.gpx")]
    numbered.sort(key=lambda t: t[0])
    return [(n, parse_leg_gpx(f)) for n, f in numbered]


def load_all_tour_folders(tours_dir: Path) -> list:
    """[(tour_name, folder_path), ...] sorted by folder name - spec §4's tourId assignment order
    ("iterating pipeline/tours/ sorted by folder name")."""
    return sorted(
        ((p.name, p) for p in Path(tours_dir).iterdir() if p.is_dir()),
        key=lambda t: t[0],
    )
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd pipeline && .pixi/envs/default/bin/pytest tests/test_tour_folder.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add pipeline/lib/tour_folder.py pipeline/tests/test_tour_folder.py pipeline/tests/fixtures/tour_folder
git commit -m "pipeline: add GPX tour-folder parser"
```

---

## Task 3: `lib/hubs.py` — nearest-hub endpoint snapping

**Files:**
- Modify: `pipeline/lib/hubs.py`
- Test: `pipeline/tests/test_hubs.py` (new file — no test currently covers `lib/hubs.py`)

**Interfaces:**
- Consumes: `binfmt.TYPE_HUT`/`TYPE_STATION`/`TYPE_PARKING`/`TYPE_PARTNER`, `load_all_hubs`'s
  existing `{id, type, lon, lat, name}` hub dict shape.
- Produces:
  - `HUB_TYPE_JSON_NAMES: dict[int, str]` — `{TYPE_HUT: "hut", TYPE_STATION: "station",
    TYPE_PARKING: "parking", TYPE_PARTNER: "partner_betrieb"}`.
  - `nearest_hub_to_point(hubs: list, point: tuple, max_snap_m: float) -> tuple` — returns
    `(chosen, nearest, nearest_dist_m)`: `chosen` is the hub dict actually snapped to (preferring
    `TYPE_HUT` over any other type when both are within `max_snap_m`) or `None` if nothing is in
    range; `nearest`/`nearest_dist_m` describe the single closest candidate of ANY type regardless
    of range, for gap reporting (spec §5's `leg_endpoint_unsnapped` must carry the nearest miss).

  Consumed by Task 4 (`match_tour_edges.py`).

- [ ] **Step 1: Write the failing tests**

Create `pipeline/tests/test_hubs.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import binfmt  # noqa: E402
from lib.hubs import HUB_TYPE_JSON_NAMES, nearest_hub_to_point  # noqa: E402


def _hub(id_, type_, lon, lat, name=""):
    return {"id": id_, "type": type_, "lon": lon, "lat": lat, "name": name}


def test_nearest_hub_to_point_snaps_to_hut_within_range():
    hubs = [_hub(0, binfmt.TYPE_HUT, 11.0, 47.0, name="Test Hut")]
    chosen, nearest, dist = nearest_hub_to_point(hubs, (11.0005, 47.0), max_snap_m=100.0)
    assert chosen == hubs[0]
    assert nearest == hubs[0]
    assert dist < 100.0


def test_nearest_hub_to_point_snaps_to_station_within_range():
    hubs = [_hub(5, binfmt.TYPE_STATION, 11.0, 47.0)]
    chosen, _, _ = nearest_hub_to_point(hubs, (11.0003, 47.0), max_snap_m=100.0)
    assert chosen["type"] == binfmt.TYPE_STATION
    assert chosen["id"] == 5


def test_nearest_hub_to_point_prefers_hut_over_equidistant_access_point():
    # A hut and a parking spot both within max_snap_m, hut slightly farther but still in range -
    # hut wins (spec §2: "a leg ending at a hut beside a car park resolves to the hut").
    point = (11.0, 47.0)
    hut = _hub(0, binfmt.TYPE_HUT, 11.0005, 47.0)
    parking = _hub(0, binfmt.TYPE_PARKING, 11.0002, 47.0)
    chosen, _, _ = nearest_hub_to_point([parking, hut], point, max_snap_m=100.0)
    assert chosen["type"] == binfmt.TYPE_HUT


def test_nearest_hub_to_point_beyond_max_snap_m_returns_none_but_reports_nearest():
    far_hub = _hub(0, binfmt.TYPE_HUT, 12.0, 48.0)
    point = (11.0, 47.0)
    chosen, nearest, dist = nearest_hub_to_point([far_hub], point, max_snap_m=100.0)
    assert chosen is None
    assert nearest == far_hub
    assert dist > 100.0


def test_nearest_hub_to_point_empty_hubs_returns_none():
    chosen, nearest, dist = nearest_hub_to_point([], (11.0, 47.0), max_snap_m=100.0)
    assert chosen is None and nearest is None and dist == float("inf")


def test_hub_type_json_names_covers_all_four_types():
    assert HUB_TYPE_JSON_NAMES == {
        binfmt.TYPE_HUT: "hut", binfmt.TYPE_STATION: "station",
        binfmt.TYPE_PARKING: "parking", binfmt.TYPE_PARTNER: "partner_betrieb",
    }
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd pipeline && .pixi/envs/default/bin/pytest tests/test_hubs.py -v`
Expected: FAIL with `ImportError: cannot import name 'nearest_hub_to_point'`

- [ ] **Step 3: Implement in `lib/hubs.py`**

Add to the top of `pipeline/lib/hubs.py` (after the existing imports):
```python
from lib.geo import haversine_m as _haversine_m

HUB_TYPE_JSON_NAMES = {
    binfmt.TYPE_HUT: "hut", binfmt.TYPE_STATION: "station",
    binfmt.TYPE_PARKING: "parking", binfmt.TYPE_PARTNER: "partner_betrieb",
}
```

Append at the end of the file:
```python
def nearest_hub_to_point(hubs: list, point: tuple, max_snap_m: float) -> tuple:
    """Nearest hub to `point` from the combined hub set (spec 2026-08-30-tour-folder-ingestion-
    design.md §2's endpoint-snapping table) - the transpose of the deleted lib/tour_geometry.py's
    assign_hut_position (nearest *hub* to an endpoint, not nearest *chain point* to a hut).
    Preferring TYPE_HUT over any other type when both sit within max_snap_m, so a leg ending at a
    hut beside a car park resolves to the hut.

    Returns (chosen, nearest, nearest_dist_m). `nearest`/`nearest_dist_m` describe the single
    closest candidate of ANY type, regardless of range or whether it was chosen - needed so a
    leg_endpoint_unsnapped gap can report what the nearest miss was (spec §5), which
    assign_hut_position could not (it discarded the distance on failure). `chosen` is None when
    nothing is within max_snap_m."""
    if not hubs:
        return None, None, float("inf")

    dists = [(_haversine_m(point[0], point[1], h["lon"], h["lat"]), h) for h in hubs]
    nearest_dist, nearest = min(dists, key=lambda t: t[0])

    in_range = [(d, h) for d, h in dists if d <= max_snap_m]
    if not in_range:
        return None, nearest, nearest_dist

    huts_in_range = [(d, h) for d, h in in_range if h["type"] == binfmt.TYPE_HUT]
    pool = huts_in_range if huts_in_range else in_range
    _, chosen = min(pool, key=lambda t: t[0])
    return chosen, nearest, nearest_dist
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd pipeline && .pixi/envs/default/bin/pytest tests/test_hubs.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add pipeline/lib/hubs.py pipeline/tests/test_hubs.py
git commit -m "pipeline: add nearest-hub endpoint snapping to lib/hubs.py"
```

---

## Task 4: Retarget `match_tour_edges.py`

**Files:**
- Modify: `pipeline/phases/graph_building/match_tour_edges.py`

**Interfaces:**
- Consumes: `lib.tour_folder.load_all_tour_folders`/`load_tour_folder` (Task 2),
  `lib.hubs.load_all_hubs`/`nearest_hub_to_point`/`HUB_TYPE_JSON_NAMES` (Task 3),
  `lib.pipeline.TOURS_DIR` (Task 1). Everything else it already imports (`hub_snap`,
  `cell_igraph`, `edge_output`, `subgraph`, `grid`) is unchanged.
- Produces: `data/osm/tour_edges/{records.npy,geometry.npy,edge_ids.npy,tour_meta.npy}`,
  `data/osm/tours.json`, `data/osm/tour-match-gaps.json` — same target set as before, `tours.json`
  now written by this script instead of by the deleted `fetch_tours.py`.

- [ ] **Step 1: Delete `build_tour_legs` and the `_chain_for_tour` machinery**

In `pipeline/phases/graph_building/match_tour_edges.py`, delete these functions entirely:
`build_tour_legs`, `_chain_for_tour`. Delete the import line:
```python
from lib.tour_geometry import (
    assign_hut_position, leg_chain_slice, orient_chain, reassemble_fragments,
)
```

- [ ] **Step 2: Rename `match_leg`'s `hut_unsnapped` reason to `hub_unsnapped`**

In `match_leg`, change:
```python
        return {"ok": False, "reason": "hut_unsnapped", "detail": {"missing": missing}}
```
to:
```python
        return {"ok": False, "reason": "hub_unsnapped", "detail": {"missing": missing}}
```
(spec §5: "Renamed from today's `hut_unsnapped`: §2 endpoints can be stations or parking, so the
old name would misreport them.")

- [ ] **Step 3: Generalize `corridor_bounds`'s caller and drop the `all_points` fallback**

No change needed to `corridor_bounds` itself (it already takes a plain `points` list) — this step
is a no-op reminder that Step 6 passes each leg's own GPX points directly, with no `all_points`
fallback (every leg now always has its own trace).

- [ ] **Step 4: Rewrite `build_tour_record` to take `(type, id)` endpoint pairs**

Replace:
```python
def build_tour_record(from_hut: int, to_hut: int, from_coord: tuple, to_coord: tuple,
                       path, src_snap, tgt_snap) -> dict:
    """..."""
    snap_m, ascent_m, descent_m = fold_endpoint_snaps(path, src_snap, tgt_snap)
    geometry = [from_coord, *path.coords, to_coord]
    return {
        "from_id": from_hut, "to_id": to_hut,
        "from_type": binfmt.TYPE_HUT, "to_type": binfmt.TYPE_HUT,
        "variant": binfmt.VARIANT_OFFICIAL,
        ...
```
with:
```python
def build_tour_record(from_key: tuple, to_key: tuple, from_coord: tuple, to_coord: tuple,
                       path, src_snap, tgt_snap) -> dict:
    """Packs one routed leg into the dict shape lib.edge_output.write_edge_records expects -
    applies the SAME endpoint treatment build_hub_edges.py applies: snap_m/gap_dz_m folded via
    fold_endpoint_snaps, geometry prefixed/suffixed with the endpoint hub's own coordinate.
    from_key/to_key are (binfmt.TYPE_*, id) pairs - spec 2026-08-30-tour-folder-ingestion-
    design.md §2: a tour leg's endpoint can be a hut, station, parking spot or partner business,
    not just a hut."""
    from_type, from_id = from_key
    to_type, to_id = to_key
    snap_m, ascent_m, descent_m = fold_endpoint_snaps(path, src_snap, tgt_snap)
    geometry = [from_coord, *path.coords, to_coord]
    return {
        "from_id": from_id, "to_id": to_id,
        "from_type": from_type, "to_type": to_type,
        "variant": binfmt.VARIANT_OFFICIAL,
        "distance_m": float(path.distance_m + snap_m),
        "road_m": float(path.road_m),
        "ascent_m": float(ascent_m), "descent_m": float(descent_m),
        "max_ele_m": float(path.max_ele_m) if path.max_ele_m != float("-inf") else 0.0,
        "ungraded_m": float(path.ungraded_m), "inferred_m": float(path.inferred_m),
        "snap_m": float(snap_m),
        "sac_rank": int(path.sac_rank), "via_ferrata": bool(path.via_ferrata),
        "geometry": geometry, "base_edge_ids": path.base_edge_ids,
    }
```

- [ ] **Step 5: Update imports at the top of the module**

Replace the block:
```python
from lib.edge_output import fold_endpoint_snaps  # noqa: E402
from lib.grid import KM_PER_DEG_LAT  # noqa: E402
from lib.subgraph import LocalSubgraph, clip_subgraph_to_bounds, gather_subgraph_for_bounds  # noqa: E402
```
by adding, right after it:
```python
from lib.geo import haversine_m  # noqa: E402
from lib.hubs import HUB_TYPE_JSON_NAMES, load_all_hubs, nearest_hub_to_point  # noqa: E402
from lib.pipeline import TOURS_DIR  # noqa: E402
from lib.tour_folder import load_all_tour_folders, load_tour_folder  # noqa: E402
```
Delete the now-duplicate `from lib.geo import haversine_m` import further down the file (it
currently sits just above `def main`).

- [ ] **Step 6: Rewrite `main()`**

Replace the whole `main()` function body with:
```python
def main(argv=None):
    config = load_config()
    tm = config["tourMatch"]
    max_snap_m = config["graph"]["maxSnapM"]
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-graph-dir", default=str(OSM_DIR / "base_graph"),
                        help="directory holding the persisted base graph (build_base_graph.py's output)")
    parser.add_argument("--out-dir", default=str(OSM_DIR),
                        help="directory to write matched tour edge output into")
    parser.add_argument("--corridor-buffer-m", type=float, default=tm["corridorBufferM"],
                        help="buffer width (m) around a leg's GPX trace used to select candidate base-graph edges")
    parser.add_argument("--length-divergence-ratio", type=float, default=tm["lengthDivergenceRatio"],
                        help="max allowed ratio between matched-edge length and the leg's own GPX trace length")
    args = parser.parse_args(argv)

    from lib.grid import Grid

    base_graph_dir = Path(args.base_graph_dir)
    manifest = binfmt.load_manifest(base_graph_dir / "manifest.json")
    grid = Grid(manifest["bbox"], manifest["tile_size_km"])

    hubs = load_all_hubs(OSM_DIR)

    hub_snaps_arr = binfmt.load_array(Path(args.out_dir) / "hub_snaps.npy", mmap=False)
    hub_snap_interior_arr = binfmt.load_array(Path(args.out_dir) / "hub_snap_interior.npy", mmap=False)
    persisted_snaps = hub_snap.load_persisted_snaps(hub_snaps_arr, hub_snap_interior_arr)

    tour_folders = load_all_tour_folders(TOURS_DIR)
    all_records, tour_meta_rows, gaps, tours_index = [], [], [], []

    with phase(SCRIPT_NAME, "match_tour_edges", n_tours=len(tour_folders)):
        for tour_id, (tour_name, folder) in enumerate(tour_folders):
            legs = load_tour_folder(folder)
            tour_legs_json = []

            for leg_number, points in legs:
                leg_index = leg_number - 1
                gap_ctx = {"tourId": tour_id, "tourName": tour_name, "legIndex": leg_index}

                from_chosen, from_nearest, from_dist = nearest_hub_to_point(hubs, points[0], max_snap_m)
                to_chosen, to_nearest, to_dist = nearest_hub_to_point(hubs, points[-1], max_snap_m)

                def _hub_json(hub):
                    return {"type": HUB_TYPE_JSON_NAMES[hub["type"]], "id": hub["id"]} if hub else None

                tour_legs_json.append({
                    "legIndex": leg_index, "from": _hub_json(from_chosen), "to": _hub_json(to_chosen),
                })

                if from_chosen is None or to_chosen is None:
                    endpoint = "from" if from_chosen is None else "to"
                    nearest, dist = (from_nearest, from_dist) if from_chosen is None else (to_nearest, to_dist)
                    gaps.append({
                        **gap_ctx, "reason": "leg_endpoint_unsnapped",
                        "detail": {
                            "endpoint": endpoint,
                            "nearestType": HUB_TYPE_JSON_NAMES[nearest["type"]] if nearest else None,
                            "nearestId": nearest["id"] if nearest else None,
                            "nearestDistM": dist,
                        },
                    })
                    continue

                from_key = (from_chosen["type"], from_chosen["id"])
                to_key = (to_chosen["type"], to_chosen["id"])
                from_coord = (from_chosen["lon"], from_chosen["lat"])
                to_coord = (to_chosen["lon"], to_chosen["lat"])

                trace_length_m = sum(
                    haversine_m(points[i][0], points[i][1], points[i + 1][0], points[i + 1][1])
                    for i in range(len(points) - 1)
                )
                bounds = corridor_bounds(points, args.corridor_buffer_m, grid)
                subgraph = clip_subgraph_to_bounds(
                    _cached_gather_for_bounds(base_graph_dir, grid, bounds), bounds,
                )

                result = match_leg(subgraph, from_key, to_key, persisted_snaps,
                                    trace_length_m, args.length_divergence_ratio)
                if not result["ok"]:
                    gaps.append({**gap_ctx, "reason": result["reason"], "detail": result["detail"]})
                    continue

                record = build_tour_record(
                    from_key, to_key, from_coord, to_coord,
                    result["path"], result["src_snap"], result["tgt_snap"],
                )
                all_records.append(record)
                tour_meta_rows.append((tour_id, leg_index))

            tours_index.append({"tourId": tour_id, "name": tour_name, "legs": tour_legs_json})

    print(f"tour legs matched: {len(all_records)}, gaps: {len(gaps)}")

    out_dir = Path(args.out_dir) / "tour_edges"
    write_edge_records(all_records, out_dir, write_edge_ids=True)
    tour_meta_arr = np.zeros(len(tour_meta_rows), dtype=binfmt.TOUR_META_DTYPE)
    for i, row in enumerate(tour_meta_rows):
        tour_meta_arr[i] = row
    binfmt.save_array(out_dir / "tour_meta.npy", tour_meta_arr)

    tours_path = Path(args.out_dir) / "tours.json"
    with open(tours_path, "w", encoding="utf-8") as fh:
        json.dump(tours_index, fh)

    gaps_path = Path(args.out_dir) / "tour-match-gaps.json"
    with open(gaps_path, "w", encoding="utf-8") as fh:
        json.dump(gaps, fh)
    print(f"written {out_dir}, {tours_path} and {gaps_path}")
```

- [ ] **Step 7: Update the module docstring**

Replace the file's top docstring with:
```python
"""Matches each tour folder's legs (pipeline/tours/<Name>/<N>.gpx, spec docs/superpowers/specs/
2026-08-30-tour-folder-ingestion-design.md) onto the persisted base graph, constrained to each
leg's own GPX trace rather than routed freely. Produces data/osm/tour_edges/{records.npy,
geometry.npy, edge_ids.npy, tour_meta.npy} (same shape as hut_edges/, plus the tour_meta.npy
sidecar), data/osm/tours.json (a per-leg endpoint-intent index) and data/osm/tour-match-gaps.json
(spec §5's never-faked gap reasons).

Usage: python pipeline/phases/graph_building/match_tour_edges.py
"""
```

- [ ] **Step 8: Manually sanity-check the file imports cleanly**

Run: `cd pipeline && .pixi/envs/default/bin/python -c "import sys; sys.path.insert(0,'.'); sys.path.insert(0,'phases'); import graph_building.match_tour_edges"`
Expected: no `ImportError`/`SyntaxError` (this will still fail at the top-level `main()` if run —
that's expected and not what this step checks; it only imports the module).

- [ ] **Step 9: Commit**

```bash
git add pipeline/phases/graph_building/match_tour_edges.py
git commit -m "pipeline: retarget match_tour_edges.py onto GPX tour folders"
```

(Tests for this rewritten module are Task 5 — the file won't have a passing test suite again until
that task lands; this is expected mid-plan state, not a regression to worry about between these two
commits.)

---

## Task 5: Rewrite `test_match_tour_edges.py`

**Files:**
- Modify: `pipeline/tests/test_match_tour_edges.py`
- Create: `pipeline/tests/fixtures/tour_folder/LQR/1.gpx`, `.../2.gpx`, `.../3.gpx` (golden-test
  fixture, reused from Task 2's fixture directory)

**Interfaces:**
- Consumes: Task 4's rewritten `match_tour_edges.py` (`corridor_bounds`, `match_leg`,
  `build_tour_record`, `_cached_gather_for_bounds`, `main`), Task 2's `lib.tour_folder`, Task 3's
  `lib.hubs`.

- [ ] **Step 1: Delete the obsolete tests**

Delete these test functions from `pipeline/tests/test_match_tour_edges.py` (they test deleted
functions/behavior): `test_chain_for_tour_falls_back_to_oa_when_reassembly_fails`,
`test_chain_for_tour_prefers_arcgis_reassembly_when_it_succeeds`,
`test_chain_for_tour_reports_gap_when_neither_source_works`,
`test_open_tour_yields_n_minus_one_legs`, `test_loop_tour_yields_n_legs_with_contiguous_leg_index`,
`test_unresolved_hut_sentinel_splits_the_chain`, `test_empty_hut_list_yields_no_legs`,
`test_single_hut_yields_no_legs`, `test_golden_tour_falls_back_to_oa_when_arcgis_fragments_dont_reassemble`.
Delete the `from graph_building.match_tour_edges import _chain_for_tour, build_tour_legs` import at
the top and the `_tour(...)` helper (both only used by the deleted tests).

- [ ] **Step 2: Fix the surviving unit tests for the renamed reason and generalized keys**

In `test_match_leg_reports_hut_unsnapped_when_src_missing`, rename the test to
`test_match_leg_reports_hub_unsnapped_when_src_missing` and change the assertion:
```python
    assert result == {"ok": False, "reason": "hub_unsnapped", "detail": {"missing": [src_key]}}
```

In `test_build_tour_record_shape_matches_write_edge_records_expectations`, change the call site:
```python
    record = build_tour_record(
        from_key=(binfmt.TYPE_HUT, 0), to_key=(binfmt.TYPE_HUT, 1),
        from_coord=(10.0, 47.0), to_coord=(10.01, 47.0),
        path=path, src_snap=_Snap(5.0, 0.0), tgt_snap=_Snap(3.0, 0.0),
    )
```
(the rest of that test's body and assertions are unchanged — `from_id`/`to_id`/`from_type`/
`to_type` still read the same off the returned dict).

- [ ] **Step 3: Update the golden end-to-end tests' fixtures**

Create three GPX files under `pipeline/tests/fixtures/tour_folder/LQR/` mirroring the synthetic
4-node straight chain the existing `_write_synthetic_base_graph` helper builds
(`(0.0,0.0)→(0.009,0.0)→(0.018,0.0)→(0.027,0.0)`, ~1000m per hop at the equator):

`1.gpx`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><trkseg>
    <trkpt lat="0.0" lon="0.0"></trkpt>
    <trkpt lat="0.0" lon="0.009"></trkpt>
  </trkseg></trk>
</gpx>
```
`2.gpx`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><trkseg>
    <trkpt lat="0.0" lon="0.009"></trkpt>
    <trkpt lat="0.0" lon="0.018"></trkpt>
  </trkseg></trk>
</gpx>
```
`3.gpx`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><trkseg>
    <trkpt lat="0.0" lon="0.018"></trkpt>
    <trkpt lat="0.0" lon="0.027"></trkpt>
  </trkseg></trk>
</gpx>
```

- [ ] **Step 4: Rewrite the golden single-part test to drive from the GPX folder**

Replace `test_golden_single_part_tour_matches_all_legs_end_to_end` with:
```python
def test_golden_single_part_tour_matches_all_legs_end_to_end(tmp_path, monkeypatch):
    grid = Grid(BBOX, tile_size_km=60.0)
    base_graph_dir, node_coords = _write_synthetic_base_graph(tmp_path, grid)

    # 4 huts sitting exactly on the 4 graph nodes (single part, no unsnapped huts).
    hut_coords = node_coords
    huts_geojson = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"id": f"{{GUID-{i}}}"},
             "geometry": {"type": "Point", "coordinates": list(c)}}
            for i, c in enumerate(hut_coords)
        ],
    }
    (tmp_path / "huts.geojson").write_text(json.dumps(huts_geojson), encoding="utf-8")
    start_points = np.zeros(0, dtype=[("lon", "f8"), ("lat", "f8"), ("osm_id", "i8"), ("type", "u1")])
    binfmt.save_array(tmp_path / "start_points.npy", start_points)

    persisted_snaps = {}
    for i, node_idx in enumerate((0, 1, 2, 3)):
        result = SnapResult(node_index=node_idx, gap_m=0.0, gap_dz_m=0.0)
        stand_in_subgraph = LocalSubgraph(
            global_node_ids=np.arange(4), local_nodes=np.zeros(0, dtype=binfmt.NODE_DTYPE),
            local_edges=np.zeros(0, dtype=binfmt.EDGE_DTYPE),
            interior=np.zeros(0, dtype=binfmt.COORD_DTYPE),
            local_node_ele=np.zeros(0, dtype=np.float32), interior_ele=np.zeros(0, dtype=np.float32),
        )
        persisted_snaps[(binfmt.TYPE_HUT, i)] = to_persisted(stand_in_subgraph, result)
    pack_hub_snaps(persisted_snaps, tmp_path)

    tours_dir = tmp_path / "tours"
    tour_folder = tours_dir / "LQR"
    tour_folder.mkdir(parents=True)
    fixtures = Path(__file__).resolve().parent / "fixtures" / "tour_folder" / "LQR"
    for name in ("1.gpx", "2.gpx", "3.gpx"):
        (tour_folder / name).write_text((fixtures / name).read_text(encoding="utf-8"), encoding="utf-8")

    import graph_building.match_tour_edges as mte

    monkeypatch.setattr(mte, "OSM_DIR", tmp_path)
    monkeypatch.setattr(mte, "TOURS_DIR", tours_dir)
    monkeypatch.setattr(
        mte, "load_config",
        lambda: {"tourMatch": {"corridorBufferM": 150.0, "lengthDivergenceRatio": 2.0},
                  "graph": {"maxSnapM": 100.0}},
    )
    mte.main(["--base-graph-dir", str(base_graph_dir), "--out-dir", str(tmp_path)])

    records = binfmt.load_array(tmp_path / "tour_edges" / "records.npy", mmap=False)
    tour_meta = binfmt.load_array(tmp_path / "tour_edges" / "tour_meta.npy", mmap=False)
    gaps = json.loads((tmp_path / "tour-match-gaps.json").read_text(encoding="utf-8"))
    tours_json = json.loads((tmp_path / "tours.json").read_text(encoding="utf-8"))

    assert len(records) == 3  # 3 legs, no gaps
    assert gaps == []
    assert list(tour_meta["leg_index"]) == [0, 1, 2]
    assert all(r == binfmt.VARIANT_OFFICIAL for r in records["variant"])
    assert (records["geom_offset"] >= 0).all()
    total_distance = records["distance_m"].sum()
    assert 2900.0 < total_distance < 3100.0  # ~3 x 1000m, order-of-magnitude sane

    assert tours_json == [{
        "tourId": 0, "name": "LQR",
        "legs": [
            {"legIndex": 0, "from": {"type": "hut", "id": 0}, "to": {"type": "hut", "id": 1}},
            {"legIndex": 1, "from": {"type": "hut", "id": 1}, "to": {"type": "hut", "id": 2}},
            {"legIndex": 2, "from": {"type": "hut", "id": 2}, "to": {"type": "hut", "id": 3}},
        ],
    }]
```

- [ ] **Step 5: Delete the Rundtour golden test**

Delete `test_rundtour_closing_leg_is_matched` in full — it exercised `isLoop`, which no longer
exists anywhere in the new input format (spec §2: "No `isLoop` field... Dropped entirely").

- [ ] **Step 6: Add a golden test for the `leg_endpoint_unsnapped` gap path**

Append:
```python
def test_golden_tour_reports_leg_endpoint_unsnapped_when_endpoint_far_from_any_hub(tmp_path, monkeypatch):
    grid = Grid(BBOX, tile_size_km=60.0)
    base_graph_dir, node_coords = _write_synthetic_base_graph(tmp_path, grid)

    # Only 3 huts on nodes 0,1,2 - node 3 (leg 3's endpoint) has NOTHING within max_snap_m.
    huts_geojson = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"id": f"{{GUID-{i}}}"},
             "geometry": {"type": "Point", "coordinates": list(node_coords[i])}}
            for i in range(3)
        ],
    }
    (tmp_path / "huts.geojson").write_text(json.dumps(huts_geojson), encoding="utf-8")
    binfmt.save_array(tmp_path / "start_points.npy", np.zeros(
        0, dtype=[("lon", "f8"), ("lat", "f8"), ("osm_id", "i8"), ("type", "u1")],
    ))

    persisted_snaps = {}
    for i in range(3):
        result = SnapResult(node_index=i, gap_m=0.0, gap_dz_m=0.0)
        stand_in_subgraph = LocalSubgraph(
            global_node_ids=np.arange(4), local_nodes=np.zeros(0, dtype=binfmt.NODE_DTYPE),
            local_edges=np.zeros(0, dtype=binfmt.EDGE_DTYPE),
            interior=np.zeros(0, dtype=binfmt.COORD_DTYPE),
            local_node_ele=np.zeros(0, dtype=np.float32), interior_ele=np.zeros(0, dtype=np.float32),
        )
        persisted_snaps[(binfmt.TYPE_HUT, i)] = to_persisted(stand_in_subgraph, result)
    pack_hub_snaps(persisted_snaps, tmp_path)

    tours_dir = tmp_path / "tours"
    tour_folder = tours_dir / "LQR"
    tour_folder.mkdir(parents=True)
    fixtures = Path(__file__).resolve().parent / "fixtures" / "tour_folder" / "LQR"
    for name in ("1.gpx", "2.gpx", "3.gpx"):
        (tour_folder / name).write_text((fixtures / name).read_text(encoding="utf-8"), encoding="utf-8")

    import graph_building.match_tour_edges as mte

    monkeypatch.setattr(mte, "OSM_DIR", tmp_path)
    monkeypatch.setattr(mte, "TOURS_DIR", tours_dir)
    monkeypatch.setattr(
        mte, "load_config",
        lambda: {"tourMatch": {"corridorBufferM": 150.0, "lengthDivergenceRatio": 2.0},
                  "graph": {"maxSnapM": 100.0}},
    )
    mte.main(["--base-graph-dir", str(base_graph_dir), "--out-dir", str(tmp_path)])

    records = binfmt.load_array(tmp_path / "tour_edges" / "records.npy", mmap=False)
    gaps = json.loads((tmp_path / "tour-match-gaps.json").read_text(encoding="utf-8"))
    tours_json = json.loads((tmp_path / "tours.json").read_text(encoding="utf-8"))

    assert len(records) == 2  # legs 1,2 route; leg 3 (node 2 -> node 3) gaps
    assert len(gaps) == 1
    assert gaps[0]["reason"] == "leg_endpoint_unsnapped"
    assert gaps[0]["legIndex"] == 2
    assert gaps[0]["detail"]["endpoint"] == "to"
    assert gaps[0]["detail"]["nearestDistM"] > 100.0
    assert tours_json[0]["legs"][2]["to"] is None
```

- [ ] **Step 7: Add the missing `from pathlib import Path` import if not already present**

`test_match_tour_edges.py` already imports `Path` at the top (`from pathlib import Path`) —
confirm this before running; no change needed if so.

- [ ] **Step 8: Run the full test file**

Run: `cd pipeline && .pixi/envs/default/bin/pytest tests/test_match_tour_edges.py -v`
Expected: PASS (all remaining/rewritten tests: `test_corridor_bounds_pads_the_points_bbox`,
`test_match_leg_routes_a_simple_corridor`, `test_match_leg_reports_hub_unsnapped_when_src_missing`,
`test_match_leg_reports_outside_extract_when_corridor_is_empty`,
`test_match_leg_reports_length_divergent_when_routed_far_exceeds_trace`,
`test_build_tour_record_shape_matches_write_edge_records_expectations`,
`test_cached_gather_for_bounds_returns_same_object_for_same_cell_set`,
`test_cached_gather_for_bounds_returns_different_object_for_different_cell_set`,
`test_golden_single_part_tour_matches_all_legs_end_to_end`,
`test_golden_tour_reports_leg_endpoint_unsnapped_when_endpoint_far_from_any_hub`)

- [ ] **Step 9: Commit**

```bash
git add pipeline/tests/test_match_tour_edges.py pipeline/tests/fixtures/tour_folder/LQR
git commit -m "pipeline: rewrite match_tour_edges tests for GPX tour-folder input"
```

---

## Task 6: DAG wiring

**Files:**
- Modify: `pipeline/dag/graph_building.py`
- Modify: `pipeline/dag/downloads.py`
- Modify: `pipeline/dodo.py`
- Modify: `pipeline/tests/test_dodo_wiring.py`

**Interfaces:**
- Consumes: `lib.pipeline.TOURS_DIR` (Task 1).
- Produces: `task_match_tour_edges()` (retargeted), with `fetch_tours`/`fetch_tour_oa_geometry`
  removed from the DAG entirely.

- [ ] **Step 1: Retarget `task_match_tour_edges` in `dag/graph_building.py`**

Replace the whole function:
```python
def task_match_tour_edges():
    # Corridor-constrained routing of tour folders (pipeline/tours/) onto the base graph (spec
    # docs/superpowers/specs/2026-08-30-tour-folder-ingestion-design.md). task_dep, not file_dep,
    # on compute_edge_profiles/snap_hubs: both rewrite their outputs in place without declaring
    # them as targets - same reasoning as task_snap_hubs/task_gather_route_subgraphs above. Never
    # a variants_json tracking param: a tour leg is not a member of graph.variants (spec §5 of the
    # 2026-08-29 official-tours-integration design).
    tour_files = sorted(TOURS_DIR.glob("*/*.gpx"))  # flat per spec §1; computed at DAG-build time
    return pipeline_task(
        "phases/graph_building/match_tour_edges.py",
        params=[
            cli_param("corridor_buffer_m", "corridor-buffer-m", float, CONFIG["tourMatch"]["corridorBufferM"]),
            cli_param("length_divergence_ratio", "length-divergence-ratio", float,
                      CONFIG["tourMatch"]["lengthDivergenceRatio"]),
        ],
        task_dep=["compute_edge_profiles", "snap_hubs"],
        file_dep=[
            OSM_DIR / "huts.geojson", OSM_DIR / "start_points.npy",
            OSM_DIR / "hub_snaps.npy", OSM_DIR / "hub_snap_interior.npy",
            *tour_files,
        ],
        targets=[
            OSM_DIR / "tour_edges" / "records.npy", OSM_DIR / "tour_edges" / "geometry.npy",
            OSM_DIR / "tour_edges" / "edge_ids.npy", OSM_DIR / "tour_edges" / "tour_meta.npy",
            OSM_DIR / "tours.json", OSM_DIR / "tour-match-gaps.json",
        ],
    )
```
Add `TOURS_DIR` to the `lib.pipeline` import line at the top of `dag/graph_building.py` (find the
existing `from lib.pipeline import OSM_DIR, ...` line and add `TOURS_DIR` to it).

- [ ] **Step 2: Remove the two downloads tasks in `dag/downloads.py`**

Delete `task_fetch_tours` and `task_fetch_tour_oa_geometry` entirely from
`pipeline/dag/downloads.py`.

- [ ] **Step 3: Update `dodo.py`'s imports and task lists**

In `pipeline/dodo.py`, change:
```python
from dag.downloads import (  # noqa: E402,F401
    task_download_extracts, task_fetch_dem, task_fetch_huts, task_fetch_stations_parking,
    task_fetch_tour_oa_geometry, task_fetch_tours,
)
```
to:
```python
from dag.downloads import (  # noqa: E402,F401
    task_download_extracts, task_fetch_dem, task_fetch_huts, task_fetch_stations_parking,
)
```

In `DOIT_CONFIG["default_tasks"]`, change:
```python
        "download_extracts", "fetch_huts", "fetch_tours", "fetch_tour_oa_geometry",
```
to:
```python
        "download_extracts", "fetch_huts",
```

In `PUBLIC_FILES`, delete the `"tour-fetch-gaps.json"` line. Keep `"tour-match-gaps.json"` and
`"tours.json"` exactly as they are.

- [ ] **Step 4: Update `test_dodo_wiring.py`**

Delete these test functions entirely (they test deleted tasks):
`test_fetch_tours_depends_on_huts_geojson_not_just_network`,
`test_fetch_tours_targets_all_three_outputs`, `test_fetch_tours_tracks_bbox`.

Replace `test_match_tour_edges_depends_on_profiles_and_snaps_not_edges_npy` with:
```python
def test_match_tour_edges_depends_on_profiles_and_snaps_not_edges_npy():
    task = dodo.task_match_tour_edges()
    assert "compute_edge_profiles" in task["task_dep"]
    assert "snap_hubs" in task["task_dep"]
    assert "fetch_tour_oa_geometry" not in task["task_dep"]
    assert not any(d.endswith("edges.npy") for d in task["file_dep"])
```

Add a new test proving the tour GPX files are tracked as `file_dep`:
```python
def test_match_tour_edges_tracks_tour_gpx_files():
    task = dodo.task_match_tour_edges()
    file_deps = [str(d) for d in task["file_dep"]]
    assert any(d.endswith(".gpx") for d in file_deps)
```

Update `test_public_files_includes_every_tour_output` — remove `"tour-fetch-gaps.json"` from its
expected list:
```python
def test_public_files_includes_every_tour_output():
    for name in [
        "tours.json", "tour-edges.pmtiles", "tour-edge-stats.json",
        "tour-edge-geometry.bin", "tour-edge-geometry.json",
        "tour-edge-payload.bin", "tour-edge-payload.json",
        "tour-match-gaps.json",
    ]:
        assert name in dodo.PUBLIC_FILES, name
```

Leave `test_match_tour_edges_targets_tour_edges_directory`,
`test_match_tour_edges_does_not_track_record_schema_version`,
`test_build_profiles_depends_on_match_tour_edges_and_tour_edges_records`,
`test_build_tour_edge_tiles_mirrors_hut_edge_tiles_wiring`,
`test_build_tour_edge_payload_passes_tour_meta_flag` unchanged — none of them reference anything
this task deleted.

- [ ] **Step 5: Run the DAG wiring tests**

Run: `cd pipeline && .pixi/envs/default/bin/pytest tests/test_dodo_wiring.py -v`
Expected: PASS. If `dodo.py` fails to import (e.g. a stray reference to
`task_fetch_tour_oa_geometry`), grep for it: `grep -n fetch_tour pipeline/dodo.py` and remove any
remaining reference.

- [ ] **Step 6: Run `doit list` as a smoke check (this does NOT run any task)**

Run: `cd pipeline && .pixi/envs/default/bin/doit list`
Expected: task list prints with no Python traceback, `match_tour_edges` present, `fetch_tours`/
`fetch_tour_oa_geometry` absent. `doit list` only inspects the DAG — it does not execute any task,
so this does not need the "ask before running a pipeline task" confirmation.

- [ ] **Step 7: Commit**

```bash
git add pipeline/dag/graph_building.py pipeline/dag/downloads.py pipeline/dodo.py \
  pipeline/tests/test_dodo_wiring.py
git commit -m "pipeline: retarget match_tour_edges DAG wiring, drop fetch_tours tasks"
```

---

## Task 7: Delete the obsolete AV-fragment/Outdooractive machinery

**Files:**
- Delete: `pipeline/phases/downloads/fetch_tours.py`
- Delete: `pipeline/phases/downloads/fetch_tour_oa_geometry.py`
- Delete: `pipeline/lib/oa_geometry.py`
- Delete: `pipeline/lib/tour_geometry.py`
- Delete: `pipeline/analysis/oa_corridor_spike.py`
- Delete: `pipeline/analysis/find_oa_ids_from_homepages.py`
- Delete: `pipeline/tests/test_fetch_tours.py`
- Delete: `pipeline/tests/test_fetch_tour_oa_geometry.py`
- Delete: `pipeline/tests/test_oa_geometry.py`
- Delete: `pipeline/tests/test_tour_geometry.py`

**Interfaces:** none — this task only removes code Task 4/6 already made unreachable
(`lib.tour_geometry`'s functions are no longer imported anywhere after Task 4 Step 1;
`fetch_tours.py`/`fetch_tour_oa_geometry.py` are no longer wired after Task 6 Step 2;
`lib.oa_geometry`/`analysis/oa_corridor_spike.py`/`analysis/find_oa_ids_from_homepages.py` are only
ever imported by the files this task deletes).

- [ ] **Step 1: Confirm nothing else still imports the modules being deleted**

Run:
```bash
grep -rn "tour_geometry\|oa_geometry\|fetch_tours\|fetch_tour_oa_geometry\|oa_corridor_spike\|find_oa_ids_from_homepages" pipeline --include="*.py" | grep -v __pycache__
```
Expected: only hits inside the files this task is about to delete, plus `pipeline/dodo.py`'s
`PUBLIC_FILES`/`default_tasks` strings if Task 6 left a stray `"tour-fetch-gaps.json"` reference
(there should be none — Task 6 Step 3 already removed it; if this grep finds one, that's a Task 6
regression to fix now, not something new to design around).

- [ ] **Step 2: Delete the files**

```bash
git rm pipeline/phases/downloads/fetch_tours.py \
  pipeline/phases/downloads/fetch_tour_oa_geometry.py \
  pipeline/lib/oa_geometry.py \
  pipeline/lib/tour_geometry.py \
  pipeline/analysis/oa_corridor_spike.py \
  pipeline/analysis/find_oa_ids_from_homepages.py \
  pipeline/tests/test_fetch_tours.py \
  pipeline/tests/test_fetch_tour_oa_geometry.py \
  pipeline/tests/test_oa_geometry.py \
  pipeline/tests/test_tour_geometry.py
```

- [ ] **Step 3: Run the full pipeline test suite**

Run: `cd pipeline && .pixi/envs/default/bin/pytest -x -q`
Expected: PASS, no collection errors (a collection error here means something still imports a
deleted module — find it with the Step 1 grep pattern and fix the import).

- [ ] **Step 4: Check `docs/backlog.md` for now-stale entries**

Run: `grep -n -i "fetch_tours\|oa_geometry\|tour_geometry\|reassembl\|chain_not_reassembled\|hut_far_from_trace" docs/backlog.md`
If any entry references machinery this task deleted, remove that entry (per root `CLAUDE.md`:
"After completing a backlog task, remove it from `backlog.md`"). The access-node coverage-gap
backlog item (bus stops / Weinbergerhaus, spec §2's "Endpoints that do not snap" section) is
**not** stale — it's about hub-layer coverage, unrelated to what this task deletes — leave it as is.

- [ ] **Step 5: Commit**

```bash
git commit -m "pipeline: delete AV-fragment/Outdooractive tour machinery, superseded by GPX folders"
```
(the `git rm`s from Step 2 are already staged; add any `docs/backlog.md` edit from Step 4 to this
commit too if you made one)

---

## Task 8: Real-data smoke check

**Files:** none modified — this task runs the retargeted pipeline task against the real
`pipeline/tours/` folders and records what it produces, per spec §8's "Real-data smoke check".

**Interfaces:** none.

**This task runs a `pipeline/` task. Stop and ask the user for explicit confirmation before Step 1**
— per root `CLAUDE.md`, this applies even though `match_tour_edges` alone is not the ~4-hour
`build_base_graph` task; its dependencies (`task_dep=["compute_edge_profiles", "snap_hubs"]`) must
already be up to date in this checkout's `data/` for a `doit match_tour_edges` invocation to stay
cheap — if they are NOT up to date, running it would transitively trigger those (potentially
expensive) upstream tasks too, which is exactly the silent-multi-hour-job risk `CLAUDE.md` warns
about. Ask the user to confirm both that they want this task run AND that `data/osm/hub_snaps.npy`/
`data/osm/tour_edges/profiles` are already fresh (or that they're fine with whatever upstream work
`doit` decides is needed).

- [ ] **Step 1: Get explicit user confirmation, then run**

Run: `cd pipeline && .pixi/envs/default/bin/doit match_tour_edges`

- [ ] **Step 2: Compare actual output against the spec's predicted baseline**

Read `data/osm/tour-match-gaps.json` and `data/osm/tours.json`. Spec §8 predicts, against the exact
candidate set (`start_points.npy`, 15,720 rows at spec-writing time — the real count in this
checkout may differ slightly if hub layers changed since): **Welser Höhenweg legs 2–5 and
Kaisertour leg 2 route; Welser Höhenweg leg 1 and Kaisertour legs 1/3/4 report
`leg_endpoint_unsnapped`** (5 of 9 legs gap). Confirm the actual run's gap count and reasons are in
the same ballpark — this is establishing a baseline, not a pass/fail gate (per spec §8: "That is
the baseline the access-node backlog item is measured against — not a passing bar"). Note any
gap whose `reason` is something OTHER than `leg_endpoint_unsnapped` (e.g. `no_corridor_path`,
`length_divergent`) — those would be new failure modes the spec didn't predict and are worth a
closer look before moving on.

- [ ] **Step 3: Verify the DAG's downstream tasks still see fresh output**

Run: `cd pipeline && .pixi/envs/default/bin/doit info build_profiles` (still read-only — `doit info`
never executes a task) and confirm it reports `match_tour_edges`'s targets as up to date, not
needing a rerun it wasn't expecting.

- [ ] **Step 4: No commit for this task** — it produces no code changes. If Step 2 surfaced an
unexpected gap reason, capture it as a note for Task 9 (the corridor-quality check) rather than
starting a fix here — this task's job is only to establish the smoke-test baseline the spec asks
for.

---

## Task 9: Corridor-quality evaluation — decide whether corridor routing is good enough, or whether HMM map-matching is needed

**Files:**
- Create: `pipeline/analysis/corridor_match_quality.py`

**Interfaces:**
- Consumes: `data/osm/tour_edges/{records.npy,geometry.npy,tour_meta.npy}` and
  `data/osm/tours.json` (Task 8's real-run output), `lib.tour_folder.load_all_tour_folders`/
  `load_tour_folder` (Task 2) to re-read the original GPX traces for comparison,
  `lib.edge_split.nearest_point_on_polyline` (existing) for point-to-polyline projection.
- Produces: `data/analysis/corridor_match_quality.json`, one row per successfully-routed leg:
  `{tourName, legIndex, lengthRatio, meanDeviationM, maxDeviationM}`. This is a read-only
  measurement script per `pipeline/analysis/README.md`'s conventions — it never modifies
  `phases/` or `dodo.py`, and is not wired into the DAG.

This is the check the user asked for: "I want to check the quality of the corridor method once
it's implemented. If it's not good we can consider using an HMM." The existing
`lengthDivergenceRatio` guard (spec §3) only compares *total length* — a routed path can match a
trace's length while following a completely different line (e.g. two parallel valley trails). This
script adds a shape-based metric: how far, on average and at worst, does the routed polyline
actually stray from the leg's own GPX trace.

- [ ] **Step 1: Implement the deviation metric**

Create `pipeline/analysis/corridor_match_quality.py`:
```python
#!/usr/bin/env python3
"""Measures how closely match_tour_edges.py's routed geometry (data/osm/tour_edges/) follows each
tour leg's own GPX trace (pipeline/tours/), beyond the length-ratio check match_leg already applies
(spec 2026-08-30-tour-folder-ingestion-design.md §3's lengthDivergenceRatio compares total length
only - two parallel valley trails of the same length would pass it while diverging badly in shape).
For each successfully-routed leg, samples every GPX trace point's nearest-point distance to the
routed polyline (lib/edge_split.py's nearest_point_on_polyline, reused rather than reimplemented)
and reports mean/max deviation in meters alongside the existing length ratio.

Read-only: never modifies phases/ or dodo.py (pipeline/analysis/README.md's rule). Requires
data/osm/tour_edges/ and data/osm/tours.json already built (pipeline/CLAUDE.md's "ask before
running any pipeline task" rule covers producing them, not reading them here).

Writes data/analysis/corridor_match_quality.json.

Usage: python pipeline/analysis/corridor_match_quality.py
"""

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import binfmt  # noqa: E402
from lib.edge_split import nearest_point_on_polyline  # noqa: E402
from lib.geo import haversine_m  # noqa: E402
from lib.hubs import HUB_TYPE_JSON_NAMES  # noqa: E402
from lib.pipeline import DATA_DIR, OSM_DIR, TOURS_DIR  # noqa: E402
from lib.tour_folder import load_all_tour_folders, load_tour_folder  # noqa: E402
from lib.timing import phase  # noqa: E402

SCRIPT_NAME = "corridor_match_quality.py"
OUT_PATH = DATA_DIR / "analysis" / "corridor_match_quality.json"


def _deviation_m(trace_points: list, routed_points: list) -> tuple:
    """(mean_m, max_m): every trace point's nearest-point distance to the routed polyline."""
    if len(routed_points) < 2:
        return 0.0, 0.0
    ref_lat = routed_points[len(routed_points) // 2][1]
    lng_scale = math.cos(math.radians(ref_lat))
    dists = []
    for p in trace_points:
        seg_i, t = nearest_point_on_polyline(routed_points, p, lng_scale=lng_scale)
        ax, ay = routed_points[seg_i]
        bx, by = routed_points[seg_i + 1]
        px, py = ax + t * (bx - ax), ay + t * (by - ay)
        dists.append(haversine_m(p[0], p[1], px, py))
    return sum(dists) / len(dists), max(dists)


def main():
    records = binfmt.load_array(OSM_DIR / "tour_edges" / "records.npy", mmap=False)
    geometry = binfmt.load_array(OSM_DIR / "tour_edges" / "geometry.npy", mmap=False)
    tour_meta = binfmt.load_array(OSM_DIR / "tour_edges" / "tour_meta.npy", mmap=False)
    tour_folders = load_all_tour_folders(TOURS_DIR)

    rows = []
    with phase(SCRIPT_NAME, "corridor_match_quality", n_records=len(records)):
        for i, rec in enumerate(records):
            tour_id, leg_index = int(tour_meta[i]["tour_id"]), int(tour_meta[i]["leg_index"])
            tour_name, folder = tour_folders[tour_id]
            legs = {n - 1: pts for n, pts in load_tour_folder(folder)}
            trace_points = legs[leg_index]

            off, cnt = int(rec["geom_offset"]), int(rec["geom_count"])
            routed_points = [(float(g["lon"]), float(g["lat"])) for g in geometry[off:off + cnt]]

            mean_m, max_m = _deviation_m(trace_points, routed_points)
            trace_length_m = sum(
                haversine_m(*trace_points[j], *trace_points[j + 1])
                for j in range(len(trace_points) - 1)
            )
            length_ratio = float(rec["distance_m"]) / trace_length_m if trace_length_m > 0 else None

            rows.append({
                "tourName": tour_name, "legIndex": leg_index,
                "lengthRatio": length_ratio, "meanDeviationM": mean_m, "maxDeviationM": max_m,
            })
            print(f"[{i + 1}/{len(records)}] {tour_name} leg {leg_index}: "
                  f"mean={mean_m:.1f}m max={max_m:.1f}m ratio={length_ratio}", flush=True)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=2)

    if rows:
        mean_of_means = sum(r["meanDeviationM"] for r in rows) / len(rows)
        worst_max = max(r["maxDeviationM"] for r in rows)
        print(f"\n{len(rows)} legs measured. mean-of-means deviation: {mean_of_means:.1f}m, "
              f"worst single-leg max deviation: {worst_max:.1f}m")
    print(f"written {OUT_PATH}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it against Task 8's real output**

This reads already-produced `data/osm/tour_edges/`/`data/osm/tours.json` from Task 8 — it does not
itself run a `doit` task, so no fresh confirmation is needed for THIS command (Task 8's run already
had it), but confirm with the user before running if any doubt remains about whether Task 8's
output is still current.

Run: `cd pipeline && .pixi/envs/default/bin/python analysis/corridor_match_quality.py`
Expected: prints one line per routed leg plus a summary, writes
`data/analysis/corridor_match_quality.json`.

- [ ] **Step 3: Make the call — corridor routing good enough, or follow-up HMM spec needed**

Read the printed summary and the per-leg JSON. There is no pre-agreed numeric pass bar (the spec
this plan implements doesn't set one) — use judgment against what the deviation numbers mean on the
ground: a few tens of meters mean deviation on an alpine trail is unremarkable (trail width, GPS
noise, minor OSM/AV-published-route differences); a mean in the hundreds of meters, or a max deviation
that puts the routed line on a visibly different trail/valley, means the corridor is not
constraining the search the way §0 of the spec assumes.

- If the numbers look good: no further action — corridor-constrained routing (as implemented) is
  the shipped approach. Report the summary numbers to the user.
- If the numbers look bad: do **not** start implementing an HMM matcher in this plan. Report the
  specific bad legs/numbers to the user, and propose writing a new
  `docs/superpowers/specs/<date>-hmm-tour-matching-design.md` (via the brainstorming/writing-plans
  skills, as a separate follow-up) that scopes an HMM-based map-matching approach as a replacement
  for or supplement to `match_leg`'s shortest-path-in-corridor search. This plan's job stops at
  producing the evidence to make that call, not at building the alternative.

- [ ] **Step 4: Commit the analysis script (not its output — `data/` is gitignored)**

```bash
git add pipeline/analysis/corridor_match_quality.py
git commit -m "pipeline: add corridor-vs-GPX-trace deviation measurement script"
```

---

## Self-Review Notes

- **Spec §0–§8 coverage:** §1 (format/parser) → Task 2. §2 (endpoint snapping) → Task 3 + Task 4
  Step 6. §3 (routing, re-tuned corridor/divergence config) → Task 1 (config trim; re-tuning itself
  deferred to real evidence from Task 8/9, per spec §3's own "to be re-tuned with evidence once the
  phase runs on real folders" — not blindly changed here). §4 (`tours.json` shape) → Task 4 Step 6.
  §5 (gap reasons) → Task 4 Step 6. §6 (DAG wiring) → Task 6. §7 (deletions) → Tasks 4 Step 1, 6
  Step 2, 7. §8 (testing) → Tasks 2, 3, 5, 8. §9 (non-goals) → deliberately untouched (no
  folder-population tooling, no hub-layer coverage fixes, no client changes).
- **User's explicit ask** (corridor-quality check, HMM fallback consideration) → Task 9, as a
  decision gate producing evidence rather than a commitment to build an HMM matcher inline.
- **Type consistency check:** `build_tour_record`'s `from_key`/`to_key` parameter names (Task 4
  Step 4) match the call site in Task 4 Step 6 and the test call site in Task 5 Step 2.
  `nearest_hub_to_point`'s 3-tuple return `(chosen, nearest, nearest_dist_m)` is used identically in
  Task 3's tests, Task 4 Step 6's `main()`, and is never called anywhere else. `HUB_TYPE_JSON_NAMES`
  is defined once (Task 3) and consumed in Task 4 Step 6 and Task 9 Step 1 with the same import
  path (`lib.hubs`).
- **No placeholders:** every step above contains literal file contents or literal commands; none
  defer to "similar to Task N" or "add appropriate handling."
