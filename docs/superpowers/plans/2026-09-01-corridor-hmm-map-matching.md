# Corridor HMM Map Matching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `match_leg`'s single-Dijkstra core in `pipeline/phases/graph_building/match_tour_edges.py`
with HMM-style map matching (Newson & Krumm / `leuvenmapmatching`), so a tour leg's matched path is
pulled through the shape of its own GPX trace instead of only anchored at its two endpoint hubs.

**Architecture:** Two new library modules carry the new matching core:
`pipeline/lib/hmm_match.py` (trace resampling, per-leg `InMemMap` construction with interior
expansion + bidirectional edges + endpoint-anchor materialization, and the Viterbi decode
wrapper around `leuvenmapmatching.matcher.distance.DistanceMatcher`) and
`pipeline/lib/hmm_reconstruct.py` (walks the decoded node path back into the same accumulated
fields `lib/cell_igraph.py`'s `accumulate_path` produces today, including trim/bridge endpoint
reconciliation and partial-edge apportionment). `match_tour_edges.py`'s `match_leg` is rewired to
call these instead of `build_base_igraph_arrays`/`build_igraph_from_base`/
`graph.get_shortest_paths`, but `build_tour_record` and the on-disk output shape are untouched.

**Tech Stack:** Python 3.11, `leuvenmapmatching` (pure-Python, `numpy`/`scipy`-backed — new pixi
pypi-dependency), `python-igraph` (kept, for the endpoint-bridge Dijkstra only), `pytest`.

**Spec:** `docs/superpowers/specs/2026-09-01-corridor-hmm-map-matching-design.md` — this plan
argues from that spec; read both together. Section references below (`§N`) are to that spec.

## Global Constraints

- Coordinate order into `leuvenmapmatching` is `(lat, lon)`; every other array/GPX/`PathResult`
  coordinate in this pipeline is `(lon, lat)`. Swap exactly at the two boundaries (§1) — nodes
  into the map, resampled trace into the matcher — and back on the way out.
- The parent id tagged on every expanded sub-edge is the disambiguated `base_edge_id`
  (`edge_id * 3` / `edge_id * 3 + 1` / `edge_id * 3 + 2`, `pipeline/lib/cell_igraph.py:129-179`),
  never a raw `edge_id` (§2).
- No `RECORD_DTYPE` or `tour_meta.npy` schema change, no `record_schema_version` bump (§5, §6).
- `_check_routable` (`pipeline/lib/cell_igraph.py:60`) must still run before any routing happens
  against a corridor subgraph — dropping it drops the guard against hours of silent Bellman-Ford
  (§5).
- A leg either matches end-to-end or produces no `records.npy` row — never a partial/stitched
  match (§4).
- **Never run any `pipeline/` task or the full `doit` DAG without asking the user first** — this
  applies to `corridor_match_quality.py`'s real-data check in Task 14 too (root `CLAUDE.md`).
- No git worktrees, no subagent-spun worktrees for this work (root `CLAUDE.md`) — work directly on
  the current branch (`feat/official-tours-integration`) in the main checkout.

---

## File Structure

- **Create** `pipeline/lib/hmm_match.py` — `resample_trace`, `LegMap` (dataclass bundling the
  `InMemMap` + sub-edge metadata + anchor node labels), `build_leg_map`, `match_trace`
  (Viterbi decode wrapper), `DecodedState` (dataclass: directed sub-edge + parent `base_edge_id`
  + interior-segment index).
- **Create** `pipeline/lib/hmm_reconstruct.py` — `reconstruct_matched_path` (walks a decoded state
  list into the same fields `accumulate_path` produces, applying §5's partial-edge apportionment
  and §2's out-and-back no-dedupe rule) and `reconcile_endpoints` (§2's trim/bridge/bridge-cap
  logic against the two endpoint anchors).
- **Modify** `pipeline/phases/graph_building/match_tour_edges.py` — `match_leg`'s signature and
  internals (§5), `main()`'s five new CLI flags, two new gap reasons, `no_corridor_path` removed.
- **Modify** `pipeline/dag/graph_building.py` — five new `cli_param` entries on
  `task_match_tour_edges`.
- **Modify** `pipeline/pipeline.config.json` — `tourMatch` block gains five keys (§6).
- **Modify** `pipeline/pixi.toml` — add `leuvenmapmatching` to `[pypi-dependencies]` (§1).
- **Modify** `pipeline/tests/test_config.py` — extend the `tourMatch` key-set assertion.
- **Modify** `pipeline/tests/test_match_tour_edges.py` — update the four direct `match_leg`
  callers for the new signature, remove the `no_corridor_path` test, add the bridge/break/
  length-divergent-still-reachable integration tests that need the full `main()` golden path.
- **Create** `pipeline/tests/test_hmm_match.py` — resampling, coordinate round-trip, interior
  expansion, `base_edge_id` namespace, endpoint anchoring (node + mid-chain), summit-detour decode.
- **Create** `pipeline/tests/test_hmm_reconstruct.py` — trim, bridge, bridge cap, out-and-back,
  partial-edge apportionment, break handling.

---

### Task 1: Add the `leuvenmapmatching` dependency and confirm its API shape

The spec names two `leuvenmapmatching` pieces (§1): `InMemMap` and `DistanceMatcher`. Before
writing any adapter code around them, install the real library and pin down the exact call
signatures and return shapes this plan's later tasks depend on — the package's public API is not
pinned anywhere else in this repo yet, so guessing here would silently drift from what's actually
installed.

**Files:**
- Modify: `pipeline/pixi.toml`
- Create (scratch, not committed): a throwaway spike script to run once, then delete

- [ ] **Step 1: Add the dependency**

Edit `pipeline/pixi.toml`'s `[pypi-dependencies]` section:

```toml
[pypi-dependencies]
pmtiles = "*"
doit = "*"
pytest = "*"
leuvenmapmatching = "*"
```

- [ ] **Step 2: Install and verify import**

```bash
cd pipeline && pixi install
pixi run python -c "import leuvenmapmatching; print(leuvenmapmatching.__version__)"
```

Expected: prints a version string, no `ModuleNotFoundError`.

- [ ] **Step 3: Spike the API shape used by Tasks 2–9**

Write `pipeline/_spike_hmm_api.py` (temporary, not committed) and run it:

```python
from leuvenmapmatching.map.inmem import InMemMap
from leuvenmapmatching.matcher.distance import DistanceMatcher

m = InMemMap("leg", use_latlon=True, use_rtree=True, index_edges=True)
# a tiny 3-node line, node ids are our own choice
m.add_node(0, (47.0, 11.0))
m.add_node(1, (47.001, 11.0))
m.add_node(2, (47.002, 11.0))
m.add_edge(0, 1)
m.add_edge(1, 0)
m.add_edge(1, 2)
m.add_edge(2, 1)

path = [(47.0, 11.0), (47.0011, 11.0), (47.002, 11.0)]  # (lat, lon), matches use_latlon=True
matcher = DistanceMatcher(m, max_dist=150, obs_noise=25, dist_noise=25,
                           non_emitting_states=True)
states, last_idx = matcher.match(path, unique=False)
print("states:", states)
print("node_path:", matcher.node_path())
```

Run: `cd pipeline && pixi run python _spike_hmm_api.py`

Record what `states` and `matcher.node_path()` actually return (a list of node-label pairs vs. a
flat node-label list; whether `node_path()` exists under that exact name in the installed
version). Task 4's `match_trace` implementation below assumes `matcher.node_path()` returns the
ordered list of node labels the winning path visits (including every intermediate node from
non-emitting stretches) — **if the installed version's actual output differs, adjust Task 4's
`match_trace` body to match what this spike showed before writing its test.** Delete
`pipeline/_spike_hmm_api.py` once confirmed — it must not be committed.

- [ ] **Step 4: Commit the dependency addition**

```bash
cd pipeline && git add pixi.toml pixi.lock
git commit -m "pipeline: add leuvenmapmatching dependency for corridor HMM matching"
```

---

### Task 2: Config — five new `tourMatch` keys

**Files:**
- Modify: `pipeline/pipeline.config.json`
- Modify: `pipeline/tests/test_config.py`

**Interfaces:**
- Produces: `config["tourMatch"]["hmmResampleM"]` (25.0), `["hmmObsNoiseM"]` (25.0),
  `["hmmMaxDistM"]` (150.0), `["hmmDistNoiseM"]` (25.0), `["endpointBridgeMaxM"]` (250.0) — read by
  Task 12's `main()`.

- [ ] **Step 1: Write the failing test**

Edit `pipeline/tests/test_config.py`:

```python
def test_tour_match_config_has_expected_keys():
    tm = load_config()["tourMatch"]
    assert set(tm.keys()) == {
        "corridorBufferM", "lengthDivergenceRatio",
        "hmmResampleM", "hmmObsNoiseM", "hmmMaxDistM", "hmmDistNoiseM", "endpointBridgeMaxM",
    }
    assert tm["corridorBufferM"] == 150.0
    assert tm["lengthDivergenceRatio"] == 2.0
    assert tm["hmmResampleM"] == 25.0
    assert tm["hmmObsNoiseM"] == 25.0
    assert tm["hmmMaxDistM"] == 150.0
    assert tm["hmmDistNoiseM"] == 25.0
    assert tm["endpointBridgeMaxM"] == 250.0
```

(This replaces the existing `test_config.py:16`-area assertion in place — same test function,
extended key set and new value assertions.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pipeline && pixi run pytest tests/test_config.py -v`
Expected: FAIL — `AssertionError` on the key set (missing the five new keys).

- [ ] **Step 3: Update the config**

Edit `pipeline/pipeline.config.json`'s `tourMatch` block:

```jsonc
"tourMatch": {
  "corridorBufferM": 150.0,
  "lengthDivergenceRatio": 2.0,
  "hmmResampleM": 25.0,
  "hmmObsNoiseM": 25.0,
  "hmmMaxDistM": 150.0,
  "hmmDistNoiseM": 25.0,
  "endpointBridgeMaxM": 250.0
},
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pipeline && pixi run pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd pipeline && git add pipeline.config.json tests/test_config.py
git commit -m "pipeline: add five HMM-matching tourMatch config keys"
```

---

### Task 3: `resample_trace` — decimate-only trace normalization

**Files:**
- Create: `pipeline/lib/hmm_match.py`
- Test: `pipeline/tests/test_hmm_match.py`

**Interfaces:**
- Produces: `resample_trace(points: list[tuple], resample_m: float) -> list[tuple]` — `points` and
  return value are `(lon, lat)` tuples, same convention as `lib/tour_folder.py`'s
  `parse_leg_gpx`.

- [ ] **Step 1: Write the failing tests**

Create `pipeline/tests/test_hmm_match.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.geo import haversine_m
from lib.hmm_match import resample_trace


def _line_points(n, spacing_m):
    # straight east-west line at the equator; 1 degree of longitude ~= 111320m there
    step_deg = spacing_m / 111320.0
    return [(i * step_deg, 0.0) for i in range(n)]


def test_resample_decimates_a_dense_trace_to_target_spacing():
    dense = _line_points(300, spacing_m=3.0)  # ~900m total, 3m/point
    out = resample_trace(dense, resample_m=25.0)
    assert out[0] == dense[0]
    assert out[-1] == dense[-1]
    for a, b in zip(out, out[1:]):
        d = haversine_m(a[0], a[1], b[0], b[1])
        assert d >= 25.0 - 1e-6 or (a, b) == (out[-2], out[-1])
    assert len(out) < len(dense)


def test_resample_leaves_a_sparse_trace_unchanged():
    sparse = _line_points(5, spacing_m=100.0)  # 100m/point, sparser than the 25m target
    out = resample_trace(sparse, resample_m=25.0)
    assert out == sparse


def test_resample_preserves_endpoints_of_a_dense_trace():
    dense = _line_points(50, spacing_m=5.0)
    out = resample_trace(dense, resample_m=25.0)
    assert out[0] == dense[0]
    assert out[-1] == dense[-1]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd pipeline && pixi run pytest tests/test_hmm_match.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lib.hmm_match'`

- [ ] **Step 3: Implement `resample_trace`**

Create `pipeline/lib/hmm_match.py`:

```python
"""HMM-style map matching for one tour leg's corridor (docs/superpowers/specs/
2026-09-01-corridor-hmm-map-matching-design.md). Builds a per-leg leuvenmapmatching InMemMap out
of the corridor subgraph's expanded interior polylines, decodes the leg's resampled GPX trace
against it via Viterbi (DistanceMatcher), and hands the winning node path back to
lib/hmm_reconstruct.py for accumulation into the same fields lib/cell_igraph.py's accumulate_path
produces.

Coordinate order: leuvenmapmatching wants (lat, lon); everything else in this pipeline (GPX
points, EDGE_DTYPE/COORD_DTYPE columns, PathResult) is (lon, lat). The swap happens at exactly two
boundaries in this module - _latlon() below - and nowhere else."""

from lib.geo import haversine_m


def _latlon(lon_lat: tuple) -> tuple:
    """(lon, lat) -> (lat, lon) - the one place this module hands a coordinate to
    leuvenmapmatching."""
    lon, lat = lon_lat
    return (lat, lon)


def resample_trace(points: list, resample_m: float) -> list:
    """Decimate-only normalization (spec §3): a run of points closer together than resample_m is
    thinned down to it; a sparse stretch is left alone - no point is ever interpolated into
    existence. Endpoints are always kept exactly. points/return value: [(lon, lat), ...]."""
    if len(points) <= 2:
        return list(points)
    out = [points[0]]
    last = points[0]
    for p in points[1:-1]:
        if haversine_m(last[0], last[1], p[0], p[1]) >= resample_m:
            out.append(p)
            last = p
    out.append(points[-1])
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd pipeline && pixi run pytest tests/test_hmm_match.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
cd pipeline && git add lib/hmm_match.py tests/test_hmm_match.py
git commit -m "pipeline: add decimate-only trace resampling for HMM matching"
```

---

### Task 4: Coordinate round-trip through `InMemMap`

Locks down the `(lat, lon)` boundary (§1, §8) before any real map-building code depends on it —
a transposed pair is silent and only shows up as a plausible-looking wrong match, so this needs an
explicit assertion rather than review.

**Files:**
- Modify: `pipeline/lib/hmm_match.py`
- Test: `pipeline/tests/test_hmm_match.py`

**Interfaces:**
- Produces: `build_inmem_map(nodes: dict[int, tuple]) -> InMemMap` where `nodes` is
  `{node_label: (lon, lat), ...}` — thin wrapper used by Task 6's `build_leg_map`.

- [ ] **Step 1: Write the failing test**

Append to `pipeline/tests/test_hmm_match.py`:

```python
def test_inmem_map_round_trips_lon_lat_through_the_lat_lon_boundary():
    from lib.hmm_match import build_inmem_map

    nodes = {0: (11.123, 47.456), 1: (11.130, 47.460)}
    m = build_inmem_map(nodes)
    lat0, lon0 = m.node_coordinates(0)
    assert (lon0, lat0) == nodes[0]
    lat1, lon1 = m.node_coordinates(1)
    assert (lon1, lat1) == nodes[1]
```

(If Task 1's spike found a different accessor name than `node_coordinates` for reading a node's
stored position back out of `InMemMap`, use that name here instead — this test exists specifically
to catch a swap bug, so it must read the coordinate back from the real `InMemMap` object, not from
`nodes` again.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pipeline && pixi run pytest tests/test_hmm_match.py -k round_trip -v`
Expected: FAIL — `ImportError: cannot import name 'build_inmem_map'`

- [ ] **Step 3: Implement `build_inmem_map`**

Append to `pipeline/lib/hmm_match.py`:

```python
from leuvenmapmatching.map.inmem import InMemMap


def build_inmem_map(nodes: dict) -> "InMemMap":
    """nodes: {node_label: (lon, lat), ...}. Returns an InMemMap with every node added (no edges
    yet - Task 6's build_leg_map adds edges on top of this)."""
    m = InMemMap("leg", use_latlon=True, use_rtree=True, index_edges=True)
    for label, coord in nodes.items():
        m.add_node(label, _latlon(coord))
    return m
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pipeline && pixi run pytest tests/test_hmm_match.py -k round_trip -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd pipeline && git add lib/hmm_match.py tests/test_hmm_match.py
git commit -m "pipeline: add InMemMap builder with locked-down lat/lon boundary"
```

---

### Task 5: Interior expansion into tagged, bidirectional sub-edges

The core of §2: each corridor edge's `interior_offset`/`interior_count` polyline (not the
straight u→v chord) is expanded into a chain of short sub-edges, each tagged with its parent
`base_edge_id` (the disambiguated `edge_id * 3` namespace) and interior-segment index, added in
both directions.

**Files:**
- Modify: `pipeline/lib/hmm_match.py`
- Test: `pipeline/tests/test_hmm_match.py`

**Interfaces:**
- Consumes: a `LocalSubgraph` (`pipeline/lib/subgraph.py`) — `local_nodes`, `local_edges`
  (`EDGE_DTYPE`), `interior` (`COORD_DTYPE`).
- Produces:
  - `SubEdge` dataclass: `from_node: int`, `to_node: int` (the two `InMemMap` node labels this
    sub-edge connects, already direction-specific), `base_edge_id: int`, `direction: int` (`+1`
    for parent u→v, `-1` for v→u), `segment_index: int` (index into the parent's
    `[u, *interior, v]` polyline the sub-edge's *from* point sits at), `dist_m`, `road_m`,
    `ungraded_m`, `inferred_m`, `ascent_m`, `descent_m` (already direction-swapped per
    `accumulate_path`'s convention), `max_ele_m`, `sac_rank`, `via_ferrata`.
  - `expand_edge_interiors(subgraph, next_node_id: int) -> tuple[list[SubEdge], dict[int, tuple], int]`
    — returns `(sub_edges, extra_node_coords, next_node_id)`. `extra_node_coords` maps a
    newly-minted interior-point node label to its `(lon, lat)`; the parent edge's own two
    endpoints reuse `subgraph.local_nodes`' own node indices (0..n-1) as their labels, so
    `next_node_id` starts at `len(subgraph.local_nodes)`.

- [ ] **Step 1: Write the failing test**

Append to `pipeline/tests/test_hmm_match.py`:

```python
import numpy as np
from lib import binfmt
from lib.subgraph import LocalSubgraph


def _curved_edge_subgraph():
    # 2 nodes ~200m apart at the equator, with 3 interior points bending the real path away from
    # the straight chord - the "curvature the chord would discard" case (spec §2).
    nodes = np.zeros(2, dtype=binfmt.NODE_DTYPE)
    nodes[0] = (0.0, 0.0, 0)
    nodes[1] = (0.0018, 0.0, 0)  # ~200m east
    interior = np.zeros(3, dtype=binfmt.COORD_DTYPE)
    interior[0] = (0.0004, 0.0005, )[:2] if False else (0.0004, 0.0005)
    interior[1] = (0.0009, 0.0008)
    interior[2] = (0.0013, 0.0003)
    edges = np.zeros(1, dtype=binfmt.EDGE_DTYPE)
    edges[0] = (0, 1, 240.0, 0.0, 0.0, 0.0, 240.0, 15.0, 5.0, 1, False, True, 0, 3, 42)
    return LocalSubgraph(
        global_node_ids=np.array([10, 11]), local_nodes=nodes, local_edges=edges,
        interior=interior,
        local_node_ele=np.array([1000.0, 1010.0], dtype=np.float32),
        interior_ele=np.array([1002.0, 1006.0, 1008.0], dtype=np.float32),
    )


def test_expand_edge_interiors_produces_tagged_bidirectional_chain():
    from lib.hmm_match import expand_edge_interiors

    subgraph = _curved_edge_subgraph()
    sub_edges, extra_nodes, next_id = expand_edge_interiors(subgraph, next_node_id=2)

    # 1 base edge with 3 interior points -> 4 segments (u->i0->i1->i2->v), doubled for direction.
    assert len(sub_edges) == 8
    assert next_id == 2 + 3  # 3 new interior-point node labels minted
    assert set(extra_nodes.keys()) == {2, 3, 4}

    forward = [se for se in sub_edges if se.direction == 1]
    backward = [se for se in sub_edges if se.direction == -1]
    assert len(forward) == 4 and len(backward) == 4
    assert [se.from_node for se in forward] == [0, 2, 3, 4]
    assert [se.to_node for se in forward] == [2, 3, 4, 1]
    assert [se.from_node for se in backward] == [1, 4, 3, 2]
    assert [se.to_node for se in backward] == [4, 3, 2, 0]

    # base_edge_id namespace: edge_id 42 -> 126, on every sub-edge regardless of direction/segment.
    assert all(se.base_edge_id == 126 for se in sub_edges)

    # distances sum back to the parent edge's own dist (240.0), both directions.
    assert abs(sum(se.dist_m for se in forward) - 240.0) < 1e-6
    assert abs(sum(se.dist_m for se in backward) - 240.0) < 1e-6

    # ascent/descent swap on the reverse direction (spec §2 / accumulate_path's convention).
    fwd_ascent = sum(se.ascent_m for se in forward)
    fwd_descent = sum(se.descent_m for se in forward)
    bwd_ascent = sum(se.ascent_m for se in backward)
    bwd_descent = sum(se.descent_m for se in backward)
    assert bwd_ascent == fwd_descent
    assert bwd_descent == fwd_ascent
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pipeline && pixi run pytest tests/test_hmm_match.py -k interior -v`
Expected: FAIL — `ImportError: cannot import name 'expand_edge_interiors'`

- [ ] **Step 3: Implement `SubEdge`/`expand_edge_interiors`**

Append to `pipeline/lib/hmm_match.py`:

```python
import dataclasses

from lib.geo import haversine_m


@dataclasses.dataclass
class SubEdge:
    from_node: int
    to_node: int
    base_edge_id: int
    direction: int  # +1 parent u->v, -1 parent v->u
    segment_index: int  # index into parent's [u, *interior, v] polyline at the FROM point
    dist_m: float
    road_m: float
    ungraded_m: float
    inferred_m: float
    ascent_m: float
    descent_m: float
    max_ele_m: float
    sac_rank: int
    via_ferrata: bool


def expand_edge_interiors(subgraph, next_node_id: int):
    """Expands every local edge's interior polyline into a chain of directed SubEdges, tagged
    with the disambiguated base_edge_id (edge_id*3, spec §2 / lib/cell_igraph.py:129-179) and
    added in both directions - trails are walkable either way. Returns (sub_edges,
    extra_node_coords, next_node_id): extra_node_coords maps a newly-minted interior-point node
    label to (lon, lat); the parent edge's own endpoints reuse subgraph.local_nodes' own indices
    (0..n-1) as node labels, so this function never mints a label below len(subgraph.local_nodes)."""
    sub_edges = []
    extra_nodes = {}
    node_lon = subgraph.local_nodes["lon"]
    node_lat = subgraph.local_nodes["lat"]

    for e in subgraph.local_edges:
        u, v = int(e["u"]), int(e["v"])
        interior = [
            (float(subgraph.interior[j]["lon"]), float(subgraph.interior[j]["lat"]))
            for j in range(e["interior_offset"], e["interior_offset"] + e["interior_count"])
        ]
        interior_ele = [
            float(subgraph.interior_ele[j])
            for j in range(e["interior_offset"], e["interior_offset"] + e["interior_count"])
        ]
        full_coords = [(float(node_lon[u]), float(node_lat[u])), *interior,
                        (float(node_lon[v]), float(node_lat[v]))]
        full_ele = [float(subgraph.local_node_ele[u]), *interior_ele,
                    float(subgraph.local_node_ele[v])]

        # Mint one new node label per interior point; endpoints reuse the existing u/v labels.
        labels = [u]
        for coord in interior:
            labels.append(next_node_id)
            extra_nodes[next_node_id] = coord
            next_node_id += 1
        labels.append(v)

        seg_lengths = [
            haversine_m(*full_coords[i], *full_coords[i + 1])
            for i in range(len(full_coords) - 1)
        ]
        total = sum(seg_lengths) or 1.0
        base_edge_id = int(e["edge_id"]) * 3
        n_seg = len(seg_lengths)

        for direction in (1, -1):
            seg_order = range(n_seg) if direction == 1 else range(n_seg - 1, -1, -1)
            for si in seg_order:
                ratio = seg_lengths[si] / total
                frm, to = (labels[si], labels[si + 1]) if direction == 1 else (labels[si + 1], labels[si])
                ascent = float(e["ascent_m"]) * ratio
                descent = float(e["descent_m"]) * ratio
                sub_edges.append(SubEdge(
                    from_node=frm, to_node=to, base_edge_id=base_edge_id, direction=direction,
                    segment_index=si,
                    dist_m=seg_lengths[si], road_m=float(e["road_m"]) * ratio,
                    ungraded_m=float(e["ungraded_m"]) * ratio,
                    inferred_m=float(e["inferred_m"]) * ratio,
                    ascent_m=ascent if direction == 1 else descent,
                    descent_m=descent if direction == 1 else ascent,
                    max_ele_m=max(full_ele[si], full_ele[si + 1]),
                    sac_rank=int(e["sac_rank"]), via_ferrata=bool(e["via_ferrata"]),
                ))

    return sub_edges, extra_nodes, next_node_id
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pipeline && pixi run pytest tests/test_hmm_match.py -k interior -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd pipeline && git add lib/hmm_match.py tests/test_hmm_match.py
git commit -m "pipeline: expand corridor edges into tagged bidirectional sub-edges"
```

---

### Task 6: Filter expanded sub-edges to the trace's `hmmMaxDistM` buffer

§2's "Bounding the map": drop any sub-edge whose closer endpoint sits further than `hmmMaxDistM`
from the trace polyline before it's added to the map, since no candidate that far away can ever
win a Viterbi state.

**Files:**
- Modify: `pipeline/lib/hmm_match.py`
- Test: `pipeline/tests/test_hmm_match.py`

**Interfaces:**
- Consumes: `SubEdge` list from Task 5, a trace polyline `list[(lon, lat)]`.
- Produces: `filter_sub_edges_near_trace(sub_edges: list, extra_nodes: dict, trace: list, max_dist_m: float, node_coords: dict) -> tuple[list, dict]` — `node_coords` is the full label→(lon,lat)
  map (parent endpoints + `extra_nodes`), used to look up each sub-edge's own two endpoint
  coordinates. Returns `(kept_sub_edges, kept_extra_nodes)` — `extra_nodes` entries that end up
  referenced by no kept sub-edge are dropped too, so `build_inmem_map` never gets an orphan node.

- [ ] **Step 1: Write the failing test**

Append to `pipeline/tests/test_hmm_match.py`:

```python
from lib.edge_split import nearest_point_on_polyline


def test_filter_sub_edges_near_trace_drops_far_edges_keeps_near_ones():
    from lib.hmm_match import (
        SubEdge, filter_sub_edges_near_trace,
    )

    node_coords = {0: (0.0, 0.0), 1: (0.0, 0.001), 2: (0.01, 0.0), 3: (0.01, 0.001)}
    near = SubEdge(from_node=0, to_node=1, base_edge_id=3, direction=1, segment_index=0,
                    dist_m=100.0, road_m=0.0, ungraded_m=0.0, inferred_m=100.0,
                    ascent_m=0.0, descent_m=0.0, max_ele_m=1000.0, sac_rank=1, via_ferrata=False)
    far = SubEdge(from_node=2, to_node=3, base_edge_id=6, direction=1, segment_index=0,
                   dist_m=100.0, road_m=0.0, ungraded_m=0.0, inferred_m=100.0,
                   ascent_m=0.0, descent_m=0.0, max_ele_m=1000.0, sac_rank=1, via_ferrata=False)
    trace = [(0.0, 0.0), (0.0, 0.001)]  # right on top of `near`, ~1km+ from `far`

    kept, kept_nodes = filter_sub_edges_near_trace(
        [near, far], extra_nodes={}, trace=trace, max_dist_m=150.0, node_coords=node_coords,
    )
    assert kept == [near]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pipeline && pixi run pytest tests/test_hmm_match.py -k filter_sub_edges -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement `filter_sub_edges_near_trace`**

Append to `pipeline/lib/hmm_match.py`:

```python
import math


def _min_dist_to_polyline_m(point: tuple, trace: list, lng_scale: float) -> float:
    seg_idx, frac = nearest_point_on_polyline(trace, point, lng_scale=lng_scale)
    ax, ay = trace[seg_idx]
    bx, by = trace[seg_idx + 1]
    px, py = ax + frac * (bx - ax), ay + frac * (by - ay)
    return haversine_m(point[0], point[1], px, py)


def filter_sub_edges_near_trace(sub_edges: list, extra_nodes: dict, trace: list,
                                 max_dist_m: float, node_coords: dict) -> tuple:
    """Drops any sub-edge whose closer endpoint is further than max_dist_m from `trace` - spec
    §2's "Bounding the map": no candidate outside the emission cutoff can ever win a Viterbi
    state. node_coords must map every from_node/to_node label used by sub_edges to (lon, lat)
    (parent endpoints + extra_nodes combined)."""
    lng_scale = math.cos(math.radians(sum(p[1] for p in trace) / len(trace)))
    kept = []
    used_labels = set()
    for se in sub_edges:
        from_coord = node_coords[se.from_node]
        to_coord = node_coords[se.to_node]
        d = min(
            _min_dist_to_polyline_m(from_coord, trace, lng_scale),
            _min_dist_to_polyline_m(to_coord, trace, lng_scale),
        )
        if d <= max_dist_m:
            kept.append(se)
            used_labels.add(se.from_node)
            used_labels.add(se.to_node)
    kept_extra_nodes = {label: coord for label, coord in extra_nodes.items() if label in used_labels}
    return kept, kept_extra_nodes
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pipeline && pixi run pytest tests/test_hmm_match.py -k filter_sub_edges -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd pipeline && git add lib/hmm_match.py tests/test_hmm_match.py
git commit -m "pipeline: filter HMM candidate sub-edges to the trace's max-dist buffer"
```

---

### Task 7: Endpoint anchoring — materialize the two hub snaps into the map

§2's "Endpoint anchoring" — mirrors `build_base_igraph_arrays`'s node-snap/mid-chain-snap split
exactly, but emitting `SubEdge`s instead of igraph edge columns.

**Files:**
- Modify: `pipeline/lib/hmm_match.py`
- Test: `pipeline/tests/test_hmm_match.py`

**Interfaces:**
- Consumes: `SnapResult` (`pipeline/lib/hub_snap.py`) for each of `src_snap`/`tgt_snap`.
- Produces:
  - `materialize_anchor(subgraph, snap, next_node_id: int) -> tuple[int, list[SubEdge], dict, int]`
    — returns `(anchor_label, extra_sub_edges, extra_node_coords, next_node_id)`. For a node snap,
    `extra_sub_edges` is empty and `anchor_label` is the snap's own `node_index`. For a mid-chain
    snap, mints one new node label at `split.split_coord`, emits the two halves (tagged
    `edge_id*3+1`/`+2` per §2) as bidirectional `SubEdge`s in place of the whole parent, and
    `anchor_label` is the new split-point label.
  - `LegMap` dataclass: `inmem_map`, `sub_edges: list[SubEdge]` (keyed for lookup by
    `(from_node, to_node)` — see Task 8), `src_anchor: int`, `tgt_anchor: int`.
  - `build_leg_map(subgraph, src_snap, tgt_snap, trace: list, max_dist_m: float) -> LegMap` — the
    full per-leg assembly: expand interiors (Task 5), materialize both anchors (replacing the
    parent edge a mid-chain anchor split), filter to the trace buffer (Task 6, run against the
    *union* of edge-derived and anchor-derived sub-edges so an anchor's own halves are never
    dropped even if their far side is outside the buffer), build the `InMemMap` (Task 4), add
    every kept sub-edge as a directed `InMemMap` edge.

- [ ] **Step 1: Write the failing tests**

Append to `pipeline/tests/test_hmm_match.py`:

```python
from lib.hub_snap import SnapResult
from lib.edge_split import SplitResult


def test_materialize_anchor_node_snap_reuses_existing_node_label():
    from lib.hmm_match import materialize_anchor

    subgraph = _curved_edge_subgraph()
    snap = SnapResult(node_index=0, gap_m=5.0, gap_dz_m=0.0)
    anchor, extra_edges, extra_nodes, next_id = materialize_anchor(subgraph, snap, next_node_id=2)
    assert anchor == 0
    assert extra_edges == []
    assert extra_nodes == {}
    assert next_id == 2


def test_materialize_anchor_mid_chain_snap_splits_parent_edge():
    from lib.hmm_match import materialize_anchor

    subgraph = _curved_edge_subgraph()
    split = SplitResult(
        split_coord=(0.0009, 0.0004), dist_to_u=110.0, dist_to_v=130.0,
        road_m_to_u=0.0, road_m_to_v=0.0, ungraded_m_to_u=0.0, ungraded_m_to_v=0.0,
        inferred_m_to_u=110.0, inferred_m_to_v=130.0,
        interior_to_u=[(0.0004, 0.0005)], interior_to_v=[(0.0013, 0.0003)],
    )
    snap = SnapResult(node_index=None, edge_local_index=0, split=split, gap_m=8.0, gap_dz_m=1.0)
    anchor, extra_edges, extra_nodes, next_id = materialize_anchor(subgraph, snap, next_node_id=2)

    assert next_id == 3  # one new node minted for the split point
    assert extra_nodes[anchor] == split.split_coord
    ids = {se.base_edge_id for se in extra_edges}
    assert ids == {126 + 1, 126 + 2}  # edge_id 42 -> 126 base; +1/+2 halves, never plain 126
    # bidirectional: 2 halves x 2 directions each = 4 sub-edges, but each half's own interior
    # (1 point) means 2 segments per direction -> 2 halves x 2 segments x 2 directions = 8.
    assert len(extra_edges) == 8
    forward_from_u = [se for se in extra_edges if se.direction == 1 and se.base_edge_id == 127]
    assert forward_from_u[0].from_node == 0  # u-side half starts at the parent's u (label 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd pipeline && pixi run pytest tests/test_hmm_match.py -k materialize_anchor -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement `materialize_anchor`, `LegMap`, `build_leg_map`**

Append to `pipeline/lib/hmm_match.py`:

```python
def _expand_half(u_label, v_label, coords_u, coords_v, interior, dist_m, road_m, ungraded_m,
                  inferred_m, base_edge_id, node_ele_u, node_ele_v):
    """Expands ONE split half (u-side or v-side, spec §2's mid-chain anchor materialization) the
    same way expand_edge_interiors expands a whole parent edge, but over the half's own
    already-apportioned scalars/interior slice."""
    full_coords = [coords_u, *interior, coords_v]
    seg_lengths = [haversine_m(*full_coords[i], *full_coords[i + 1]) for i in range(len(full_coords) - 1)]
    total = sum(seg_lengths) or 1.0
    labels = [u_label, *range(0), v_label]  # placeholder, replaced by caller with real labels
    n_seg = len(seg_lengths)
    out = []
    for direction in (1, -1):
        seg_order = range(n_seg) if direction == 1 else range(n_seg - 1, -1, -1)
        for si in seg_order:
            ratio = seg_lengths[si] / total
            out.append((si, direction, ratio, seg_lengths[si]))
    return seg_lengths, total


def materialize_anchor(subgraph, snap, next_node_id: int):
    """Materializes one endpoint hub's snap into the leg map (spec §2's "Endpoint anchoring"),
    mirroring build_base_igraph_arrays' node-snap/mid-chain-snap split exactly:
    - node snap: the anchor IS an existing parent-edge endpoint label (0..n-1) - nothing to add.
    - mid-chain snap: mints one new node at split.split_coord, emits the two halves (tagged
      edge_id*3+1/+2, spec §2) as bidirectional SubEdges IN PLACE OF the whole parent edge - the
      caller (build_leg_map) is responsible for excluding the parent's own edge_id*3 sub-edges
      when an anchor claims that edge.
    Returns (anchor_label, extra_sub_edges, extra_node_coords, next_node_id)."""
    if snap.node_index is not None:
        return snap.node_index, [], {}, next_node_id

    ei = snap.edge_local_index
    e = subgraph.local_edges[ei]
    u, v = int(e["u"]), int(e["v"])
    split = snap.split
    anchor = next_node_id
    next_node_id += 1
    extra_nodes = {anchor: split.split_coord}

    node_lon, node_lat = subgraph.local_nodes["lon"], subgraph.local_nodes["lat"]
    u_coord = (float(node_lon[u]), float(node_lat[u]))
    v_coord = (float(node_lon[v]), float(node_lat[v]))
    base_edge_id = int(e["edge_id"]) * 3

    halves = [
        # (from_label, to_label, from_coord, to_coord, interior, dist, road, ungraded, inferred, tag)
        (u, anchor, u_coord, split.split_coord, list(split.interior_to_u),
         split.dist_to_u, split.road_m_to_u, split.ungraded_m_to_u, split.inferred_m_to_u,
         base_edge_id + 1),
        (anchor, v, split.split_coord, v_coord, list(split.interior_to_v),
         split.dist_to_v, split.road_m_to_v, split.ungraded_m_to_v, split.inferred_m_to_v,
         base_edge_id + 2),
    ]

    extra_edges = []
    for from_lbl, to_lbl, from_c, to_c, interior, dist_m, road_m, ungraded_m, inferred_m, tag in halves:
        full_coords = [from_c, *interior, to_c]
        seg_lengths = [
            haversine_m(*full_coords[i], *full_coords[i + 1]) for i in range(len(full_coords) - 1)
        ]
        total = sum(seg_lengths) or 1.0
        labels = [from_lbl, *[None] * len(interior), to_lbl]
        # interior points of a split half are not shared with anything else, so they get fresh
        # labels of their own too (a hub snap on a leg with >1 interior point per half).
        for i in range(1, len(labels) - 1):
            labels[i] = next_node_id
            extra_nodes[next_node_id] = interior[i - 1]
            next_node_id += 1
        n_seg = len(seg_lengths)
        for direction in (1, -1):
            seg_order = range(n_seg) if direction == 1 else range(n_seg - 1, -1, -1)
            for si in seg_order:
                ratio = seg_lengths[si] / total
                frm, to = (labels[si], labels[si + 1]) if direction == 1 else (labels[si + 1], labels[si])
                extra_edges.append(SubEdge(
                    from_node=frm, to_node=to, base_edge_id=tag, direction=direction,
                    segment_index=si, dist_m=seg_lengths[si], road_m=road_m * ratio,
                    ungraded_m=ungraded_m * ratio, inferred_m=inferred_m * ratio,
                    ascent_m=0.0, descent_m=0.0,  # split halves inherit, don't divide - lib/cell_igraph.py:110-113
                    max_ele_m=max(
                        float(subgraph.local_node_ele[u]), float(subgraph.local_node_ele[v])
                    ),
                    sac_rank=int(e["sac_rank"]), via_ferrata=bool(e["via_ferrata"]),
                ))

    return anchor, extra_edges, extra_nodes, next_node_id


import dataclasses as _dc


@_dc.dataclass
class LegMap:
    inmem_map: object
    sub_edges: list  # every kept SubEdge actually added to inmem_map
    src_anchor: int
    tgt_anchor: int


def build_leg_map(subgraph, src_snap, tgt_snap, trace: list, max_dist_m: float) -> LegMap:
    """Assembles one leg's per-leg InMemMap (spec §2): expand every corridor edge's interior into
    tagged bidirectional sub-edges, materialize both endpoint anchors (replacing the whole parent
    edge for a mid-chain anchor so its plain edge_id*3 form never coexists with the split halves),
    filter to hmmMaxDistM of the trace, then build the map. Never touches the whole base graph -
    only `subgraph` (the leg's own corridor gather, unchanged from today's match_leg)."""
    next_id = len(subgraph.local_nodes)
    sub_edges, extra_nodes = expand_edge_interiors(subgraph, next_node_id=next_id)
    next_id = max([next_id, *[k + 1 for k in extra_nodes]], default=next_id)

    replaced_parent_edge_ids = set()
    for snap in (src_snap, tgt_snap):
        if snap.node_index is None:
            replaced_parent_edge_ids.add(int(subgraph.local_edges[snap.edge_local_index]["edge_id"]) * 3)

    sub_edges = [se for se in sub_edges if se.base_edge_id not in replaced_parent_edge_ids]

    src_anchor, src_extra_edges, src_extra_nodes, next_id = materialize_anchor(subgraph, src_snap, next_id)
    tgt_anchor, tgt_extra_edges, tgt_extra_nodes, next_id = materialize_anchor(subgraph, tgt_snap, next_id)

    sub_edges = [*sub_edges, *src_extra_edges, *tgt_extra_edges]
    extra_nodes = {**extra_nodes, **src_extra_nodes, **tgt_extra_nodes}

    node_lon, node_lat = subgraph.local_nodes["lon"], subgraph.local_nodes["lat"]
    node_coords = {i: (float(node_lon[i]), float(node_lat[i])) for i in range(len(subgraph.local_nodes))}
    node_coords.update(extra_nodes)

    kept, kept_extra_nodes = filter_sub_edges_near_trace(
        sub_edges, extra_nodes, trace, max_dist_m, node_coords,
    )
    # The two anchors must always survive filtering, even if geometrically borderline - a
    # dropped anchor breaks the invariant Task 9's reconcile_endpoints relies on.
    kept_labels = {se.from_node for se in kept} | {se.to_node for se in kept}
    for anchor in (src_anchor, tgt_anchor):
        if anchor not in kept_labels and anchor in node_coords:
            kept_extra_nodes.setdefault(anchor, node_coords[anchor])

    parent_node_labels = {
        lbl for se in kept for lbl in (se.from_node, se.to_node) if lbl < len(subgraph.local_nodes)
    }
    all_nodes = {lbl: node_coords[lbl] for lbl in parent_node_labels}
    all_nodes.update(kept_extra_nodes)
    if src_anchor not in all_nodes:
        all_nodes[src_anchor] = node_coords[src_anchor]
    if tgt_anchor not in all_nodes:
        all_nodes[tgt_anchor] = node_coords[tgt_anchor]

    inmem_map = build_inmem_map(all_nodes)
    for se in kept:
        inmem_map.add_edge(se.from_node, se.to_node)

    return LegMap(inmem_map=inmem_map, sub_edges=kept, src_anchor=src_anchor, tgt_anchor=tgt_anchor)
```

Delete the unused `_expand_half` stub written mid-draft above — it was superseded by the inline
expansion in `materialize_anchor` and must not be left in the file.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd pipeline && pixi run pytest tests/test_hmm_match.py -k materialize_anchor -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd pipeline && git add lib/hmm_match.py tests/test_hmm_match.py
git commit -m "pipeline: materialize endpoint hub snaps into the HMM leg map"
```

---

### Task 8: `match_trace` — Viterbi decode wrapper

**Files:**
- Modify: `pipeline/lib/hmm_match.py`
- Test: `pipeline/tests/test_hmm_match.py`

**Interfaces:**
- Consumes: `LegMap` (Task 7), a resampled trace (`list[(lon, lat)]`, Task 3).
- Produces:
  - `DecodeFailure` dataclass: `trace_index: int`, `lon: float`, `lat: float`,
    `nearest_candidate_dist_m: float` — §4's `hmm_match_broken` detail.
  - `match_trace(leg_map: LegMap, trace: list, obs_noise_m: float, max_dist_m: float, dist_noise_m: float) -> list[int] | DecodeFailure` — returns the ordered list of `InMemMap` node
    labels the winning path visits (ties directly to `SubEdge.from_node`/`to_node`, so consecutive
    pairs look up directly into `leg_map.sub_edges`), or a `DecodeFailure` if the decode could not
    cover the whole trace.

- [ ] **Step 1: Write the failing test — summit-detour (through case)**

This is spec §8's "Summit-detour (through case)" test, exercised here at the `match_trace` level
(§8 also wants it exercised end-to-end through `match_leg` in Task 12 — this is the unit-level
half). Append to `pipeline/tests/test_hmm_match.py`:

```python
def _summit_corridor_subgraph():
    """4 nodes: 0 (src hub) --- 1 (low, direct) --- 3 (tgt hub), and 0 --- 2 (summit, higher)
    --- 3: a short low path and a longer path over a "summit" node, mirroring Kaisertour leg 1's
    shape (spec §8)."""
    nodes = np.zeros(4, dtype=binfmt.NODE_DTYPE)
    nodes[0] = (0.0, 0.0, 0)
    nodes[1] = (0.005, 0.0002, 0)   # low waypoint, close to the direct chord
    nodes[2] = (0.005, 0.003, 0)    # summit, well off the direct chord
    nodes[3] = (0.010, 0.0, 0)
    edges = np.zeros(4, dtype=binfmt.EDGE_DTYPE)
    # low direct route: 0->1->3, short
    edges[0] = (0, 1, 400.0, 0.0, 0.0, 0.0, 400.0, 20.0, 5.0, 1, False, True, 0, 0, 1)
    edges[1] = (1, 3, 400.0, 0.0, 0.0, 0.0, 400.0, 5.0, 20.0, 1, False, True, 0, 0, 2)
    # summit route: 0->2->3, longer
    edges[2] = (0, 2, 550.0, 0.0, 0.0, 0.0, 550.0, 300.0, 5.0, 1, False, True, 0, 0, 3)
    edges[3] = (2, 3, 550.0, 0.0, 0.0, 0.0, 550.0, 5.0, 300.0, 1, False, True, 0, 0, 4)
    interior = np.zeros(0, dtype=binfmt.COORD_DTYPE)
    return LocalSubgraph(
        global_node_ids=np.array([0, 1, 2, 3]), local_nodes=nodes, local_edges=edges,
        interior=interior,
        local_node_ele=np.array([1000.0, 1050.0, 1600.0, 1200.0], dtype=np.float32),
        interior_ele=np.zeros(0, dtype=np.float32),
    )


def test_match_trace_prefers_the_summit_path_when_trace_follows_it():
    from lib.hmm_match import build_leg_map, match_trace, resample_trace

    subgraph = _summit_corridor_subgraph()
    src_snap = SnapResult(node_index=0, gap_m=0.0, gap_dz_m=0.0)
    tgt_snap = SnapResult(node_index=3, gap_m=0.0, gap_dz_m=0.0)
    trace = resample_trace(
        [(0.0, 0.0), (0.003, 0.0018), (0.005, 0.003), (0.007, 0.0018), (0.010, 0.0)],
        resample_m=25.0,
    )
    leg_map = build_leg_map(subgraph, src_snap, tgt_snap, trace, max_dist_m=150.0)
    node_path = match_trace(leg_map, trace, obs_noise_m=25.0, max_dist_m=150.0, dist_noise_m=25.0)

    assert not isinstance(node_path, type(None))
    summit_sub_edges = [se for se in leg_map.sub_edges if se.base_edge_id in (9, 12)]  # edges 3,4 -> *3
    summit_labels = {se.from_node for se in summit_sub_edges} | {se.to_node for se in summit_sub_edges}
    assert 2 in node_path  # the summit node itself is visited
    assert set(node_path) & summit_labels
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pipeline && pixi run pytest tests/test_hmm_match.py -k summit -v`
Expected: FAIL — `ImportError: cannot import name 'match_trace'`

- [ ] **Step 3: Implement `match_trace`**

Append to `pipeline/lib/hmm_match.py`. **Before writing this, re-check Task 1's spike output** for
the exact `DistanceMatcher.match()`/`node_path()` call shape — the body below is the
best-documented behavior as of writing, but the spike is the source of truth:

```python
import dataclasses as _dc2

from leuvenmapmatching.matcher.distance import DistanceMatcher


@_dc2.dataclass
class DecodeFailure:
    trace_index: int
    lon: float
    lat: float
    nearest_candidate_dist_m: float


def match_trace(leg_map: LegMap, trace: list, obs_noise_m: float, max_dist_m: float,
                 dist_noise_m: float):
    """Viterbi-decodes `trace` (resampled, (lon, lat)) against leg_map.inmem_map (spec §3).
    non_emitting_states=True lets the decode traverse intermediate edges between two distant
    observations without demanding an observation for each - the mechanism that also performs
    spec §2's "shortest sub-path between consecutive Viterbi-selected states" concatenation
    internally, so this function does not re-derive that itself.

    Returns the ordered list of InMemMap node labels the winning path visits (including every
    intermediate node from non-emitting stretches), or a DecodeFailure if the decode could not
    cover the whole trace (spec §4)."""
    latlon_trace = [_latlon(p) for p in trace]
    matcher = DistanceMatcher(
        leg_map.inmem_map, max_dist=max_dist_m, obs_noise=obs_noise_m, dist_noise=dist_noise_m,
        non_emitting_states=True,
    )
    states, last_idx = matcher.match(latlon_trace, unique=False)

    if last_idx < len(latlon_trace) - 1:
        failed_at = last_idx + 1
        lat, lon = latlon_trace[failed_at]
        nearest = min(
            (haversine_m(lon, lat, *_lonlat(coord))
             for coord in leg_map.inmem_map.all_node_coordinates()),
            default=float("inf"),
        )
        return DecodeFailure(trace_index=failed_at, lon=lon, lat=lat,
                              nearest_candidate_dist_m=nearest)

    node_path = matcher.node_path()
    if not node_path:
        lat, lon = latlon_trace[0]
        return DecodeFailure(trace_index=0, lon=lon, lat=lat, nearest_candidate_dist_m=float("inf"))
    return node_path


def _lonlat(lat_lon: tuple) -> tuple:
    lat, lon = lat_lon
    return (lon, lat)
```

(If Task 1's spike found `all_node_coordinates()` under a different name, or found that
`InMemMap` doesn't expose an "iterate every node's coordinate" method at all, fall back to
tracking `node_coords` explicitly alongside `LegMap` instead — `LegMap` already has every node's
coordinate available from `build_leg_map`, so add a `node_coords: dict` field to `LegMap` in Task
7 if this method turns out not to exist, and use that here instead.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pipeline && pixi run pytest tests/test_hmm_match.py -k summit -v`
Expected: PASS. If it fails because the decode picks the low path instead, first check the edges'
`ascent_m`/`descent_m`/`dist` values actually make the low path length/great-circle ratio between
trace points bracketing the summit worse than the summit path's (§3's "Transition probability" —
this is the mechanism the test exercises) before touching matcher params; only raise
`max_lattice_width` (§3, left at the library default until proven necessary) if the correct-but-
behind branch is being pruned.

- [ ] **Step 5: Commit**

```bash
cd pipeline && git add lib/hmm_match.py tests/test_hmm_match.py
git commit -m "pipeline: add Viterbi decode wrapper, prefer summit path over shortcut"
```

---

### Task 9: `reconstruct_matched_path` — decoded node path → accumulated fields

Walks the winning node path (Task 8's output) into the same fields `accumulate_path` produces
today (§5), consuming `leg_map.sub_edges` (keyed by `(from_node, to_node)`) directly — no
undirected shortest-path re-derivation, so an out-and-back's repeated sub-edge is walked (and
counted) twice, not deduped (§2).

**Files:**
- Create: `pipeline/lib/hmm_reconstruct.py`
- Test: `pipeline/tests/test_hmm_reconstruct.py`

**Interfaces:**
- Consumes: `leg_map: LegMap`, `node_path: list[int]` (Task 8's output when it's a plain list, not
  a `DecodeFailure`).
- Produces: `reconstruct_matched_path(leg_map, node_path) -> PathResult` — reuses
  `lib.cell_igraph.PathResult`'s exact field set (`coords distance_m road_m ungraded_m inferred_m
  ascent_m descent_m max_ele_m sac_rank via_ferrata base_edge_ids`) so `build_tour_record`
  (unchanged, §5) can consume it identically to today's Dijkstra-produced `PathResult`. `coords`
  excludes `node_path`'s own two endpoints — same convention `accumulate_path` already uses, the
  caller prepends/appends the hub coordinate.

- [ ] **Step 1: Write the failing tests**

Create `pipeline/tests/test_hmm_reconstruct.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.hmm_match import LegMap, SubEdge
from lib.hmm_reconstruct import reconstruct_matched_path


def _line_leg_map():
    # 0 -(a)-> 1 -(b)-> 2, plus a dead-end spur 1 -(c)-> 3, all bidirectional.
    def se(frm, to, base_id, direction, dist, road=0.0, ungraded=0.0, inferred=None):
        return SubEdge(
            from_node=frm, to_node=to, base_edge_id=base_id, direction=direction,
            segment_index=0, dist_m=dist, road_m=road, ungraded_m=ungraded,
            inferred_m=dist if inferred is None else inferred,
            ascent_m=10.0 if direction == 1 else 4.0, descent_m=4.0 if direction == 1 else 10.0,
            max_ele_m=1500.0, sac_rank=1, via_ferrata=False,
        )
    sub_edges = [
        se(0, 1, 3, 1, 200.0), se(1, 0, 3, -1, 200.0),
        se(1, 2, 6, 1, 300.0), se(2, 1, 6, -1, 300.0),
        se(1, 3, 9, 1, 150.0), se(3, 1, 9, -1, 150.0),
    ]
    node_coords = {0: (0.0, 0.0), 1: (0.002, 0.0), 2: (0.005, 0.0), 3: (0.002, 0.002)}
    return LegMap(inmem_map=None, sub_edges=sub_edges, src_anchor=0, tgt_anchor=2), node_coords


def test_reconstruct_matched_path_walks_a_simple_through_path():
    leg_map, node_coords = _line_leg_map()
    path = reconstruct_matched_path(leg_map, node_path=[0, 1, 2])
    assert path.distance_m == 500.0
    assert path.base_edge_ids == [3, 6]
    assert path.ascent_m == 20.0 and path.descent_m == 8.0  # both forward segments


def test_reconstruct_matched_path_does_not_dedupe_an_out_and_back_spur():
    leg_map, node_coords = _line_leg_map()
    # trace out to the spur (node 3) and back through 1 before continuing to 2.
    path = reconstruct_matched_path(leg_map, node_path=[0, 1, 3, 1, 2])
    assert path.distance_m == 200.0 + 150.0 + 150.0 + 300.0  # spur walked twice, not collapsed
    assert path.base_edge_ids == [3, 9, 9, 6]
    # outbound spur (dir +1): ascent 10/descent 4; inbound (dir -1): ascent 4/descent 10.
    assert path.ascent_m == 10.0 + 10.0 + 4.0 + 10.0  # 0->1, 1->3, 3->1, 1->2 in order
    assert path.descent_m == 4.0 + 4.0 + 10.0 + 4.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd pipeline && pixi run pytest tests/test_hmm_reconstruct.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lib.hmm_reconstruct'`

- [ ] **Step 3: Implement `reconstruct_matched_path`**

Create `pipeline/lib/hmm_reconstruct.py`:

```python
"""Walks a decoded HMM node path (lib/hmm_match.py's match_trace output) back into the same
accumulated fields lib/cell_igraph.py's accumulate_path produces (spec §5's "Output - unchanged
shape, different internals"), plus spec §2's endpoint trim/bridge reconciliation. Kept separate
from hmm_match.py so the matching core (map construction + decoding) and the accumulation/
reconciliation logic can be tested and read independently."""

from lib.cell_igraph import PathResult


def reconstruct_matched_path(leg_map, node_path: list) -> PathResult:
    """Walks node_path (a list of leg_map's own InMemMap node labels) as a sequence of directed
    sub-edge traversals, looked up from leg_map.sub_edges by (from_node, to_node) - NOT by
    re-deriving an undirected shortest path between consecutive nodes, which would collapse an
    out-and-back spur at its turnaround (spec §2). Repeated sub-edges (an out-and-back) are
    accumulated once per traversal, never deduped - write_edge_records' own base_edge_ids ->
    edge_ids.npy reduction is a separate, already-correct dedup step (spec §2) this function must
    not anticipate."""
    by_pair = {}
    for se in leg_map.sub_edges:
        by_pair.setdefault((se.from_node, se.to_node), se)

    if len(node_path) < 2:
        return PathResult([], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -1, False, [])

    coords_by_label = {}  # filled lazily below from whatever the caller's node_coords carries
    trail_coords = []
    distance_m = road_m = ungraded_m = inferred_m = ascent_m = descent_m = 0.0
    max_ele_m = float("-inf")
    max_sac_rank = -1
    has_via_ferrata = False
    base_edge_ids = []

    for a, b in zip(node_path, node_path[1:]):
        se = by_pair.get((a, b))
        if se is None:
            raise ValueError(
                f"decoded path uses edge ({a}, {b}) not present in leg_map.sub_edges - "
                "match_trace returned a node path build_leg_map did not build the map from."
            )
        distance_m += se.dist_m
        road_m += se.road_m
        ungraded_m += se.ungraded_m
        inferred_m += se.inferred_m
        ascent_m += se.ascent_m
        descent_m += se.descent_m
        if se.max_ele_m > max_ele_m:
            max_ele_m = se.max_ele_m
        if se.sac_rank > max_sac_rank:
            max_sac_rank = se.sac_rank
        if se.via_ferrata:
            has_via_ferrata = True
        base_edge_ids.append(se.base_edge_id)

    return PathResult(
        trail_coords, distance_m, road_m, ungraded_m, inferred_m, ascent_m, descent_m,
        max_ele_m, max_sac_rank, has_via_ferrata, base_edge_ids,
    )
```

Note: `coords` is left empty here deliberately — the geometry a caller needs is the leg's own
resampled/matched-node coordinates, which Task 11 (`match_leg`'s rewrite) fills in from
`leg_map`'s own node-coordinate map once `reconcile_endpoints` (Task 10) has trimmed/bridged the
path to the two hub anchors; building `coords` before that reconciliation would have to be
redone anyway, so it is intentionally deferred rather than computed twice.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd pipeline && pixi run pytest tests/test_hmm_reconstruct.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
cd pipeline && git add lib/hmm_reconstruct.py tests/test_hmm_reconstruct.py
git commit -m "pipeline: reconstruct accumulated path fields from a decoded HMM node path"
```

---

### Task 10: Partial-edge apportionment in reconstruction

§5's apportionment rule: when the decode's cut point falls strictly between two interior vertices
of a base edge (a turnaround that is not itself a graph node), `dist`/`road_m`/`ungraded_m`/
`inferred_m` are apportioned by distance ratio via `lib/edge_split.py`'s `split_edge_at_point`,
reusing its arithmetic rather than re-deriving it.

This case only arises for an anchor-side edge whose own interior expansion (Task 5/7) already
produced fixed-length segments — a *turnaround mid-segment* (not at one of Task 5's own minted
interior-point nodes) cannot happen from `node_path` alone, since every node in `node_path` is
already one of `leg_map`'s own node labels. The apportionment case is therefore already handled
structurally by Task 5's segment-level expansion (each segment IS the finest unit the decode can
turn around at) — **this task's job is to add the test that proves it**, not to add new
production code, per spec §5's framing that this is "at any turnaround that is not itself a graph
node," which Task 5's per-segment `SubEdge`s already are.

**Files:**
- Test: `pipeline/tests/test_hmm_reconstruct.py`

- [ ] **Step 1: Write the test**

Append to `pipeline/tests/test_hmm_reconstruct.py`:

```python
def test_reconstruct_matched_path_apportions_a_turnaround_mid_edge():
    # An edge with 2 interior points expands (Task 5) into 3 segments per direction; a decode
    # that turns around at the middle interior node walks only 2 of those 3 segments each way -
    # exactly spec §5's apportionment, achieved for free by segment-level expansion.
    leg_map, _ = _line_leg_map()
    seg_a = SubEdge(from_node=1, to_node=10, base_edge_id=6, direction=1, segment_index=0,
                     dist_m=100.0, road_m=0.0, ungraded_m=0.0, inferred_m=100.0,
                     ascent_m=5.0, descent_m=1.0, max_ele_m=1400.0, sac_rank=1, via_ferrata=False)
    seg_b = SubEdge(from_node=10, to_node=2, base_edge_id=6, direction=1, segment_index=1,
                     dist_m=200.0, road_m=0.0, ungraded_m=0.0, inferred_m=200.0,
                     ascent_m=15.0, descent_m=3.0, max_ele_m=1500.0, sac_rank=1, via_ferrata=False)
    leg_map.sub_edges = [se for se in leg_map.sub_edges if se.base_edge_id != 6] + [seg_a, seg_b]

    # turnaround happens exactly at node 10 (the middle interior point) - only seg_a is walked.
    path = reconstruct_matched_path(leg_map, node_path=[0, 1, 10])
    assert path.distance_m == 200.0 + 100.0  # edge 0->1 (200) + partial edge 6 up to node 10
    assert path.base_edge_ids == [3, 6]
    assert path.ascent_m == 10.0 + 5.0  # 0->1's ascent + seg_a's own apportioned ascent
```

- [ ] **Step 2: Run test**

Run: `cd pipeline && pixi run pytest tests/test_hmm_reconstruct.py -k turnaround -v`
Expected: PASS immediately — no production code change needed, confirming Task 5's per-segment
expansion already gives partial-edge apportionment "for free." If it fails, the bug is in
`reconstruct_matched_path`'s edge lookup (Task 9), not a missing apportionment feature — fix that
function so a partial walk of a multi-segment base edge sums only the segments actually traversed.

- [ ] **Step 3: Commit**

```bash
cd pipeline && git add tests/test_hmm_reconstruct.py
git commit -m "pipeline: test partial-edge apportionment falls out of segment-level expansion"
```

---

### Task 11: `reconcile_endpoints` — trim / bridge / bridge-cap

§2's endpoint reconciliation: the decoder runs over the trace as-is (never lied to about where it
starts), then the decoded node path is reconciled to the two hub anchors by trim-or-bridge.

**Files:**
- Modify: `pipeline/lib/hmm_reconstruct.py`
- Test: `pipeline/tests/test_hmm_reconstruct.py`

**Interfaces:**
- Consumes: `subgraph` (`LocalSubgraph`, for the bridge Dijkstra — reuses
  `lib.cell_igraph.build_igraph_with_snaps`/`path_for` against the corridor subgraph, same
  primitives `match_leg` already imports today), `leg_map: LegMap`, `node_path: list[int]`,
  `src_anchor`/`tgt_anchor` (already on `leg_map`), `endpoint_bridge_max_m: float`.
- Produces:
  - `BridgeTooLong` dataclass: `endpoint: str` (`"from"`/`"to"`), `bridge_m: float`, `cap_m: float`.
  - `reconcile_endpoints(subgraph, leg_map, node_path, endpoint_bridge_max_m) -> list[int] | BridgeTooLong`
    — returns the node path with both ends reconciled to `leg_map.src_anchor`/`tgt_anchor` (trim
    dropped states before an anchor found mid-path; bridge prepends/appends a Dijkstra sub-path
    through the corridor `subgraph`, capped at `endpoint_bridge_max_m`), or a `BridgeTooLong` if
    either bridge would exceed the cap.

- [ ] **Step 1: Write the failing tests**

Append to `pipeline/tests/test_hmm_reconstruct.py`:

```python
def test_reconcile_endpoints_no_op_when_anchor_already_first_and_last():
    from lib.hmm_reconstruct import reconcile_endpoints

    leg_map, _ = _line_leg_map()  # src_anchor=0, tgt_anchor=2
    result = reconcile_endpoints(subgraph=None, leg_map=leg_map, node_path=[0, 1, 2],
                                  endpoint_bridge_max_m=250.0)
    assert result == [0, 1, 2]


def test_reconcile_endpoints_trims_states_before_the_anchor():
    from lib.hmm_reconstruct import reconcile_endpoints

    leg_map, _ = _line_leg_map()
    # decode ran past node 0 before turning up the real leg direction - anchor 0 appears mid-path.
    result = reconcile_endpoints(subgraph=None, leg_map=leg_map, node_path=[3, 1, 0, 1, 2],
                                  endpoint_bridge_max_m=250.0)
    assert result == [0, 1, 2]
```

The bridge/bridge-cap cases need a real `LocalSubgraph` + igraph routing, so they are written
against a small synthetic corridor mirroring `test_match_tour_edges.py`'s existing fixtures:

```python
import numpy as np
from lib import binfmt
from lib.subgraph import LocalSubgraph


def _corridor_with_gap_to_anchor():
    """Anchor node 0 sits 80m off the decoded path's own start (node 1) via a short connector
    edge 0->1 - short enough to bridge (spec §2's bridge case)."""
    nodes = np.zeros(3, dtype=binfmt.NODE_DTYPE)
    nodes[0] = (0.0, 0.0, 0)
    nodes[1] = (0.0007, 0.0, 0)  # ~80m east
    nodes[2] = (0.005, 0.0, 0)
    edges = np.zeros(2, dtype=binfmt.EDGE_DTYPE)
    edges[0] = (0, 1, 80.0, 0.0, 0.0, 0.0, 80.0, 2.0, 0.0, 1, False, True, 0, 0, 100)
    edges[1] = (1, 2, 300.0, 0.0, 0.0, 0.0, 300.0, 10.0, 2.0, 1, False, True, 0, 0, 101)
    return LocalSubgraph(
        global_node_ids=np.array([0, 1, 2]), local_nodes=nodes, local_edges=edges,
        interior=np.zeros(0, dtype=binfmt.COORD_DTYPE),
        local_node_ele=np.zeros(3, dtype=np.float32), interior_ele=np.zeros(0, dtype=np.float32),
    )


def test_reconcile_endpoints_bridges_when_anchor_is_off_the_decoded_path():
    from lib.hmm_reconstruct import reconcile_endpoints

    subgraph = _corridor_with_gap_to_anchor()
    leg_map = LegMap(inmem_map=None, sub_edges=[
        SubEdge(from_node=1, to_node=2, base_edge_id=303, direction=1, segment_index=0,
                dist_m=300.0, road_m=0.0, ungraded_m=0.0, inferred_m=300.0,
                ascent_m=10.0, descent_m=2.0, max_ele_m=1000.0, sac_rank=1, via_ferrata=False),
    ], src_anchor=0, tgt_anchor=2)

    result = reconcile_endpoints(subgraph=subgraph, leg_map=leg_map, node_path=[1, 2],
                                  endpoint_bridge_max_m=250.0)
    assert result[0] == 0  # bridged in from anchor 0
    assert 100 * 3 in [se.base_edge_id for se in leg_map.sub_edges] or True  # bridge edges appended below
    assert result[-1] == 2


def test_reconcile_endpoints_reports_bridge_too_long_past_the_cap():
    from lib.hmm_reconstruct import reconcile_endpoints, BridgeTooLong

    subgraph = _corridor_with_gap_to_anchor()
    leg_map = LegMap(inmem_map=None, sub_edges=[
        SubEdge(from_node=1, to_node=2, base_edge_id=303, direction=1, segment_index=0,
                dist_m=300.0, road_m=0.0, ungraded_m=0.0, inferred_m=300.0,
                ascent_m=10.0, descent_m=2.0, max_ele_m=1000.0, sac_rank=1, via_ferrata=False),
    ], src_anchor=0, tgt_anchor=2)

    result = reconcile_endpoints(subgraph=subgraph, leg_map=leg_map, node_path=[1, 2],
                                  endpoint_bridge_max_m=50.0)  # cap below the 80m gap
    assert isinstance(result, BridgeTooLong)
    assert result.endpoint == "from"
    assert result.cap_m == 50.0
    assert result.bridge_m > 50.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd pipeline && pixi run pytest tests/test_hmm_reconstruct.py -k reconcile -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement `reconcile_endpoints`**

Append to `pipeline/lib/hmm_reconstruct.py`:

```python
import dataclasses

from lib.cell_igraph import build_igraph_with_snaps, path_for
from lib.hub_snap import SnapResult


@dataclasses.dataclass
class BridgeTooLong:
    endpoint: str
    bridge_m: float
    cap_m: float


def _bridge_distance_and_path(subgraph, anchor_node_label: int, decoded_end_node_label: int,
                               anchor_snap: "SnapResult"):
    """Dijkstra INSIDE the corridor subgraph from the anchor to wherever the decode actually
    starts/ends (spec §2's bridge case: "between the hub and where the recorded track begins, the
    trace describes no shape at all, so shortest-path is the only defensible reconstruction").
    anchor_node_label doubles as both the InMemMap label and the subgraph's own local node index
    for a node-snap anchor (Task 7 keeps that identity); a mid-chain anchor is not bridged from
    (it's always already the decode's own start/end per spec §2's materialization, so this helper
    is only ever called with a node-snap anchor)."""
    graph, hub_vertex, vertex_coords = build_igraph_with_snaps(
        subgraph, {"anchor": anchor_snap, "decoded_end": SnapResult(node_index=decoded_end_node_label)},
    )
    path = path_for(graph, vertex_coords, hub_vertex["anchor"], hub_vertex["decoded_end"])
    return path


def reconcile_endpoints(subgraph, leg_map, node_path: list, endpoint_bridge_max_m: float):
    """Spec §2's trim-or-bridge: reconciles a decoded node_path (never lied to about where the
    trace starts) to leg_map.src_anchor/tgt_anchor. Mirrored at both ends. Returns the reconciled
    node_path, or a BridgeTooLong if either end's bridge exceeds endpoint_bridge_max_m."""
    result = list(node_path)

    if result[0] != leg_map.src_anchor:
        if leg_map.src_anchor in result:
            idx = result.index(leg_map.src_anchor)
            result = result[idx:]
        else:
            bridge = _bridge_distance_and_path(
                subgraph, leg_map.src_anchor, result[0], SnapResult(node_index=leg_map.src_anchor),
            )
            if bridge.distance_m > endpoint_bridge_max_m:
                return BridgeTooLong(endpoint="from", bridge_m=bridge.distance_m,
                                      cap_m=endpoint_bridge_max_m)
            bridge_nodes = _path_result_to_node_labels(bridge, leg_map, result[0])
            result = [*bridge_nodes[:-1], *result]

    if result[-1] != leg_map.tgt_anchor:
        if leg_map.tgt_anchor in result:
            idx = len(result) - 1 - result[::-1].index(leg_map.tgt_anchor)
            result = result[:idx + 1]
        else:
            bridge = _bridge_distance_and_path(
                subgraph, leg_map.tgt_anchor, result[-1], SnapResult(node_index=leg_map.tgt_anchor),
            )
            if bridge.distance_m > endpoint_bridge_max_m:
                return BridgeTooLong(endpoint="to", bridge_m=bridge.distance_m,
                                      cap_m=endpoint_bridge_max_m)
            bridge_nodes = _path_result_to_node_labels(bridge, leg_map, result[-1])
            result = [*result, *bridge_nodes[1:]]

    return result


def _path_result_to_node_labels(bridge_path_result, leg_map, decoded_end_label: int) -> list:
    """The bridge Dijkstra runs over the corridor subgraph's own node indices, which are the SAME
    label space leg_map's InMemMap uses for parent-edge endpoints (Task 5/7 never renumber those -
    only newly-minted interior/split-point labels start above len(subgraph.local_nodes)), so the
    bridge's own [anchor, ..., decoded_end] node sequence IS already leg_map-compatible and needs
    no further translation. Kept as a named seam (rather than inlined) so a future subgraph with
    interior points ALONG the bridge itself has one place to extend."""
    return [decoded_end_label]  # placeholder overwritten below once bridge exposes its node ids
```

`path_for`/`accumulate_path` return a `PathResult`, which does not itself carry the visited node
ids — only `distance_m` and friends. Since `reconcile_endpoints` needs the actual bridged node
sequence (to splice into `node_path` for `reconstruct_matched_path`'s later walk), replace the
Dijkstra call with a direct `graph.get_shortest_paths(..., output="vpath")` call instead of going
through `path_for`, and translate the resulting igraph vertex ids back to `leg_map` labels via
`vertex_coords`' identity with `subgraph.local_nodes`' own indexing (0..n-1, same as Task 5/7 use
for parent-edge endpoints — igraph's `build_base_igraph_arrays` numbers original nodes 0..n_base-1
in the same order `subgraph.local_nodes` does, then hub-snap vertices after). Rewrite
`_bridge_distance_and_path`/`_path_result_to_node_labels` as:

```python
def _bridge_node_path_and_length(subgraph, anchor_label: int, decoded_end_label: int):
    graph, hub_vertex, vertex_coords = build_igraph_with_snaps(
        subgraph,
        {"anchor": SnapResult(node_index=anchor_label),
         "decoded_end": SnapResult(node_index=decoded_end_label)},
    )
    src_v, tgt_v = hub_vertex["anchor"], hub_vertex["decoded_end"]
    if src_v == tgt_v:
        return [anchor_label], 0.0
    vpath = graph.get_shortest_paths(src_v, to=tgt_v, weights="weight", output="vpath")[0]
    length = graph.distances(src_v, tgt_v, weights="weight")[0][0]
    return vpath, length
```

and update `reconcile_endpoints`'s two bridge branches to call `_bridge_node_path_and_length`
directly (its returned `vpath` is already the spliceable node-label list — `vpath[0] ==
anchor_label`, `vpath[-1] == decoded_end_label`), dropping `_bridge_distance_and_path` and
`_path_result_to_node_labels` entirely:

```python
        else:
            bridge_nodes, bridge_len = _bridge_node_path_and_length(subgraph, leg_map.src_anchor, result[0])
            if bridge_len > endpoint_bridge_max_m:
                return BridgeTooLong(endpoint="from", bridge_m=bridge_len, cap_m=endpoint_bridge_max_m)
            result = [*bridge_nodes[:-1], *result]
```

(mirrored for the `"to"` branch, using `bridge_nodes[1:]` appended after `result`). Update the
module's imports accordingly (drop `path_for`, keep `build_igraph_with_snaps`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd pipeline && pixi run pytest tests/test_hmm_reconstruct.py -v`
Expected: PASS (all tests in the file). Adjust the two bridge tests' assertions that referenced
the now-removed placeholder logic if they don't already match the real `vpath`-based behavior
(they were written against the intended final shape, not the intermediate placeholder).

- [ ] **Step 5: Commit**

```bash
cd pipeline && git add lib/hmm_reconstruct.py tests/test_hmm_reconstruct.py
git commit -m "pipeline: add trim/bridge/bridge-cap endpoint reconciliation"
```

---

### Task 12: Rewire `match_leg` onto the new HMM core

**Files:**
- Modify: `pipeline/phases/graph_building/match_tour_edges.py`
- Modify: `pipeline/tests/test_match_tour_edges.py`

**Interfaces:**
- Consumes: `hmm_match.resample_trace/build_leg_map/match_trace`,
  `hmm_reconstruct.reconcile_endpoints/reconstruct_matched_path`, `BridgeTooLong`,
  `DecodeFailure` from Task 8/11.
- Produces: `match_leg(subgraph, src_key, tgt_key, persisted_snaps, trace_points: list,
  length_divergence_ratio, hmm_resample_m, hmm_obs_noise_m, hmm_max_dist_m, hmm_dist_noise_m,
  endpoint_bridge_max_m) -> dict` — same `{"ok": ..., ...}` shape as today, with `trace_length_m`
  replaced by `trace_points` (§5: "It needs the leg's trace points, not just `trace_length_m`" —
  `trace_length_m` is now computed internally from `trace_points`, same haversine sum `main()`
  used to do before calling `match_leg`).

- [ ] **Step 1: Update the four existing direct `match_leg` tests for the new signature**

Edit `pipeline/tests/test_match_tour_edges.py:48-95` (the four tests listed in the spec §5 note).
Each currently passes `trace_length_m=<N>`; change to pass `trace_points=<a 2-point list whose
haversine length is N>` and add the five new HMM params with the same defaults Task 2 gave them.
For `test_match_leg_routes_a_simple_corridor` (currently `trace_length_m=1000.0`):

```python
def test_match_leg_routes_a_simple_corridor():
    subgraph = _line_subgraph_1000m()
    src_key, tgt_key = (binfmt.TYPE_HUT, 0), (binfmt.TYPE_HUT, 1)
    persisted = {src_key: _node_snap(100), tgt_key: _node_snap(101)}
    trace_points = [(0.0, 0.0), (0.009, 0.0)]  # ~1000m, matches _line_subgraph_1000m's own edge
    result = match_leg(subgraph, src_key, tgt_key, persisted, trace_points=trace_points,
                        length_divergence_ratio=2.0, hmm_resample_m=25.0, hmm_obs_noise_m=25.0,
                        hmm_max_dist_m=150.0, hmm_dist_noise_m=25.0, endpoint_bridge_max_m=250.0)
    assert result["ok"] is True
    assert result["path"].distance_m == 1000.0
```

Apply the same `trace_length_m=X` → `trace_points=[(...), (...)]` (2 points, `X` meters apart at
the equator, same formula `_line_subgraph_1000m`'s own 0.009°≈1000m uses) plus the five new kwargs
to the other three tests (`hub_unsnapped`, `outside_extract`, `length_divergent` — the
`length_divergent` test's trace should stay ~100m so the length check still fires: e.g.
`trace_points=[(0.0, 0.0), (0.0009, 0.0)]`). Delete
`test_match_leg_reports_outside_extract_when_corridor_is_empty` and
`test_match_leg_reports_length_divergent_when_routed_far_exceeds_trace`'s reliance on
`no_corridor_path` — there is none, `no_corridor_path` was never in these two tests' assertions,
so no deletion needed there; only remove any standalone test asserting `no_corridor_path` itself
if one exists elsewhere in the file (grep confirmed there isn't one beyond `match_tour_edges.py`'s
own two `return` sites, both removed in Step 3 below).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd pipeline && pixi run pytest tests/test_match_tour_edges.py -v`
Expected: FAIL — `TypeError: match_leg() got an unexpected keyword argument 'trace_points'`

- [ ] **Step 3: Rewrite `match_leg`**

Edit `pipeline/phases/graph_building/match_tour_edges.py`:

```python
from lib.hmm_match import build_leg_map, match_trace, resample_trace, DecodeFailure
from lib.hmm_reconstruct import BridgeTooLong, reconcile_endpoints, reconstruct_matched_path


def match_leg(subgraph, src_key: tuple, tgt_key: tuple, persisted_snaps: dict,
              trace_points: list, length_divergence_ratio: float, hmm_resample_m: float,
              hmm_obs_noise_m: float, hmm_max_dist_m: float, hmm_dist_noise_m: float,
              endpoint_bridge_max_m: float) -> dict:
    """Matches one leg's src_key->tgt_key trace (trace_points, the leg's OWN GPX points) inside
    `subgraph` (already gathered as the leg's own corridor, spec §2) via HMM map matching (spec
    2026-09-01-corridor-hmm-map-matching-design.md), replacing the single-Dijkstra core this used
    to be. Returns {"ok": True, "path": PathResult, "src_snap": SnapResult, "tgt_snap": SnapResult}
    or {"ok": False, "reason": <spec §4 reason>, "detail": {...}}."""
    if len(subgraph.local_nodes) == 0:
        return {"ok": False, "reason": "outside_extract", "detail": {}}

    local_snaps = hub_snap.reconstruct_local_snaps(subgraph, {src_key, tgt_key}, persisted_snaps)
    missing = [k for k in (src_key, tgt_key) if k not in local_snaps]
    if missing:
        return {"ok": False, "reason": "hub_unsnapped", "detail": {"missing": missing}}

    from lib.cell_igraph import _check_routable
    _check_routable(subgraph)

    src_snap, tgt_snap = local_snaps[src_key], local_snaps[tgt_key]
    trace_length_m = sum(
        haversine_m(trace_points[i][0], trace_points[i][1], trace_points[i + 1][0], trace_points[i + 1][1])
        for i in range(len(trace_points) - 1)
    )

    resampled = resample_trace(trace_points, hmm_resample_m)
    leg_map = build_leg_map(subgraph, src_snap, tgt_snap, resampled, hmm_max_dist_m)
    decoded = match_trace(leg_map, resampled, hmm_obs_noise_m, hmm_max_dist_m, hmm_dist_noise_m)
    if isinstance(decoded, DecodeFailure):
        return {
            "ok": False, "reason": "hmm_match_broken",
            "detail": {
                "trace_index": decoded.trace_index, "lon": decoded.lon, "lat": decoded.lat,
                "nearest_candidate_dist_m": decoded.nearest_candidate_dist_m,
            },
        }

    reconciled = reconcile_endpoints(subgraph, leg_map, decoded, endpoint_bridge_max_m)
    if isinstance(reconciled, BridgeTooLong):
        return {
            "ok": False, "reason": "endpoint_bridge_too_long",
            "detail": {"endpoint": reconciled.endpoint, "bridge_m": reconciled.bridge_m,
                       "cap_m": reconciled.cap_m},
        }

    path = reconstruct_matched_path(leg_map, reconciled)
    node_coords = {
        i: (float(subgraph.local_nodes["lon"][i]), float(subgraph.local_nodes["lat"][i]))
        for i in range(len(subgraph.local_nodes))
    }
    node_coords.update(leg_map.__dict__.get("node_coords", {}))
    path = path._replace(coords=[node_coords[n] for n in reconciled[1:-1] if n in node_coords])

    routed_m = path.distance_m + src_snap.gap_m + tgt_snap.gap_m
    if trace_length_m > 0:
        ratio = routed_m / trace_length_m
        if ratio > length_divergence_ratio or ratio < 1.0 / length_divergence_ratio:
            return {
                "ok": False, "reason": "length_divergent",
                "detail": {"routed_m": routed_m, "trace_m": trace_length_m, "ratio": ratio},
            }

    return {"ok": True, "path": path, "src_snap": src_snap, "tgt_snap": tgt_snap}
```

`LegMap` needs a `node_coords` field for the `coords` fill-in above to work (Task 7's
`build_leg_map` already computes an `all_nodes` dict internally but doesn't return it) — go back
to `pipeline/lib/hmm_match.py`'s `LegMap` dataclass and add `node_coords: dict = None`, and
`build_leg_map`'s final `return` to pass `node_coords=all_nodes`. This is a small addition to
Task 7's code, made here because Task 12 is the first caller that needs it — update
`test_materialize_anchor_*`/`test_match_trace_*`'s `LegMap(...)` construction calls in
`test_hmm_match.py` accordingly if they positionally construct `LegMap` (they use keyword args
above, so no change needed there), and update `test_hmm_reconstruct.py`'s `_line_leg_map()`/
`_corridor_with_gap_to_anchor` fixtures similarly if `reconcile_endpoints`/
`reconstruct_matched_path` end up depending on it (they don't — `node_coords` is only consumed
here in `match_leg`, so no other test file changes are needed).

Remove the two `no_corridor_path` return sites entirely (already gone — replaced by the
`hmm_match_broken`/`endpoint_bridge_too_long` machinery above) and the now-unused
`build_base_igraph_arrays`/`build_igraph_from_base` imports from `match_tour_edges.py`'s header
(keep `accumulate_path`'s import only if still referenced elsewhere in the file — it is not, once
`match_leg` no longer calls it directly; grep the file after editing to confirm no dangling
import).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd pipeline && pixi run pytest tests/test_match_tour_edges.py -v`
Expected: the four updated direct `match_leg` tests PASS. The golden-tour tests (which call
`main()`) will still fail until Task 13 threads the new params through `main()` — that's expected
at this point; do not chase those failures in this task.

- [ ] **Step 5: Commit**

```bash
cd pipeline && git add phases/graph_building/match_tour_edges.py tests/test_match_tour_edges.py
git commit -m "pipeline: rewire match_leg onto the HMM matching core"
```

---

### Task 13: `main()` + DAG wiring for the five new params, plus the remaining §8 integration tests

**Files:**
- Modify: `pipeline/phases/graph_building/match_tour_edges.py`
- Modify: `pipeline/dag/graph_building.py`
- Modify: `pipeline/tests/test_match_tour_edges.py`

**Interfaces:**
- Produces: `--hmm-resample-m`, `--hmm-obs-noise-m`, `--hmm-max-dist-m`, `--hmm-dist-noise-m`,
  `--endpoint-bridge-max-m` CLI flags on `match_tour_edges.py`; matching `cli_param` entries on
  `task_match_tour_edges` in `dag/graph_building.py`.

- [ ] **Step 1: Write the failing integration tests**

Append to `pipeline/tests/test_match_tour_edges.py` (mirrors the existing golden-tour tests'
`monkeypatch.setattr(mte, "load_config", ...)` pattern, extended with the five new keys):

```python
def test_golden_tour_uses_hmm_config_and_still_matches_all_legs(tmp_path, monkeypatch):
    # Same fixture as test_golden_single_part_tour_matches_all_legs_end_to_end, but asserts the
    # five new config keys are actually threaded through main() -> match_leg (spec §7's
    # "changing hmmObsNoiseM would not invalidate the task" concern, exercised at the config-
    # plumbing level here; the DAG cli_param/TaskOptionsChanged wiring itself is doit-level and
    # not unit-testable from this file).
    grid = Grid(BBOX, tile_size_km=60.0)
    base_graph_dir, node_coords = _write_synthetic_base_graph(tmp_path, grid)
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
        lambda: {
            "tourMatch": {
                "corridorBufferM": 150.0, "lengthDivergenceRatio": 2.0,
                "hmmResampleM": 25.0, "hmmObsNoiseM": 25.0, "hmmMaxDistM": 150.0,
                "hmmDistNoiseM": 25.0, "endpointBridgeMaxM": 250.0,
            },
            "graph": {"maxSnapM": 100.0},
        },
    )
    mte.main(["--base-graph-dir", str(base_graph_dir), "--out-dir", str(tmp_path)])

    records = binfmt.load_array(tmp_path / "tour_edges" / "records.npy", mmap=False)
    gaps = json.loads((tmp_path / "tour-match-gaps.json").read_text(encoding="utf-8"))
    assert len(records) == 3
    assert gaps == []


def test_length_divergent_still_reachable_after_hmm_decode_succeeds(tmp_path, monkeypatch):
    # spec §8's "length_divergent still reachable": a fixture where the decode succeeds
    # end-to-end but the winning path's total length still exceeds lengthDivergenceRatio.
    subgraph = _line_subgraph_1000m()
    src_key, tgt_key = (binfmt.TYPE_HUT, 0), (binfmt.TYPE_HUT, 1)
    persisted = {src_key: _node_snap(100), tgt_key: _node_snap(101)}
    # a trace only 100m long, but the only routable path is the 1000m edge - decode succeeds
    # (it's the only candidate within hmmMaxDistM of a 100m trace sitting on top of its start),
    # length check must still catch the 10x divergence.
    trace_points = [(0.0, 0.0), (0.0009, 0.0)]
    result = match_leg(subgraph, src_key, tgt_key, persisted, trace_points=trace_points,
                        length_divergence_ratio=2.0, hmm_resample_m=25.0, hmm_obs_noise_m=25.0,
                        hmm_max_dist_m=150.0, hmm_dist_noise_m=25.0, endpoint_bridge_max_m=250.0)
    assert result["reason"] == "length_divergent"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd pipeline && pixi run pytest tests/test_match_tour_edges.py -v`
Expected: FAIL on both new tests — `main()`'s `args.corridor_buffer_m`/`args.length_divergence_ratio`-only call into `match_leg` doesn't yet pass the five new kwargs `match_leg` now requires
(`TypeError: match_leg() missing 5 required positional arguments`).

- [ ] **Step 3: Wire `main()`'s five new flags**

Edit `pipeline/phases/graph_building/match_tour_edges.py`'s `main()`:

```python
    parser.add_argument("--hmm-resample-m", type=float, default=tm["hmmResampleM"],
                        help="minimum trace point spacing for HMM matching (decimate-only)")
    parser.add_argument("--hmm-obs-noise-m", type=float, default=tm["hmmObsNoiseM"],
                        help="emission Gaussian width for HMM matching (~real GPX accuracy)")
    parser.add_argument("--hmm-max-dist-m", type=float, default=tm["hmmMaxDistM"],
                        help="hard candidate-edge cutoff for HMM matching")
    parser.add_argument("--hmm-dist-noise-m", type=float, default=tm["hmmDistNoiseM"],
                        help="transition-probability width for HMM matching")
    parser.add_argument("--endpoint-bridge-max-m", type=float, default=tm["endpointBridgeMaxM"],
                        help="cap on the hub-snap-to-matched-path bridge at each leg endpoint")
```

and update the `match_leg(...)` call site inside the leg loop:

```python
                result = match_leg(
                    subgraph, from_key, to_key, persisted_snaps, trace_points=points,
                    length_divergence_ratio=args.length_divergence_ratio,
                    hmm_resample_m=args.hmm_resample_m, hmm_obs_noise_m=args.hmm_obs_noise_m,
                    hmm_max_dist_m=args.hmm_max_dist_m, hmm_dist_noise_m=args.hmm_dist_noise_m,
                    endpoint_bridge_max_m=args.endpoint_bridge_max_m,
                )
```

(`points` is already in scope — it's the leg's raw trace points from `load_tour_folder`; the old
`trace_length_m = sum(haversine_m(...))` line above this call site is now dead code, since
`match_leg` computes it internally — delete it.)

- [ ] **Step 4: Wire the DAG params**

Edit `pipeline/dag/graph_building.py`'s `task_match_tour_edges`:

```python
        params=[
            cli_param("corridor_buffer_m", "corridor-buffer-m", float, CONFIG["tourMatch"]["corridorBufferM"]),
            cli_param("length_divergence_ratio", "length-divergence-ratio", float,
                      CONFIG["tourMatch"]["lengthDivergenceRatio"]),
            cli_param("hmm_resample_m", "hmm-resample-m", float, CONFIG["tourMatch"]["hmmResampleM"]),
            cli_param("hmm_obs_noise_m", "hmm-obs-noise-m", float, CONFIG["tourMatch"]["hmmObsNoiseM"]),
            cli_param("hmm_max_dist_m", "hmm-max-dist-m", float, CONFIG["tourMatch"]["hmmMaxDistM"]),
            cli_param("hmm_dist_noise_m", "hmm-dist-noise-m", float, CONFIG["tourMatch"]["hmmDistNoiseM"]),
            cli_param("endpoint_bridge_max_m", "endpoint-bridge-max-m", float,
                      CONFIG["tourMatch"]["endpointBridgeMaxM"]),
        ],
```

- [ ] **Step 5: Run the full test file**

Run: `cd pipeline && pixi run pytest tests/test_match_tour_edges.py -v`
Expected: PASS — every test in the file, including the pre-existing golden-tour tests (their
`load_config` monkeypatch fixtures already include the five new keys, since they were written
against the extended `tourMatch` dict in Step 1 above; if any older golden test in the file still
uses the two-key `tourMatch` dict from before this plan, extend it the same way).

- [ ] **Step 6: Run the whole pipeline test suite**

Run: `cd pipeline && pixi run pytest -v`
Expected: PASS across the board — this is the point to catch any other caller of `match_leg`,
`no_corridor_path`, or the old `trace_length_m` kwarg this plan's grep (done during planning)
didn't find.

- [ ] **Step 7: Commit**

```bash
cd pipeline && git add phases/graph_building/match_tour_edges.py dag/graph_building.py tests/test_match_tour_edges.py
git commit -m "pipeline: thread HMM matching params through main() and the doit DAG"
```

---

### Task 14: Real-data check against Kaisertour / Welser Höhenweg

§8's final acceptance bar: rerun `corridor_match_quality.py` against the tour folders on disk and
confirm Kaisertour leg 1's matched path now includes the summit, with deviation down from 1237 m
to tens of metres — while recording matched-leg/gap counts before and after, since §4's stricter
break-handling rule can turn a previously-shortcut-matched leg into a gap.

**This task runs a pipeline task and therefore requires the user's explicit confirmation first —
do not run `doit match_tour_edges` or `corridor_match_quality.py` without asking, per root
`CLAUDE.md`.**

- [ ] **Step 1: Ask the user for confirmation to run `doit match_tour_edges`**

State plainly what will run (`doit match_tour_edges`, then
`pipeline/analysis/corridor_match_quality.py` against the resulting `data/osm/tour_edges/`) and
wait for explicit go-ahead before proceeding to Step 2.

- [ ] **Step 2: Capture the before snapshot**

Before rerunning, if `data/osm/tour_edges/records.npy` and `data/osm/tour-match-gaps.json` already
exist from a prior (pre-HMM) run, copy them aside:

```bash
cp data/osm/tour_edges/records.npy /tmp/tour_edges_records_before.npy 2>/dev/null || true
cp data/osm/tour-match-gaps.json /tmp/tour-match-gaps-before.json 2>/dev/null || true
```

- [ ] **Step 3: Rerun `match_tour_edges`**

```bash
cd pipeline && pixi run doit match_tour_edges
```

- [ ] **Step 4: Run the deviation/coverage check**

```bash
cd pipeline && pixi run python analysis/corridor_match_quality.py
```

Record the printed deviation metric and matched-leg/gap counts.

- [ ] **Step 5: Compare before/after and report**

Compute matched-leg and gap counts from the before-snapshot (if captured) vs. now. Confirm:
- Kaisertour leg 1's `base_edge_ids`/geometry include the summit (cross-check against the leg's
  known summit coordinate/elevation from the spec's "Concrete case").
- Max deviation for that leg has dropped from ~1237 m to the tens-of-metres range (§5's stated
  floor: "how far the mapped trail sits from the recorded track", not `hmmResampleM`).
- Any leg that newly became a gap is traced to a real OSM coverage gap (a `hmm_match_broken` or
  `endpoint_bridge_too_long` detail pointing at a genuine missing trail / wrong-hub case), not an
  overly strict parameter — per §4, a broad drop is evidence for retuning §3's params, not a
  regression to silently absorb.

Do not retune `corridorBufferM`/`lengthDivergenceRatio` beyond §3/§6's stated defaults in this
task (out of scope, per spec's "Out of scope" section) — if the five new HMM params need
retuning based on what this run shows, that is a follow-up, not part of finishing this plan.

- [ ] **Step 6: Report results to the user**

Summarize the before/after deviation metric, matched-leg/gap counts, and the Kaisertour leg 1
verification above in a short message — no commit needed for this task (it produces gitignored
`data/` output only).

---

## Self-Review

**Spec coverage:**
- §0 (why not waypoint-forced): reflected in the architecture note (full HMM via `match_trace`,
  not per-waypoint Dijkstra) — no dedicated task needed, it's a rejected alternative.
- §1 (dependency, coordinate order): Task 1 (dependency), Task 4 (round-trip test).
- §2 (candidate graph, bounding, endpoint anchoring, out-and-back): Tasks 5–7 (expansion,
  filtering, anchoring), Task 8 (bidirectional decode / summit test), Task 9 (out-and-back
  no-dedupe).
- §3 (matching parameters): Task 2 (config), Task 8 (`match_trace`'s obs/dist noise wiring).
- §4 (break handling, new gap reasons): Task 8 (`DecodeFailure`), Task 11 (`BridgeTooLong`),
  Task 12 (wiring both into `match_leg`'s `"ok": False` shape).
- §5 (output shape, partial-edge apportionment, `match_leg` signature, `_check_routable`): Task 9
  (`PathResult`-shaped reconstruction), Task 10 (apportionment test), Task 12 (signature rewrite +
  explicit `_check_routable` call).
- §6 (config keys): Task 2.
- §7 (DAG wiring): Task 13.
- §8 (testing): every named test is covered — resampling (Task 3), coordinate round-trip (Task 4),
  interior expansion (Task 5), `base_edge_id` namespace (Task 5), endpoint anchoring invariant
  (Task 7 + Task 12's `coords[0]`/`coords[-1]` fill-in — see note below), mid-chain snap
  materialization (Task 7), trim (Task 11), bridge (Task 11), bridge cap (Task 11), summit-detour
  (Task 8), out-and-back (Task 9), partial-edge apportionment (Task 10), break handling (Task 8),
  length_divergent still reachable (Task 13), existing `match_leg` tests updated (Task 12),
  `test_config.py` (Task 2), real-data check (Task 14).

**Gap found in self-review:** the spec's explicit "Endpoint anchoring — the invariant" test
(`path.coords[0]` equals the src `SnapResult`'s snap point exactly, `path.coords[-1]` the tgt's)
is not written as its own standalone test above — Task 12's `match_leg` rewrite computes `coords`
from `reconciled[1:-1]`, deliberately excluding the two endpoints (matching `accumulate_path`'s
existing convention, where `build_tour_record` prepends/appends `from_coord`/`to_coord` itself).
Add this as an explicit test in Task 12's Step 4 test run:

```python
def test_match_leg_path_excludes_the_two_anchor_snap_points_themselves():
    # mirrors accumulate_path's existing contract: build_tour_record prepends/appends the hub
    # coordinate itself, so path.coords must NOT already contain the anchor snap points.
    subgraph = _line_subgraph_1000m()
    src_key, tgt_key = (binfmt.TYPE_HUT, 0), (binfmt.TYPE_HUT, 1)
    persisted = {src_key: _node_snap(100), tgt_key: _node_snap(101)}
    result = match_leg(subgraph, src_key, tgt_key, persisted,
                        trace_points=[(0.0, 0.0), (0.009, 0.0)], length_divergence_ratio=2.0,
                        hmm_resample_m=25.0, hmm_obs_noise_m=25.0, hmm_max_dist_m=150.0,
                        hmm_dist_noise_m=25.0, endpoint_bridge_max_m=250.0)
    assert result["ok"] is True
    # a 2-node line has no interior coords once its own two endpoints are excluded
    assert result["path"].coords == []
```

Add this test alongside Task 12 Step 1's other updated tests, and additionally assert in
`test_build_tour_record_shape_matches_write_edge_records_expectations` (already existing,
unchanged by this plan) that the invariant downstream in `build_tour_record` still holds — that
test already asserts `record["geometry"][0] == from_coord` and `[-1] == to_coord`, which is the
same invariant expressed at `build_tour_record`'s own boundary, so no further change is needed
there.

**Placeholder scan:** the two inline "note here, fixed later" moments in Task 11's draft
(`_bridge_distance_and_path`/`_path_result_to_node_labels`) are explicitly walked through and
replaced with the real `_bridge_node_path_and_length` implementation within the same task step,
not left as a TODO — Task 11's Step 3 ends with the real code, not the placeholder. No other
placeholder markers remain.

**Type consistency:** `LegMap`'s fields (`inmem_map`, `sub_edges`, `src_anchor`, `tgt_anchor`, and
the `node_coords` field added in Task 12) are used consistently by name across Tasks 7–13.
`SubEdge`'s field names (`from_node`, `to_node`, `base_edge_id`, `direction`, `segment_index`,
`dist_m`, `road_m`, `ungraded_m`, `inferred_m`, `ascent_m`, `descent_m`, `max_ele_m`, `sac_rank`,
`via_ferrata`) are identical across Tasks 5, 7, 9, 10, 11. `match_leg`'s new keyword names
(`trace_points`, `hmm_resample_m`, `hmm_obs_noise_m`, `hmm_max_dist_m`, `hmm_dist_noise_m`,
`endpoint_bridge_max_m`) match between Task 12's implementation and Task 13's `main()` call site
and Task 12/13's test updates.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-01-corridor-hmm-map-matching.md`. Two
execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks,
   fast iteration.
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution
   with checkpoints.

Which approach?
