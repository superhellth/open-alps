# Contraction Measurement Spike Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure *why* `build_base_graph.py`'s `contract_structural` phase takes 3963s, so the
tiled-contraction spec is accepted or rejected on evidence instead of on the raw wall-clock number.

**Architecture:** Make `build_base_graph.py` importable, apply the strictly-free memory and
vectorization wins, add an RSS sampler, then build a standalone `analysis/` harness that
*reconstructs the real raw (pre-contraction) graph by un-contracting the already-persisted
`base_graph/`* — no re-streaming of `trails.osm.pbf` needed. That harness can emit any-size
faithful subsets, which drives a scaling sweep (is cost per raw edge flat or exploding?) and a
`cProfile` hot-spot run. A findings doc turns those two numbers into an accept/reject decision on
`docs/superpowers/specs/2026-08-20-tiled-contraction-design.md`.

**Tech Stack:** Python 3, numpy, psutil 5.9.1 (already in the `alpen-osm` env), pytest, cProfile.

**Spec:** `docs/superpowers/specs/2026-08-20-tiled-contraction-design.md` — this plan does **not**
implement that spec. It produces the measurement that decides whether that spec gets implemented
at all. Read it for context on what the numbers are for.

## Global Constraints

- **Never run any `pipeline/` doit task without explicit user confirmation** (`pipeline/CLAUDE.md`).
  This plan adds only `pipeline/analysis/` scripts, which are outside the doit DAG — but Task 7's
  sweep is still a ~45-90 minute run and **must be handed to the user to start**, not launched by
  an agent.
- Conda env: `alpen-osm`. Tests run with `pytest pipeline/tests/`.
- Config values are read from `pipeline/pipeline.config.json` — never hardcode `tileSizeKm`,
  `bbox`, `roadPenaltyFactor`, `roadHighwayTags`.
- `pipeline/analysis/` scripts are standalone, read-only, never part of `dodo.py`, and call the
  real phase functions rather than reimplementing them (`pipeline/CLAUDE.md`).
- Every long-running loop prints progress with `flush=True` (`pipeline/CLAUDE.md`, "Progress
  logging").
- Existing behaviour of `build_base_graph.py`'s output must not change in Tasks 1-3. Those tasks
  are refactor + strictly-equivalent optimization only.

## Measured facts this plan starts from (already verified, do not re-derive)

| Fact | Value | Source |
|---|---|---|
| `stream_osm` | 914s | `data/timings.jsonl` |
| `contract_structural` | 3963s | `data/timings.jsonl` |
| contracted nodes | 6,853,136 | `nodes.npy` len |
| chain edges | 8,341,484 | `edges.npy` len |
| interior points | 33,081,647 | `interior.npy` len |
| ⇒ raw nodes / raw edges | ~39.93M / ~41.42M | sums of the above |
| cost per raw edge | ~96 µs | 3963s / 41.42M |
| **box physical RAM** | **17.1 GB** | `psutil.virtual_memory()` |
| **box swap** | **20.1 GB** | `psutil.swap_memory()` |
| physical / logical cores | 6 / 12 | `psutil.cpu_count()` |
| grid cells at `tileSizeKm: 60` | 88 (11 × 8) | `cell_index.npy` len |
| `interior_offset` monotone in edge order | True | verified |
| partially-road chain edges (`0 < road_m < dist`) | 162,169 | verified |

**The hypothesis under test:** ~96 µs per raw edge is roughly 30× more than the walk body's Python
work should cost. `build_base_graph.py:126` frees `handler` *after* the contraction block, so
during all 3963s the raw Python lists (`handler.coords` ≈ 4.8 GB of 40M 2-tuples,
`edges_i`/`edges_j` ≈ 3 GB, `edges_dist`/`edges_w` ≈ 3.3 GB) stay live *alongside* the numpy copies
made at lines 116-123, plus contraction's own ~1.4 GB CSR arrays and a `c_interior` list growing to
33M tuples (~4 GB). That is ~15-20 GB live on a **17.1 GB** box with 20.1 GB of swap behind it.

The two possible outcomes and what each means:

- **Memory-bound** (peak RSS at/over physical RAM, swap-in > 0, cost-per-edge rising with size):
  the tiled spec is attacking the wrong bottleneck and makes per-worker memory pressure worse.
  Fix memory, re-measure, likely reject the spec.
- **CPU-bound** (flat cost per edge, RSS comfortably under RAM): tiling is justified — but its
  ceiling is **6 physical cores**, so best case is ~3963/6 ≈ 660s *before* the spec's phase-1
  overhead, not "66 min ÷ 88 cells".

---

### Task 1: Make `build_base_graph.py` importable

Today the script is straight-line module-level code: `argparse` at line 30-34 and the whole
pipeline at lines 108-195 run on import. Nothing can call its pieces. `pipeline/analysis/`'s
convention (see `snap_stats.py`'s header comment) is to import and call the *real* phase functions,
so the phases must be functions first. Pure refactor — byte-identical output.

**Files:**
- Modify: `pipeline/phases/graph_building/build_base_graph.py:30-34,108-195`
- Test: `pipeline/tests/test_build_base_graph.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces, all importable from `build_base_graph`:
  - `stream_osm(trails_path: str, config: dict) -> WayGraphHandler`
  - `contract(handler: WayGraphHandler, progress_every: int = 20_000) -> ContractedGraph`
    — **note:** Task 7 Step 2 changes this signature to take the eight already-converted numpy
    arrays instead of the handler, so `main` can free the handler's raw Python lists first. Task 1
    keeps the handler form so the refactor stays behaviour-identical.
  - `pack_and_write(contracted: ContractedGraph, bbox: dict, tile_size_km: float, out_dir: Path) -> None`
  - `main(argv: list[str] | None = None) -> None`
  - `WayGraphHandler`, `haversine_m_vec`, `SAC_SCALE_RANK` (unchanged, already module-level)

- [ ] **Step 1: Write the failing test**

Create `pipeline/tests/test_build_base_graph.py`:

```python
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases" / "graph_building"))

import build_base_graph as bbg  # noqa: E402
from lib import binfmt  # noqa: E402
from lib.contraction import ContractedGraph  # noqa: E402


def test_module_exposes_callable_phases_without_running_them():
    # Importing must not parse argv or touch the filesystem - the module is imported by
    # pipeline/analysis/ harnesses that pass their own arguments.
    for name in ("stream_osm", "contract", "pack_and_write", "main"):
        assert callable(getattr(bbg, name)), f"{name} missing or not callable"


def _tiny_contracted():
    # Two chain edges sharing node 1: 0 --(one interior pt)-- 1 --(no interior)-- 2
    return ContractedGraph(
        coords=np.array([(11.0, 47.0), (11.1, 47.1), (11.2, 47.2)]),
        edges_u=np.array([0, 1], dtype=np.int64),
        edges_v=np.array([1, 2], dtype=np.int64),
        edges_dist=np.array([100.0, 200.0]),
        edges_weight=np.array([130.0, 200.0]),
        edges_road_m=np.array([100.0, 0.0]),
        edges_sac_rank=np.array([2, -1], dtype=np.int8),
        edges_via_ferrata=np.array([False, True]),
        interior_coords=[[(11.05, 47.05)], []],
    )


def test_pack_and_write_emits_the_seven_base_graph_files(tmp_path):
    bbox = {"minLng": 8.9, "maxLng": 17.2, "minLat": 46.3, "maxLat": 50.6}
    bbg.pack_and_write(_tiny_contracted(), bbox, 60.0, tmp_path)

    for fname in ("nodes.npy", "cell_index.npy", "node_edge_index.npy", "node_edge_ids.npy",
                  "edges.npy", "interior.npy", "manifest.json"):
        assert (tmp_path / fname).exists(), f"{fname} not written"

    nodes = binfmt.load_array(tmp_path / "nodes.npy")
    edges = binfmt.load_array(tmp_path / "edges.npy")
    interior = binfmt.load_array(tmp_path / "interior.npy")
    assert len(nodes) == 3
    assert len(edges) == 2
    assert len(interior) == 1
    # nodes are re-sorted by cell_id, so edge endpoints must be remapped, not raw indices
    assert set(edges["u"].tolist()) | set(edges["v"].tolist()) == {0, 1, 2}
    assert sorted(edges["dist"].tolist()) == [100.0, 200.0]
    assert interior["lon"][0] == pytest.approx(11.05)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest pipeline/tests/test_build_base_graph.py -v`
Expected: collection error or FAIL — importing `build_base_graph` today executes `argparse` against
pytest's argv and then runs the whole pipeline (`streaming data/osm/trails.osm.pbf ...`).

- [ ] **Step 3: Refactor the script into functions**

Replace `build_base_graph.py` lines 30-34 (module-level argparse) and lines 108-195 (module-level
pipeline) with functions. Keep `config = load_config()` at module level (cheap JSON read, matches
`build_hub_edges.py`'s shape). Keep `WayGraphHandler`, `haversine_m_vec`, `SAC_SCALE_RANK` exactly
as they are.

Delete lines 30-34 and replace lines 108-195 with:

```python
def stream_osm(trails_path, config):
    print(f"streaming {trails_path} ...", flush=True)
    handler = WayGraphHandler(
        config["graph"]["roadHighwayTags"], config["graph"]["roadPenaltyFactor"]
    )
    with phase(SCRIPT_NAME, "stream_osm"):
        handler.apply_file(trails_path, locations=True)
    print(f"raw graph nodes: {len(handler.coords):,}, edges: {len(handler.edges_i):,}", flush=True)
    return handler


def contract(handler, progress_every: int = 20_000):
    with phase(SCRIPT_NAME, "contract_structural"):
        contracted = contract_structural(
            np.array(handler.coords, dtype=np.float64),
            np.array(handler.edges_i, dtype=np.int64),
            np.array(handler.edges_j, dtype=np.int64),
            np.array(handler.edges_dist, dtype=np.float64),
            np.array(handler.edges_w, dtype=np.float64),
            np.array(handler.edges_road, dtype=bool),
            np.array(handler.edges_sac_rank, dtype=np.int8),
            np.array(handler.edges_via_ferrata, dtype=bool),
            progress_every=progress_every,
        )
    print(f"contracted to {len(contracted.coords):,} nodes / "
          f"{len(contracted.edges_u):,} edges", flush=True)
    return contracted


def pack_and_write(contracted, bbox, tile_size_km, out_dir):
    # --- assign cell ids, re-sort nodes by cell so cell_index.npy addresses a contiguous slice ---
    grid = Grid(bbox, tile_size_km)
    cell_ids = np.array(
        [grid.cell_id_for_point(lon, lat) for lon, lat in contracted.coords], dtype=np.int32
    )
    sort_order, cell_index = binfmt.build_csr_index(cell_ids, n_groups=len(grid.all_cell_ids()))

    old_to_new = np.empty(len(contracted.coords), dtype=np.int64)
    old_to_new[sort_order] = np.arange(len(sort_order))

    nodes_arr = np.zeros(len(contracted.coords), dtype=binfmt.NODE_DTYPE)
    nodes_arr["lon"] = contracted.coords[sort_order, 0]
    nodes_arr["lat"] = contracted.coords[sort_order, 1]
    nodes_arr["cell_id"] = cell_ids[sort_order]

    # --- remap edge endpoints through the node reorder, pack interior polylines ---
    n_edges = len(contracted.edges_u)
    interior_offsets = np.zeros(n_edges, dtype=np.int64)
    interior_counts = np.zeros(n_edges, dtype=np.int32)
    flat_interior = []
    cursor = 0
    for i, pts in enumerate(contracted.interior_coords):
        interior_offsets[i] = cursor
        interior_counts[i] = len(pts)
        flat_interior.extend(pts)
        cursor += len(pts)

    interior_arr = np.zeros(len(flat_interior), dtype=binfmt.COORD_DTYPE)
    if flat_interior:
        interior_arr["lon"] = [p[0] for p in flat_interior]
        interior_arr["lat"] = [p[1] for p in flat_interior]

    edges_arr = np.zeros(n_edges, dtype=binfmt.EDGE_DTYPE)
    edges_arr["u"] = old_to_new[contracted.edges_u]
    edges_arr["v"] = old_to_new[contracted.edges_v]
    edges_arr["dist"] = contracted.edges_dist
    edges_arr["weight"] = contracted.edges_weight
    edges_arr["road_m"] = contracted.edges_road_m
    edges_arr["sac_rank"] = contracted.edges_sac_rank
    edges_arr["via_ferrata"] = contracted.edges_via_ferrata
    edges_arr["interior_offset"] = interior_offsets
    edges_arr["interior_count"] = interior_counts
    edges_arr["edge_id"] = np.arange(n_edges, dtype=np.int64)  # stable: row position == edge_id

    # --- node -> incident edge ids CSR (built on FINAL node ids, after the cell-sort remap) ---
    doubled_nodes = np.concatenate([edges_arr["u"], edges_arr["v"]])
    doubled_edge_ids = np.concatenate([edges_arr["edge_id"], edges_arr["edge_id"]])
    ne_order, node_edge_index = binfmt.build_csr_index(doubled_nodes, n_groups=len(nodes_arr))
    node_edge_ids = doubled_edge_ids[ne_order]

    out_dir = Path(out_dir)
    binfmt.save_array(out_dir / "nodes.npy", nodes_arr)
    binfmt.save_array(out_dir / "cell_index.npy", cell_index)
    binfmt.save_array(out_dir / "node_edge_index.npy", node_edge_index)
    binfmt.save_array(out_dir / "node_edge_ids.npy", node_edge_ids)
    binfmt.save_array(out_dir / "edges.npy", edges_arr)
    binfmt.save_array(out_dir / "interior.npy", interior_arr)
    binfmt.save_manifest(out_dir / "manifest.json", {
        "bbox": bbox,
        "tile_size_km": tile_size_km,
        "n_cols": grid.n_cols,
        "n_rows": grid.n_rows,
        "n_nodes": len(nodes_arr),
        "n_edges": n_edges,
    })
    print(f"written {out_dir}", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--trails", default=str(OSM_DIR / "trails.osm.pbf"))
    parser.add_argument("--out-dir", default=str(OSM_DIR / "base_graph"))
    parser.add_argument("--tile-size-km", type=float, default=config["graph"]["tileSizeKm"])
    args = parser.parse_args(argv)

    handler = stream_osm(args.trails, config)
    contracted = contract(handler)
    del handler
    pack_and_write(contracted, config["bbox"], args.tile_size_km, args.out_dir)


if __name__ == "__main__":
    main()
```

Note the `del handler` moved from old line 126 into `main` — it is still *after* `contract`
returns at this point. Task 2 moves it earlier; keeping it here first isolates the refactor from
the behaviour change.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest pipeline/tests/test_build_base_graph.py pipeline/tests/test_contraction.py -v`
Expected: PASS (all 3 new tests, plus `test_contraction.py` unaffected).

- [ ] **Step 5: Commit**

```bash
git add pipeline/phases/graph_building/build_base_graph.py pipeline/tests/test_build_base_graph.py
git commit -m "refactor(pipeline): make build_base_graph.py importable

Extract stream_osm/contract/pack_and_write/main from module-level code so
pipeline/analysis/ harnesses can call the real phases instead of reimplementing
them. No behaviour change."
```

---

### Task 2: Vectorize cell-id assignment

`pack_and_write` assigns cell ids with a Python list comprehension calling
`Grid.cell_id_for_point` once per node. That is 6.85M calls today, and the tiled spec's phase 1
would run it over **40M** raw nodes. Vectorize it on `Grid` so both callers benefit, and so the
spike's own harness (Task 4) can assign cells to 40M nodes without a Python loop.

`Grid.col_row_for_point` truncates with `int()` and then clamps to `[0, n-1]`. `np.floor` differs
from `int()` only for negative values, and every negative value is clamped to 0 by both paths —
so `floor` + `clip` is exactly equivalent. The test proves that rather than assuming it.

**Files:**
- Modify: `pipeline/lib/grid.py` (add method after `cell_id_for_point`, line 31)
- Modify: `pipeline/phases/graph_building/build_base_graph.py` (in `pack_and_write`, the `cell_ids` line)
- Test: `pipeline/tests/test_grid.py` (append)

**Interfaces:**
- Consumes: Task 1's `pack_and_write`.
- Produces: `Grid.cell_ids_for_points(lons: np.ndarray, lats: np.ndarray) -> np.ndarray[int32]`

- [ ] **Step 1: Write the failing test**

Append to `pipeline/tests/test_grid.py`:

```python
import numpy as np


def test_cell_ids_for_points_matches_scalar_version_including_out_of_bbox():
    bbox = {"minLng": 8.9, "maxLng": 17.2, "minLat": 46.3, "maxLat": 50.6}
    grid = Grid(bbox, 60.0)

    rng = np.random.default_rng(0)
    # deliberately overshoot the bbox on both sides: Grid clamps, and the vectorized path
    # must clamp identically (np.floor vs int() disagree on negatives before clamping)
    lons = rng.uniform(bbox["minLng"] - 2.0, bbox["maxLng"] + 2.0, 5000)
    lats = rng.uniform(bbox["minLat"] - 2.0, bbox["maxLat"] + 2.0, 5000)

    expected = np.array([grid.cell_id_for_point(lo, la) for lo, la in zip(lons, lats)],
                        dtype=np.int32)
    assert np.array_equal(grid.cell_ids_for_points(lons, lats), expected)


def test_cell_ids_for_points_returns_int32_and_handles_empty():
    grid = Grid({"minLng": 8.9, "maxLng": 17.2, "minLat": 46.3, "maxLat": 50.6}, 60.0)
    out = grid.cell_ids_for_points(np.zeros(0), np.zeros(0))
    assert out.dtype == np.int32
    assert len(out) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest pipeline/tests/test_grid.py -v`
Expected: FAIL with `AttributeError: 'Grid' object has no attribute 'cell_ids_for_points'`

- [ ] **Step 3: Implement**

Add to `pipeline/lib/grid.py` after `cell_id_for_point` (line 31), plus `import numpy as np` at
the top:

```python
    def cell_ids_for_points(self, lons, lats):
        """Vectorized cell_id_for_point over whole arrays - the per-point Python call was the
        cost driver when build_base_graph.py assigned cells to millions of nodes one at a time.
        np.floor and int() differ only on negative values, all of which both paths clamp to 0,
        so this is exactly equivalent to looping cell_id_for_point (test_grid.py proves it)."""
        lons = np.asarray(lons, dtype=np.float64)
        lats = np.asarray(lats, dtype=np.float64)
        col = np.floor((lons - self.bbox["minLng"]) * self.km_per_deg_lng / self.tile_size_km)
        row = np.floor((lats - self.bbox["minLat"]) * KM_PER_DEG_LAT / self.tile_size_km)
        col = np.clip(col, 0, self.n_cols - 1).astype(np.int64)
        row = np.clip(row, 0, self.n_rows - 1).astype(np.int64)
        return (row * self.n_cols + col).astype(np.int32)
```

Then in `build_base_graph.py`'s `pack_and_write`, replace:

```python
    cell_ids = np.array(
        [grid.cell_id_for_point(lon, lat) for lon, lat in contracted.coords], dtype=np.int32
    )
```

with:

```python
    cell_ids = grid.cell_ids_for_points(contracted.coords[:, 0], contracted.coords[:, 1])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest pipeline/tests/test_grid.py pipeline/tests/test_build_base_graph.py -v`
Expected: PASS. `test_pack_and_write_emits_the_seven_base_graph_files` is the guard that the
swap did not change `pack_and_write`'s output.

- [ ] **Step 5: Commit**

```bash
git add pipeline/lib/grid.py pipeline/tests/test_grid.py pipeline/phases/graph_building/build_base_graph.py
git commit -m "perf(pipeline): vectorize Grid cell-id assignment

Per-point cell_id_for_point calls were 6.85M today and would be 40M under any
raw-graph persistence scheme. Exactly equivalent (floor+clip == int()+clip after
clamping), proven against the scalar path over out-of-bbox points."
```

---

### Task 3: Peak-RSS sampler, wired into `phase()`

The whole hypothesis is about memory, so every timing this spike produces must carry a peak-RSS
number next to it. `phase()` currently takes its `meta` up front, before the block runs — peak RSS
is only known after. Change `phase()` to yield its meta dict so a block can fill in values that
only exist at the end; `rec["meta"] = meta` is built post-yield, so mutations are picked up. All
existing `with phase(...):` call sites (which ignore the yielded value) keep working unchanged.

**Files:**
- Create: `pipeline/lib/memtrace.py`
- Modify: `pipeline/lib/timing.py:20-24` (yield the meta dict)
- Modify: `pipeline/phases/graph_building/build_base_graph.py` (`stream_osm`, `contract`)
- Test: `pipeline/tests/test_memtrace.py` (create)

**Interfaces:**
- Consumes: Task 1's `stream_osm`/`contract`.
- Produces:
  - `memtrace.rss_sampler(interval_s: float = 0.5)` — context manager yielding a `RssSample`
    dataclass with fields filled on exit: `peak_rss_gb: float`, `start_rss_gb: float`,
    `swap_in_delta_mb: float`, `total_ram_gb: float`.
  - `timing.phase(script, name, **meta)` now yields `dict` (was `None`).

- [ ] **Step 1: Write the failing test**

Create `pipeline/tests/test_memtrace.py`:

```python
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.memtrace import rss_sampler  # noqa: E402


def test_sampler_sees_a_large_allocation_made_inside_the_block():
    with rss_sampler(interval_s=0.01) as sample:
        block = np.ones(40_000_000, dtype=np.float64)  # ~320 MB, held for the whole block
        block[0] = 1.0
        import time
        time.sleep(0.1)  # give the sampler thread a few ticks
        del block
    assert sample.total_ram_gb > 0
    assert sample.start_rss_gb > 0
    # peak must have risen by roughly the allocation, allowing generous slack for the allocator
    assert sample.peak_rss_gb - sample.start_rss_gb > 0.15


def test_sampler_reports_zero_growth_for_a_trivial_block():
    with rss_sampler(interval_s=0.01) as sample:
        pass
    assert sample.peak_rss_gb >= sample.start_rss_gb
    assert sample.swap_in_delta_mb >= 0
```

Append to `pipeline/tests/test_add_elevation.py`... no — create the `phase()` test inside
`pipeline/tests/test_memtrace.py` too, since it is the same change:

```python
from lib.timing import phase  # noqa: E402


def test_phase_yields_a_mutable_meta_dict(tmp_path, monkeypatch):
    import json

    import lib.timing as timing
    path = tmp_path / "timings.jsonl"
    monkeypatch.setattr(timing, "TIMINGS_PATH", path)

    with timing.phase("test.py", "demo", nodes=5) as meta:
        meta["peak_rss_gb"] = 1.25

    rec = json.loads(path.read_text(encoding="utf-8").strip())
    assert rec["meta"] == {"nodes": 5, "peak_rss_gb": 1.25}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest pipeline/tests/test_memtrace.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lib.memtrace'`, and once that is created,
`test_phase_yields_a_mutable_meta_dict` fails with `AttributeError: 'NoneType' object does not
support item assignment`.

- [ ] **Step 3: Implement**

Create `pipeline/lib/memtrace.py`:

```python
"""Samples process RSS on a background thread for the duration of a block, so an expensive phase
can record how close it came to physical RAM alongside its wall-clock time. Exists because
build_base_graph.py's contract_structural phase costs ~96us per raw edge - roughly 30x what its
Python walk body should cost - on a 17.1 GB box where the live set is estimated at 15-20 GB. A
seconds number alone cannot tell swapping apart from slow code; this is the other half."""

import threading
import time
from dataclasses import dataclass
from contextlib import contextmanager

import psutil

_GB = 1024 ** 3
_MB = 1024 ** 2


@dataclass
class RssSample:
    total_ram_gb: float = 0.0
    start_rss_gb: float = 0.0
    peak_rss_gb: float = 0.0
    swap_in_delta_mb: float = 0.0

    def as_meta(self) -> dict:
        return {
            "total_ram_gb": round(self.total_ram_gb, 2),
            "start_rss_gb": round(self.start_rss_gb, 2),
            "peak_rss_gb": round(self.peak_rss_gb, 2),
            "swap_in_delta_mb": round(self.swap_in_delta_mb, 1),
        }


@contextmanager
def rss_sampler(interval_s: float = 0.5):
    proc = psutil.Process()
    sample = RssSample(
        total_ram_gb=psutil.virtual_memory().total / _GB,
        start_rss_gb=proc.memory_info().rss / _GB,
    )
    sample.peak_rss_gb = sample.start_rss_gb
    swap_in_start = psutil.swap_memory().sin

    stop = threading.Event()

    def _poll():
        while not stop.wait(interval_s):
            try:
                rss = proc.memory_info().rss / _GB
            except psutil.Error:  # process gone / permission blip - nothing useful to record
                return
            if rss > sample.peak_rss_gb:
                sample.peak_rss_gb = rss

    thread = threading.Thread(target=_poll, daemon=True, name="rss-sampler")
    thread.start()
    try:
        yield sample
    finally:
        stop.set()
        thread.join(timeout=interval_s * 4)
        rss = proc.memory_info().rss / _GB
        if rss > sample.peak_rss_gb:
            sample.peak_rss_gb = rss
        # psutil's swap sin/sout are cumulative machine-wide counters; the delta over the block is
        # the signal that this block (or something contending with it) actually paged in.
        sample.swap_in_delta_mb = max(0.0, (psutil.swap_memory().sin - swap_in_start) / _MB)
```

Change `pipeline/lib/timing.py`'s `phase` body — replace `yield` (line 21) and the `if meta:` line:

```python
@contextmanager
def phase(script: str, name: str, **meta):
    t0 = time.monotonic()
    yield meta  # mutable: a block can add values (e.g. peak RSS) only knowable at the end
    elapsed = time.monotonic() - t0
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "script": script,
        "phase": name,
        "seconds": round(elapsed, 2),
    }
    if meta:
        rec["meta"] = meta
    with open(TIMINGS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
```

Wire it into `build_base_graph.py`'s two phases — in `stream_osm`:

```python
    with phase(SCRIPT_NAME, "stream_osm") as meta, rss_sampler() as sample:
        handler.apply_file(trails_path, locations=True)
        meta.update(sample.as_meta())
```

and in `contract`:

```python
    with phase(SCRIPT_NAME, "contract_structural") as meta, rss_sampler() as sample:
        contracted = contract_structural(...)   # unchanged argument list
        meta.update(sample.as_meta())
```

Note: `sample`'s fields are finalized in `rss_sampler`'s `finally`, which runs *after* the
`meta.update(...)` line inside the block. Put the `meta.update(sample.as_meta())` line **outside**
the `with` instead — restructure both as:

```python
    with phase(SCRIPT_NAME, "contract_structural") as meta:
        with rss_sampler() as sample:
            contracted = contract_structural(...)
        meta.update(sample.as_meta())
```

Add `from lib.memtrace import rss_sampler  # noqa: E402` to `build_base_graph.py`'s imports.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest pipeline/tests/test_memtrace.py pipeline/tests/test_build_base_graph.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add pipeline/lib/memtrace.py pipeline/lib/timing.py pipeline/tests/test_memtrace.py pipeline/phases/graph_building/build_base_graph.py
git commit -m "feat(pipeline): record peak RSS alongside phase timings

phase() now yields its meta dict so a block can add values only knowable at the
end. build_base_graph.py's two phases now log peak RSS and swap-in delta - a
seconds number alone cannot distinguish swapping from slow code."
```

---

### Task 4: Reconstruct the raw graph from `base_graph/`

The spike needs the real pre-contraction graph at arbitrary sizes. Re-streaming
`trails.osm.pbf` costs 914s per attempt, and sub-bbox `osmium extract` runs add a second moving
part. But `base_graph/` already contains the raw graph, losslessly, in topology: each chain edge
`e` is the raw path `u -> interior[offset..offset+count) -> v`, and `interior_offset` is monotone
in edge order (verified), so raw node ids can be handed out as `n_junctions + flat_interior_index`
with no bookkeeping.

**This reconstruction is for timing only.** One field cannot be recovered: which *segments* of a
partially-road chain were road (162,169 chain edges have `0 < road_m < dist`). The reconstruction
sets the per-segment road flag from `road_m > 0` for the whole chain. That changes `road_m`
totals, so a reconstruction must never be used for the tiled spec's reference-equivalence test —
only for measuring how long contraction takes on a graph of this exact shape and size. The module
docstring must say so.

**Files:**
- Create: `pipeline/analysis/reconstruct_raw_graph.py`
- Test: `pipeline/tests/test_reconstruct_raw_graph.py` (create)

**Interfaces:**
- Consumes: Task 2's `Grid.cell_ids_for_points`, `lib.binfmt`.
- Produces:
  - `RawGraph` dataclass: `coords (n,2) f8`, `edges_i i8`, `edges_j i8`, `edges_dist f8`,
    `edges_weight f8`, `edges_road bool`, `edges_sac_rank i1`, `edges_via_ferrata bool` — exactly
    the eight positional arguments `contract_structural` takes, in order.
  - `reconstruct_raw(nodes, edges, interior, edge_ids, road_penalty_factor) -> RawGraph`
    — `edge_ids` selects which chain edges to expand (pass `np.arange(len(edges))` for all).
  - `select_edges_in_cells(nodes, edges, cell_ids: set[int]) -> np.ndarray[int64]`
    — chain edge ids whose `u` endpoint's `cell_id` is in `cell_ids`.

- [ ] **Step 1: Write the failing test**

Create `pipeline/tests/test_reconstruct_raw_graph.py`:

```python
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))

from lib import binfmt  # noqa: E402
from lib.contraction import contract_structural  # noqa: E402
from reconstruct_raw_graph import reconstruct_raw, select_edges_in_cells  # noqa: E402


def _fixture():
    """Two chain edges sharing junction 1:
         0 --[p0, p1]-- 1 --[]-- 2
       so the raw graph is 0-p0-p1-1-2 : 5 nodes, 4 edges."""
    nodes = np.zeros(3, dtype=binfmt.NODE_DTYPE)
    nodes["lon"] = [11.0, 11.3, 11.4]
    nodes["lat"] = [47.0, 47.0, 47.0]
    nodes["cell_id"] = [0, 0, 1]

    interior = np.zeros(2, dtype=binfmt.COORD_DTYPE)
    interior["lon"] = [11.1, 11.2]
    interior["lat"] = [47.0, 47.0]

    edges = np.zeros(2, dtype=binfmt.EDGE_DTYPE)
    edges["u"] = [0, 1]
    edges["v"] = [1, 2]
    edges["dist"] = [300.0, 100.0]
    edges["road_m"] = [300.0, 0.0]
    edges["sac_rank"] = [3, -1]
    edges["via_ferrata"] = [False, True]
    edges["interior_offset"] = [0, 2]
    edges["interior_count"] = [2, 0]
    edges["edge_id"] = [0, 1]
    return nodes, edges, interior


def test_reconstruct_expands_chains_into_per_segment_raw_edges():
    nodes, edges, interior = _fixture()
    raw = reconstruct_raw(nodes, edges, interior, np.arange(2), road_penalty_factor=1.3)

    assert len(raw.coords) == 5          # 3 junctions + 2 interior points
    assert len(raw.edges_i) == 4         # (2 interior + 1) + (0 + 1) segments

    # every raw node must appear, and the two interior nodes must have degree exactly 2
    deg = np.bincount(np.concatenate([raw.edges_i, raw.edges_j]), minlength=5)
    interior_ids = [i for i in range(5) if deg[i] == 2]
    assert len(interior_ids) >= 2


def test_reconstruct_preserves_node_ordering_along_the_chain():
    nodes, edges, interior = _fixture()
    raw = reconstruct_raw(nodes, edges, interior, np.arange(2), road_penalty_factor=1.3)
    # walking the reconstruction must recover the original left-to-right longitudes
    lons = sorted(raw.coords[:, 0].tolist())
    assert lons == pytest.approx([11.0, 11.1, 11.2, 11.3, 11.4])


def test_recontracting_the_reconstruction_reproduces_the_original_chains():
    nodes, edges, interior = _fixture()
    raw = reconstruct_raw(nodes, edges, interior, np.arange(2), road_penalty_factor=1.3)
    out = contract_structural(
        raw.coords, raw.edges_i, raw.edges_j, raw.edges_dist, raw.edges_weight,
        raw.edges_road, raw.edges_sac_rank, raw.edges_via_ferrata,
    )
    assert len(out.edges_u) == 2
    assert sorted(out.edges_sac_rank.tolist()) == [-1, 3]
    assert sorted(int(len(p)) for p in out.interior_coords) == [0, 2]


def test_reconstructed_distances_sum_to_the_original_chain_distances():
    nodes, edges, interior = _fixture()
    raw = reconstruct_raw(nodes, edges, interior, np.arange(2), road_penalty_factor=1.3)
    # segment haversines are recomputed from the same coords with the same formula, so the total
    # must match the persisted chain totals - this is what proves interior ordering is right
    assert raw.edges_dist.sum() == pytest.approx(float(edges["dist"].sum()), rel=1e-6)


def test_select_edges_in_cells_filters_by_the_u_endpoints_cell():
    nodes, edges, interior = _fixture()
    assert select_edges_in_cells(nodes, edges, {0}).tolist() == [0, 1]
    assert select_edges_in_cells(nodes, edges, {1}).tolist() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest pipeline/tests/test_reconstruct_raw_graph.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'reconstruct_raw_graph'`

- [ ] **Step 3: Implement**

Create `pipeline/analysis/reconstruct_raw_graph.py`:

```python
#!/usr/bin/env python3
"""Standalone analysis module - not part of the doit task graph, not imported by any phase script.

Rebuilds the raw (pre-contraction) node/edge arrays by un-contracting the already-persisted
data/osm/base_graph/, so contraction cost can be measured at any graph size without re-running
stream_osm (914s per attempt). Each chain edge e is the raw path u -> interior[offset..offset+
count) -> v; interior_offset is monotone in edge order, so raw node ids fall out as
n_junctions + flat_interior_index with no bookkeeping.

TIMING ONLY - NOT AN EQUIVALENCE FIXTURE. One field cannot be recovered: which segments of a
partially-road chain were road (162,169 chain edges have 0 < road_m < dist). This sets the
per-segment road flag from road_m > 0 for the whole chain, so reconstructed road_m totals differ
from the originals. Topology, coordinates, per-segment distances, sac_rank and via_ferrata are
exact, which is everything contraction's cost depends on.

Usage: python pipeline/analysis/reconstruct_raw_graph.py [--base-graph data/osm/base_graph]
       (running it directly reconstructs the full graph and prints a size/consistency report)
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import binfmt  # noqa: E402
from lib.pipeline import OSM_DIR, load_config  # noqa: E402


@dataclass
class RawGraph:
    """Exactly contract_structural's eight positional arguments, in order."""
    coords: np.ndarray
    edges_i: np.ndarray
    edges_j: np.ndarray
    edges_dist: np.ndarray
    edges_weight: np.ndarray
    edges_road: np.ndarray
    edges_sac_rank: np.ndarray
    edges_via_ferrata: np.ndarray

    def as_args(self):
        return (self.coords, self.edges_i, self.edges_j, self.edges_dist, self.edges_weight,
                self.edges_road, self.edges_sac_rank, self.edges_via_ferrata)


def _haversine_m_vec(lon1, lat1, lon2, lat2):
    # same formula and earth radius as build_base_graph.py's haversine_m_vec, so reconstructed
    # segment distances sum back to the persisted chain distances
    r = 6_371_000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlambda / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def select_edges_in_cells(nodes, edges, cell_ids) -> np.ndarray:
    """Chain edge ids whose u endpoint's home cell is in cell_ids. Selecting by u (not by both
    endpoints) keeps boundary-crossing chains in the subset, which is what makes a subset look
    like a real region rather than a set of disconnected cell interiors."""
    wanted = np.zeros(int(nodes["cell_id"].max()) + 1, dtype=bool)
    for cid in cell_ids:
        if 0 <= cid < len(wanted):
            wanted[cid] = True
    u_cells = np.asarray(nodes["cell_id"])[np.asarray(edges["u"])]
    return np.flatnonzero(wanted[u_cells]).astype(np.int64)


def reconstruct_raw(nodes, edges, interior, edge_ids, road_penalty_factor) -> RawGraph:
    edge_ids = np.asarray(edge_ids, dtype=np.int64)
    sel = edges[edge_ids]
    n_j = len(nodes)

    starts = np.asarray(sel["interior_offset"], dtype=np.int64)
    counts = np.asarray(sel["interior_count"], dtype=np.int64)

    # --- provisional raw node ids: junctions keep 0..n_j-1, interior point k of the flat
    # interior array becomes n_j + k. Sparse for a subset; compacted at the end. ---
    seg_counts = counts + 1                      # a chain of c interior points has c+1 segments
    pos = binfmt.ragged_positions(seg_counts)    # 0..counts[e] within each chain
    eidx = np.repeat(np.arange(len(sel), dtype=np.int64), seg_counts)

    tail = np.where(pos == 0,
                    np.asarray(sel["u"], dtype=np.int64)[eidx],
                    n_j + starts[eidx] + pos - 1)
    head = np.where(pos == counts[eidx],
                    np.asarray(sel["v"], dtype=np.int64)[eidx],
                    n_j + starts[eidx] + pos)

    # --- compact the sparse id space, and gather coords for exactly the nodes used ---
    used = np.unique(np.concatenate([tail, head]))
    edges_i = np.searchsorted(used, tail)
    edges_j = np.searchsorted(used, head)

    coords = np.empty((len(used), 2), dtype=np.float64)
    is_junction = used < n_j
    j_ids = used[is_junction]
    coords[is_junction, 0] = np.asarray(nodes["lon"])[j_ids]
    coords[is_junction, 1] = np.asarray(nodes["lat"])[j_ids]
    i_ids = used[~is_junction] - n_j
    coords[~is_junction, 0] = np.asarray(interior["lon"])[i_ids]
    coords[~is_junction, 1] = np.asarray(interior["lat"])[i_ids]

    edges_dist = _haversine_m_vec(coords[edges_i, 0], coords[edges_i, 1],
                                  coords[edges_j, 0], coords[edges_j, 1])

    # per-chain fields broadcast to that chain's segments; road is the lossy one (see docstring)
    edges_road = (np.asarray(sel["road_m"]) > 0)[eidx]
    edges_weight = np.where(edges_road, edges_dist * road_penalty_factor, edges_dist)
    edges_sac_rank = np.asarray(sel["sac_rank"], dtype=np.int8)[eidx]
    edges_via_ferrata = np.asarray(sel["via_ferrata"], dtype=bool)[eidx]

    return RawGraph(coords, edges_i, edges_j, edges_dist, edges_weight,
                    edges_road, edges_sac_rank, edges_via_ferrata)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-graph", default=str(OSM_DIR / "base_graph"))
    args = parser.parse_args(argv)

    config = load_config()
    d = Path(args.base_graph)
    nodes = binfmt.load_array(d / "nodes.npy")
    edges = binfmt.load_array(d / "edges.npy")
    interior = binfmt.load_array(d / "interior.npy")
    print(f"base_graph: {len(nodes):,} nodes, {len(edges):,} chain edges, "
          f"{len(interior):,} interior points", flush=True)

    raw = reconstruct_raw(nodes, edges, interior, np.arange(len(edges)),
                          config["graph"]["roadPenaltyFactor"])
    print(f"reconstructed raw: {len(raw.coords):,} nodes, {len(raw.edges_i):,} edges", flush=True)

    expected_nodes = len(nodes) + len(interior)
    expected_edges = len(edges) + len(interior)
    print(f"  node count identity: {len(raw.coords):,} vs expected {expected_nodes:,} "
          f"({'OK' if len(raw.coords) == expected_nodes else 'MISMATCH'})", flush=True)
    print(f"  edge count identity: {len(raw.edges_i):,} vs expected {expected_edges:,} "
          f"({'OK' if len(raw.edges_i) == expected_edges else 'MISMATCH'})", flush=True)

    got, want = float(raw.edges_dist.sum()), float(np.asarray(edges["dist"]).sum())
    rel = abs(got - want) / want
    print(f"  distance identity: {got:,.1f} m vs {want:,.1f} m, rel err {rel:.2e} "
          f"({'OK' if rel < 1e-6 else 'MISMATCH'})", flush=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest pipeline/tests/test_reconstruct_raw_graph.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Validate against the real base graph**

This is a read-only `analysis/` script over already-persisted data — no pipeline task runs. It
allocates ~4 GB briefly; on a 17.1 GB box that is fine.

Run: `python pipeline/analysis/reconstruct_raw_graph.py`
Expected output, all three identities `OK`:

```
base_graph: 6,853,136 nodes, 8,341,484 chain edges, 33,081,647 interior points
reconstructed raw: 39,934,783 nodes, 41,423,131 edges
  node count identity: 39,934,783 vs expected 39,934,783 (OK)
  edge count identity: 41,423,131 vs expected 41,423,131 (OK)
  distance identity: 994,395,254.5 m vs 994,395,254.5 m, rel err 0.00e+00 (OK)
```

If the distance identity fails, interior ordering or offsets are being read wrong — stop and fix
before Task 5, because every later number depends on this graph being the real one.

- [ ] **Step 6: Commit**

```bash
git add pipeline/analysis/reconstruct_raw_graph.py pipeline/tests/test_reconstruct_raw_graph.py
git commit -m "feat(analysis): reconstruct the raw graph by un-contracting base_graph

Lets contraction be measured at any graph size without re-running stream_osm
(914s per attempt). Topology/coords/distances are exact; per-segment road flags
are approximated, so this is a timing fixture only, never an equivalence fixture."
```

---

### Task 5: Contraction scaling sweep

The decisive experiment. Contract increasingly large subsets of the real graph and record
seconds-per-raw-edge and peak RSS for each. Flat cost per edge ⇒ CPU-bound ⇒ tiling is the right
fix. Cost per edge climbing sharply as the working set approaches 17.1 GB ⇒ memory-bound ⇒ the
tiled spec is aimed at the wrong bottleneck.

Subsets are built by cell, in descending density order, so each size step is a superset of the
last and the densest (worst-case, and the cell that would set the tiled design's wall-clock floor)
region is present from the smallest size on.

**Files:**
- Create: `pipeline/analysis/contraction_scaling.py`
- Test: `pipeline/tests/test_contraction_scaling.py` (create)

**Interfaces:**
- Consumes: Task 3's `rss_sampler`, Task 4's `reconstruct_raw` / `select_edges_in_cells`.
- Produces:
  - `cells_by_density(nodes, n_cells: int) -> list[int]` — cell ids sorted by node count, densest
    first, empty cells excluded.
  - `pick_cell_sets(nodes, n_cells, fractions: list[float]) -> list[tuple[float, list[int]]]` —
    for each target fraction of total nodes, the densest-first prefix of cells reaching it.
  - `run_sweep(base_graph_dir, fractions, out_path) -> list[dict]` — writes one JSON line per
    measured point to `out_path` with keys `fraction, n_cells, raw_nodes, raw_edges, seconds,
    us_per_edge, peak_rss_gb, swap_in_delta_mb`.

- [ ] **Step 1: Write the failing test**

Create `pipeline/tests/test_contraction_scaling.py`:

```python
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))

from lib import binfmt  # noqa: E402
from contraction_scaling import cells_by_density, pick_cell_sets  # noqa: E402


def _nodes(cell_ids):
    nodes = np.zeros(len(cell_ids), dtype=binfmt.NODE_DTYPE)
    nodes["cell_id"] = cell_ids
    return nodes


def test_cells_by_density_orders_densest_first_and_drops_empty_cells():
    # cell 2 has 4 nodes, cell 0 has 2, cell 1 has 1, cell 3 has none
    nodes = _nodes([0, 0, 1, 2, 2, 2, 2])
    assert cells_by_density(nodes, n_cells=4) == [2, 0, 1]


def test_pick_cell_sets_returns_nested_prefixes_reaching_each_fraction():
    nodes = _nodes([0, 0, 1, 2, 2, 2, 2])  # 7 nodes total
    sets = pick_cell_sets(nodes, n_cells=4, fractions=[0.5, 1.0])

    assert [f for f, _ in sets] == [0.5, 1.0]
    half, whole = sets[0][1], sets[1][1]
    assert half == [2]                 # 4/7 >= 0.5 with the densest cell alone
    assert half == whole[:len(half)]   # nested: every step is a superset of the last
    assert set(whole) == {0, 1, 2}


def test_pick_cell_sets_never_returns_an_empty_set():
    nodes = _nodes([0, 0, 1, 2, 2, 2, 2])
    sets = pick_cell_sets(nodes, n_cells=4, fractions=[0.001])
    assert len(sets[0][1]) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest pipeline/tests/test_contraction_scaling.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'contraction_scaling'`

- [ ] **Step 3: Implement**

Create `pipeline/analysis/contraction_scaling.py`:

```python
#!/usr/bin/env python3
"""Standalone analysis script - not part of the doit task graph, not imported by any phase script.

Answers the one question docs/superpowers/specs/2026-08-20-tiled-contraction-design.md never asks:
is contract_structural's 3963s CPU-bound or memory-bound? 3963s over 41.4M raw edges is ~96us per
edge, roughly 30x what the walk body's Python work should cost, on a box with 17.1 GB RAM and
20.1 GB of swap behind it.

Contracts increasingly large subsets of the REAL graph (rebuilt by reconstruct_raw_graph.py) and
records seconds-per-raw-edge next to peak RSS for each:
  - flat us/edge, RSS well under RAM     -> CPU-bound  -> tiling is the right fix (ceiling: 6
                                                          physical cores, not 88 cells)
  - us/edge climbing as RSS nears 17 GB  -> memory-bound -> fix memory first, re-measure

Subsets are densest-cell-first and nested, so the worst-case alpine cell - the one that would set
a tiled design's wall-clock floor - is present at every size.

Usage: python pipeline/analysis/contraction_scaling.py [--fractions 0.02,0.05,0.1,0.2,0.4]
Runtime: roughly (sum of fractions) x 66 min if cost is linear, MORE if it is not - which is the
finding. Expect ~45-90 min for the default fractions. Ask before starting it.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import binfmt  # noqa: E402
from lib.contraction import contract_structural  # noqa: E402
from lib.grid import Grid  # noqa: E402
from lib.memtrace import rss_sampler  # noqa: E402
from lib.pipeline import DATA_DIR, OSM_DIR, load_config  # noqa: E402
from reconstruct_raw_graph import reconstruct_raw, select_edges_in_cells  # noqa: E402


def cells_by_density(nodes, n_cells: int) -> list[int]:
    counts = np.bincount(np.asarray(nodes["cell_id"]), minlength=n_cells)
    order = np.argsort(-counts, kind="stable")
    return [int(c) for c in order if counts[c] > 0]


def pick_cell_sets(nodes, n_cells: int, fractions) -> list[tuple[float, list[int]]]:
    """Densest-first nested prefixes: the cells needed to cover each target fraction of all nodes.
    Nested so each larger measurement is a strict superset of the smaller ones - otherwise a
    size-vs-time curve would also be measuring a change of terrain."""
    ranked = cells_by_density(nodes, n_cells)
    counts = np.bincount(np.asarray(nodes["cell_id"]), minlength=n_cells)
    total = counts.sum()
    cum = np.cumsum([counts[c] for c in ranked])

    out = []
    for f in fractions:
        k = int(np.searchsorted(cum, f * total) + 1)
        out.append((f, ranked[:min(k, len(ranked))]))
    return out


def run_sweep(base_graph_dir, fractions, out_path):
    config = load_config()
    d = Path(base_graph_dir)
    nodes = binfmt.load_array(d / "nodes.npy")
    edges = binfmt.load_array(d / "edges.npy")
    interior = binfmt.load_array(d / "interior.npy")
    manifest = binfmt.load_manifest(d / "manifest.json")
    grid = Grid(manifest["bbox"], manifest["tile_size_km"])
    n_cells = len(grid.all_cell_ids())

    results = []
    sets = pick_cell_sets(nodes, n_cells, fractions)
    for step, (frac, cells) in enumerate(sets, start=1):
        edge_ids = select_edges_in_cells(nodes, edges, set(cells))
        raw = reconstruct_raw(nodes, edges, interior, edge_ids,
                              config["graph"]["roadPenaltyFactor"])
        print(f"[{step}/{len(sets)}] fraction {frac:.0%}: {len(cells)} cells -> "
              f"{len(raw.coords):,} raw nodes / {len(raw.edges_i):,} raw edges, "
              f"contracting ...", flush=True)

        t0 = time.monotonic()
        with rss_sampler() as sample:
            contract_structural(*raw.as_args())
        seconds = time.monotonic() - t0

        rec = {
            "fraction": frac,
            "n_cells": len(cells),
            "raw_nodes": int(len(raw.coords)),
            "raw_edges": int(len(raw.edges_i)),
            "seconds": round(seconds, 2),
            "us_per_edge": round(seconds * 1e6 / max(1, len(raw.edges_i)), 2),
            **sample.as_meta(),
        }
        results.append(rec)
        with open(out_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"    {seconds:,.1f}s | {rec['us_per_edge']} us/edge | "
              f"peak RSS {rec['peak_rss_gb']} GB of {rec['total_ram_gb']} GB | "
              f"swap-in {rec['swap_in_delta_mb']} MB", flush=True)

        del raw

    print("\nfraction  raw_edges     seconds  us/edge  peak_rss_gb  swap_in_mb", flush=True)
    for r in results:
        print(f"{r['fraction']:>7.0%}  {r['raw_edges']:>10,}  {r['seconds']:>9,.1f}  "
              f"{r['us_per_edge']:>7.2f}  {r['peak_rss_gb']:>11.2f}  "
              f"{r['swap_in_delta_mb']:>10.1f}", flush=True)
    if len(results) >= 2:
        ratio = results[-1]["us_per_edge"] / results[0]["us_per_edge"]
        print(f"\nus/edge ratio (largest / smallest): {ratio:.2f}x", flush=True)
        print("  < 1.3x  -> linear, CPU-bound     -> tiling justified (ceiling ~6 cores)",
              flush=True)
        print("  > 2.0x  -> super-linear, memory-bound -> fix memory first, re-measure",
              flush=True)
    return results


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-graph", default=str(OSM_DIR / "base_graph"))
    parser.add_argument("--fractions", default="0.02,0.05,0.1,0.2,0.4")
    parser.add_argument("--out", default=str(DATA_DIR / "contraction_scaling.jsonl"))
    args = parser.parse_args(argv)
    fractions = [float(x) for x in args.fractions.split(",")]
    run_sweep(args.base_graph, fractions, Path(args.out))


if __name__ == "__main__":
    main()
```

(`lib/pipeline.py:14` exports `DATA_DIR = REPO_ROOT / "data"`, so both the `DATA_DIR` and
`OSM_DIR` imports resolve.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest pipeline/tests/test_contraction_scaling.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Smoke-run the smallest fraction only**

Run: `python pipeline/analysis/contraction_scaling.py --fractions 0.02`
Expected: completes in roughly 1-3 minutes, prints one result row and appends one line to
`data/contraction_scaling.jsonl`. This verifies the harness end to end without committing to the
full sweep (which Task 7 hands to the user).

- [ ] **Step 6: Commit**

```bash
git add pipeline/analysis/contraction_scaling.py pipeline/tests/test_contraction_scaling.py
git commit -m "feat(analysis): contraction scaling sweep

Measures seconds-per-raw-edge and peak RSS across nested densest-first subsets
of the real graph, to decide whether contract_structural's 3963s is CPU-bound
(tiling is the fix) or memory-bound (tiling is aimed at the wrong bottleneck)."
```

---

### Task 6: Function-level hot-spot profile

The sweep says *whether* the cost scales badly; it does not say *where* the cost sits. If it turns
out CPU-bound, the next question is whether the serial walk has cheap wins left — `_neighbors`
(`lib/contraction.py:49-51`) builds two Python lists via `.tolist()` for every interior node, and
line 79 does two scalar numpy indexes per interior node, 33M times. `cProfile` attributes that
directly.

Runs at one fixed, small fraction so it is a couple of minutes, not an hour — `cProfile`'s own
overhead makes large runs pointless anyway, and hot-spot *shares* are what matter, not absolutes.

**Files:**
- Modify: `pipeline/analysis/contraction_scaling.py` (add `--profile-fraction`)
- Test: `pipeline/tests/test_contraction_scaling.py` (append)

**Interfaces:**
- Consumes: Task 5's `pick_cell_sets`, `reconstruct_raw`.
- Produces: `profile_one(base_graph_dir, fraction, out_path) -> str` — runs one contraction under
  `cProfile`, writes the raw stats to `out_path` (a `.prof` file) and returns the formatted
  top-20-by-cumulative-time table as a string.

- [ ] **Step 1: Write the failing test**

Append to `pipeline/tests/test_contraction_scaling.py`:

```python
from contraction_scaling import profile_one  # noqa: E402


def test_profile_one_writes_a_prof_file_and_returns_a_table(tmp_path, monkeypatch):
    # build a minimal on-disk base_graph so profile_one has something real to read
    import build_base_graph as bbg
    from lib.contraction import ContractedGraph

    contracted = ContractedGraph(
        coords=np.array([(11.0, 47.0), (11.1, 47.1), (11.2, 47.2)]),
        edges_u=np.array([0, 1], dtype=np.int64),
        edges_v=np.array([1, 2], dtype=np.int64),
        edges_dist=np.array([100.0, 200.0]),
        edges_weight=np.array([130.0, 200.0]),
        edges_road_m=np.array([100.0, 0.0]),
        edges_sac_rank=np.array([2, -1], dtype=np.int8),
        edges_via_ferrata=np.array([False, True]),
        interior_coords=[[(11.05, 47.05)], []],
    )
    graph_dir = tmp_path / "base_graph"
    bbg.pack_and_write(contracted, {"minLng": 8.9, "maxLng": 17.2,
                                    "minLat": 46.3, "maxLat": 50.6}, 60.0, graph_dir)

    prof_path = tmp_path / "contraction.prof"
    table = profile_one(graph_dir, fraction=1.0, out_path=prof_path)

    assert prof_path.exists()
    assert "contract_structural" in table
```

Add `sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases" / "graph_building"))`
to the test module's imports so `build_base_graph` resolves.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest pipeline/tests/test_contraction_scaling.py::test_profile_one_writes_a_prof_file_and_returns_a_table -v`
Expected: FAIL with `ImportError: cannot import name 'profile_one'`

- [ ] **Step 3: Implement**

Add to `pipeline/analysis/contraction_scaling.py` (imports `cProfile`, `io`, `pstats`):

```python
def profile_one(base_graph_dir, fraction, out_path):
    """One contraction under cProfile at a deliberately small fraction - cProfile's per-call
    overhead makes long runs pointless, and what matters here is the SHARE of time in the walk's
    hot spots (_neighbors' per-node .tolist(), the two scalar coords[] reads per interior node),
    not the absolute seconds."""
    config = load_config()
    d = Path(base_graph_dir)
    nodes = binfmt.load_array(d / "nodes.npy")
    edges = binfmt.load_array(d / "edges.npy")
    interior = binfmt.load_array(d / "interior.npy")
    manifest = binfmt.load_manifest(d / "manifest.json")
    grid = Grid(manifest["bbox"], manifest["tile_size_km"])

    _, cells = pick_cell_sets(nodes, len(grid.all_cell_ids()), [fraction])[0]
    edge_ids = select_edges_in_cells(nodes, edges, set(cells))
    raw = reconstruct_raw(nodes, edges, interior, edge_ids, config["graph"]["roadPenaltyFactor"])
    print(f"profiling contraction over {len(raw.edges_i):,} raw edges "
          f"({len(cells)} cells) ...", flush=True)

    profiler = cProfile.Profile()
    profiler.enable()
    contract_structural(*raw.as_args())
    profiler.disable()

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    profiler.dump_stats(str(out_path))

    buf = io.StringIO()
    pstats.Stats(profiler, stream=buf).sort_stats("cumulative").print_stats(20)
    table = buf.getvalue()
    print(table, flush=True)
    print(f"raw stats written to {out_path} (open with: "
          f"python -m pstats {out_path})", flush=True)
    return table
```

And in `main`, add the flag and branch:

```python
    parser.add_argument("--profile-fraction", type=float, default=None,
                        help="skip the sweep; cProfile one contraction at this fraction")
    parser.add_argument("--profile-out", default=str(DATA_DIR / "contraction.prof"))
    ...
    if args.profile_fraction is not None:
        profile_one(args.base_graph, args.profile_fraction, Path(args.profile_out))
        return
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest pipeline/tests/test_contraction_scaling.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Run the real profile**

Run: `python pipeline/analysis/contraction_scaling.py --profile-fraction 0.05`
Expected: a few minutes; prints the top-20 cumulative table and writes `data/contraction.prof`.
Record the `tottime` share of `_neighbors` and of `contract_structural`'s own frame.

- [ ] **Step 6: Commit**

```bash
git add pipeline/analysis/contraction_scaling.py pipeline/tests/test_contraction_scaling.py
git commit -m "feat(analysis): cProfile mode for contract_structural

Attributes walk cost to _neighbors' per-node .tolist() and the scalar coords[]
reads, so a CPU-bound verdict can be turned into a concrete serial-optimization
list instead of straight to parallelism."
```

---

### Task 7: Run the sweep and write the findings

The deliverable of the whole spike: a short findings doc that either kills or green-lights the
tiled spec, with the numbers attached.

**Files:**
- Create: `docs/superpowers/specs/2026-08-20-contraction-measurement-findings.md`
- Modify: `docs/superpowers/specs/2026-08-20-tiled-contraction-design.md` (Status line + a link)

**Interfaces:**
- Consumes: Tasks 5 and 6's outputs (`data/contraction_scaling.jsonl`, `data/contraction.prof`).
- Produces: a decision — no code.

- [ ] **Step 1: Hand the sweep to the user**

Do **not** launch this from an agent. Tell the user to run, in their own terminal:

```
python pipeline/analysis/contraction_scaling.py
```

Expected runtime ~45-90 min (longer is itself the finding). It appends to
`data/contraction_scaling.jsonl` and prints the summary table plus the us/edge ratio verdict line.

- [ ] **Step 2: Apply the free memory win and re-measure the real phase**

Independent of the sweep's verdict, `del handler` should free the raw Python lists *before*
contraction rather than after — the numpy copies made inside `contract` are the only thing the
contraction needs. In `build_base_graph.py`'s `main`, the `handler` reference must be dropped
before `contract_structural` runs, which means `contract` has to take the arrays rather than the
handler. Change `contract`'s signature to `contract(coords, edges_i, edges_j, edges_dist,
edges_weight, edges_road, edges_sac_rank, edges_via_ferrata, progress_every=20_000)`, move the
eight `np.array(...)` conversions into `main`, and there do:

```python
    handler = stream_osm(args.trails, config)
    raw_args = (
        np.array(handler.coords, dtype=np.float64),
        np.array(handler.edges_i, dtype=np.int64),
        np.array(handler.edges_j, dtype=np.int64),
        np.array(handler.edges_dist, dtype=np.float64),
        np.array(handler.edges_w, dtype=np.float64),
        np.array(handler.edges_road, dtype=bool),
        np.array(handler.edges_sac_rank, dtype=np.int8),
        np.array(handler.edges_via_ferrata, dtype=bool),
    )
    del handler  # ~12 GB of raw Python lists, dead once copied into the arrays above
    contracted = contract(*raw_args)
    del raw_args
    pack_and_write(contracted, config["bbox"], args.tile_size_km, args.out_dir)
```

Update `test_build_base_graph.py`'s callable check to match the new `contract` signature (assert
it accepts eight positional arrays by calling it on the tiny chain fixture from
`test_contraction.py` and asserting one chain edge comes back).

Then ask the user to run the real thing once — **this is a pipeline task, so explicit confirmation
is required first** (`pipeline/CLAUDE.md`), and it costs ~15 min of `stream_osm` plus however long
contraction now takes:

```
python pipeline/phases/graph_building/build_base_graph.py
```

The new `contract_structural` line in `data/timings.jsonl` now carries `peak_rss_gb`,
`start_rss_gb` and `swap_in_delta_mb` from Task 3.

- [ ] **Step 3: Write the findings doc**

Create `docs/superpowers/specs/2026-08-20-contraction-measurement-findings.md` with these
sections, filled from the real numbers:

1. **What was measured** — one paragraph, link to this plan and to the tiled spec.
2. **Scaling table** — the summary table from `contraction_scaling.jsonl` verbatim.
3. **Profile table** — the top-10 rows by `tottime` from Task 6.
4. **Effect of freeing `handler` early** — old 3963s / no RSS data vs. the new timing line's
   `seconds`, `peak_rss_gb`, `swap_in_delta_mb`.
5. **Verdict**, using these thresholds decided in advance:

| Observation | Verdict |
|---|---|
| us/edge ratio (largest / smallest subset) < 1.3× **and** peak RSS < ~70% of 17.1 GB | CPU-bound. Tiled spec is justified. Note its real ceiling is 6 physical cores (~660s best case before phase-1 overhead), not 88 cells. |
| us/edge ratio > 2.0× **or** swap-in delta > 0 at the larger sizes | Memory-bound. Tiled spec attacks the wrong bottleneck and would worsen per-worker pressure. Reject for now. |
| Ratio between 1.3× and 2.0× | Mixed. Apply the profile's top serial wins first (`_neighbors` list-building, scalar `coords[]` reads), re-run the sweep, then re-decide. |
| Post-`del handler` contraction time already acceptable | Spec is moot regardless of the ratio. Say so plainly. |

6. **If CPU-bound: gaps the tiled spec must close first** — carry over the four correctness gaps
   already identified in review, so they are not lost between documents:
   - phantom degree-0 nodes from one-hop far endpoints; the merged node set must be defined as the
     union of merged edge endpoints;
   - `edges_interior` has no slot for the *first* edge's polyline (`lib/contraction.py:75` starts
     `interior = []` after edge `e` is consumed at lines 70-74), and its orientation depends on
     which end the walk entered;
   - `road_m`'s initializer at `lib/contraction.py:72` needs the same fix as the loop body at
     lines 92-93;
   - the global-raw-node-id contract must cover **final** edges' endpoints, not just boundary
     nodes, because phase 3's `forced_keep` is built from which nodes own final edges.

- [ ] **Step 4: Update the tiled spec's status**

In `docs/superpowers/specs/2026-08-20-tiled-contraction-design.md`, change the `Status:` line from
`approved for planning` to whichever the findings support — `blocked: see
2026-08-20-contraction-measurement-findings.md` or `approved for planning (measurement confirmed
CPU-bound, see 2026-08-20-contraction-measurement-findings.md)` — and add a one-line pointer to
the findings doc under the Goal section.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-08-20-contraction-measurement-findings.md docs/superpowers/specs/2026-08-20-tiled-contraction-design.md pipeline/phases/graph_building/build_base_graph.py pipeline/tests/test_build_base_graph.py data/contraction_scaling.jsonl
git commit -m "docs(spec): contraction measurement findings

Frees handler's ~12GB of raw Python lists before contraction rather than after,
and records the scaling sweep + profile that decide whether tiled contraction is
attacking the real bottleneck."
```

Note: `data/` is gitignored, so `data/contraction_scaling.jsonl` will not stage — the numbers live
in the findings doc, which is the point. Drop it from the `git add` if git refuses it.

---

## Out of scope for this spike

- Implementing any part of the tiled design (`raw_graph/` persistence, per-tile workers, the
  stitch pass, `contract_structural`'s three new parameters). That is the *next* plan, and only
  if Task 7's verdict calls for it.
- Optimizing the serial walk (`_neighbors`, scalar `coords[]` reads). Task 6 identifies the
  targets; acting on them is a separate plan, because the sweep may show the memory fix alone is
  enough.
- Tiling `stream_osm` — already a non-goal of the spec being tested.
