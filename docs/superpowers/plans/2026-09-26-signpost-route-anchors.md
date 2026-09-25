# Signpost Route Anchors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (this repo forbids subagent-driven development and worktrees, see root `CLAUDE.md`). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** From `ROUTE_REVEAL_ZOOM` on, every Discover tour board stands on a mast planted on its own route near the tour's half-distance, instead of at the start point.

**Architecture:** The pipeline ships three arc-length anchor points per edge (i2 offsets from the hut coordinate) in `hut-edge-payload.*` and `approaches.*`, and absolute anchors per leg in `tours.json`. The client decodes them lazily into a `LegAnchorLookup`, a pure `tourAnchor` picks the candidate nearest the tour's half-distance (clipped to the viewport), a second clusterer groups tours by anchor, and `SignpostMarker` renders a board on a mast with the foot on the anchor.

**Tech Stack:** Python 3.11 + numpy + pytest (pixi, `pipeline/`), TypeScript + React + Leaflet/react-leaflet + supercluster + vitest (`huts/`).

**Spec:** `docs/superpowers/specs/2026-09-26-signpost-route-anchors-design.md`

## Global Constraints

- Anchors at **25 %, 50 %, 75 %** of arc length on the full-resolution `geometry.npy` polyline (not tile geometry).
- Columns `a25_dlat`, `a25_dlng`, `a50_dlat`, `a50_dlng`, `a75_dlat`, `a75_dlng`, dtype **i2**, unit **1e-4°**, per-column layout like every other column; the build asserts no offset overflows.
- Reference coordinate = the **hut's coordinate as shipped in `huts.geojson`**: `from_id` hut for `hut-edge-payload`, the row's hut (`hut_id`) for `approaches`.
- Direction: "25 %" is in the row's stored direction (`from → to`, `access point → hut`); a reversed leg swaps 25/75, 50 stays.
- `tours.json` legs: `anchors: [[lat, lng], [lat, lng], [lat, lng]]` in walking order, from the raw GPX trace.
- Size gate: if gzipped payload growth exceeds **+60 KB**, ship only `a50_*` and the client treats candidates as leg-midpoints only.
- Quality check: sampled decoded anchors lie within **25 m** of the edge's full-resolution polyline.
- Below `ROUTE_REVEAL_ZOOM` the count bubbles grouped by start point behave exactly as today.
- Mast ≈ 24 px tall, 1.5 px wide; foot dot ≈ 5 px in ink at the anchor (Leaflet `iconAnchor`); mast and foot are `pointer-events: none`.
- Hovered tour (from route line or results list, not from its own board): board opacity 35 %.
- Never run a `doit` task or any `pipeline/` task without asking the user first. Never create a git worktree. No historical comments in code (state what the code does now).
- Imports point downward (`huts/src/architecture.test.ts`): `tourSearch/` must not import `features/`, `data/` or `lib/`-siblings it does not already import; `features/map/` may import `tourSearch/`.

## Review Focus

1. A leg with **no shipped anchors** (exit leg whose `edgeId` comes from the reverse index rather than the approach table, `edgeId < 0`, or data built before this change) must fall back to the chord point, never throw and never hide the board. Tested in Task 8 and Task 6.
2. **Degenerate geometry** (duplicate points, zero total length, one point) must give finite anchors, not NaN. Tested in Task 1.
3. A **tour with total distance 0** or a single leg must still produce a board (all candidates tie; first wins). Tested in Task 8.
4. A route that only **crosses the viewport between anchors** shows no board and does not crash; anchors outside the bbox are never chosen. Tested in Task 8 and Task 12.
5. **Two tours sharing an anchor** cluster into one stack whose foot is the best-ranked tour's anchor, not a centroid; a board near the **viewport edge** flips sides while its arrow keeps the travel direction. Tested in Task 10 and Task 11.

---

## File Structure

| File | Responsibility |
|---|---|
| `pipeline/lib/anchors.py` (new) | arc-length points, quantise/decode offsets, per-edge anchor columns, point-to-polyline distance, sizing note |
| `pipeline/phases/postprocessing/build_edge_payload.py` | append anchor columns to `hut-edge-payload` |
| `pipeline/phases/postprocessing/build_approach_table.py` | append anchor columns to `approaches` |
| `pipeline/phases/graph_building/match_tour_edges.py` | `anchors` per leg in `tours.json` |
| `pipeline/phases/quality/check_postprocessing.py` | anchors-on-path check |
| `pipeline/dag/postprocessing.py`, `pipeline/dag/quality.py` | new `file_dep`s / args |
| `huts/src/tourSearch/binaryColumns.ts` | `i2` dtype |
| `huts/src/tourSearch/anchors.ts` (new) | offset reading, decoding, fractions |
| `huts/src/tourSearch/legAnchors.ts` (new) | `createLegAnchorLookup` |
| `huts/src/tourSearch/tourAnchor.ts` (new) | pure anchor choice + heading |
| `huts/src/features/map/routes.ts` | `RouteContext.legAnchors`, `tourAnchorOf` |
| `huts/src/features/map/clusterStarts.ts` | `createAnchorClusterer`, `anchorMarkerKind` |
| `huts/src/features/map/signpostHtml.ts`, `map.css`, `SignpostMarker.tsx` | mast, side flip, fade |
| `huts/src/features/map/DiscoverLayer.tsx` | anchored boards from `routedTours` |
| `docs/tour-suggestion-payload.md`, `CLAUDE.md`, `pipeline/phases/postprocessing/README.md`, `docs/superpowers/STATUS.md` | docs |

Commands: pipeline tests `cd pipeline && pixi run pytest tests/<file> -v`; client tests `cd huts && npx vitest run <path>`; also `npm run typecheck`, `npm run lint`.

---

### Task 0: Commit the spec

**Files:** `docs/superpowers/specs/2026-09-26-signpost-route-anchors-design.md`, `docs/superpowers/STATUS.md`, this plan.

- [ ] **Step 1:** Confirm branch is `feat/discover-map-signposts` (not `main`): `git branch --show-current`.
- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-09-26-signpost-route-anchors-design.md docs/superpowers/STATUS.md docs/superpowers/plans/2026-09-26-signpost-route-anchors.md
git commit -m "docs: signpost route anchors spec and plan"
```

(End the message with the `Co-Authored-By` line from the session's attribution reminder, on every commit in this plan.)

---

### Task 1: Pipeline anchor helper

**Files:**
- Create: `pipeline/lib/anchors.py`
- Test: `pipeline/tests/test_anchors.py`

**Interfaces:**
- Produces (used by Tasks 2-5):
  - `ANCHOR_FRACTIONS: tuple[float, ...] = (0.25, 0.5, 0.75)`, `ANCHOR_UNIT_DEG = 1e-4`
  - `anchor_column_names(fractions=ANCHOR_FRACTIONS) -> list[str]` → `["a25_dlat", "a25_dlng", "a50_dlat", ...]`
  - `points_at_fractions(lons, lats, fractions=ANCHOR_FRACTIONS) -> np.ndarray` shape `(k, 2)` of `lon, lat`
  - `quantise_offsets(points_lonlat, ref_lonlat) -> (dlat: i2[k], dlng: i2[k])`, raises `ValueError` on overflow
  - `decode_offsets(ref_lonlat, dlat, dlng) -> np.ndarray (k, 2)` `lon, lat`
  - `edge_anchor_columns(records, geometry, row_ids, ref_lonlat, fractions=ANCHOR_FRACTIONS) -> dict[str, np.ndarray i2]` (`records` has `geom_offset`/`geom_count`; `geometry` is `COORD_DTYPE`; `ref_lonlat` is `(n, 2)` aligned with `row_ids`)
  - `decode_row(columns, i, ref_lonlat, fractions=ANCHOR_FRACTIONS) -> np.ndarray (k, 2)`
  - `distance_to_polyline_m(lon, lat, poly_lonlat) -> float`

- [ ] **Step 1: Write the failing tests** (`pipeline/tests/test_anchors.py`)

```python
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import binfmt  # noqa: E402
from lib.anchors import (  # noqa: E402
    ANCHOR_UNIT_DEG, anchor_column_names, decode_offsets, decode_row, distance_to_polyline_m,
    edge_anchor_columns, points_at_fractions, quantise_offsets,
)


def test_column_names_follow_fraction_order():
    assert anchor_column_names() == ["a25_dlat", "a25_dlng", "a50_dlat", "a50_dlng", "a75_dlat", "a75_dlng"]
    assert anchor_column_names((0.5,)) == ["a50_dlat", "a50_dlng"]


def test_straight_line_quarters_are_evenly_spaced():
    pts = points_at_fractions([11.0, 11.4], [47.0, 47.0])
    assert pts[:, 1] == pytest.approx([47.0] * 3)
    assert pts[:, 0] == pytest.approx([11.1, 11.2, 11.3], abs=1e-4)


def test_l_shape_puts_the_midpoint_on_the_corner():
    # equal-length legs: east then north; 50 % is the corner
    lat = 47.0
    dlon = 0.01
    dlat = dlon * np.cos(np.radians(lat))
    pts = points_at_fractions([11.0, 11.0 + dlon, 11.0 + dlon], [lat, lat, lat + dlat])
    assert pts[1] == pytest.approx([11.0 + dlon, lat], abs=1e-6)


def test_zero_length_segments_do_not_break_interpolation():
    pts = points_at_fractions([11.0, 11.0, 11.0, 11.2], [47.0, 47.0, 47.0, 47.0])
    assert np.isfinite(pts).all()
    assert pts[1, 0] == pytest.approx(11.1, abs=1e-4)


@pytest.mark.parametrize("lons,lats", [([11.0], [47.0]), ([11.0, 11.0], [47.0, 47.0])])
def test_degenerate_geometry_collapses_to_the_point(lons, lats):
    pts = points_at_fractions(lons, lats)
    assert np.isfinite(pts).all()
    assert pts == pytest.approx(np.tile([11.0, 47.0], (3, 1)))


def test_empty_geometry_is_an_error():
    with pytest.raises(ValueError):
        points_at_fractions([], [])


def test_quantise_round_trips_within_one_unit():
    ref = np.array([11.0, 47.0])
    pts = np.array([[11.01234, 47.02345], [10.99, 46.98]])
    dlat, dlng = quantise_offsets(pts, ref)
    assert dlat.dtype == np.dtype("i2") and dlng.dtype == np.dtype("i2")
    back = decode_offsets(ref, dlat, dlng)
    assert np.abs(back - pts).max() <= ANCHOR_UNIT_DEG


def test_quantise_rejects_offsets_beyond_i2():
    with pytest.raises(ValueError):
        quantise_offsets(np.array([[11.0 + 4.0, 47.0]]), np.array([11.0, 47.0]))


def _geometry(points):
    g = np.zeros(len(points), dtype=binfmt.COORD_DTYPE)
    g["lon"] = [p[0] for p in points]
    g["lat"] = [p[1] for p in points]
    return g


def test_edge_anchor_columns_decode_back_to_the_polyline():
    geometry = _geometry([(11.0, 47.0), (11.4, 47.0), (11.0, 47.1), (11.0, 47.2)])
    records = np.zeros(2, dtype=binfmt.RECORD_DTYPE)
    records["geom_offset"] = [0, 2]
    records["geom_count"] = [2, 2]
    ref = np.array([[11.0, 47.0], [11.0, 47.1]])
    cols = edge_anchor_columns(records, geometry, np.array([0, 1]), ref)
    assert set(cols) == set(anchor_column_names())
    assert all(c.dtype == np.dtype("i2") for c in cols.values())
    row0 = decode_row(cols, 0, ref[0])
    assert row0[1] == pytest.approx([11.2, 47.0], abs=1e-4)
    row1 = decode_row(cols, 1, ref[1])
    assert row1[1] == pytest.approx([11.0, 47.15], abs=1e-3)


def test_distance_to_polyline_is_zero_on_the_line_and_positive_off_it():
    poly = np.array([[11.0, 47.0], [11.1, 47.0]])
    assert distance_to_polyline_m(11.05, 47.0, poly) == pytest.approx(0.0, abs=0.5)
    assert distance_to_polyline_m(11.05, 47.001, poly) == pytest.approx(111.3, abs=2.0)
    assert distance_to_polyline_m(11.2, 47.0, poly) == pytest.approx(0.1 * 111_320 * np.cos(np.radians(47.0)), rel=0.01)
```

- [ ] **Step 2: Run to verify failure**

Run: `cd pipeline && pixi run pytest tests/test_anchors.py -v`
Expected: FAIL (`ModuleNotFoundError: lib.anchors`).

- [ ] **Step 3: Implement** (`pipeline/lib/anchors.py`)

```python
"""Anchor points on an edge's real path, shipped so the client can stand a tour's signpost on its
route without loading geometry. An anchor sits at a fixed fraction of the edge's arc length,
measured on the full-resolution polyline. Each anchor ships as an i2 offset, in 1e-4 degree units,
from a reference coordinate (the hut coordinate as shipped in huts.geojson), one column per axis
and fraction (docs/tour-suggestion-payload.md §1)."""

import numpy as np

from lib.geo import haversine_m_vec_pairs

ANCHOR_FRACTIONS = (0.25, 0.5, 0.75)
ANCHOR_UNIT_DEG = 1e-4
_I2_MAX = 32767
_M_PER_DEG = 111_320.0


def anchor_column_names(fractions=ANCHOR_FRACTIONS) -> list:
    return [f"a{int(round(f * 100))}_{axis}" for f in fractions for axis in ("dlat", "dlng")]


def points_at_fractions(lons, lats, fractions=ANCHOR_FRACTIONS) -> np.ndarray:
    """Points at the given fractions of the polyline's haversine arc length, linearly interpolated
    inside the segment that crosses each target. Returns (k, 2) of lon, lat."""
    lons = np.asarray(lons, dtype=np.float64)
    lats = np.asarray(lats, dtype=np.float64)
    if len(lons) == 0:
        raise ValueError("cannot place anchors on an empty polyline")
    k = len(fractions)
    if len(lons) == 1:
        return np.tile([lons[0], lats[0]], (k, 1))
    seg = haversine_m_vec_pairs(lons[:-1], lats[:-1], lons[1:], lats[1:])
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = cum[-1]
    if total == 0:
        return np.tile([lons[0], lats[0]], (k, 1))
    targets = np.asarray(fractions, dtype=np.float64) * total
    idx = np.clip(np.searchsorted(cum, targets, side="right") - 1, 0, len(seg) - 1)
    seg_len = seg[idx]
    t = np.divide(targets - cum[idx], seg_len, out=np.zeros_like(targets), where=seg_len > 0)
    lon = lons[idx] + t * (lons[idx + 1] - lons[idx])
    lat = lats[idx] + t * (lats[idx + 1] - lats[idx])
    return np.column_stack([lon, lat])


def quantise_offsets(points_lonlat, ref_lonlat) -> tuple:
    """(dlat, dlng) i2 arrays of each point's offset from ref, in ANCHOR_UNIT_DEG units."""
    d = np.rint((np.asarray(points_lonlat) - np.asarray(ref_lonlat)) / ANCHOR_UNIT_DEG)
    if np.abs(d).max() > _I2_MAX:
        raise ValueError(f"anchor offset {np.abs(d).max():.0f} units overflows i2 (max {_I2_MAX})")
    return d[:, 1].astype("i2"), d[:, 0].astype("i2")


def decode_offsets(ref_lonlat, dlat, dlng) -> np.ndarray:
    ref = np.asarray(ref_lonlat, dtype=np.float64)
    return np.column_stack([
        ref[0] + np.asarray(dlng, dtype=np.float64) * ANCHOR_UNIT_DEG,
        ref[1] + np.asarray(dlat, dtype=np.float64) * ANCHOR_UNIT_DEG,
    ])


def edge_anchor_columns(records, geometry, row_ids, ref_lonlat, fractions=ANCHOR_FRACTIONS) -> dict:
    """Anchor columns (i2, one entry per row in `row_ids`) for the edges `records[row_ids]`, cut from
    their slices of `geometry`. `ref_lonlat` is (n, 2), aligned with `row_ids`."""
    n = len(row_ids)
    columns = {name: np.zeros(n, dtype="i2") for name in anchor_column_names(fractions)}
    for i, row in enumerate(row_ids):
        offset, count = int(records[row]["geom_offset"]), int(records[row]["geom_count"])
        piece = geometry[offset:offset + count]
        points = points_at_fractions(piece["lon"], piece["lat"], fractions)
        dlat, dlng = quantise_offsets(points, ref_lonlat[i])
        for k, f in enumerate(fractions):
            key = int(round(f * 100))
            columns[f"a{key}_dlat"][i] = dlat[k]
            columns[f"a{key}_dlng"][i] = dlng[k]
    return columns


def decode_row(columns, i, ref_lonlat, fractions=ANCHOR_FRACTIONS) -> np.ndarray:
    """(k, 2) lon, lat of row i's anchors from unpacked columns."""
    dlat = [columns[f"a{int(round(f * 100))}_dlat"][i] for f in fractions]
    dlng = [columns[f"a{int(round(f * 100))}_dlng"][i] for f in fractions]
    return decode_offsets(ref_lonlat, dlat, dlng)


def distance_to_polyline_m(lon, lat, poly_lonlat) -> float:
    """Minimum distance in metres from a point to a lon/lat polyline (local equirectangular)."""
    poly = np.asarray(poly_lonlat, dtype=np.float64)
    kx = _M_PER_DEG * np.cos(np.radians(lat))
    xy = np.column_stack([(poly[:, 0] - lon) * kx, (poly[:, 1] - lat) * _M_PER_DEG])
    if len(xy) == 1:
        return float(np.hypot(*xy[0]))
    a, ab = xy[:-1], xy[1:] - xy[:-1]
    len2 = (ab ** 2).sum(axis=1)
    t = np.divide(-(a * ab).sum(axis=1), len2, out=np.zeros_like(len2), where=len2 > 0)
    closest = a + np.clip(t, 0.0, 1.0)[:, None] * ab
    return float(np.hypot(closest[:, 0], closest[:, 1]).min())
```

- [ ] **Step 4: Run to verify pass**

Run: `cd pipeline && pixi run pytest tests/test_anchors.py -v` → PASS.

- [ ] **Step 5: Commit** `git add pipeline/lib/anchors.py pipeline/tests/test_anchors.py && git commit -m "feat(pipeline): arc-length anchor helper"`

---

### Task 2: Anchors in `hut-edge-payload`

**Files:**
- Modify: `pipeline/phases/postprocessing/build_edge_payload.py`
- Modify: `pipeline/dag/postprocessing.py` (`task_build_edge_payload`)
- Test: `pipeline/tests/test_build_edge_payload.py`, `pipeline/tests/test_dodo_wiring.py`

**Interfaces:**
- Consumes: `edge_anchor_columns`, `anchor_column_names` (Task 1).
- Produces: `pack_edges(records, hut_ids, anchors=None)` (anchors: `dict[str, i2 array]`, appended as columns after `COLUMNS`); `anchor_columns_for_payload(records, geometry, hut_lonlat) -> dict`.

- [ ] **Step 1: Write failing tests** (append to `test_build_edge_payload.py`)

```python
from lib.anchors import anchor_column_names, decode_row  # noqa: E402
from postprocessing.build_edge_payload import anchor_columns_for_payload  # noqa: E402


def test_anchor_columns_are_appended_as_i2_after_the_scalar_columns():
    records = _records([_record(0, 1, binfmt.VARIANT_FAST_ANY)])
    records["geom_offset"], records["geom_count"] = 0, 2
    geometry = np.zeros(2, dtype=binfmt.COORD_DTYPE)
    geometry["lon"], geometry["lat"] = [11.0, 11.4], [47.0, 47.0]
    hut_lonlat = np.array([[11.0, 47.0], [11.4, 47.0]])

    anchors = anchor_columns_for_payload(records, geometry, hut_lonlat)
    payload, manifest = pack_edges(records, ["a", "b"], anchors)

    for name in anchor_column_names():
        assert manifest["columns"][name]["dtype"] == "i2"
    cols = {n: np.frombuffer(payload, dtype="i2", count=1, offset=s["offset"])
            for n, s in manifest["columns"].items() if n in anchors}
    assert decode_row(cols, 0, hut_lonlat[0])[1] == pytest.approx([11.2, 47.0], abs=1e-4)


def test_pack_edges_without_anchors_is_unchanged():
    _, manifest = pack_edges(RECORDS, HUT_IDS)
    assert "a50_dlat" not in manifest["columns"]
```

Append to `test_dodo_wiring.py`:

```python
def test_build_edge_payload_depends_on_hut_edge_geometry():
    deps = [str(d) for d in dodo.task_build_edge_payload()["file_dep"]]
    assert any(d.endswith("hut-edges/geometry.npy") for d in deps)
```

- [ ] **Step 2: Run** `pixi run pytest tests/test_build_edge_payload.py tests/test_dodo_wiring.py -v` → new tests FAIL.

- [ ] **Step 3: Implement.** In `build_edge_payload.py` add imports `from lib.anchors import edge_anchor_columns` and change:

```python
def anchor_columns_for_payload(records: np.ndarray, geometry: np.ndarray, hut_lonlat: np.ndarray) -> dict:
    """Anchor columns for every payload row, offset from the row's from_id hut coordinate."""
    ref = hut_lonlat[records["from_id"].astype(np.int64)]
    return edge_anchor_columns(records, geometry, np.arange(len(records)), ref)


def pack_edges(records: np.ndarray, hut_ids: list, anchors: dict | None = None) -> tuple:
    columns = {name: (dtype, records[name]) for name, dtype in COLUMNS}
    for name, values in (anchors or {}).items():
        columns[name] = ("i2", values)
    payload, column_manifest = binfmt.pack_columns(columns)
    ...  # manifest unchanged
```

In `__main__` (inside `phase(...)`), after `hut_ids = ...`:

```python
        geometry = binfmt.load_array(Path(args.edges_dir) / "geometry.npy")
        hut_lonlat = np.array(hut_points(args.huts))
        anchors = anchor_columns_for_payload(records, geometry, hut_lonlat)
        plain, _ = pack_edges(records, hut_ids)
        payload, manifest = pack_edges(records, hut_ids, anchors)
        plain_gz = len(gzip.compress(plain, compresslevel=9))
```

Replace the existing `gz_size` block to use `payload` and print `anchor growth: {gz_size - plain_gz:+,} B gzipped`; move `import gzip` to the top of the file. Update the module docstring's measured-size sentence to say anchors add 6 i2 columns (measured growth recorded in `docs/tour-suggestion-payload.md` §1). In `dag/postprocessing.py` `task_build_edge_payload` add `HUT_EDGES_DIR / "geometry.npy"` to `file_dep`.

- [ ] **Step 4: Run** the two test files → PASS.
- [ ] **Step 5: Commit** `feat(pipeline): ship edge anchors in hut-edge-payload`

---

### Task 3: Anchors in `approaches`

**Files:**
- Modify: `pipeline/phases/postprocessing/build_approach_table.py`, `pipeline/dag/postprocessing.py` (`task_build_approach_table`)
- Test: `pipeline/tests/test_build_approach_table.py`, `pipeline/tests/test_dodo_wiring.py`

**Interfaces:**
- Consumes: `edge_anchor_columns` (Task 1).
- Produces: `approach_anchor_columns(approaches, records, geometry, hut_lonlat) -> dict` — `approaches` is the list of row dicts from `select_approaches` (keys `edge_id`, `hut_id`); reference = the row's hut; geometry slice = `records[edge_id]`.

- [ ] **Step 1: Failing tests** (append to `test_build_approach_table.py`; it already imports `binfmt`, `np`, `_records`, `_record`)

```python
from lib.anchors import decode_row  # noqa: E402
from postprocessing.build_approach_table import approach_anchor_columns  # noqa: E402


def test_approach_anchors_are_offsets_from_the_rows_hut_along_the_start_edge():
    records = _records([_record(1, binfmt.TYPE_PARKING, 0, 1000.0, 0.0, 0.0)])
    records["geom_offset"], records["geom_count"] = 0, 2
    geometry = np.zeros(2, dtype=binfmt.COORD_DTYPE)
    geometry["lon"], geometry["lat"] = [11.4, 11.0], [47.0, 47.0]  # parking -> hut
    hut_lonlat = np.array([[11.0, 47.0]])

    cols = approach_anchor_columns([{"edge_id": 0, "hut_id": 0}], records, geometry, hut_lonlat)

    anchors = decode_row(cols, 0, hut_lonlat[0])
    assert anchors[0, 0] == pytest.approx(11.3, abs=1e-4)  # 25 % is near the parking end
    assert anchors[2, 0] == pytest.approx(11.1, abs=1e-4)
```

(add `import pytest` if the file lacks it). Append to `test_dodo_wiring.py`:

```python
def test_build_approach_table_depends_on_start_edge_geometry_and_huts():
    deps = [str(d) for d in dodo.task_build_approach_table()["file_dep"]]
    assert any(d.endswith("start-edges/geometry.npy") for d in deps)
    assert any(d.endswith("huts.geojson") for d in deps)
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** In `build_approach_table.py`:

```python
from lib.anchors import edge_anchor_columns  # noqa: E402
from lib.geo import hut_points  # noqa: E402
from lib.pipeline import RAW_DIR, START_EDGES_DIR, START_POINTS_DIR, load_config  # noqa: E402


def approach_anchor_columns(approaches: list, records: np.ndarray, geometry: np.ndarray,
                            hut_lonlat: np.ndarray) -> dict:
    """Anchor columns for the approach rows: each row's start edge geometry, offsets from its hut."""
    row_ids = np.array([r["edge_id"] for r in approaches], dtype=np.int64)
    ref = hut_lonlat[np.array([r["hut_id"] for r in approaches], dtype=np.int64)]
    return edge_anchor_columns(records, geometry, row_ids, ref)
```

Add CLI arg `--huts` (default `str(RAW_DIR / "huts.geojson")`, help "path to the hut master-data GeoJSON"). In `__main__`, after `approaches, index = build_tables(...)`:

```python
        geometry = binfmt.load_array(Path(args.edges_dir) / "geometry.npy")
        hut_lonlat = np.array(hut_points(args.huts))
        anchors = approach_anchor_columns(approaches, records, geometry, hut_lonlat)
```

and extend `columns` after building it: `for name, values in anchors.items(): columns[name] = ("i2", values)`; before packing, compute `plain_gz` by `binfmt.pack_columns` of the columns without anchors, and print `anchor growth: {…:+,} B gzipped` after packing (gzip the final payload). Add `f"--huts {RAW_DIR / 'huts.geojson'}"` to `task_build_approach_table` args, and `START_EDGES_DIR / "geometry.npy"`, `RAW_DIR / "huts.geojson"` to its `file_dep`.

- [ ] **Step 4: Run** both test files → PASS.
- [ ] **Step 5: Commit** `feat(pipeline): ship approach anchors in approaches.bin`

---

### Task 4: Anchors in `tours.json`

**Files:**
- Modify: `pipeline/phases/graph_building/match_tour_edges.py`
- Test: `pipeline/tests/test_match_tour_edges.py`

**Interfaces:**
- Consumes: `points_at_fractions` (Task 1).
- Produces: `leg_anchors_json(points) -> list[[lat, lng]]` and `"anchors"` on every tours.json leg.

- [ ] **Step 1: Failing tests** (append; file imports `mte`)

```python
def test_leg_anchors_json_is_lat_lng_pairs_in_walking_order():
    anchors = mte.leg_anchors_json([(11.0, 47.0), (11.4, 47.0)])
    assert len(anchors) == 3
    assert anchors[0] == pytest.approx([47.0, 11.1], abs=1e-4)
    assert anchors[2] == pytest.approx([47.0, 11.3], abs=1e-4)
```

Also add to the existing `test_main_writes_records_geometry_profiles_tours_and_gaps` an assertion that every leg of the written `tours.json` has `len(leg["anchors"]) == 3` (read how the test loads tours.json and add the loop in place).

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** In `match_tour_edges.py`: `from lib.anchors import points_at_fractions`, then

```python
def leg_anchors_json(points) -> list:
    """The leg's 25/50/75 % anchors as [lat, lng] pairs in walking order, rounded to 6 decimals."""
    pts = points_at_fractions([p[0] for p in points], [p[1] for p in points])
    return [[round(float(lat), 6), round(float(lon), 6)] for lon, lat in pts]
```

and add `"anchors": leg_anchors_json(points),` to the `tour_legs_json.append({...})` dict.

- [ ] **Step 4: Run** `pixi run pytest tests/test_match_tour_edges.py -v` → PASS.
- [ ] **Step 5: Commit** `feat(pipeline): ship leg anchors in tours.json`

---

### Task 5: Anchors-on-path quality check

**Files:**
- Modify: `pipeline/phases/quality/check_postprocessing.py`, `pipeline/dag/quality.py` (`task_check_postprocessing`)
- Test: `pipeline/tests/test_check_postprocessing.py`, `pipeline/tests/test_dodo_wiring.py`

**Interfaces:**
- Consumes: `decode_row`, `distance_to_polyline_m` (Task 1).
- Produces: `check_anchors_on_path(layer_name, anchors, polylines, tolerance_m, max_flagged) -> dict` where `anchors[i]` is `(k, 2)` lon/lat and `polylines[i]` is `(n, 2)` lon/lat.

- [ ] **Step 1: Failing tests** (append to `test_check_postprocessing.py`; mirror its imports)

```python
def test_anchors_on_path_passes_points_on_the_line():
    poly = np.array([[11.0, 47.0], [11.4, 47.0]])
    c = check_anchors_on_path("hut_edges", [np.array([[11.1, 47.0], [11.2, 47.0]])], [poly], 25.0, 500)
    assert c["summary"]["flagged"] == 0 and c["summary"]["checked"] == 1


def test_anchors_on_path_flags_a_point_off_the_line():
    poly = np.array([[11.0, 47.0], [11.4, 47.0]])
    c = check_anchors_on_path("hut_edges", [np.array([[11.2, 47.01]])], [poly], 25.0, 500)
    assert c["summary"]["flagged"] == 1
```

(import `numpy as np` and `check_anchors_on_path` at the top). Append to `test_dodo_wiring.py`:

```python
def test_check_postprocessing_depends_on_the_geometry_it_samples_anchors_against():
    deps = [str(d) for d in dodo.task_check_postprocessing()["file_dep"]]
    for name in ("hut-edges/geometry.npy", "start-edges/geometry.npy", "tour-edges/geometry.npy", "hut-edges/payload.bin"):
        assert any(d.endswith(name) for d in deps), name
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** In `check_postprocessing.py` (imports: `from lib.anchors import ANCHOR_FRACTIONS, decode_row, distance_to_polyline_m`, `from lib.geo import haversine_m, hut_points`):

```python
ANCHOR_SAMPLE_ROWS = 500


def check_anchors_on_path(layer_name: str, anchors: list, polylines: list, tolerance_m: float,
                          max_flagged: int) -> dict:
    """Every sampled decoded anchor lies within tolerance_m of its edge's full-resolution polyline.
    anchors[i] is (k, 2) lon/lat, polylines[i] is (n, 2) lon/lat."""
    flagged = []
    for i, (points, poly) in enumerate(zip(anchors, polylines)):
        for k, (lon, lat) in enumerate(points):
            d = distance_to_polyline_m(lon, lat, poly)
            if d > tolerance_m:
                flagged.append({"layer": layer_name, "sample": i, "anchor": k, "distance_m": d})
    return build_check(
        f"anchors_on_path_{layer_name}", {"tolerance_m": tolerance_m}, checked=len(anchors),
        flagged_rows=flagged, baseline=0, max_flagged_rows=max_flagged,
        sort_key=lambda r: r["distance_m"],
    )


def _polyline(records, geometry, row):
    off, cnt = int(records[row]["geom_offset"]), int(records[row]["geom_count"])
    piece = geometry[off:off + cnt]
    return np.column_stack([piece["lon"], piece["lat"]])
```

Add CLI arg `--anchor-tolerance-m` (default `pp_cfg.get("anchorToleranceM", 25.0)`). In `main`, after the approach coverage check, add (skipping a layer when a file is missing, like the loop below it does):

```python
        huts_lonlat = np.array(hut_points(raw_dir / "huts.geojson"))
        hut_dir = build_dir / "hut-edges"
        if (hut_dir / "payload.json").exists() and (hut_dir / "geometry.npy").exists():
            manifest = json.loads((hut_dir / "payload.json").read_text(encoding="utf-8"))
            cols = _unpack_columns((hut_dir / "payload.bin").read_bytes(), manifest["columns"], manifest["rows"])
            if "a50_dlat" in cols:
                recs = binfmt.load_array(hut_dir / "records.npy")
                geom = binfmt.load_array(hut_dir / "geometry.npy")
                rows = range(0, manifest["rows"], max(1, manifest["rows"] // ANCHOR_SAMPLE_ROWS))
                fractions = tuple(f for f in ANCHOR_FRACTIONS if f"a{int(round(f * 100))}_dlat" in cols)
                c = check_anchors_on_path(
                    "hut_edges",
                    [decode_row(cols, i, huts_lonlat[int(cols["from_id"][i])], fractions) for i in rows],
                    [_polyline(recs, geom, i) for i in rows], args.anchor_tolerance_m, args.max_flagged_rows)
                checks.append(c)
```

Add the same block for approaches (`start-edges/approaches.json`+`.bin`, reference `huts_lonlat[int(cols["hut_id"][i])]`, polyline row `int(cols["edge_id"][i])` from `start-edges/records.npy`/`geometry.npy`; reuse the already-loaded `approach_columns`/`start_records`), and for tours (`tour-edges/tours.json` legs' `anchors` `[lat, lng]` flipped to lon/lat, polyline row `leg["edgeId"]` from `tour-edges/records.npy`/`geometry.npy`). Factor the three blocks through one local helper if it reads cleaner. Print each check's flagged/checked line like the neighbours.

In `dag/quality.py` `task_check_postprocessing` add to `file_dep`: `HUT_EDGES_DIR / "payload.bin"`, `HUT_EDGES_DIR / "records.npy"`, `HUT_EDGES_DIR / "geometry.npy"`, `START_EDGES_DIR / "geometry.npy"`, `TOUR_EDGES_DIR / "records.npy"`, `TOUR_EDGES_DIR / "geometry.npy"`, `START_EDGES_DIR / "approaches.bin"` (already listed; keep once) — import `HUT_EDGES_DIR` there if missing.

- [ ] **Step 4: Run** `pixi run pytest tests/test_check_postprocessing.py tests/test_dodo_wiring.py -v`, then the whole suite `pixi run pytest -q` → PASS.
- [ ] **Step 5: Commit** `feat(pipeline): check shipped anchors lie on their polyline`

---

### Task 6: Client i2 dtype and anchor offsets in the loaders

**Files:**
- Modify: `huts/src/tourSearch/binaryColumns.ts`, `types.ts`, `loadHutEdges.ts`, `loadApproaches.ts`, `loadOfficialTours.ts`
- Create: `huts/src/tourSearch/anchors.ts`
- Test: `binaryColumns.test.ts`, `loadHutEdges.test.ts`, `loadApproaches.test.ts`, new `anchors.test.ts`

**Interfaces:**
- Produces:
  - `Dtype` gains `'i2'`.
  - `anchors.ts`: `ANCHOR_UNIT_DEG = 1e-4`, `interface LatLng { lat: number; lng: number }`, `readAnchorOffsets(columns: Record<string, number[]>, row: number): number[] | null` (flat `[dlat0, dlng0, dlat1, dlng1, …]`, null when no anchor column exists), `decodeAnchors(offsets: readonly number[], ref: LatLng): LatLng[]`, `anchorFractions(count: number): number[]` (`(i+1)/(count+1)`: 3 → `[.25,.5,.75]`, 1 → `[.5]`).
  - `HutEdgeRecord.anchorOffsets?: number[] | null`, `ApproachRecord.anchorOffsets?: number[] | null` (optional so existing literals compile).
  - `RawTourLeg.anchors?: [number, number][]` (`[lat, lng]` pairs).

- [ ] **Step 1: Failing tests.**

`binaryColumns.test.ts` — add:

```ts
it('round-trips signed i2 columns', () => {
  const { manifest, buffer } = packColumns({ d: 'i2' }, { d: [-3, 0, 32767, -32768] }, 4)
  expect(readColumns(buffer, manifest).d).toEqual([-3, 0, 32767, -32768])
})
```

`anchors.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { anchorFractions, decodeAnchors, readAnchorOffsets } from './anchors.js'

describe('anchors', () => {
  it('reads every present anchor column pair as flat offsets, null when none', () => {
    const cols = { a25_dlat: [1], a25_dlng: [2], a50_dlat: [3], a50_dlng: [4], a75_dlat: [5], a75_dlng: [6] }
    expect(readAnchorOffsets(cols, 0)).toEqual([1, 2, 3, 4, 5, 6])
    expect(readAnchorOffsets({ a50_dlat: [3], a50_dlng: [4] }, 0)).toEqual([3, 4])
    expect(readAnchorOffsets({}, 0)).toBeNull()
  })
  it('decodes offsets relative to the reference in 1e-4 degree units', () => {
    const [a] = decodeAnchors([10, -20], { lat: 47, lng: 11 })
    expect(a.lat).toBeCloseTo(47.001, 9)
    expect(a.lng).toBeCloseTo(10.998, 9)
  })
  it('spaces fractions evenly', () => {
    expect(anchorFractions(3)).toEqual([0.25, 0.5, 0.75])
    expect(anchorFractions(1)).toEqual([0.5])
  })
})
```

`loadHutEdges.test.ts` — add a test that packs the standard columns plus `a25_dlat…a75_dlng` (`'i2'`) and expects `data.records[0].anchorOffsets` to equal the six values; and that the existing test (no anchor columns) yields `anchorOffsets: null`. `loadApproaches.test.ts` — same for approaches (`a50_dlat`/`a50_dlng` only → `[dlat, dlng]`).

- [ ] **Step 2: Run** `cd huts && npx vitest run src/tourSearch` → new tests FAIL.
- [ ] **Step 3: Implement.**

`binaryColumns.ts`: `export type Dtype = 'u1' | 'i1' | 'u2' | 'i2' | 'u4' | 'u8' | 'f4'` and

```ts
i2: { bytes: 2, get: (v, o) => v.getInt16(o, true), set: (v, o, x) => v.setInt16(o, x, true) },
```

`anchors.ts`:

```ts
export const ANCHOR_UNIT_DEG = 1e-4

export interface LatLng { lat: number; lng: number }

const ANCHOR_COLUMNS = [['a25_dlat', 'a25_dlng'], ['a50_dlat', 'a50_dlng'], ['a75_dlat', 'a75_dlng']] as const

/** Flat `[dlat0, dlng0, dlat1, dlng1, ...]` of the anchor columns the payload carries, in arc-length order; null when it carries none. */
export function readAnchorOffsets(columns: Record<string, number[]>, row: number): number[] | null {
  const out: number[] = []
  for (const [dlat, dlng] of ANCHOR_COLUMNS) {
    if (columns[dlat] && columns[dlng]) out.push(columns[dlat][row], columns[dlng][row])
  }
  return out.length > 0 ? out : null
}

/** Absolute anchors of an edge in its stored direction; offsets count 1e-4 degrees from `ref`. */
export function decodeAnchors(offsets: readonly number[], ref: LatLng): LatLng[] {
  const out: LatLng[] = []
  for (let i = 0; i + 1 < offsets.length; i += 2) {
    out.push({ lat: ref.lat + offsets[i] * ANCHOR_UNIT_DEG, lng: ref.lng + offsets[i + 1] * ANCHOR_UNIT_DEG })
  }
  return out
}

/** Arc-length fractions of `count` evenly spread anchors: 3 gives 25/50/75 %, 1 gives 50 %. */
export function anchorFractions(count: number): number[] {
  return Array.from({ length: count }, (_, i) => (i + 1) / (count + 1))
}
```

`types.ts`: add `anchorOffsets?: number[] | null` to `ApproachRecord` and `HutEdgeRecord`. Loaders: in each record literal add `anchorOffsets: readAnchorOffsets(c, i),` (import from `./anchors.js`). `loadOfficialTours.ts`: `RawTourLeg` gets `anchors?: [number, number][]` (doc: `[lat, lng]` at 25/50/75 % of the leg in walking order).

- [ ] **Step 4: Run** `npx vitest run src/tourSearch && npm run typecheck` → PASS.
- [ ] **Step 5: Commit** `feat(tourSearch): read anchor offsets from the payloads`

---

### Task 7: Leg anchor lookup

**Files:**
- Create: `huts/src/tourSearch/legAnchors.ts`, `legAnchors.test.ts`
- Modify: `huts/src/tourSearch/officialTours.ts` (+ its test)

**Interfaces:**
- Consumes: `decodeAnchors`, `LatLng` (Task 6), `HutEdgesData`, `ApproachesData`, `OfficialTourView`, `GeometryLayer`.
- Produces:
  - `type LegAnchorLookup = (layer: GeometryLayer, edgeId: number) => LatLng[] | null` — anchors in **stored direction**, null when none shipped or the edge is unknown.
  - `createLegAnchorLookup(input: { hutEdges: HutEdgesData; approaches: ApproachesData; hutCoordsById: ReadonlyMap<number, LatLng>; officialTours: readonly OfficialTourView[] }): LegAnchorLookup`
  - `OfficialTourLeg.anchors?: LatLng[] | null`.

- [ ] **Step 1: Failing tests** (`legAnchors.test.ts`)

```ts
import { describe, it, expect } from 'vitest'
import { createLegAnchorLookup } from './legAnchors.js'
import type { ApproachRecord, HutEdgeRecord } from './types.js'

const hut = (over: Partial<HutEdgeRecord>): HutEdgeRecord => ({
  fromIndex: 0, toIndex: 1, variant: 0, distanceM: 1, ascentM: 0, descentM: 0, maxEleM: 0, sacRank: 0,
  viaFerrata: false, roadM: 0, ungradedM: 0, inferredM: 0, snapM: 0, edgeId: 0, ...over,
})
const approach = (over: Partial<ApproachRecord>): ApproachRecord => ({
  hutIndex: 1, startId: 9, sourceType: 1, variant: 0, accessUnknown: false, distanceM: 1, ascentM: 0, descentM: 0,
  access: null, edgeId: 40, ...over,
})
const hutCoordsById = new Map([[0, { lat: 47, lng: 11 }], [1, { lat: 47.1, lng: 11.2 }]])
const lookup = createLegAnchorLookup({
  hutEdges: { hutIds: [], variantNames: {}, records: [hut({ anchorOffsets: [10, 20, 30, 40, 50, 60] }), hut({ edgeId: 1 })] },
  approaches: { records: [approach({ anchorOffsets: [1, 2] }), approach({ edgeId: 41 })], reverseIndex: { hut_to_starts: {}, start_to_huts: {} } },
  hutCoordsById,
  officialTours: [{ tourId: 1, name: 't', totalDistanceM: 0, totalAscentM: 0, totalDescentM: 0, totalDurationH: 0, legs: [
    { legIndex: 0, from: { type: 'hut', id: 0 }, to: { type: 'hut', id: 1 }, edgeId: 7, reversed: false, distanceM: 1, ascentM: 0, descentM: 0, durationH: 0, maxEleM: 0, anchors: [{ lat: 1, lng: 2 }] },
  ] }],
})

describe('createLegAnchorLookup', () => {
  it('decodes hut-edge anchors relative to the from hut', () => {
    const a = lookup('hut_edges', 0)!
    expect(a).toHaveLength(3)
    expect(a[0].lat).toBeCloseTo(47.001, 9)
    expect(a[0].lng).toBeCloseTo(11.002, 9)
  })
  it('decodes approach anchors relative to the approach hut, keyed by start-edge id', () => {
    const [a] = lookup('start_edges', 40)!
    expect(a.lat).toBeCloseTo(47.1001, 9)
    expect(a.lng).toBeCloseTo(11.2002, 9)
  })
  it('returns the official leg anchors as shipped', () => {
    expect(lookup('tour_edges', 7)).toEqual([{ lat: 1, lng: 2 }])
  })
  it('returns null when no anchors shipped, the edge is unknown, or the id is negative', () => {
    expect(lookup('hut_edges', 1)).toBeNull()
    expect(lookup('start_edges', 41)).toBeNull()
    expect(lookup('start_edges', 999)).toBeNull()
    expect(lookup('hut_edges', -1)).toBeNull()
    expect(lookup('tour_edges', 1)).toBeNull()
  })
})
```

In `officialTours.test.ts` add: a `RawTour` leg with `anchors: [[47, 11], [47.1, 11.1]]` yields `views[0].legs[0].anchors` `[{lat:47,lng:11},{lat:47.1,lng:11.1}]`, and a leg without `anchors` yields `null`.

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**

`legAnchors.ts`:

```ts
import { decodeAnchors } from './anchors.js'
import type { LatLng } from './anchors.js'
import type { GeometryLayer } from './loadLegGeometry.js'
import type { OfficialTourView } from './officialTours.js'
import type { ApproachesData, HutEdgesData } from './types.js'

/** Anchors of one leg's edge in its stored direction; null when none were shipped for it. */
export type LegAnchorLookup = (layer: GeometryLayer, edgeId: number) => LatLng[] | null

export function createLegAnchorLookup({ hutEdges, approaches, hutCoordsById, officialTours }: {
  hutEdges: HutEdgesData
  approaches: ApproachesData
  hutCoordsById: ReadonlyMap<number, LatLng>
  officialTours: readonly OfficialTourView[]
}): LegAnchorLookup {
  const approachByEdge = new Map(approaches.records.map((r) => [r.edgeId, r]))
  const officialByEdge = new Map(officialTours.flatMap((t) => t.legs.map((l) => [l.edgeId, l.anchors ?? null] as const)))
  const decode = (offsets: number[] | null | undefined, hutIndex: number | undefined): LatLng[] | null => {
    const ref = hutIndex === undefined ? undefined : hutCoordsById.get(hutIndex)
    return offsets && ref ? decodeAnchors(offsets, ref) : null
  }
  return (layer, edgeId) => {
    if (edgeId < 0) return null
    if (layer === 'hut_edges') {
      const r = hutEdges.records[edgeId]
      return decode(r?.anchorOffsets, r?.fromIndex)
    }
    if (layer === 'start_edges') {
      const r = approachByEdge.get(edgeId)
      return decode(r?.anchorOffsets, r?.hutIndex)
    }
    return officialByEdge.get(edgeId) ?? null
  }
}
```

`officialTours.ts`: import `LatLng`; `OfficialTourLeg` gets `anchors?: LatLng[] | null`; in `buildOfficialTourViews` add `anchors: leg.anchors ? leg.anchors.map(([lat, lng]) => ({ lat, lng })) : null,`.

- [ ] **Step 4: Run** `npx vitest run src/tourSearch && npm run typecheck` → PASS.
- [ ] **Step 5: Commit** `feat(tourSearch): leg anchor lookup`

---

### Task 8: `tourAnchor`

**Files:**
- Create: `huts/src/tourSearch/tourAnchor.ts`, `tourAnchor.test.ts`

**Interfaces:**
- Consumes: `LegAnchorLookup` (Task 7), `LatLng`, `anchorFractions` (Task 6), `GeometryLayer`.
- Produces:
  - `type Heading = 'east' | 'west'`
  - `interface AnchorLeg { layer: GeometryLayer; edgeId: number; reversed: boolean; distanceM: number }`
  - `interface AnchorRoute { waypoints: LatLng[]; legs: AnchorLeg[] }` (`waypoints.length === legs.length + 1`)
  - `type Bbox = [west: number, south: number, east: number, north: number]`
  - `interface TourAnchor extends LatLng { heading: Heading }`
  - `tourAnchor(route: AnchorRoute, lookup: LegAnchorLookup, bbox: Bbox): TourAnchor | null`

- [ ] **Step 1: Failing tests** (`tourAnchor.test.ts`)

```ts
import { describe, it, expect } from 'vitest'
import { tourAnchor } from './tourAnchor.js'
import type { AnchorRoute } from './tourAnchor.js'
import type { LegAnchorLookup } from './legAnchors.js'

const WORLD: [number, number, number, number] = [-180, -90, 180, 90]
const none: LegAnchorLookup = () => null
const leg = (edgeId: number, distanceM: number, reversed = false) => ({ layer: 'hut_edges' as const, edgeId, reversed, distanceM })
const pt = (lat: number, lng: number) => ({ lat, lng })

// Two legs west->east, 1000 m each, anchors known for edge 0 (a, b, c), chord for edge 1.
const route: AnchorRoute = { waypoints: [pt(47, 11), pt(47, 11.4), pt(47, 11.8)], legs: [leg(0, 1000), leg(1, 1000)] }
const stored: LegAnchorLookup = (_l, id) => (id === 0 ? [pt(47.01, 11.1), pt(47.02, 11.2), pt(47.03, 11.3)] : null)

describe('tourAnchor', () => {
  it('picks the candidate closest to half the tour distance', () => {
    // half = 1000 m: leg 0 spans 0..1000 (anchors at 250/500/750), leg 1 spans 1000..2000 (chord 1250/1500/1750)
    const a = tourAnchor(route, stored, WORLD)!
    expect(a.lat).toBeCloseTo(47.03, 6)   // 750 m is the nearest to 1000 m
    expect(a.lng).toBeCloseTo(11.3, 6)
  })

  it('swaps the 25 and 75 % anchors of a reversed leg', () => {
    const rev: AnchorRoute = { waypoints: [pt(47, 11.4), pt(47, 11)], legs: [leg(0, 1000, true)] }
    const a = tourAnchor(rev, stored, WORLD)!
    // candidates in walking order: 11.3 @250, 11.2 @500, 11.1 @750; half = 500 -> the 50 % anchor
    expect(a.lng).toBeCloseTo(11.2, 6)
    const rev2: AnchorRoute = { waypoints: [pt(47, 11.4), pt(47, 11), pt(47, 10.6)], legs: [leg(0, 1000, true), leg(5, 1)] }
    // half = 500.5: nearest is the 50 % anchor again, but now with 25/75 swapped it must still be 11.2
    expect(tourAnchor(rev2, stored, WORLD)!.lng).toBeCloseTo(11.2, 6)
  })

  it('takes the chord point when a leg has no shipped anchors or edgeId < 0', () => {
    const r: AnchorRoute = { waypoints: [pt(47, 11), pt(47, 11.4)], legs: [leg(-1, 1000)] }
    const a = tourAnchor(r, none, WORLD)!
    expect(a.lat).toBeCloseTo(47, 6)
    expect(a.lng).toBeCloseTo(11.2, 6)
  })

  it('heads west when the route runs westward at the anchor, else east', () => {
    const west: AnchorRoute = { waypoints: [pt(47, 11.4), pt(47, 11)], legs: [leg(-1, 1000)] }
    expect(tourAnchor(west, none, WORLD)!.heading).toBe('west')
    expect(tourAnchor(route, none, WORLD)!.heading).toBe('east')
  })

  it('derives the heading from the neighbouring candidates, not the whole leg', () => {
    // the leg doubles back: at the 50 % anchor the previous anchor (11.3) lies east of the next (11.1), so the travel there is west
    const bulge: LegAnchorLookup = () => [pt(47, 11.3), pt(47, 10.9), pt(47, 11.1)]
    const r: AnchorRoute = { waypoints: [pt(47, 11), pt(47, 11.4)], legs: [leg(0, 1000)] }
    expect(tourAnchor(r, bulge, WORLD)!.heading).toBe('west')
  })

  it('falls back to the in-view candidate closest to half the distance', () => {
    // bbox covers only lng 11.0..11.15: only the 25 % anchor (11.1) is inside
    const a = tourAnchor(route, stored, [11.0, 46, 11.15, 48])!
    expect(a.lng).toBeCloseTo(11.1, 6)
  })

  it('returns null when no candidate lies in the viewport', () => {
    expect(tourAnchor(route, stored, [12.5, 46, 13, 48])).toBeNull()
  })

  it('still yields an anchor for a tour of zero total distance', () => {
    const r: AnchorRoute = { waypoints: [pt(47, 11), pt(47, 11.4)], legs: [leg(-1, 0)] }
    expect(tourAnchor(r, none, WORLD)).not.toBeNull()
  })

  it('returns null for a route without legs', () => {
    expect(tourAnchor({ waypoints: [pt(47, 11)], legs: [] }, none, WORLD)).toBeNull()
  })

  it('handles a lookup that ships only the 50 % anchor', () => {
    const one: LegAnchorLookup = () => [pt(47.05, 11.2)]
    const r: AnchorRoute = { waypoints: [pt(47, 11), pt(47, 11.4)], legs: [leg(0, 1000)] }
    expect(tourAnchor(r, one, WORLD)!.lat).toBeCloseTo(47.05, 6)
  })
})
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** (`tourAnchor.ts`)

```ts
import { anchorFractions } from './anchors.js'
import type { LatLng } from './anchors.js'
import type { LegAnchorLookup } from './legAnchors.js'
import type { GeometryLayer } from './loadLegGeometry.js'

export type Heading = 'east' | 'west'
export type Bbox = [west: number, south: number, east: number, north: number]

export interface AnchorLeg { layer: GeometryLayer; edgeId: number; reversed: boolean; distanceM: number }
/** A tour's route as the anchor choice sees it: `waypoints.length === legs.length + 1`. */
export interface AnchorRoute { waypoints: LatLng[]; legs: AnchorLeg[] }
export interface TourAnchor extends LatLng { heading: Heading }

interface Candidate extends TourAnchor { at: number }

const CHORD_FRACTIONS = anchorFractions(3)

const inBbox = (p: LatLng, [w, s, e, n]: Bbox) => p.lng >= w && p.lng <= e && p.lat >= s && p.lat <= n

const lerp = (a: LatLng, b: LatLng, t: number): LatLng => ({ lat: a.lat + (b.lat - a.lat) * t, lng: a.lng + (b.lng - a.lng) * t })

/** Every anchor of the route in walking order with its arc-length position along the tour and the travel
 *  direction there (from the previous point of the route to the next, waypoints included). A leg without
 *  shipped anchors contributes the chord points at the same fractions. */
function candidates(route: AnchorRoute, lookup: LegAnchorLookup): Candidate[] {
  const seq: { p: LatLng; at: number | null }[] = [{ p: route.waypoints[0], at: null }]
  let walked = 0
  route.legs.forEach((leg, i) => {
    const shipped = lookup(leg.layer, leg.edgeId)
    const points = shipped
      ? (leg.reversed ? [...shipped].reverse() : shipped)
      : CHORD_FRACTIONS.map((t) => lerp(route.waypoints[i], route.waypoints[i + 1], t))
    const fractions = anchorFractions(points.length)
    points.forEach((p, k) => seq.push({ p, at: walked + fractions[k] * leg.distanceM }))
    walked += leg.distanceM
    seq.push({ p: route.waypoints[i + 1], at: null })
  })
  return seq.flatMap(({ p, at }, j) => {
    if (at === null) return []
    const heading: Heading = seq[j + 1].p.lng < seq[j - 1].p.lng ? 'west' : 'east'
    return [{ lat: p.lat, lng: p.lng, at, heading }]
  })
}

/** Where a tour's signpost stands: the anchor nearest half the tour's distance, or, when that is outside `bbox`,
 *  the in-view anchor nearest it; null when the tour has no anchor in view. */
export function tourAnchor(route: AnchorRoute, lookup: LegAnchorLookup, bbox: Bbox): TourAnchor | null {
  const half = route.legs.reduce((sum, l) => sum + l.distanceM, 0) / 2
  let best: Candidate | null = null
  let bestInView: Candidate | null = null
  for (const c of candidates(route, lookup)) {
    const d = Math.abs(c.at - half)
    if (!best || d < Math.abs(best.at - half)) best = c
    if (inBbox(c, bbox) && (!bestInView || d < Math.abs(bestInView.at - half))) bestInView = c
  }
  const chosen = best && inBbox(best, bbox) ? best : bestInView
  return chosen ? { lat: chosen.lat, lng: chosen.lng, heading: chosen.heading } : null
}
```

- [ ] **Step 4: Run** `npx vitest run src/tourSearch/tourAnchor.test.ts && npm run typecheck && npm run lint` → PASS. (If the `rev2` case in the reversed-leg test does not resolve as commented after running, fix the test's expectation from the code's actual walking-order arithmetic — the swap itself is the behaviour under test — never weaken the swap assertion in the first case.)
- [ ] **Step 5: Commit** `feat(tourSearch): tourAnchor picks the mid-route anchor`

---

### Task 9: `RouteContext.legAnchors` and `tourAnchorOf`

**Files:**
- Modify: `huts/src/features/map/routes.ts`, `huts/src/features/planner/PlannerPage.tsx`
- Modify (test literals): `routes.test.ts`, `SavedTripsLayer.test.tsx`, `DiscoverLayer.test.tsx`, any other `RouteContext` literal `tsc` reports
- Test: `routes.test.ts`

**Interfaces:**
- Consumes: `LegAnchorLookup`, `createLegAnchorLookup`, `tourAnchor`, `TourAnchor`, `Bbox`.
- Produces: `RouteContext.legAnchors: LegAnchorLookup`; `tourAnchorOf(tour: PlannerTour, route: Route, ctx: RouteContext, bbox: Bbox): TourAnchor | null`.

- [ ] **Step 1: Failing test** (`routes.test.ts`; reuse its `ctx`, extend with `legAnchors: () => null`)

```ts
it('tourAnchorOf runs the anchor choice over the route with the tour leg distances', () => {
  const tour = { ...baseTour, legs: baseTour.legs.map((l) => ({ ...l, distanceM: 1000 })) }
  const route = tourToRoute(tour, ctx)!
  const a = tourAnchorOf(tour, route, ctx, [-180, -90, 180, 90])
  expect(a).not.toBeNull()
})
```

(use whichever tour fixture the file already builds; name it accordingly). Add `legAnchors: () => null` to every `RouteContext` literal in tests.

- [ ] **Step 2: Run** → FAIL (type error / missing export).
- [ ] **Step 3: Implement.** `routes.ts`:

```ts
import { tourAnchor } from '@/tourSearch/tourAnchor.js'
import type { Bbox, TourAnchor } from '@/tourSearch/tourAnchor.js'
import type { LegAnchorLookup } from '@/tourSearch/legAnchors.js'
// RouteContext gains:
  /** Anchor points of a leg's edge, for placing a tour's signpost on its route. */
  legAnchors: LegAnchorLookup

/** Where the tour's signpost stands on its route, or null when no anchor of the tour is in `bbox`. */
export function tourAnchorOf(tour: PlannerTour, route: Route, ctx: RouteContext, bbox: Bbox): TourAnchor | null {
  return tourAnchor({
    waypoints: route.waypoints,
    legs: route.legs.map((l, i) => ({ layer: l.layer, edgeId: l.edgeId, reversed: l.reversed, distanceM: tour.legs[i].distanceM })),
  }, ctx.legAnchors, bbox)
}
```

`PlannerPage.tsx` routeCtx memo:

```ts
import { createLegAnchorLookup } from '@/tourSearch/legAnchors.js'
...
    hutClassByIndex: data.hutClassByIndex,
    legAnchors: createLegAnchorLookup({
      hutEdges: data.graph.hutEdges, approaches: data.graph.approaches,
      hutCoordsById: data.hutCoordsById, officialTours: data.officialTours,
    }),
```

- [ ] **Step 4: Run** `npx vitest run src/features && npm run typecheck` → PASS.
- [ ] **Step 5: Commit** `feat(map): route context carries leg anchors`

---

### Task 10: Anchor clusterer

**Files:**
- Modify: `huts/src/features/map/clusterStarts.ts`, `clusterStarts.test.ts`

**Interfaces:**
- Produces:
  - `interface AnchorPoint { tourKey: string; lat: number; lng: number }`
  - `interface AnchorMarker { id: string; lat: number; lng: number; tourKeys: string[] }` — `tourKeys` best-ranked first, `lat/lng` the best-ranked member's own anchor, `id` = `tourKeys[0]`
  - `createAnchorClusterer(points: AnchorPoint[]): { markersFor(bbox: [number, number, number, number], zoom: number): AnchorMarker[] }` — **input order is the rank order** (best first)
  - `anchorMarkerKind(m: AnchorMarker): MarkerKind` (`'single'` when one tour, else `'stack'`)
- Unchanged: `createStartClusterer`, `markerRadius` (still serve the bubble zoom levels). Remove `markerKind` (it is replaced) and update its test.

- [ ] **Step 1: Failing tests** (replace the `markerKind` describe in `clusterStarts.test.ts`)

```ts
import { anchorMarkerKind, createAnchorClusterer } from './clusterStarts.js'
import type { AnchorMarker } from './clusterStarts.js'

describe('createAnchorClusterer', () => {
  const points = [
    { tourKey: 'best', lat: 47.0, lng: 11.0 },
    { tourKey: 'near', lat: 47.0001, lng: 11.0001 },
    { tourKey: 'far', lat: 48.5, lng: 13.0 },
  ]
  const clusterer = createAnchorClusterer(points)

  it('groups nearby anchors into one marker whose foot is the best-ranked tour\'s own anchor', () => {
    const markers = clusterer.markersFor(WORLD, 13)
    const stack = markers.find((m) => m.tourKeys.length === 2)!
    expect(stack.tourKeys).toEqual(['best', 'near'])
    expect(stack.lat).toBe(47.0)
    expect(stack.lng).toBe(11.0)
    expect(stack.id).toBe('best')
  })

  it('keeps distant anchors as single markers', () => {
    const markers = clusterer.markersFor(WORLD, 13)
    expect(markers.find((m) => m.tourKeys[0] === 'far')!.tourKeys).toEqual(['far'])
  })

  it('ranks by input order even when the cluster tree returns members differently', () => {
    const reversed = createAnchorClusterer([...points.slice(0, 2)].reverse())
    expect(reversed.markersFor(WORLD, 13).find((m) => m.tourKeys.length === 2)!.tourKeys).toEqual(['near', 'best'])
  })

  it('separates every anchor past the clusterer\'s max zoom', () => {
    expect(clusterer.markersFor(WORLD, 20).map((m) => m.tourKeys.length)).toEqual([1, 1, 1])
  })

  it('handles no points', () => { expect(createAnchorClusterer([]).markersFor(WORLD, 13)).toEqual([]) })
})

describe('anchorMarkerKind', () => {
  const m = (n: number): AnchorMarker => ({ id: 'a', lat: 0, lng: 0, tourKeys: Array.from({ length: n }, (_, i) => `k${i}`) })
  it('is single for one tour and stack for several', () => {
    expect(anchorMarkerKind(m(1))).toBe('single')
    expect(anchorMarkerKind(m(3))).toBe('stack')
  })
})
```

(the `markers`/`WORLD` constants at the top of the file stay for the start clusterer tests).

- [ ] **Step 2: Run** `npx vitest run src/features/map/clusterStarts.test.ts` → FAIL.
- [ ] **Step 3: Implement** in `clusterStarts.ts`:

```ts
export interface AnchorPoint { tourKey: string; lat: number; lng: number }

/** One signpost: the tours whose anchors cluster together, best-ranked first. The foot stands on the
 *  best-ranked tour's own anchor, never on a cluster centroid. */
export interface AnchorMarker { id: string; lat: number; lng: number; tourKeys: string[] }

export interface AnchorClusterer {
  markersFor(bbox: [number, number, number, number], zoom: number): AnchorMarker[]
}

/** Screen radius (px) within which anchors share one signpost; boards are wider than count bubbles. */
const ANCHOR_CLUSTER_RADIUS = 70
const ANCHOR_CLUSTER_MAX_ZOOM = 16

/** `points` are in rank order, best first; that order decides each marker's foot and board order. */
export function createAnchorClusterer(points: AnchorPoint[]): AnchorClusterer {
  const index = new Supercluster<{ rank: number }>({ radius: ANCHOR_CLUSTER_RADIUS, maxZoom: ANCHOR_CLUSTER_MAX_ZOOM })
  index.load(points.map((p, rank) => ({
    type: 'Feature' as const,
    properties: { rank },
    geometry: { type: 'Point' as const, coordinates: [p.lng, p.lat] },
  })))
  return {
    markersFor(bbox, zoom) {
      return index.getClusters(bbox, Math.round(zoom)).map((f): AnchorMarker => {
        const props = f.properties as { cluster?: boolean; cluster_id?: number; rank?: number }
        const ranks = props.cluster
          ? index.getLeaves(props.cluster_id!, Infinity).map((leaf) => (leaf.properties as { rank: number }).rank).sort((a, b) => a - b)
          : [props.rank!]
        const foot = points[ranks[0]]
        return { id: foot.tourKey, lat: foot.lat, lng: foot.lng, tourKeys: ranks.map((r) => points[r].tourKey) }
      })
    },
  }
}

export function anchorMarkerKind(m: AnchorMarker): MarkerKind {
  return m.tourKeys.length === 1 ? 'single' : 'stack'
}
```

Delete `markerKind` and update its callers in Task 12 (compile stays red for `DiscoverLayer.tsx` until then; do Tasks 10-12 before running the full typecheck, or keep `markerKind` until Task 12 removes it — prefer the latter: leave `markerKind` in place now and delete it in Task 12).

- [ ] **Step 4: Run** the clusterer tests → PASS.
- [ ] **Step 5: Commit** `feat(map): cluster tour anchors into signposts`

---

### Task 11: Board on a mast (markup, CSS, side flip, fade)

**Files:**
- Modify: `huts/src/features/map/signpostHtml.ts`, `map.css`, `SignpostMarker.tsx`
- Test: `signpostHtml.test.ts`, `SignpostMarker.test.tsx`

**Interfaces:**
- Consumes: `Heading` from `signpostHtml.ts` (unchanged export).
- Produces: `singleHtml`/`stackHtml` output now begins with `<span class="mast"></span><span class="foot"></span>`; `SignpostMarker` gains props `heading: Heading` (default `'east'`; used for `single` only) and `fadedKeys: ReadonlySet<string>`; marker element carries `side-left` | `side-right` (single) and boards with a key in `fadedKeys` carry class `faded`.

- [ ] **Step 1: Failing tests.**

`signpostHtml.test.ts` — add:

```ts
it('singleHtml and stackHtml plant a mast and foot dot before the board', () => {
  for (const html of [singleHtml(bt(1)), stackHtml([bt(1), bt(2)])]) {
    const d = doc(html)
    expect(d.querySelector('.mast')).not.toBeNull()
    expect(d.querySelector('.foot')).not.toBeNull()
    expect(d.querySelector('.mast')!.getAttribute('data-tour-key')).toBeNull()
  }
})
```

`SignpostMarker.test.tsx` (read the existing file for its render helper first; follow its setup). Add tests:

```ts
it('puts a single board on its heading side of the mast', () => {
  vi.spyOn(L.Map.prototype, 'getSize').mockReturnValue(L.point(1000, 600))
  vi.spyOn(L.Map.prototype, 'latLngToContainerPoint').mockReturnValue(L.point(500, 300))
  const east = renderMarker({ kind: 'single', heading: 'east' })
  expect(markerEl(east).classList.contains('side-right')).toBe(true)
  const west = renderMarker({ kind: 'single', heading: 'west' })
  expect(markerEl(west).classList.contains('side-left')).toBe(true)
})

it('flips a board that would leave the viewport, keeping the arrow direction', () => {
  vi.spyOn(L.Map.prototype, 'getSize').mockReturnValue(L.point(1000, 600))
  vi.spyOn(L.Map.prototype, 'latLngToContainerPoint').mockReturnValue(L.point(950, 300))
  const east = renderMarker({ kind: 'single', heading: 'east' })
  expect(markerEl(east).classList.contains('side-left')).toBe(true)
  expect(east.container.querySelector('.sign')!.classList.contains('heads-west')).toBe(false)
})

it('fades boards of the given tour keys and leaves the others opaque', () => {
  const r = renderMarker({ kind: 'stack', fadedKeys: new Set(['k1']) })
  expect(r.container.querySelector('[data-tour-key="k1"]')!.classList.contains('faded')).toBe(true)
  expect(r.container.querySelector('[data-tour-key="k2"]')!.classList.contains('faded')).toBe(false)
})
```

Adapt `renderMarker`/`markerEl` to the file's existing helpers (they render `SignpostMarker` inside a `MapContainer`; add defaults `heading='east'`, `fadedKeys=new Set()`); the stack html for the fade test is `stackHtml([bt(1), bt(2)])` with keys `k1`, `k2`.

- [ ] **Step 2: Run** `npx vitest run src/features/map/signpostHtml.test.ts src/features/map/SignpostMarker.test.tsx` → new tests FAIL.
- [ ] **Step 3: Implement.**

`signpostHtml.ts`: add

```ts
/** The mast and the foot dot on the anchor; both ignore the pointer so the route line under them stays hoverable. */
const MAST = '<span class="mast"></span><span class="foot"></span>'
```

`singleHtml` returns `` `${MAST}<div class="sign${heading === 'west' ? ' heads-west' : ''}" …>${boardBody(tour)}</div>` `` and `stackHtml` returns `` `${MAST}<div class="sign stack-sign" …` ``. Update both doc comments: the board hangs by its tail from the mast top; the arrow points in `heading` (`east`: arrow on the right).

`SignpostMarker.tsx`: add props `heading?: Heading` (default `'east'`), `fadedKeys: ReadonlySet<string>`; import `Heading` from `./signpostHtml.js`. Add the effects:

```ts
/** Widest a board can be (matches `max-width` in map.css); the side flips when it would cross the viewport edge. */
const BOARD_MAX_WIDTH = 220

useEffect(() => {
  const marker = markerRef.current
  const el = marker?.getElement()
  if (!marker || !el || kind !== 'single') return
  const place = () => {
    const x = map.latLngToContainerPoint(marker.getLatLng()).x
    const preferred = heading === 'west' ? 'left' : 'right'
    const fits = preferred === 'right' ? x + BOARD_MAX_WIDTH <= map.getSize().x : x - BOARD_MAX_WIDTH >= 0
    const side = fits ? preferred : preferred === 'right' ? 'left' : 'right'
    el.classList.toggle('side-left', side === 'left')
    el.classList.toggle('side-right', side === 'right')
  }
  place()
  map.on('moveend zoomend', place)
  return () => { map.off('moveend zoomend', place) }
}, [icon, kind, heading, map])

useEffect(() => {
  markerRef.current?.getElement()?.querySelectorAll<HTMLElement>('[data-tour-key]')
    .forEach((board) => board.classList.toggle('faded', fadedKeys.has(board.dataset.tourKey!)))
}, [icon, fadedKeys])
```

`map.css` (edit the existing signpost block; keep everything not named here):

```css
.signpost-marker {
  --board-h: 26px;
  --board-pitch: 30px;
  --mast-h: 24px;
}
/* Mast and foot: the foot dot sits on the anchor (the marker origin), the mast rises from it. */
.signpost-marker .mast {
  position: absolute; left: -0.75px; top: calc(var(--mast-h) * -1);
  width: 1.5px; height: var(--mast-h); background: var(--color-ink); pointer-events: none;
}
.signpost-marker .foot {
  position: absolute; left: -2.5px; top: -2.5px; width: 5px; height: 5px;
  border-radius: 50%; background: var(--color-ink); pointer-events: none;
}
```

Change the `top` of `.sign` positioning to hang from the mast top: in the shared `.sign, .board` rule add `top: calc(var(--board-h) / -2 - var(--mast-h));` and replace the three existing `top: calc(var(--board-h) / -2)` occurrences (`.stack-sign`, `.board`) with the same expression. Replace the single-tour rules with:

```css
/* Single: the board hangs from the mast top by its tail. Arrow direction is the heading (`.heads-west` = arrow on the left);
   the side of the mast is `side-right`/`side-left`, set by SignpostMarker so a board never leaves the viewport. */
.signpost-marker.single .sign { left: 0; }
.signpost-marker.single.side-left .sign { transform: translateX(-100%); }
.signpost-marker.single .sign.heads-west { padding: 0 8px 0 16px; }
.signpost-marker.single .sign.heads-west,
.signpost-marker.single .sign.heads-west::before { clip-path: polygon(10px 0, 100% 0, 100% 100%, 10px 100%, 0 50%); }
```

Shift the spread backdrop up by the mast: `top: calc(var(--board-pitch) * -9 - var(--mast-h) - 10px);`. Extend the dim rule: `.signpost-marker.dimmed .sign, .signpost-marker.dimmed .mast, .signpost-marker.dimmed .foot { opacity: 0.45; }` and add

```css
/* A tour hovered from its route line or the list: its board steps back so the highlighted line reads clearly. */
.signpost-marker .faded { opacity: 0.35; }
```

- [ ] **Step 4: Run** the two test files and `npx vitest run src/features/map` → PASS (fix any test that asserted the old start-point anchoring of singles).
- [ ] **Step 5: Commit** `feat(map): signpost board on a mast`

---

### Task 12: DiscoverLayer stands boards on their routes

**Files:**
- Modify: `huts/src/features/map/DiscoverLayer.tsx`, `clusterStarts.ts` (drop `markerKind`), `clusterStarts.test.ts` (drop its `markerKind` describe if still present)
- Test: `huts/src/features/map/DiscoverLayer.test.tsx`

**Interfaces:**
- Consumes: `tourAnchorOf` (Task 9), `createAnchorClusterer`, `anchorMarkerKind`, `AnchorMarker` (Task 10), `SignpostMarker` props (Task 11).
- Behaviour after this task: below `ROUTE_REVEAL_ZOOM` only the start-point count bubbles render (unchanged); from `ROUTE_REVEAL_ZOOM` on only anchor signposts render (no start clusters, no start signposts).

- [ ] **Step 1: Failing tests** (`DiscoverLayer.test.tsx`). Import `* as routes from './routes.js'`. Add:

```ts
describe('DiscoverLayer signposts on the route', () => {
  const signposts = (c: HTMLElement) => c.querySelectorAll('.signpost-marker')

  it('draws no signposts below the reveal zoom, only count bubbles', () => {
    const t = tour(1, [10, 11])
    const { container } = renderLayer({ ...focusOn(t), groups: [{ startId: 1, tours: [t] }] }, 9)
    expect(signposts(container)).toHaveLength(0)
    expect(container.querySelectorAll('.start-count-marker')).toHaveLength(1)
  })

  it('stands a tour\'s board on its anchor, not on its start point', async () => {
    vi.spyOn(routes, 'tourAnchorOf').mockReturnValue({ lat: 47.305, lng: 12.005, heading: 'east' })
    const t = tour(1, [10, 11])
    const { container } = renderLayer({ ...focusOn(t), groups: [{ startId: 1, tours: [t] }] }, 13)
    await waitFor(() => expect(signposts(container)).toHaveLength(1))
    const el = container.querySelector<HTMLElement>('.signpost-marker')!
    const expected = map.latLngToLayerPoint(L.latLng(47.305, 12.005))
    expect(L.DomUtil.getPosition(el).x).toBeCloseTo(expected.x, 0)
    expect(L.DomUtil.getPosition(el).y).toBeCloseTo(expected.y, 0)
    expect(container.querySelector('.start-count-marker')).toBeNull()
  })

  it('draws no signpost for a tour with no anchor in view', () => {
    vi.spyOn(routes, 'tourAnchorOf').mockReturnValue(null)
    const t = tour(1, [10, 11])
    const { container } = renderLayer({ ...focusOn(t), groups: [{ startId: 1, tours: [t] }] }, 13)
    expect(signposts(container)).toHaveLength(0)
  })

  it('stacks tours whose anchors coincide into one signpost with a count', async () => {
    vi.spyOn(routes, 'tourAnchorOf').mockReturnValue({ lat: 47.305, lng: 12.005, heading: 'east' })
    const a = tour(1, [10, 11])
    const b = tour(1, [10, 11, 12])
    const { container } = renderLayer({ ...focusOn(a, b), groups: [{ startId: 1, tours: [a, b] }] }, 13)
    await waitFor(() => expect(container.querySelectorAll('.signpost-marker.stack')).toHaveLength(1))
    expect(container.querySelector('.stack-sign')!.textContent).toBe('2')
  })

  it('fades a board while its tour is hovered from elsewhere, not while the board itself is hovered', async () => {
    vi.spyOn(routes, 'tourAnchorOf').mockReturnValue({ lat: 47.305, lng: 12.005, heading: 'east' })
    const t = tour(1, [10, 11])
    const { container, rerender } = renderLayer({ ...focusOn(t), groups: [{ startId: 1, tours: [t] }], hoveredTourKeys: new Set([tourKey(t)]) }, 13)
    await waitFor(() => expect(container.querySelector('.sign.faded')).not.toBeNull())
    fireEvent.mouseOver(container.querySelector('.sign')!)
    await waitFor(() => expect(container.querySelector('.sign.faded')).toBeNull())
    void rerender
  })
})
```

(`renderLayer` returns RTL's render result; if it does not expose `rerender`, drop that variable. `groups` items follow `StartGroup<PlannerTour>` — match its real shape from `tourSearch/groupByStart.ts`.) Also add to every `routeCtx`/`routeCtxMany` literal in this file `legAnchors: () => null`.

- [ ] **Step 2: Run** `npx vitest run src/features/map/DiscoverLayer.test.tsx` → new tests FAIL; note which pre-existing tests fail after Step 3 and adjust in Step 4.
- [ ] **Step 3: Implement** in `DiscoverLayer.tsx`:

1. Imports: replace `markerKind` with `createAnchorClusterer, anchorMarkerKind` and `AnchorMarker`; add `tourAnchorOf` to the `./routes.js` import; delete `headingOf` and the `Heading` import if unused; import `type { TourAnchor } from '@/tourSearch/tourAnchor.js'`.
2. Keep `clusterer`, `groupOfStart`, `keysOfStarts`, `markers`, `startIdsOf`, `markerKey`, `highlightedStarts`, and the bubble `Marker` branch, but render bubbles only when `!routeReveal` (a cluster or start marker never renders from the reveal zoom on). Delete `htmlByMarker`.
3. After `routedTours`, add:

```tsx
  const anchoredTours = useMemo(() => routedTours.flatMap(({ key, tour, route }) => {
    const anchor = routeCtx ? tourAnchorOf(tour, route, routeCtx, view.bbox) : null
    return anchor ? [{ key, tour, anchor }] : []
  }), [routedTours, routeCtx, view.bbox])
  const anchorByKey = useMemo(() => new Map<string, TourAnchor>(anchoredTours.map((t) => [t.key, t.anchor])), [anchoredTours])
  const anchorClusterer = useMemo(
    () => createAnchorClusterer(anchoredTours.map(({ key, anchor }) => ({ tourKey: key, lat: anchor.lat, lng: anchor.lng }))),
    [anchoredTours],
  )
  const signposts = useMemo(() => (routeReveal ? anchorClusterer.markersFor(view.bbox, view.zoom) : []), [anchorClusterer, routeReveal, view])
  const boardsOf = (m: AnchorMarker) => m.tourKeys.flatMap((k) => {
    const t = tourByKey.get(k)
    return t ? [{ key: k, label: tourBoardLabel(t, startById) }] : []
  })
  const htmlOfSignpost = (m: AnchorMarker) => {
    const boards = boardsOf(m)
    return anchorMarkerKind(m) === 'single' && boards[0]
      ? singleHtml(boards[0], anchorByKey.get(m.tourKeys[0])?.heading ?? 'east')
      : stackHtml(boards)
  }
  /** The pointer is on a signpost: its own board keeps full opacity. */
  const [pointerOnSignpost, setPointerOnSignpost] = useState(false)
```

`routedTours` is built from `allTours`, so `createAnchorClusterer`'s input is in the list's rank order.

4. Replace the signpost branch of the `markers.map` render: the existing `markers.map` renders bubbles only, wrapped in `!routeReveal &&`; add below it:

```tsx
      {signposts.map((m) => {
        const outsideFocus = focusTours != null && !m.tourKeys.some((k) => focusTours.has(k))
        const highlighted = m.tourKeys.some((k) => hoveredTourKeys.has(k))
        const startHovered = m.tourKeys.some((k) => hoveredStartIds?.has(tourByKey.get(k)?.startId ?? -1))
        const dimmedMarker = dimmed || outsideFocus || (hoverActive && !(highlighted || startHovered))
        return (
          <SignpostMarker
            key={m.id} position={[m.lat, m.lng]} kind={anchorMarkerKind(m)} html={htmlOfSignpost(m)}
            heading={anchorByKey.get(m.tourKeys[0])?.heading ?? 'east'}
            dimmed={dimmedMarker} highlighted={highlighted || startHovered}
            fadedKeys={pointerOnSignpost ? NO_TOURS : hoveredTourKeys}
            onHoverMarker={(hovering) => { setPointerOnSignpost(hovering); onHoverTours(hovering ? new Set(m.tourKeys) : NO_TOURS) }}
            onHoverTour={(key) => onHoverTours(key ? new Set([key]) : NO_TOURS)}
            onActivate={(a) => activateSignpost(m, a)}
          />
        )
      })}
```

5. Add the activation and simplify the bubble `activate`:

```tsx
  const activateSignpost = (m: AnchorMarker, a: Activation) => {
    onNavigate?.()
    const only = a.kind === 'tour' ? tourByKey.get(a.tourKey) : m.tourKeys.length === 1 ? tourByKey.get(m.tourKeys[0]) : undefined
    if (only) { onPickRoute(only); return }
    onFocusTours?.(m.tourKeys)
    const bounds = boundsOfTours(m.tourKeys.flatMap((k) => tourByKey.get(k) ?? []))
    if (bounds) zoomToBounds(bounds)
  }
```

In the bubble `activate`, drop the `a.kind === 'tour'` and `only` branches (bubbles only carry `{ kind: 'body' }`); its signature becomes `activate(m: MapMarker)`.
6. Delete `markerKind` from `clusterStarts.ts` and its `describe('markerKind')` block if Task 10 left it; update the component's doc comment: from `ROUTE_REVEAL_ZOOM` on each tour's board stands on its route's mid-route anchor, grouped by anchor.

- [ ] **Step 4: Run** `npx vitest run src/features/map` and fix pre-existing tests that assumed start-point signposts: their expectations move to anchor-based signposts (tests with `groups={[]}` now draw signposts from `allTours`, so assertions such as "no marker" must use a zoom below the reveal or a tour with no anchor in view). Do not delete an assertion without replacing it by the anchor-based equivalent. Then `npm test && npm run typecheck && npm run lint` → PASS.
- [ ] **Step 5: Commit** `feat(map): stand each tour's signpost on its route`

---

### Task 13: Docs

**Files:** `docs/tour-suggestion-payload.md`, `CLAUDE.md` (root), `pipeline/phases/postprocessing/README.md`

- [ ] **Step 1:** `docs/tour-suggestion-payload.md`:
  - §1 table: add a row `a25_dlat`, `a25_dlng`, `a50_dlat`, `a50_dlng`, `a75_dlat`, `a75_dlng` | i2 | "anchor at 25 / 50 / 75 % of the edge's full-resolution arc length, stored direction, as an offset from the `from_id` hut's coordinate in `huts.geojson` in units of 1e-4° (≈ 11 m N–S, ≈ 7.6 m E–W at 47° N). Pipeline asserts no overflow; `check_postprocessing` asserts sampled anchors lie within 25 m of the polyline". Note that the reference is arithmetic only (the geometry's endpoints may differ from the hut by `snap_m`).
  - §3 Direction: add "a leg walked reversed swaps the 25 % and 75 % anchors; 50 % stays."
  - §6 `approaches` table: same six columns, referenced to the row's hut (`hut_id`); note that reverse-index rows (exit legs that are not approach rows) carry no anchors and the client falls back to the chord point.
  - Add a "tours.json" note: each leg has `anchors: [[lat, lng] × 3]` in walking order from the raw GPX.
  - Record the measured gzipped growth (from Task 14) and which fractions ship.
- [ ] **Step 2:** root `CLAUDE.md`: in "App structure" replace the sentence describing Discover signpost markers with: signposts are boards on masts standing on each tour's anchor (`tourSearch/tourAnchor.ts`: the candidate nearest half the tour's distance, viewport-clipped), grouped by `createAnchorClusterer`, count bubbles below `ROUTE_REVEAL_ZOOM`; add `anchors.ts`, `legAnchors.ts`, `tourAnchor.ts` to the `tourSearch/` inventory; mention the anchor columns in the "Hut-to-hut routing graph" payload sentence.
- [ ] **Step 3:** `pipeline/phases/postprocessing/README.md`: one paragraph on the anchor columns of `build_edge_payload` and `build_approach_table` and their new inputs (`geometry.npy`, `huts.geojson`).
- [ ] **Step 4: Commit** `docs: describe anchor columns and anchored signposts`

---

### Task 14: Rebuild the data, measure, verify

Requires the user's go-ahead for every pipeline command (root `CLAUDE.md`).

- [ ] **Step 1: Ask the user** for permission to run exactly these tasks (none is multi-hour): `build_edge_payload`, `build_approach_table`, `match_tour_edges`, `build_tour_edge_tiles`, `check_postprocessing`, `copy_public_data`. Also ask them to confirm that no stale dependency will trigger `hub_snap`/`build_base_graph`; if a dry `doit list --status` (also ask first) shows those stale, stop and report instead of running.
- [ ] **Step 2:** Run the approved tasks. Read the printed `anchor growth: … B gzipped` lines for both payloads.
- [ ] **Step 3: Size gate.** If the summed gzipped growth exceeds 60 KB, set `ANCHOR_FRACTIONS = (0.5,)` in `pipeline/lib/anchors.py`, adjust the anchor tests to the single fraction (`anchor_column_names()`, quarter positions), re-ask, re-run the tasks; the client already handles a lone `a50_*` pair (`anchorFractions(1)`). Record the outcome in `docs/tour-suggestion-payload.md` §1.
- [ ] **Step 4:** `data/quality/postprocessing.json` must show `anchors_on_path_*` checks with 0 flagged rows; if not, stop and investigate at the pipeline layer (do not widen the tolerance without asking).
- [ ] **Step 5: Full verification** — `cd pipeline && pixi run pytest -q`; `cd huts && npm test && npm run typecheck && npm run lint`. Report any failure with its output; do not claim success without these results.
- [ ] **Step 6:** Do **not** start a dev server or browser unless the user asks (memory: no unrequested visual confirmation).
- [ ] **Step 7:** Flip the spec's row in `docs/superpowers/STATUS.md` to `done`, delete this plan file, commit `docs: mark signpost route anchors done`.
