# Official ÖAV/DAV Tours Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **This repo overrides the usual subagent-driven-development recommendation.** Per
> `/home/superhellth/open-alps/CLAUDE.md`: "Never use superpowers:subagent-driven-development or
> any other approach that spins up worktrees/subagents to execute plan tasks in this repo, even if
> a skill recommends it." Execute every task directly, in-session, on the current checkout —
> `superpowers:executing-plans` is the only allowed executor for this plan.

**Goal:** Ship a new `tour_edges/` pipeline output (`records.npy`/`geometry.npy`/`edge_ids.npy`/
`tour_meta.npy`) that gives each of the AV's 26 official multi-day tours real per-leg
distance/ascent/descent/difficulty data, routed on the AV's own published geometry (corridor-
constrained on the existing base graph) rather than the free-shortest-path hub-edge graph — plus
the postprocessing (tiles/payload) and doit wiring to publish it as `tours.json` +
`tour-edges.pmtiles` + `tour-edge-payload.bin`/`.json`.

**Architecture:** A new `fetch_tours.py` download task resolves the AV tour layer's hut-GUID
chains into `huts.geojson` positional indices and ships `tours.json` (client-shaped) +
`tour_traces.json` (internal-only raw polyline fragments). A new `lib/tour_geometry.py` reassembles
each tour's scrambled polyline fragments into ordered chains and assigns each hut a position along
its chain. A new `match_tour_edges.py` phase script then, per leg, buffers the leg's own chain slice
into a bbox corridor (reusing `lib/subgraph.py`'s existing padded-gather machinery against an
arbitrary bbox instead of a grid cell), builds an igraph over just that corridor
(`lib/cell_igraph.py`'s existing `build_base_igraph_arrays`/`build_igraph_from_base`), and routes
hut-snap → hut-snap inside it (`accumulate_path`) — never touching `graph.variants` or the free
hub-edge graph. Record packing and endpoint-snap folding are factored out of
`build_hub_edges.py` into a shared `lib/edge_output.py` so both scripts emit the exact same
`RECORD_DTYPE` shape. `build_profiles.py`/`build_edge_tiles.py`/`build_edge_payload.py` are
extended (not forked) to also run over `tour_edges/`.

**Tech Stack:** Python (pipeline's `alpen-osm` pixi env — numpy, igraph, scipy, rasterio), doit task
DAG, pytest. No new dependency (the corridor-routing primary path needs nothing `pipeline.toml`
doesn't already have — see spec §2.3's "no new dependency" note). `leuvenmapmatching` (spec §2.4) is
explicitly a documented fallback, gated on the §2.7 spike's outcome, and is **out of scope for this
plan** — see the "Out of scope" section below.

**Spec:** `docs/superpowers/specs/2026-08-29-official-tours-integration-design.md`

## Global Constraints

- **Never run any `pipeline/` doit task (individually or the full DAG) without first asking the
  user and getting explicit confirmation** — this applies to `doit fetch_tours` and
  `doit match_tour_edges` exactly as much as to the multi-hour tasks (root `CLAUDE.md`). Every
  task below that could execute a pipeline script against real `data/` outputs is written to run
  only synthetic, in-test fixtures; Task 20 (the real-25-tour spike) is explicitly gated and must
  stop and ask before running `doit fetch_tours`.
- Region coverage is `["austria", "bayern"]` (`pipeline.config.json`'s `regions`) — legs leaving
  that extract (Switzerland, South Tyrol) are a real coverage limit, not a bug to work around
  (spec §0.3, "Out of scope").
- `Shape__Length` on the AV tour layer is Web Mercator metres (ratio ≈0.68 to ground metres at
  47°N) — never compare it directly against a routed length; sum the tour's own geometry instead
  (spec §0, §2.5's `length_divergent`).
- `RECORD_DTYPE` gets **no new columns** for this feature — `tour_meta.npy` is a separate,
  row-aligned sidecar (spec §2.6). No `RECORD_SCHEMA_VERSION`/`EDGE_SCHEMA_VERSION`/
  `SNAP_SCHEMA_VERSION` bump, so `task_build_base_graph`/`task_build_hub_edges` are not
  force-rerun by anything in this plan.
- A leg that hits any of §2.5's gap reasons (`hut_unsnapped`, `hut_far_from_trace`,
  `outside_extract`, `no_corridor_path`, `length_divergent`, `chain_not_reassembled`) is **never**
  emitted with a placeholder — it is simply absent from `records.npy`, recorded in
  `tour-match-gaps.json` with tour/leg identity and reason. No straight-line/partial-distance
  fallback is ever written.
- `time_s` is summed only as an internal plausibility check inside `match_leg` — never persisted
  (spec's Goal note, D3 convention already followed by `build_edge_payload.py`).
- New tunable thresholds (fragment-join break distance, corridor buffer, hut→trace cap, length
  divergence ratio) live in `pipeline.config.json`, not hardcoded, following every other
  `--max-edge-km`/`--max-snap-m`-style knob in this pipeline.

---

## Task 1: `pipeline.config.json` — `tourMatch` config section

**Files:**
- Modify: `pipeline/pipeline.config.json`
- Test: `pipeline/tests/test_config.py`

**Interfaces:**
- Produces: `config["tourMatch"]` = `{"fragmentBreakM": 150.0, "corridorBufferM": 150.0,
  "maxHutTraceM": 250.0, "lengthDivergenceRatio": 2.0}` — consumed by Tasks 3, 6, 12, 14.

- [ ] **Step 1: Read the current config test to see the assertion style**

Run: `sed -n '1,40p' pipeline/tests/test_config.py`

- [ ] **Step 2: Write the failing test**

Append to `pipeline/tests/test_config.py`:

```python
def test_tour_match_config_has_all_four_thresholds():
    config = load_config()
    tm = config["tourMatch"]
    assert tm["fragmentBreakM"] == 150.0
    assert tm["corridorBufferM"] == 150.0
    assert tm["maxHutTraceM"] == 250.0
    assert tm["lengthDivergenceRatio"] == 2.0
```

(Use whatever `load_config` import the existing tests in that file already use.)

- [ ] **Step 3: Run test to verify it fails**

Run: `cd pipeline && python -m pytest tests/test_config.py::test_tour_match_config_has_all_four_thresholds -v`
Expected: FAIL with `KeyError: 'tourMatch'`

- [ ] **Step 4: Add the config section**

In `pipeline/pipeline.config.json`, add after the `"approach"` key (before `"trailTiles"`):

```json
  "tourMatch": {
    "fragmentBreakM": 150.0,
    "corridorBufferM": 150.0,
    "maxHutTraceM": 250.0,
    "lengthDivergenceRatio": 2.0
  },
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd pipeline && python -m pytest tests/test_config.py::test_tour_match_config_has_all_four_thresholds -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pipeline/pipeline.config.json pipeline/tests/test_config.py
git commit -m "config: add tourMatch thresholds for official-tours matching"
```

---

## Task 2: `lib/binfmt.py` — `VARIANT_OFFICIAL` + `TOUR_META_DTYPE`

**Files:**
- Modify: `pipeline/lib/binfmt.py`
- Test: `pipeline/tests/test_binfmt.py`

**Interfaces:**
- Produces: `binfmt.VARIANT_OFFICIAL` (int, `4`), `binfmt.VARIANT_NAMES[VARIANT_OFFICIAL] ==
  "OFFICIAL"`, `binfmt.TOUR_META_DTYPE = np.dtype([("tour_id", "u1"), ("leg_index", "u1")])`.
  Consumed by Task 13 (record building) and Task 17 (`build_edge_payload.py`'s tour-meta merge).

- [ ] **Step 1: Write the failing test**

Add to `pipeline/tests/test_binfmt.py`:

```python
def test_variant_official_does_not_collide_with_the_search_grid():
    assert binfmt.VARIANT_OFFICIAL not in (
        binfmt.VARIANT_FAST_ANY, binfmt.VARIANT_FAST_T2,
        binfmt.VARIANT_FAST_T3, binfmt.VARIANT_FAST_T3_UNGRADED,
    )
    assert binfmt.VARIANT_NAMES[binfmt.VARIANT_OFFICIAL] == "OFFICIAL"


def test_tour_meta_dtype_fields():
    assert binfmt.TOUR_META_DTYPE.names == ("tour_id", "leg_index")
    assert binfmt.TOUR_META_DTYPE["tour_id"] == np.dtype("u1")
    assert binfmt.TOUR_META_DTYPE["leg_index"] == np.dtype("u1")
```

(Match the existing file's import alias for `binfmt`/`np` — check the top of
`pipeline/tests/test_binfmt.py` first.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pipeline && python -m pytest tests/test_binfmt.py -k "variant_official or tour_meta_dtype" -v`
Expected: FAIL with `AttributeError: module 'lib.binfmt' has no attribute 'VARIANT_OFFICIAL'`

- [ ] **Step 3: Add the constant and dtype**

In `pipeline/lib/binfmt.py`, after the `VARIANT_FAST_T3_UNGRADED = 3` block (around line 94),
before `VARIANT_NAMES = {...}`:

```python
# A tour leg is not a member of the graph.variants search grid (spec 2026-08-29-official-tours-
# integration-design.md §5) - it is the ONE route the AV publishes, nothing to search among - so
# it gets its own sentinel rather than reusing a FAST_* row.
VARIANT_OFFICIAL = 4
```

Change `VARIANT_NAMES` to:

```python
VARIANT_NAMES = {
    VARIANT_FAST_ANY: "FAST_ANY", VARIANT_FAST_T2: "FAST_T2", VARIANT_FAST_T3: "FAST_T3",
    VARIANT_FAST_T3_UNGRADED: "FAST_T3_UNGRADED", VARIANT_OFFICIAL: "OFFICIAL",
}
```

Add after `HUB_SNAP_DTYPE`'s definition (near the other `*_DTYPE` constants):

```python
# tour_edges/tour_meta.npy - row-aligned 1:1 with tour_edges/records.npy (NOT folded into
# RECORD_DTYPE itself, spec §2.6: avoids touching the shared dtype every other consumer depends
# on). 25 tours x <=9 legs each fits u1 comfortably.
TOUR_META_DTYPE = np.dtype([("tour_id", "u1"), ("leg_index", "u1")])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pipeline && python -m pytest tests/test_binfmt.py -v`
Expected: PASS (all tests, not just the two new ones — confirms no collision with existing dtypes)

- [ ] **Step 5: Commit**

```bash
git add pipeline/lib/binfmt.py pipeline/tests/test_binfmt.py
git commit -m "binfmt: add VARIANT_OFFICIAL and TOUR_META_DTYPE for tour legs"
```

---

## Task 3: `lib/tour_geometry.py` — fragment reassembly

**Files:**
- Create: `pipeline/lib/tour_geometry.py`
- Test: `pipeline/tests/test_tour_geometry.py`

**Interfaces:**
- Produces: `reassemble_fragments(fragments: list[list[tuple[float, float]]], break_threshold_m:
  float) -> list[list[tuple[float, float]]]` — a list of chains (each a list of `(lon, lat)`
  points). Consumed by Task 11/13 (`match_tour_edges.py`).

- [ ] **Step 1: Write the failing tests**

Create `pipeline/tests/test_tour_geometry.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.tour_geometry import reassemble_fragments  # noqa: E402


def test_two_fragments_join_head_to_tail():
    # Fragment B's start (10.001, 47.0) is ~74m from fragment A's end (10.0, 47.0) - within
    # break_threshold_m, should join into one 4-point chain in A-then-B order.
    a = [(9.998, 47.0), (10.0, 47.0)]
    b = [(10.001, 47.0), (10.003, 47.0)]
    chains = reassemble_fragments([a, b], break_threshold_m=150.0)
    assert len(chains) == 1
    assert chains[0] == a + b


def test_reversed_fragment_is_flipped_before_joining():
    # b's TAIL (not head) is near a's end - must be reversed before appending.
    a = [(9.998, 47.0), (10.0, 47.0)]
    b = [(10.003, 47.0), (10.001, 47.0)]
    chains = reassemble_fragments([a, b], break_threshold_m=150.0)
    assert len(chains) == 1
    assert chains[0] == a + list(reversed(b))


def test_real_break_stays_two_chains():
    # b's start is ~11km from a's end - far past any reasonable break_threshold_m, must NOT join.
    a = [(9.998, 47.0), (10.0, 47.0)]
    b = [(10.1, 47.0), (10.103, 47.0)]
    chains = reassemble_fragments([a, b], break_threshold_m=150.0)
    assert len(chains) == 2


def test_scrambled_order_still_reassembles():
    # Three fragments given out of route order (a, c, b) still join into one ordered chain.
    a = [(9.998, 47.0), (10.0, 47.0)]
    b = [(10.001, 47.0), (10.003, 47.0)]
    c = [(10.0031, 47.0), (10.005, 47.0)]
    chains = reassemble_fragments([a, c, b], break_threshold_m=150.0)
    assert len(chains) == 1
    assert chains[0][0] == a[0] and chains[0][-1] == c[-1]


def test_single_point_fragments_are_dropped():
    a = [(9.998, 47.0), (10.0, 47.0)]
    degenerate = [(11.0, 48.0)]
    chains = reassemble_fragments([a, degenerate], break_threshold_m=150.0)
    assert chains == [a]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd pipeline && python -m pytest tests/test_tour_geometry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lib.tour_geometry'`

- [ ] **Step 3: Implement `reassemble_fragments`**

Create `pipeline/lib/tour_geometry.py`:

```python
"""Reassembles an AV tour's scrambled polyline fragments into ordered chains, and orients/
positions huts along the result - the ground-truth-shape work `match_tour_edges.py` needs before
any leg can be routed (spec 2026-08-29-official-tours-integration-design.md §2.2, §0.1: the AV's
own `paths` field is an unordered bag of fragments, not one ordered polyline per tour, but the
fragments chain by nearest endpoint with a measured median join gap of 0-14m)."""

import math


def _haversine_m(lon1, lat1, lon2, lat2):
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def reassemble_fragments(fragments: list, break_threshold_m: float) -> list:
    """Greedily joins fragments by nearest endpoint (reversing a fragment when it joins tail-to-
    tail or head-to-head), stopping when the nearest remaining join exceeds break_threshold_m -
    spec §2.2 step 1. O(n^2) per merge / O(n^3) worst case over the whole fragment set, fine at
    this pipeline's real scale (max 51 fragments per tour, spec §0.2's SVR7T).

    Fragments with fewer than 2 points are dropped (can't be joined or meaningfully routed)."""
    remaining = [list(f) for f in fragments if len(f) >= 2]
    chains = []
    while remaining:
        chain = remaining.pop(0)
        merged = True
        while merged and remaining:
            merged = False
            head, tail = chain[0], chain[-1]
            best = None  # (dist_m, index_into_remaining, join_kind)
            for i, frag in enumerate(remaining):
                fh, ft = frag[0], frag[-1]
                for d, kind in (
                    (_haversine_m(*tail, *fh), "tail_head"),
                    (_haversine_m(*tail, *ft), "tail_tail"),
                    (_haversine_m(*head, *fh), "head_head"),
                    (_haversine_m(*head, *ft), "head_tail"),
                ):
                    if best is None or d < best[0]:
                        best = (d, i, kind)
            if best is not None and best[0] <= break_threshold_m:
                _, idx, kind = best
                frag = remaining.pop(idx)
                if kind == "tail_head":
                    chain = chain + frag
                elif kind == "tail_tail":
                    chain = chain + list(reversed(frag))
                elif kind == "head_head":
                    chain = list(reversed(frag)) + chain
                else:  # head_tail
                    chain = frag + chain
                merged = True
        chains.append(chain)
    return chains
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd pipeline && python -m pytest tests/test_tour_geometry.py -v`
Expected: PASS (all 5)

- [ ] **Step 5: Commit**

```bash
git add pipeline/lib/tour_geometry.py pipeline/tests/test_tour_geometry.py
git commit -m "graph_building: add fragment reassembly for AV tour geometry"
```

---

## Task 4: `lib/tour_geometry.py` — chain orientation

**Files:**
- Modify: `pipeline/lib/tour_geometry.py`
- Test: `pipeline/tests/test_tour_geometry.py`

**Interfaces:**
- Consumes: `_haversine_m` (Task 3, same module).
- Produces: `orient_chain(chain: list[tuple], hut_coords_in_order: list[tuple], is_loop: bool) ->
  list[tuple]`. Consumed by Task 11/13.

- [ ] **Step 1: Write the failing tests**

Append to `pipeline/tests/test_tour_geometry.py`:

```python
from lib.tour_geometry import orient_chain  # noqa: E402


def test_open_chain_already_forward_is_unchanged():
    chain = [(10.0, 47.0), (10.01, 47.0), (10.02, 47.0)]
    huts = [(10.0, 47.0), (10.02, 47.0)]  # first hut near chain start
    assert orient_chain(chain, huts, is_loop=False) == chain


def test_open_chain_backward_gets_reversed():
    chain = [(10.0, 47.0), (10.01, 47.0), (10.02, 47.0)]
    huts = [(10.02, 47.0), (10.0, 47.0)]  # first hut near chain END
    assert orient_chain(chain, huts, is_loop=False) == list(reversed(chain))


def test_loop_chain_picks_direction_matching_hut_order():
    # A 4-point loop; huts visit it in FORWARD point order (0, 1, 2, 3) - orienting forward should
    # win over reversed, which would visit them 3, 2, 1, 0 (all "violations").
    chain = [(10.0, 47.0), (10.01, 47.0), (10.02, 47.0), (10.03, 47.0)]
    huts = [(10.0, 47.0), (10.01, 47.0), (10.02, 47.0), (10.03, 47.0)]
    assert orient_chain(chain, huts, is_loop=True) == chain


def test_loop_chain_reverses_when_huts_visit_backward():
    chain = [(10.0, 47.0), (10.01, 47.0), (10.02, 47.0), (10.03, 47.0)]
    huts = [(10.03, 47.0), (10.02, 47.0), (10.01, 47.0), (10.0, 47.0)]
    assert orient_chain(chain, huts, is_loop=True) == list(reversed(chain))


def test_empty_hut_list_returns_chain_unchanged():
    chain = [(10.0, 47.0), (10.01, 47.0)]
    assert orient_chain(chain, [], is_loop=False) == chain
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd pipeline && python -m pytest tests/test_tour_geometry.py -k orient -v`
Expected: FAIL with `ImportError: cannot import name 'orient_chain'`

- [ ] **Step 3: Implement `orient_chain`**

Append to `pipeline/lib/tour_geometry.py`:

```python
def _nearest_chain_index(chain: list, point: tuple) -> int:
    dists = [_haversine_m(*p, *point) for p in chain]
    return dists.index(min(dists))


def orient_chain(chain: list, hut_coords_in_order: list, is_loop: bool) -> list:
    """Orients a reassembled chain (Task 3) so its point order matches the tour's own hut visit
    order (spec §2.2 step 3). For an open chain, whichever end sits nearer the first hut becomes
    index 0. For a Rundtour the chain closes on itself, so both directions are valid geometric
    walks - the one that visits the hut list with fewer order violations (a later hut assigned to
    an earlier chain position than the one before it) wins."""
    if not hut_coords_in_order:
        return chain
    if not is_loop:
        start_d = _haversine_m(*chain[0], *hut_coords_in_order[0])
        end_d = _haversine_m(*chain[-1], *hut_coords_in_order[0])
        return chain if start_d <= end_d else list(reversed(chain))

    def violations(oriented_chain):
        positions = [_nearest_chain_index(oriented_chain, h) for h in hut_coords_in_order]
        return sum(1 for a, b in zip(positions, positions[1:]) if b < a)

    reversed_chain = list(reversed(chain))
    return chain if violations(chain) <= violations(reversed_chain) else reversed_chain
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd pipeline && python -m pytest tests/test_tour_geometry.py -v`
Expected: PASS (all tests so far)

- [ ] **Step 5: Commit**

```bash
git add pipeline/lib/tour_geometry.py pipeline/tests/test_tour_geometry.py
git commit -m "graph_building: add chain orientation against hut visit order"
```

---

## Task 5: `lib/tour_geometry.py` — hut→chain-position assignment + leg slicing

**Files:**
- Modify: `pipeline/lib/tour_geometry.py`
- Test: `pipeline/tests/test_tour_geometry.py`

**Interfaces:**
- Produces: `assign_hut_position(chain: list[tuple], hut_coord: tuple, max_hut_trace_m: float) ->
  tuple[int, float] | None` (returns `(chain_index, dist_m)` or `None` if beyond threshold) and
  `leg_chain_slice(chain: list[tuple], pos_a: int, pos_b: int) -> list[tuple]` (handles the
  Rundtour closing-leg wraparound when `pos_a > pos_b`). Consumed by Task 11/13.

- [ ] **Step 1: Write the failing tests**

Append to `pipeline/tests/test_tour_geometry.py`:

```python
from lib.tour_geometry import assign_hut_position, leg_chain_slice  # noqa: E402


def test_assign_hut_position_finds_nearest_index():
    chain = [(10.0, 47.0), (10.01, 47.0), (10.02, 47.0)]
    result = assign_hut_position(chain, (10.0095, 47.0), max_hut_trace_m=250.0)
    assert result is not None
    idx, dist_m = result
    assert idx == 1
    assert dist_m < 250.0


def test_assign_hut_position_rejects_beyond_threshold():
    # KHW-style gap (spec §0.3): a hut far from every chain point (~9km scale reproduced small
    # here) must come back None, not the nearest-anyway index.
    chain = [(10.0, 47.0), (10.01, 47.0)]
    result = assign_hut_position(chain, (11.0, 48.0), max_hut_trace_m=250.0)
    assert result is None


def test_leg_chain_slice_normal_leg():
    chain = [(10.0, 47.0), (10.01, 47.0), (10.02, 47.0), (10.03, 47.0)]
    assert leg_chain_slice(chain, 1, 3) == chain[1:4]


def test_leg_chain_slice_wraps_for_rundtour_closing_leg():
    # Closing leg: last hut sits at position 3, first hut at position 0 - the slice must wrap
    # rather than come back empty or run backward through the whole tour.
    chain = [(10.0, 47.0), (10.01, 47.0), (10.02, 47.0), (10.03, 47.0)]
    assert leg_chain_slice(chain, 3, 0) == [chain[3], chain[0]]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd pipeline && python -m pytest tests/test_tour_geometry.py -k "assign_hut_position or leg_chain_slice" -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement both functions**

Append to `pipeline/lib/tour_geometry.py`:

```python
def assign_hut_position(chain: list, hut_coord: tuple, max_hut_trace_m: float):
    """Nearest chain point to a hut's own coordinate, as a (chain_index, dist_m) pair - or None
    when even the nearest point exceeds max_hut_trace_m (spec §0.3: "huts sit right on the trail"
    is false, e.g. KHW's Zollnersee-Hütte at 9,178m; this is the hut_far_from_trace gap case,
    spec §2.5)."""
    idx = _nearest_chain_index(chain, hut_coord)
    dist_m = _haversine_m(*chain[idx], *hut_coord)
    if dist_m > max_hut_trace_m:
        return None
    return idx, dist_m


def leg_chain_slice(chain: list, pos_a: int, pos_b: int) -> list:
    """Sub-chain between two chain-position indices, order-agnostic. Handles the Rundtour closing
    leg's wraparound (pos_a > pos_b, e.g. last hut's position > first hut's position on an oriented
    loop chain) by concatenating the tail and the head instead of returning an empty/reversed
    slice."""
    if pos_a <= pos_b:
        return chain[pos_a:pos_b + 1]
    return chain[pos_a:] + chain[:pos_b + 1]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd pipeline && python -m pytest tests/test_tour_geometry.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Commit**

```bash
git add pipeline/lib/tour_geometry.py pipeline/tests/test_tour_geometry.py
git commit -m "graph_building: add hut-to-chain-position assignment and leg slicing"
```

---

## Task 6: `lib/subgraph.py` — corridor gather over an arbitrary bbox

**Files:**
- Modify: `pipeline/lib/subgraph.py`
- Test: `pipeline/tests/test_subgraph.py`

**Interfaces:**
- Produces: `gather_subgraph_for_bounds(base_graph_dir: Path, grid, bounds: dict) -> LocalSubgraph`
  (same shape `bounds` as `Grid.padded_bounds`'s return: `{"minLng", "maxLng", "minLat",
  "maxLat"}`). `gather_padded_subgraph` becomes a thin wrapper over it (no behavior change — all
  existing callers/tests keep passing). Consumed by Task 12/13 (`match_tour_edges.py`'s corridor
  gather, which computes its own bbox from a leg's chain slice rather than from a grid cell).

- [ ] **Step 1: Write the failing test**

Append to `pipeline/tests/test_subgraph.py` (reuse `_write_fixture_base_graph` already defined in
that file):

```python
from lib.subgraph import gather_subgraph_for_bounds  # noqa: E402


def test_gather_subgraph_for_bounds_excludes_far_away_nodes(tmp_path):
    fine_grid = Grid(BBOX, tile_size_km=20.0)
    base_graph_dir = _write_fixture_base_graph(tmp_path, fine_grid)
    # Tight bbox around only the first two nodes (0.05,0.05)-(0.95,0.05) - the third node at
    # (0.05, 0.95) sits well outside it.
    bounds = {"minLng": 0.0, "maxLng": 1.0, "minLat": 0.0, "maxLat": 0.5}
    subgraph = gather_subgraph_for_bounds(base_graph_dir, fine_grid, bounds)
    assert len(subgraph.local_nodes) == 2


def test_gather_subgraph_for_bounds_equals_padded_gather_on_same_effective_bounds(tmp_path):
    fine_grid = Grid(BBOX, tile_size_km=20.0)
    base_graph_dir = _write_fixture_base_graph(tmp_path, fine_grid)
    padded = fine_grid.padded_bounds(cell_id=fine_grid.cell_id_for_point(0.05, 0.05), buffer_km=5.0)
    direct = gather_subgraph_for_bounds(base_graph_dir, fine_grid, padded)
    via_wrapper = gather_padded_subgraph(
        base_graph_dir, fine_grid, fine_grid.cell_id_for_point(0.05, 0.05), buffer_km=5.0
    )
    assert list(direct.global_node_ids) == list(via_wrapper.global_node_ids)
    assert len(direct.local_edges) == len(via_wrapper.local_edges)
```

The final file should contain
`test_gather_subgraph_for_bounds_excludes_far_away_nodes` and
`test_gather_subgraph_for_bounds_equals_padded_gather_on_same_effective_bounds` as the two new tests.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd pipeline && python -m pytest tests/test_subgraph.py -k gather_subgraph_for_bounds -v`
Expected: FAIL with `ImportError: cannot import name 'gather_subgraph_for_bounds'`

- [ ] **Step 3: Refactor `gather_padded_subgraph` to extract the bounds-based gather**

In `pipeline/lib/subgraph.py`, replace the body of `gather_padded_subgraph` (currently lines
38-105) with:

```python
def gather_subgraph_for_bounds(base_graph_dir: Path, grid, bounds: dict) -> LocalSubgraph:
    """Gathers every base-graph node/edge whose cell overlaps `bounds`, plus the one-hop edge-
    incidence closure (see module docstring) - the bbox-driven half of gather_padded_subgraph,
    factored out so a caller with its own bbox (match_tour_edges.py's per-leg corridor, sized off
    a chain slice rather than a grid cell) can reuse the exact same gather instead of re-deriving
    it from a cell_id it doesn't have."""
    base_graph_dir = Path(base_graph_dir)
    nodes = binfmt.load_array(base_graph_dir / "nodes.npy")
    cell_index = binfmt.load_array(base_graph_dir / "cell_index.npy")
    node_edge_index = binfmt.load_array(base_graph_dir / "node_edge_index.npy")
    node_edge_ids = binfmt.load_array(base_graph_dir / "node_edge_ids.npy")
    edges = binfmt.load_array(base_graph_dir / "edges.npy")
    interior = binfmt.load_array(base_graph_dir / "interior.npy")
    node_ele_path = base_graph_dir / "node_ele.npy"
    interior_ele_path = base_graph_dir / "interior_ele.npy"
    node_ele = (binfmt.load_array(node_ele_path) if node_ele_path.exists()
                else np.zeros(len(nodes), dtype=np.float32))
    interior_ele = (binfmt.load_array(interior_ele_path) if interior_ele_path.exists()
                     else np.zeros(len(interior), dtype=np.float32))

    overlapping_cells = grid.cell_ids_overlapping(bounds)

    if overlapping_cells:
        base_node_ids = np.unique(np.concatenate([
            np.arange(int(cell_index["start_offset"][cid]),
                      int(cell_index["start_offset"][cid] + cell_index["count"][cid]))
            for cid in overlapping_cells
        ]))
    else:
        base_node_ids = np.zeros(0, dtype=np.int64)

    incident_edge_ids, _ = binfmt.gather_ragged(
        node_edge_ids, node_edge_index["start_offset"][base_node_ids],
        node_edge_index["count"][base_node_ids],
    )
    frontier_edge_ids = np.unique(incident_edge_ids)

    if len(frontier_edge_ids):
        global_node_ids = np.unique(np.concatenate([
            base_node_ids, edges["u"][frontier_edge_ids], edges["v"][frontier_edge_ids],
        ]))
    else:
        global_node_ids = base_node_ids

    local_nodes = np.array(nodes[global_node_ids])

    local_edges = np.array(edges[frontier_edge_ids], dtype=binfmt.EDGE_DTYPE)
    if len(local_edges):
        local_edges["u"] = np.searchsorted(global_node_ids, local_edges["u"])
        local_edges["v"] = np.searchsorted(global_node_ids, local_edges["v"])

    return LocalSubgraph(
        global_node_ids=global_node_ids,
        local_nodes=local_nodes,
        local_edges=local_edges,
        interior=interior,
        local_node_ele=np.array(node_ele[global_node_ids]),
        interior_ele=interior_ele,
    )


def gather_padded_subgraph(base_graph_dir: Path, grid, cell_id: int, buffer_km: float) -> LocalSubgraph:
    return gather_subgraph_for_bounds(base_graph_dir, grid, grid.padded_bounds(cell_id, buffer_km))
```

- [ ] **Step 4: Run the full subgraph test file plus every existing caller's tests**

Run: `cd pipeline && python -m pytest tests/test_subgraph.py tests/test_build_hub_edges.py -v`
Expected: PASS — the refactor must not change `gather_padded_subgraph`'s observable behavior, so
every pre-existing test in both files must still pass unmodified.

- [ ] **Step 5: Commit**

```bash
git add pipeline/lib/subgraph.py pipeline/tests/test_subgraph.py
git commit -m "graph_building: extract bounds-based corridor gather from gather_padded_subgraph"
```

---

## Task 7: `lib/edge_output.py` — extract `write_edge_records`

**Files:**
- Create: `pipeline/lib/edge_output.py`
- Modify: `pipeline/phases/graph_building/build_hub_edges.py`
- Modify: `pipeline/tests/test_build_hub_edges.py`
- Test: `pipeline/tests/test_edge_output.py`

**Interfaces:**
- Produces: `write_edge_records(records: list[dict], out_dir: Path, write_edge_ids: bool = False)
  -> None` and `K_TRAVERSAL = 8` (moved from `build_hub_edges.py`). Consumed by
  `build_hub_edges.py` (this task) and Task 13 (`match_tour_edges.py`).
- Consumes: `binfmt.RECORD_DTYPE`, `binfmt.COORD_DTYPE`, `binfmt.save_array`.

- [ ] **Step 1: Write the failing test**

Create `pipeline/tests/test_edge_output.py` by copying the geometry-dedup / edge-ids tests
currently in `pipeline/tests/test_build_hub_edges.py` (the `_rec`, `test_write_edge_output_*` tests
around lines 460-490 and 761-799), but importing from the new location:

```python
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import binfmt  # noqa: E402
from lib.edge_output import K_TRAVERSAL, write_edge_records  # noqa: E402


def _rec(from_id=0, to_id=1, variant=0, geometry=None, base_edge_ids=None):
    return {
        "from_id": from_id, "to_id": to_id, "from_type": binfmt.TYPE_HUT,
        "to_type": binfmt.TYPE_HUT, "variant": variant,
        "distance_m": 1000.0, "road_m": 0.0, "ascent_m": 50.0, "descent_m": 20.0,
        "max_ele_m": 1500.0, "ungraded_m": 0.0, "inferred_m": 0.0, "snap_m": 5.0,
        "sac_rank": 1, "via_ferrata": False,
        "geometry": geometry if geometry is not None else [(10.0, 47.0), (10.01, 47.0)],
        "base_edge_ids": base_edge_ids if base_edge_ids is not None else [10, 11, 12],
    }


def test_write_edge_output_preserves_each_record_variant(tmp_path):
    write_edge_records([_rec(variant=0), _rec(variant=2)], tmp_path)
    arr = binfmt.load_array(tmp_path / "records.npy", mmap=False)
    assert sorted(arr["variant"].tolist()) == [0, 2]


def test_identical_variant_geometries_share_one_offset(tmp_path):
    geom = [(10.0, 47.0), (10.01, 47.0), (10.02, 47.0)]
    write_edge_records([_rec(variant=0, geometry=geom), _rec(variant=2, geometry=geom)], tmp_path)
    records = binfmt.load_array(tmp_path / "records.npy", mmap=False)
    geometry = binfmt.load_array(tmp_path / "geometry.npy", mmap=False)
    assert records["geom_offset"][0] == records["geom_offset"][1]
    assert len(geometry) == len(geom)


def test_differing_geometries_do_not_share(tmp_path):
    write_edge_records([
        _rec(variant=0, geometry=[(10.0, 47.0), (10.01, 47.0)]),
        _rec(variant=2, geometry=[(11.0, 48.0), (11.01, 48.0)]),
    ], tmp_path)
    records = binfmt.load_array(tmp_path / "records.npy", mmap=False)
    assert records["geom_offset"][0] != records["geom_offset"][1]


def test_write_edge_output_writes_sorted_edge_ids_and_prefix_suffix(tmp_path):
    out_dir = tmp_path / "hut_edges"
    write_edge_records([_rec(base_edge_ids=[30, 10, 20])], out_dir, write_edge_ids=True)
    records = binfmt.load_array(out_dir / "records.npy", mmap=False)
    edge_ids = binfmt.load_array(out_dir / "edge_ids.npy", mmap=False)
    assert list(edge_ids) == [10, 20, 30]
    assert records["edge_id_count"][0] == 3
    assert records["prefix_count"][0] == 3
    assert records["prefix_ids"][0][:3].tolist() == [30, 10, 20]


def test_write_edge_output_skips_edge_ids_when_not_requested(tmp_path):
    out_dir = tmp_path / "start_edges"
    write_edge_records([_rec()], out_dir, write_edge_ids=False)
    assert not (out_dir / "edge_ids.npy").exists()
    records = binfmt.load_array(out_dir / "records.npy", mmap=False)
    assert records["edge_id_count"][0] == 0
    assert records["prefix_count"][0] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd pipeline && python -m pytest tests/test_edge_output.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lib.edge_output'`

- [ ] **Step 3: Create `lib/edge_output.py` with the moved implementation**

Create `pipeline/lib/edge_output.py`:

```python
"""Packs a routed leg/edge (a plain dict with distance/ascent/descent/geometry/base_edge_ids) into
binfmt.RECORD_DTYPE + a flat geometry.npy - the record-packing half of build_hub_edges.py's old
_write_edge_output, extracted so match_tour_edges.py (spec 2026-08-29-official-tours-integration-
design.md §2.6) can emit the exact same on-disk shape without duplicating this logic."""

import hashlib
from pathlib import Path

import numpy as np

from lib import binfmt

K_TRAVERSAL = 8  # spec §4 of the overlapping-tracks design: ~1km at 132m mean base-edge length.


def write_edge_records(records: list, out_dir: Path, write_edge_ids: bool = False) -> None:
    """Packs `records` (each a dict with from_id/to_id/from_type/to_type/variant/distance_m/
    road_m/ascent_m/descent_m/max_ele_m/ungraded_m/inferred_m/snap_m/sac_rank/via_ferrata/
    geometry/base_edge_ids) into out_dir/records.npy + out_dir/geometry.npy, mirroring how
    build_base_graph.py packs contracted-edge interior polylines: one growing geometry array, each
    record's geom_offset/geom_count pointing into it. profile_offset/profile_count stay 0 here -
    the elevation profile pass (build_profiles.py) fills those in a later pass over this same
    records.npy.

    Identical coordinate runs are deduplicated by content hash (blake2b-128, collision probability
    far below floating-point noise in the coordinates themselves) so repeated geometry (e.g. a
    constrained hub-edge variant routing the same polyline as FAST_ANY) doesn't grow the geometry
    file linearly for zero new information.

    write_edge_ids: True to also write out_dir/edge_ids.npy - each record's FULL base-edge-id set,
    deduped and sorted ascending, concatenated across records in record order. RECORD_DTYPE's
    edge_id_offset/edge_id_count slice into it; prefix_ids/suffix_ids (fixed-width K_TRAVERSAL,
    -1-padded) live directly on RECORD_DTYPE."""
    records_arr = np.zeros(len(records), dtype=binfmt.RECORD_DTYPE)
    flat_geometry = []
    flat_edge_ids = []
    cursor = 0
    edge_id_cursor = 0
    seen_geoms = {}
    for i, r in enumerate(records):
        geom = r["geometry"]
        key = hashlib.blake2b(
            np.asarray(geom, dtype=np.float64).tobytes(), digest_size=16
        ).digest()
        offset = seen_geoms.get(key)
        if offset is None:
            offset = cursor
            seen_geoms[key] = offset
            flat_geometry.extend(geom)
            cursor += len(geom)

        if write_edge_ids:
            traversal_ids = r["base_edge_ids"]
            sorted_ids = sorted(set(traversal_ids))
            edge_id_offset = edge_id_cursor
            edge_id_count = len(sorted_ids)
            flat_edge_ids.extend(sorted_ids)
            edge_id_cursor += edge_id_count
            prefix = traversal_ids[:K_TRAVERSAL]
            suffix = list(reversed(traversal_ids[-K_TRAVERSAL:])) if traversal_ids else []
            prefix_count = len(prefix)
            suffix_count = len(suffix)
            prefix_ids = tuple(prefix + [-1] * (K_TRAVERSAL - prefix_count))
            suffix_ids = tuple(suffix + [-1] * (K_TRAVERSAL - suffix_count))
        else:
            edge_id_offset, edge_id_count = 0, 0
            prefix_ids = suffix_ids = (-1,) * K_TRAVERSAL
            prefix_count = suffix_count = 0

        records_arr[i] = (
            r["from_id"], r["to_id"], r["from_type"], r["to_type"], r["variant"],
            r["distance_m"], r["road_m"], r["ascent_m"], r["descent_m"], r["max_ele_m"],
            r["ungraded_m"], r["inferred_m"], r["snap_m"], r["sac_rank"],
            r["via_ferrata"], offset, len(geom), 0, 0,
            edge_id_offset, edge_id_count, prefix_ids, prefix_count, suffix_ids, suffix_count,
        )

    geometry_arr = np.zeros(len(flat_geometry), dtype=binfmt.COORD_DTYPE)
    if flat_geometry:
        geometry_arr["lon"] = [p[0] for p in flat_geometry]
        geometry_arr["lat"] = [p[1] for p in flat_geometry]

    binfmt.save_array(out_dir / "records.npy", records_arr)
    binfmt.save_array(out_dir / "geometry.npy", geometry_arr)
    if write_edge_ids:
        binfmt.save_array(out_dir / "edge_ids.npy", np.array(flat_edge_ids, dtype="i4"))
```

- [ ] **Step 4: Run the new test file to verify it passes**

Run: `cd pipeline && python -m pytest tests/test_edge_output.py -v`
Expected: PASS (all 5)

- [ ] **Step 5: Point `build_hub_edges.py` at the extracted function**

In `pipeline/phases/graph_building/build_hub_edges.py`:
- Remove the `import hashlib` line if `_write_edge_output` was its only user (check first with
  `grep -n hashlib pipeline/phases/graph_building/build_hub_edges.py` — keep it if used
  elsewhere).
- Remove the `K_TRAVERSAL = 8` module-level constant (line 262) and the entire
  `_write_edge_output` function definition (lines 266-338).
- Add to the imports block: `from lib.edge_output import write_edge_records  # noqa: E402`
- In `__main__`, change:
  ```python
  _write_edge_output(hut_records, out_dir / "hut_edges", write_edge_ids=True)
  _write_edge_output(access_records, out_dir / "start_edges", write_edge_ids=False)
  ```
  to:
  ```python
  write_edge_records(hut_records, out_dir / "hut_edges", write_edge_ids=True)
  write_edge_records(access_records, out_dir / "start_edges", write_edge_ids=False)
  ```

- [ ] **Step 6: Update `test_build_hub_edges.py`'s import and remove the now-duplicated tests**

In `pipeline/tests/test_build_hub_edges.py`:
- Remove `_write_edge_output` from the `from graph_building.build_hub_edges import (...)` block.
- Add `from lib.edge_output import write_edge_records  # noqa: E402` near the other imports.
- Delete the five tests that were copied into `test_edge_output.py` in Step 1
  (`test_write_edge_output_preserves_each_record_variant`,
  `test_identical_variant_geometries_share_one_offset`,
  `test_differing_geometries_do_not_share`,
  `test_write_edge_output_writes_sorted_edge_ids_and_prefix_suffix`,
  `test_write_edge_output_skips_edge_ids_when_not_requested`) — they now live in
  `test_edge_output.py`, keeping them here too would just be a duplicate of the same assertions
  against the same code.
- If any other test in the file called `_write_edge_output(...)` directly (not just imported it),
  rename those call sites to `write_edge_records(...)`.

- [ ] **Step 7: Run the full pipeline test suite**

Run: `cd pipeline && python -m pytest tests/ -v`
Expected: PASS — this is the widest blast-radius step in the plan so far (touches
`build_hub_edges.py`'s `__main__`), confirm nothing else broke.

- [ ] **Step 8: Commit**

```bash
git add pipeline/lib/edge_output.py pipeline/phases/graph_building/build_hub_edges.py \
        pipeline/tests/test_edge_output.py pipeline/tests/test_build_hub_edges.py
git commit -m "graph_building: extract write_edge_records into lib/edge_output.py"
```

---

## Task 8: `lib/edge_output.py` — extract `fold_endpoint_snaps`

**Files:**
- Modify: `pipeline/lib/edge_output.py`
- Modify: `pipeline/phases/graph_building/build_hub_edges.py`
- Test: `pipeline/tests/test_edge_output.py`

**Interfaces:**
- Produces: `fold_endpoint_snaps(path, src_snap, tgt_snap) -> tuple[float, float, float]`
  (`(snap_m, ascent_m, descent_m)`). `path` is a `lib.cell_igraph.PathResult`; `src_snap`/
  `tgt_snap` are `lib.hub_snap.SnapResult`s (both only need `.gap_m`/`.gap_dz_m`, and
  `path` only needs `.ascent_m`/`.descent_m`). Consumed by `build_hub_edges.py`'s
  `compute_hub_edges_for_cell` (this task) and Task 13 (`match_tour_edges.py`).

- [ ] **Step 1: Write the failing test**

Append to `pipeline/tests/test_edge_output.py`:

```python
from dataclasses import dataclass

from lib.edge_output import fold_endpoint_snaps  # noqa: E402


@dataclass
class _FakeSnap:
    gap_m: float
    gap_dz_m: float


@dataclass
class _FakePath:
    ascent_m: float
    descent_m: float


def test_fold_endpoint_snaps_sums_the_horizontal_gap():
    path = _FakePath(ascent_m=100.0, descent_m=50.0)
    src = _FakeSnap(gap_m=10.0, gap_dz_m=0.0)
    tgt = _FakeSnap(gap_m=5.0, gap_dz_m=0.0)
    snap_m, ascent_m, descent_m = fold_endpoint_snaps(path, src, tgt)
    assert snap_m == 15.0
    assert ascent_m == 100.0
    assert descent_m == 50.0


def test_fold_endpoint_snaps_prices_departure_climb_as_ascent():
    # src below its snap point (gap_dz_m < 0): climbing UP to the trail is ascent.
    path = _FakePath(ascent_m=0.0, descent_m=0.0)
    src = _FakeSnap(gap_m=10.0, gap_dz_m=-20.0)
    tgt = _FakeSnap(gap_m=0.0, gap_dz_m=0.0)
    _, ascent_m, descent_m = fold_endpoint_snaps(path, src, tgt)
    assert ascent_m == 20.0
    assert descent_m == 0.0


def test_fold_endpoint_snaps_prices_arrival_climb_as_ascent():
    # tgt above its snap point (gap_dz_m > 0): climbing UP off the trail to the hut is ascent.
    path = _FakePath(ascent_m=0.0, descent_m=0.0)
    src = _FakeSnap(gap_m=0.0, gap_dz_m=0.0)
    tgt = _FakeSnap(gap_m=10.0, gap_dz_m=30.0)
    _, ascent_m, descent_m = fold_endpoint_snaps(path, src, tgt)
    assert ascent_m == 30.0
    assert descent_m == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd pipeline && python -m pytest tests/test_edge_output.py -k fold_endpoint_snaps -v`
Expected: FAIL with `ImportError: cannot import name 'fold_endpoint_snaps'`

- [ ] **Step 3: Implement `fold_endpoint_snaps`**

Append to `pipeline/lib/edge_output.py`:

```python
def fold_endpoint_snaps(path, src_snap, tgt_snap) -> tuple:
    """Prices the hub-to-trail gap at both ends into distance/ascent/descent (spec E3 of
    2026-08-19-pipeline-v2-design.md): a routed path only sums routed edges, so the snap gap
    contributes zero to distance/ascent/descent unless folded in here. Shared by
    build_hub_edges.py's compute_hub_edges_for_cell and match_tour_edges.py's per-leg accumulation
    (spec 2026-08-29-official-tours-integration-design.md §2.6: "apply the SAME endpoint treatment
    build_hub_edges.py applies").

    Departure (src): climbing from the hub up to the trail (hub below its snap point, gap_dz_m < 0)
    is ascent; descending down to the trail (gap_dz_m > 0) is descent. Arrival (tgt): climbing from
    the trail up to the hub (gap_dz_m > 0) is ascent; descending down off the trail to the hub
    (gap_dz_m < 0) is descent. Returns (snap_m, ascent_m, descent_m) - distance_m folding is the
    caller's own `path.distance_m + snap_m`, since callers differ in whether distance_m already
    includes other terms."""
    snap_m = src_snap.gap_m + tgt_snap.gap_m
    ascent_m = path.ascent_m + max(0.0, -src_snap.gap_dz_m) + max(0.0, tgt_snap.gap_dz_m)
    descent_m = path.descent_m + max(0.0, src_snap.gap_dz_m) + max(0.0, -tgt_snap.gap_dz_m)
    return snap_m, ascent_m, descent_m
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd pipeline && python -m pytest tests/test_edge_output.py -v`
Expected: PASS

- [ ] **Step 5: Point `build_hub_edges.py`'s `compute_hub_edges_for_cell` at the extracted helper**

In `pipeline/phases/graph_building/build_hub_edges.py`, in `compute_hub_edges_for_cell` (around
lines 216-226), replace:

```python
                src_snap = snaps[src_key]
                tgt_snap = snaps[(t["type"], t["id"])]
                snap_m = src_snap.gap_m + tgt_snap.gap_m
                # Departure (src): climbing from hub up to the trail (hub below its snap point,
                # gap_dz_m < 0) is ascent; descending down to the trail (gap_dz_m > 0) is descent.
                # Arrival (tgt): climbing from the trail up to the hub (gap_dz_m > 0) is ascent;
                # descending down off the trail to the hub (gap_dz_m < 0) is descent.
                ascent_m = path.ascent_m + max(0.0, -src_snap.gap_dz_m) + max(0.0, tgt_snap.gap_dz_m)
                descent_m = path.descent_m + max(0.0, src_snap.gap_dz_m) + max(0.0, -tgt_snap.gap_dz_m)
```

with:

```python
                src_snap = snaps[src_key]
                tgt_snap = snaps[(t["type"], t["id"])]
                snap_m, ascent_m, descent_m = fold_endpoint_snaps(path, src_snap, tgt_snap)
```

Add `from lib.edge_output import fold_endpoint_snaps, write_edge_records  # noqa: E402` (merge with
the existing `from lib.edge_output import write_edge_records` import added in Task 7).

- [ ] **Step 6: Run the full pipeline test suite**

Run: `cd pipeline && python -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add pipeline/lib/edge_output.py pipeline/phases/graph_building/build_hub_edges.py \
        pipeline/tests/test_edge_output.py
git commit -m "graph_building: extract fold_endpoint_snaps into lib/edge_output.py"
```

---

## Task 9: `phases/downloads/fetch_tours.py`

**Files:**
- Create: `pipeline/phases/downloads/fetch_tours.py`
- Test: `pipeline/tests/test_fetch_tours.py`

**Interfaces:**
- Produces: `parse_huettenliste(raw: str) -> list[str]`, `resolve_hut_indices(guids: list[str],
  hut_id_to_index: dict, tour_short_code: str, gaps: list) -> list[int]` (unresolved → `-1`
  sentinel, appended to `gaps`), `build_tour_records(features: list, hut_id_to_index: dict) ->
  tuple[list[dict], list[dict], list[dict]]` (`(tours, traces, gaps)`, `#DUMMY`-filtered).
  Consumed by this task's own `__main__` and by Task 10 (dag wiring, indirectly via the produced
  files).

- [ ] **Step 1: Write the failing tests**

Create `pipeline/tests/test_fetch_tours.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from downloads.fetch_tours import (  # noqa: E402
    build_tour_records, parse_huettenliste, resolve_hut_indices,
)

HUT_ID_TO_INDEX = {"{GUID-A}": 0, "{GUID-B}": 1, "{GUID-C}": 2}


def test_parse_huettenliste_splits_and_strips():
    assert parse_huettenliste("{GUID-A}, {GUID-B} ,{GUID-C}") == ["{GUID-A}", "{GUID-B}", "{GUID-C}"]


def test_parse_huettenliste_empty_is_empty_list():
    assert parse_huettenliste(None) == []
    assert parse_huettenliste("") == []


def test_resolve_hut_indices_resolves_every_known_guid():
    gaps = []
    out = resolve_hut_indices(["{GUID-A}", "{GUID-C}"], HUT_ID_TO_INDEX, "TST", gaps)
    assert out == [0, 2]
    assert gaps == []


def test_resolve_hut_indices_records_unresolvable_guid_as_sentinel_not_dropped():
    # spec §1: dropping a hut from the middle of the chain would silently fuse two real stages
    # into one leg - it must come back as a sentinel (-1) plus a gap record, never be omitted.
    gaps = []
    out = resolve_hut_indices(["{GUID-A}", "{GUID-MISSING}", "{GUID-C}"], HUT_ID_TO_INDEX, "TST", gaps)
    assert out == [0, -1, 2]
    assert len(gaps) == 1
    assert gaps[0]["globalId"] == "{GUID-MISSING}"
    assert gaps[0]["tourShortCode"] == "TST"


def _feature(short_code, name, huettenliste, is_loop=0, global_id="{TOUR-1}", geometry_paths=None):
    return {
        "attributes": {
            "GlobalID": global_id, "Bezeichnung": name, "Kurzbezeichnung": short_code,
            "Rundtour": is_loop, "Homepage": "https://example.invalid",
            "Download": None, "Huettenliste": huettenliste,
        },
        "geometry": {"paths": geometry_paths if geometry_paths is not None else [[[10.0, 47.0], [10.1, 47.1]]]},
    }


def test_dummy_record_is_filtered_by_short_code_not_by_missing_name():
    # #DUMMY has a non-empty, resolvable Huettenliste (spec §0) - the filter must key off
    # Kurzbezeichnung=="#DUMMY", not off a null-name/empty-hut-list heuristic.
    features = [
        _feature("#DUMMY", None, "{GUID-A},{GUID-B}"),
        _feature("REAL", "Real Tour", "{GUID-A},{GUID-C}"),
    ]
    tours, traces, gaps = build_tour_records(features, HUT_ID_TO_INDEX)
    assert len(tours) == 1
    assert tours[0]["shortCode"] == "REAL"


def test_karwendel_hoehenweg_style_null_name_is_kept():
    # A real tour can also lack a distinct Bezeichnung/Kurzbezeichnung pair (spec §0) - must NOT
    # be filtered just because Kurzbezeichnung is missing/None, only #DUMMY is special-cased.
    features = [_feature(None, "Karwendel Höhenweg", "{GUID-A},{GUID-B}")]
    tours, _, _ = build_tour_records(features, HUT_ID_TO_INDEX)
    assert len(tours) == 1
    assert tours[0]["name"] == "Karwendel Höhenweg"


def test_empty_hut_list_tour_is_kept_with_empty_hut_indices():
    # Wiener Höhenweg / MontafonerSilvrettarunde (spec §0): geometry exists, hut list doesn't -
    # stays in tours.json, just produces zero legs downstream (out of scope here).
    features = [_feature("WHW", "Wiener Höhenweg", None)]
    tours, traces, _ = build_tour_records(features, HUT_ID_TO_INDEX)
    assert tours[0]["hutIndices"] == []


def test_tour_id_is_the_positional_index_and_traces_are_aligned():
    features = [
        _feature("A", "Tour A", "{GUID-A}", global_id="{G-A}"),
        _feature("B", "Tour B", "{GUID-B}", global_id="{G-B}"),
    ]
    tours, traces, _ = build_tour_records(features, HUT_ID_TO_INDEX)
    assert [t["tourId"] for t in tours] == [0, 1]
    assert [t["tourId"] for t in traces] == [0, 1]
    assert tours[1]["globalId"] == "{G-B}"


def test_is_loop_and_hut_indices_populated():
    features = [_feature("A", "Tour A", "{GUID-A},{GUID-B},{GUID-C}", is_loop=1)]
    tours, _, _ = build_tour_records(features, HUT_ID_TO_INDEX)
    assert tours[0]["isLoop"] is True
    assert tours[0]["hutIndices"] == [0, 1, 2]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd pipeline && python -m pytest tests/test_fetch_tours.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'downloads.fetch_tours'`

- [ ] **Step 3: Implement `fetch_tours.py`**

Create `pipeline/phases/downloads/fetch_tours.py`:

```python
#!/usr/bin/env python3
"""Fetches the AV's 26 official multi-day tour routes from the AVT_CAA_TOUR_View_L ArcGIS layer
(docs/alpenverein-api.md §3, docs/superpowers/specs/2026-08-29-official-tours-integration-
design.md §0/§1) and resolves each tour's Huettenliste (a comma-separated, IN-ORDER list of hut
GUIDs) against huts.geojson's own `id` property into RECORD_DTYPE's positional hut index
convention (the same index build_hub_edges.py's load_all_hubs uses for TYPE_HUT).

Two output files, not one: tours.json (shipped - client-shaped tour metadata) and
tour_traces.json (internal - the ~3.5MB raw per-tour polyline fragments, consumed only by
match_tour_edges.py, never shipped to the client - that geometry ships matched, via
tour-edges.pmtiles, once match_tour_edges.py has run).

Usage: python pipeline/phases/downloads/fetch_tours.py
"""

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib.pipeline import OSM_DIR  # noqa: E402
from lib.timing import phase  # noqa: E402

SCRIPT_NAME = "fetch_tours.py"


def parse_huettenliste(raw) -> list:
    if not raw:
        return []
    return [g.strip() for g in raw.split(",") if g.strip()]


def resolve_hut_indices(guids: list, hut_id_to_index: dict, tour_short_code: str, gaps: list) -> list:
    """Resolves each GUID to huts.geojson's positional index, in the SAME order as `guids` -
    tour order is meaningful (leg sequence), so this must never reorder or drop entries. An
    unresolvable GUID (hut outside config["bbox"], reclassified to partner_betriebe.geojson, or
    genuinely absent - verified empty against the live layer as of 2026-08-29, so this path is
    defensive) becomes -1 and is recorded in `gaps` - match_tour_edges.py splits the chain at a
    -1 entry rather than silently fusing the two real stages on either side of it into one leg."""
    out = []
    for guid in guids:
        idx = hut_id_to_index.get(guid)
        if idx is None:
            gaps.append({
                "tourShortCode": tour_short_code, "globalId": guid, "reason": "unresolved_hut_guid",
            })
            out.append(-1)
        else:
            out.append(idx)
    return out


def build_tour_records(features: list, hut_id_to_index: dict) -> tuple:
    """Returns (tours, traces, gaps). tours/traces are index-aligned by position - tourId is the
    array index into BOTH lists (same convention as huts.geojson's own feature-array-position
    hut ids), stable for the life of one pipeline run. `#DUMMY` (garbage record, geometry in
    Bolivia, spec §0) is filtered by Kurzbezeichnung, not by a null-name/empty-hut-list heuristic -
    both of those also occur on real tours."""
    tours, traces, gaps = [], [], []
    for f in features:
        a = f["attributes"]
        if a.get("Kurzbezeichnung") == "#DUMMY":
            continue
        guids = parse_huettenliste(a.get("Huettenliste"))
        short_code = a.get("Kurzbezeichnung") or ""
        hut_indices = resolve_hut_indices(guids, hut_id_to_index, short_code, gaps)
        tour_id = len(tours)
        tours.append({
            "tourId": tour_id,
            "globalId": a.get("GlobalID"),
            "name": a.get("Bezeichnung"),
            "shortCode": a.get("Kurzbezeichnung"),
            "isLoop": bool(a.get("Rundtour")),
            "homepage": a.get("Homepage"),
            "hutIndices": hut_indices,
        })
        traces.append({"tourId": tour_id, "paths": f.get("geometry", {}).get("paths", [])})
    return tours, traces, gaps


if __name__ == "__main__":
    huts_path = OSM_DIR / "huts.geojson"
    with open(huts_path, encoding="utf-8") as fh:
        hut_id_to_index = {
            feat["properties"]["id"]: i
            for i, feat in enumerate(json.load(fh)["features"])
        }

    url = (
        "https://services1.arcgis.com/PHS4LHADrqt5glC9/arcgis/rest/services/"
        "AVT_CAA_TOUR_View_L/FeatureServer/0/query"
        "?where=1%3D1&outFields=*&returnGeometry=true&outSR=4326&resultRecordCount=200&f=json"
    )

    with phase(SCRIPT_NAME, "fetch_tours"):
        with urllib.request.urlopen(url) as res:
            data = json.load(res)

    tours, traces, gaps = build_tour_records(data["features"], hut_id_to_index)
    print(f"tours: {len(tours)}, hut-guid gaps: {len(gaps)}")

    tours_path = OSM_DIR / "tours.json"
    traces_path = OSM_DIR / "tour_traces.json"
    gaps_path = OSM_DIR / "tour-fetch-gaps.json"
    with open(tours_path, "w", encoding="utf-8") as fh:
        json.dump(tours, fh)
    with open(traces_path, "w", encoding="utf-8") as fh:
        json.dump(traces, fh)
    with open(gaps_path, "w", encoding="utf-8") as fh:
        json.dump(gaps, fh)
    print(f"written {tours_path}, {traces_path} and {gaps_path}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd pipeline && python -m pytest tests/test_fetch_tours.py -v`
Expected: PASS (all tests — no network call happens in any of them, only the pure functions are
exercised)

- [ ] **Step 5: Commit**

```bash
git add pipeline/phases/downloads/fetch_tours.py pipeline/tests/test_fetch_tours.py
git commit -m "downloads: add fetch_tours.py for the AV official-tours layer"
```

---

## Task 10: `dag/downloads.py` — `task_fetch_tours` wiring

**Files:**
- Modify: `pipeline/dag/downloads.py`
- Modify: `pipeline/dodo.py`
- Test: `pipeline/tests/test_dodo_wiring.py`

**Interfaces:**
- Produces: `dag.downloads.task_fetch_tours()` — a doit task dict with `file_dep=[huts.geojson]`
  (not `[]` — resolving GUIDs to positional indices means a huts refetch that reorders/refilters
  huts must invalidate this), `targets=[tours.json, tour_traces.json, tour-fetch-gaps.json]`,
  tracking `bbox_json` for the same reason `task_fetch_huts` does.

- [ ] **Step 1: Write the failing test**

Append to `pipeline/tests/test_dodo_wiring.py`:

```python
def test_fetch_tours_depends_on_huts_geojson_not_just_network():
    # Resolving Huettenliste GUIDs to positional indices means a huts refetch that reorders or
    # re-filters huts silently invalidates every hutIndices entry - file_dep must NOT be [].
    deps = dodo.task_fetch_tours()["file_dep"]
    assert any(d.endswith("huts.geojson") for d in deps)


def test_fetch_tours_targets_all_three_outputs():
    targets = dodo.task_fetch_tours()["targets"]
    assert any(t.endswith("tours.json") for t in targets)
    assert any(t.endswith("tour_traces.json") for t in targets)
    assert any(t.endswith("tour-fetch-gaps.json") for t in targets)


def test_fetch_tours_tracks_bbox():
    param_names = {p["name"] for p in dodo.task_fetch_tours().get("params", [])}
    assert "bbox_json" in param_names
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd pipeline && python -m pytest tests/test_dodo_wiring.py -k fetch_tours -v`
Expected: FAIL with `AttributeError: module 'dodo' has no attribute 'task_fetch_tours'`

- [ ] **Step 3: Add `task_fetch_tours` to `dag/downloads.py`**

In `pipeline/dag/downloads.py`, after `task_fetch_huts`:

```python
def task_fetch_tours():
    return pipeline_task(
        "phases/downloads/fetch_tours.py",
        # fetch_tours.py resolves Huettenliste GUIDs against huts.geojson's own feature-array
        # position - unlike fetch_huts.py's plain network fetch, a huts refetch that reorders or
        # re-filters huts silently invalidates every hutIndices entry, so this must be a real
        # file_dep, not just a tracked param.
        tracking_params=[
            tracking_param("bbox_json", str, json.dumps(CONFIG["bbox"], sort_keys=True)),
        ],
        file_dep=[OSM_DIR / "huts.geojson"],
        targets=[
            OSM_DIR / "tours.json", OSM_DIR / "tour_traces.json", OSM_DIR / "tour-fetch-gaps.json",
        ],
    )
```

- [ ] **Step 4: Register the task in `dodo.py`**

In `pipeline/dodo.py`, change the `dag.downloads` import to include `task_fetch_tours`:

```python
from dag.downloads import (  # noqa: E402,F401
    task_download_extracts, task_fetch_dem, task_fetch_huts, task_fetch_stations_parking,
    task_fetch_tours,
)
```

Do **not** add `"fetch_tours"` to `DOIT_CONFIG["default_tasks"]` yet — that happens in Task 18,
once `match_tour_edges` and the postprocessing tasks that consume its output exist, so the ordered
list can be added in one place with its correct position in the DAG.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd pipeline && python -m pytest tests/test_dodo_wiring.py -v`
Expected: PASS (all tests, confirming no other wiring test broke)

- [ ] **Step 6: Commit**

```bash
git add pipeline/dag/downloads.py pipeline/dodo.py pipeline/tests/test_dodo_wiring.py
git commit -m "downloads: wire fetch_tours into the doit DAG"
```

---

## Task 11: `match_tour_edges.py` — leg enumeration

**Files:**
- Create: `pipeline/phases/graph_building/match_tour_edges.py`
- Test: `pipeline/tests/test_match_tour_edges.py`

**Interfaces:**
- Produces: `build_tour_legs(tour: dict) -> list[tuple[int, int, int]]` — returns
  `(leg_index, from_hut_index, to_hut_index)` triples, skipping any leg touching a `-1` sentinel
  (spec §1's split-chain convention from Task 9) and appending the `Rundtour` closing leg
  (`hutIndices[-1] -> hutIndices[0]`) when `tour["isLoop"]` is true (spec §2.1). Consumed by this
  task's own `__main__` (Task 13).

- [ ] **Step 1: Write the failing tests**

Create `pipeline/tests/test_match_tour_edges.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from graph_building.match_tour_edges import build_tour_legs  # noqa: E402


def _tour(hut_indices, is_loop=False):
    return {"tourId": 0, "hutIndices": hut_indices, "isLoop": is_loop}


def test_open_tour_yields_n_minus_one_legs():
    legs = build_tour_legs(_tour([0, 1, 2, 3]))
    assert legs == [(0, 0, 1), (1, 1, 2), (2, 2, 3)]


def test_loop_tour_yields_n_legs_with_contiguous_leg_index():
    # spec §2.1 / Testing: a loop tour yields N legs, not N-1, and leg_index is contiguous -
    # the closing leg (last hut -> first hut) is appended.
    legs = build_tour_legs(_tour([0, 1, 2], is_loop=True))
    assert legs == [(0, 0, 1), (1, 1, 2), (2, 2, 0)]
    assert [leg[0] for leg in legs] == [0, 1, 2]


def test_unresolved_hut_sentinel_splits_the_chain():
    # -1 (fetch_tours.py's unresolved-GUID sentinel) drops BOTH legs touching it, not just one -
    # never silently fuses the two real stages on either side into one leg (spec §1).
    legs = build_tour_legs(_tour([0, 1, -1, 3, 4]))
    assert legs == [(0, 0, 1), (3, 3, 4)]


def test_empty_hut_list_yields_no_legs():
    assert build_tour_legs(_tour([])) == []


def test_single_hut_yields_no_legs():
    assert build_tour_legs(_tour([0])) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd pipeline && python -m pytest tests/test_match_tour_edges.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'graph_building.match_tour_edges'`

- [ ] **Step 3: Implement `build_tour_legs`**

Create `pipeline/phases/graph_building/match_tour_edges.py`:

```python
#!/usr/bin/env python3
"""Matches each official AV tour's legs (hutIndices[i] -> hutIndices[i+1], plus the closing leg
for a Rundtour) onto the persisted base graph, constrained to the AV's own published route
geometry rather than routed freely - see docs/superpowers/specs/2026-08-29-official-tours-
integration-design.md. Produces data/osm/tour_edges/{records.npy, geometry.npy, edge_ids.npy,
tour_meta.npy} (same shape as hut_edges/, plus the tour_meta.npy sidecar) and
tour-match-gaps.json (spec §2.5's never-faked gap reasons).

Usage: python pipeline/phases/graph_building/match_tour_edges.py
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import binfmt  # noqa: E402
from lib.pipeline import OSM_DIR, load_config  # noqa: E402
from lib.timing import phase  # noqa: E402

SCRIPT_NAME = "match_tour_edges.py"


def build_tour_legs(tour: dict) -> list:
    """(leg_index, from_hut_index, to_hut_index) triples in tour order, plus the Rundtour closing
    leg (spec §2.1). A leg touching fetch_tours.py's -1 unresolved-GUID sentinel is dropped -
    BOTH legs on either side of a -1 entry are skipped, since neither has a real hut on both ends
    (spec §1's "split the chain" convention)."""
    huts = tour["hutIndices"]
    pairs = list(zip(huts, huts[1:]))
    if tour.get("isLoop") and len(huts) >= 2:
        pairs.append((huts[-1], huts[0]))
    legs = []
    for i, (a, b) in enumerate(pairs):
        if a == -1 or b == -1:
            continue
        legs.append((i, a, b))
    return legs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd pipeline && python -m pytest tests/test_match_tour_edges.py -v`
Expected: PASS (all 5)

- [ ] **Step 5: Commit**

```bash
git add pipeline/phases/graph_building/match_tour_edges.py pipeline/tests/test_match_tour_edges.py
git commit -m "graph_building: add match_tour_edges.py leg enumeration"
```

---

## Task 12: `match_tour_edges.py` — per-leg corridor match

**Files:**
- Modify: `pipeline/phases/graph_building/match_tour_edges.py`
- Test: `pipeline/tests/test_match_tour_edges.py`

**Interfaces:**
- Consumes: `lib.subgraph.gather_subgraph_for_bounds` (Task 6), `lib.hub_snap.
  reconstruct_local_snaps`, `lib.cell_igraph.build_base_igraph_arrays`/`build_igraph_from_base`/
  `accumulate_path`, `lib.edge_output.fold_endpoint_snaps` (Task 8), `lib.tour_geometry.
  leg_chain_slice` (Task 5).
- Produces: `corridor_bounds(points: list[tuple], buffer_m: float, grid) -> dict`,
  `match_leg(subgraph, src_key: tuple, tgt_key: tuple, persisted_snaps: dict, trace_length_m:
  float, length_divergence_ratio: float) -> dict` — returns either `{"ok": True, "path":
  PathResult, "src_snap": SnapResult, "tgt_snap": SnapResult}` or `{"ok": False, "reason": str,
  "detail": dict}` (one of §2.5's gap reasons: `hut_unsnapped`, `outside_extract`,
  `no_corridor_path`, `length_divergent`). Consumed by Task 13's `__main__`.

- [ ] **Step 1: Write the failing tests**

Append to `pipeline/tests/test_match_tour_edges.py`:

```python
import numpy as np

from lib import binfmt  # noqa: E402
from lib.grid import Grid  # noqa: E402
from lib.hub_snap import PersistedSnap  # noqa: E402
from lib.subgraph import LocalSubgraph  # noqa: E402
from graph_building.match_tour_edges import corridor_bounds, match_leg  # noqa: E402

BBOX = {"minLng": 0.0, "maxLng": 1.0, "minLat": 0.0, "maxLat": 1.0}


def test_corridor_bounds_pads_the_points_bbox():
    grid = Grid(BBOX, tile_size_km=20.0)
    points = [(0.5, 0.5), (0.51, 0.5), (0.52, 0.5)]
    bounds = corridor_bounds(points, buffer_m=150.0, grid=grid)
    assert bounds["minLng"] < 0.5
    assert bounds["maxLng"] > 0.52
    assert bounds["minLat"] < 0.5
    assert bounds["maxLat"] > 0.5


def _line_subgraph_1000m():
    nodes = np.zeros(2, dtype=binfmt.NODE_DTYPE)
    nodes[0] = (0.0, 0.0, 0)
    nodes[1] = (0.009, 0.0, 0)  # ~1000m east at the equator
    edges = np.zeros(1, dtype=binfmt.EDGE_DTYPE)
    edges[0] = (0, 1, 1000.0, 0.0, 0.0, 0.0, 1000.0, 30.0, 10.0, -1, False, True, 0, 0, 0)
    interior = np.zeros(0, dtype=binfmt.COORD_DTYPE)
    return LocalSubgraph(
        global_node_ids=np.array([100, 101]), local_nodes=nodes, local_edges=edges,
        interior=interior,
        local_node_ele=np.zeros(2, dtype=np.float32), interior_ele=np.zeros(0, dtype=np.float32),
    )


def _node_snap(global_node_id, gap_m=0.0, gap_dz_m=0.0):
    return PersistedSnap(kind=binfmt.SNAP_KIND_NODE, global_node_id=global_node_id,
                          gap_m=gap_m, gap_dz_m=gap_dz_m)


def test_match_leg_routes_a_simple_corridor():
    subgraph = _line_subgraph_1000m()
    src_key, tgt_key = (binfmt.TYPE_HUT, 0), (binfmt.TYPE_HUT, 1)
    persisted = {src_key: _node_snap(100), tgt_key: _node_snap(101)}
    result = match_leg(subgraph, src_key, tgt_key, persisted, trace_length_m=1000.0,
                        length_divergence_ratio=2.0)
    assert result["ok"] is True
    assert result["path"].distance_m == 1000.0


def test_match_leg_reports_hut_unsnapped_when_src_missing():
    subgraph = _line_subgraph_1000m()
    src_key, tgt_key = (binfmt.TYPE_HUT, 0), (binfmt.TYPE_HUT, 1)
    persisted = {tgt_key: _node_snap(101)}  # src_key never snapped
    result = match_leg(subgraph, src_key, tgt_key, persisted, trace_length_m=1000.0,
                        length_divergence_ratio=2.0)
    assert result == {"ok": False, "reason": "hut_unsnapped", "detail": {"missing": [src_key]}}


def test_match_leg_reports_outside_extract_when_corridor_is_empty():
    empty = LocalSubgraph(
        global_node_ids=np.zeros(0, dtype=np.int64),
        local_nodes=np.zeros(0, dtype=binfmt.NODE_DTYPE),
        local_edges=np.zeros(0, dtype=binfmt.EDGE_DTYPE),
        interior=np.zeros(0, dtype=binfmt.COORD_DTYPE),
        local_node_ele=np.zeros(0, dtype=np.float32), interior_ele=np.zeros(0, dtype=np.float32),
    )
    src_key, tgt_key = (binfmt.TYPE_HUT, 0), (binfmt.TYPE_HUT, 1)
    result = match_leg(empty, src_key, tgt_key, {}, trace_length_m=1000.0,
                        length_divergence_ratio=2.0)
    assert result["reason"] == "outside_extract"


def test_match_leg_reports_length_divergent_when_routed_far_exceeds_trace():
    subgraph = _line_subgraph_1000m()
    src_key, tgt_key = (binfmt.TYPE_HUT, 0), (binfmt.TYPE_HUT, 1)
    persisted = {src_key: _node_snap(100), tgt_key: _node_snap(101)}
    # routed 1000m vs a trace of only 100m - ratio 10x, past the 2.0 divergence ratio.
    result = match_leg(subgraph, src_key, tgt_key, persisted, trace_length_m=100.0,
                        length_divergence_ratio=2.0)
    assert result["reason"] == "length_divergent"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd pipeline && python -m pytest tests/test_match_tour_edges.py -k "corridor_bounds or match_leg" -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement `corridor_bounds` and `match_leg`**

Add to `pipeline/phases/graph_building/match_tour_edges.py` (after the imports, before
`build_tour_legs`, or after it — order within the file doesn't matter, keep `build_tour_legs`
where Task 11 put it):

```python
from lib import hub_snap  # noqa: E402
from lib.cell_igraph import (  # noqa: E402
    accumulate_path, build_base_igraph_arrays, build_igraph_from_base,
)
from lib.edge_output import fold_endpoint_snaps  # noqa: E402
from lib.grid import KM_PER_DEG_LAT  # noqa: E402
from lib.subgraph import gather_subgraph_for_bounds  # noqa: E402
```

```python
def corridor_bounds(points: list, buffer_m: float, grid) -> dict:
    """Bbox around `points`, padded by buffer_m - the "buffer the fragments" half of spec §2.3's
    corridor construction, sized directly off a leg's own chain slice rather than a grid cell (see
    lib/subgraph.py's gather_subgraph_for_bounds, which this feeds)."""
    lons = [p[0] for p in points]
    lats = [p[1] for p in points]
    dlng = (buffer_m / 1000.0) / grid.km_per_deg_lng
    dlat = (buffer_m / 1000.0) / KM_PER_DEG_LAT
    return {
        "minLng": min(lons) - dlng, "maxLng": max(lons) + dlng,
        "minLat": min(lats) - dlat, "maxLat": max(lats) + dlat,
    }


def match_leg(subgraph, src_key: tuple, tgt_key: tuple, persisted_snaps: dict,
              trace_length_m: float, length_divergence_ratio: float) -> dict:
    """Routes one leg's src_key->tgt_key hut pair inside `subgraph` (already gathered as the leg's
    own corridor, spec §2.3) using the SAME igraph-building/path-walking primitives
    build_hub_edges.py uses (build_base_igraph_arrays/build_igraph_from_base/accumulate_path) -
    unmasked (edge_mask=None), since a tour leg is not a member of graph.variants (spec §5).

    Returns {"ok": True, "path": PathResult, "src_snap": SnapResult, "tgt_snap": SnapResult} or
    {"ok": False, "reason": <spec §2.5 reason>, "detail": {...}} - never a placeholder result."""
    if len(subgraph.local_nodes) == 0:
        return {"ok": False, "reason": "outside_extract", "detail": {}}

    local_snaps = hub_snap.reconstruct_local_snaps(subgraph, {src_key, tgt_key}, persisted_snaps)
    missing = [k for k in (src_key, tgt_key) if k not in local_snaps]
    if missing:
        return {"ok": False, "reason": "hut_unsnapped", "detail": {"missing": missing}}

    base_arrays = build_base_igraph_arrays(subgraph, local_snaps)
    graph, hub_vertex, vertex_coords = build_igraph_from_base(base_arrays, edge_mask=None)
    src_v, tgt_v = hub_vertex.get(src_key), hub_vertex.get(tgt_key)
    if src_v is None or tgt_v is None:
        return {"ok": False, "reason": "no_corridor_path", "detail": {}}

    if src_v == tgt_v:
        epath = []
    else:
        epath = graph.get_shortest_paths(src_v, to=tgt_v, weights="weight", output="epath")[0]
        if not epath:
            return {"ok": False, "reason": "no_corridor_path", "detail": {}}
    path = accumulate_path(graph, vertex_coords, src_v, tgt_v, epath)

    src_snap, tgt_snap = local_snaps[src_key], local_snaps[tgt_key]
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

Note: `hub_snap.reconstruct_local_snaps` returns `lib.hub_snap.SnapResult` objects (not
`PersistedSnap`) — the test fixture above builds `PersistedSnap` for the `persisted_snaps` dict
input (matching `reconstruct_local_snaps`'s own expected input shape, exactly as
`build_hub_edges.py`'s `_run_cell` passes it), and `reconstruct_local_snaps` translates those into
subgraph-local `SnapResult`s internally — verify this by re-reading
`pipeline/lib/hub_snap.py:438-481` if the test's `_node_snap` fixture doesn't line up.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd pipeline && python -m pytest tests/test_match_tour_edges.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add pipeline/phases/graph_building/match_tour_edges.py pipeline/tests/test_match_tour_edges.py
git commit -m "graph_building: add corridor-constrained leg matching to match_tour_edges.py"
```

---

## Task 13: `match_tour_edges.py` — `__main__` orchestration

**Files:**
- Modify: `pipeline/phases/graph_building/match_tour_edges.py`
- Test: `pipeline/tests/test_match_tour_edges.py`

**Interfaces:**
- Consumes: `lib.tour_geometry.reassemble_fragments`/`orient_chain`/`assign_hut_position`/
  `leg_chain_slice` (Tasks 3-5), `lib.edge_output.write_edge_records` (Task 7), `binfmt.
  VARIANT_OFFICIAL`/`TOUR_META_DTYPE` (Task 2), `build_tour_legs`/`corridor_bounds`/`match_leg`
  (Tasks 11-12).
- Produces: `build_tour_record(tour_id, leg_index, from_hut, to_hut, from_coord, to_coord,
  match_result) -> dict` (the per-record dict `write_edge_records` expects), plus the script's
  `__main__` that reads `tours.json`/`tour_traces.json`/`hub_snaps.npy`/`hub_snap_interior.npy`/
  `base_graph/manifest.json`, and writes `tour_edges/{records.npy, geometry.npy, edge_ids.npy,
  tour_meta.npy}` + `tour-match-gaps.json`.

- [ ] **Step 1: Write the failing test for `build_tour_record`**

Append to `pipeline/tests/test_match_tour_edges.py`:

```python
from lib.cell_igraph import PathResult  # noqa: E402
from graph_building.match_tour_edges import build_tour_record  # noqa: E402


def test_build_tour_record_shape_matches_write_edge_records_expectations():
    path = PathResult(
        coords=[(0.003, 0.0)], distance_m=900.0, road_m=0.0, ungraded_m=0.0, inferred_m=0.0,
        ascent_m=30.0, descent_m=10.0, max_ele_m=1200.0, sac_rank=1, via_ferrata=False,
        base_edge_ids=[7],
    )
    src_snap = _node_snap(100, gap_m=5.0, gap_dz_m=0.0)
    tgt_snap = _node_snap(101, gap_m=3.0, gap_dz_m=0.0)
    # match_leg returns SnapResult (post-reconstruct_local_snaps), not PersistedSnap - build a
    # minimal stand-in with the same .gap_m/.gap_dz_m surface fold_endpoint_snaps reads.
    from dataclasses import dataclass

    @dataclass
    class _Snap:
        gap_m: float
        gap_dz_m: float

    record = build_tour_record(
        from_hut=0, to_hut=1, from_coord=(10.0, 47.0), to_coord=(10.01, 47.0),
        path=path, src_snap=_Snap(5.0, 0.0), tgt_snap=_Snap(3.0, 0.0),
    )
    assert record["from_id"] == 0 and record["to_id"] == 1
    assert record["from_type"] == binfmt.TYPE_HUT and record["to_type"] == binfmt.TYPE_HUT
    assert record["variant"] == binfmt.VARIANT_OFFICIAL
    assert record["distance_m"] == 900.0 + 5.0 + 3.0
    assert record["snap_m"] == 8.0
    assert record["geometry"][0] == (10.0, 47.0)
    assert record["geometry"][-1] == (10.01, 47.0)
    assert record["base_edge_ids"] == [7]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pipeline && python -m pytest tests/test_match_tour_edges.py -k build_tour_record -v`
Expected: FAIL with `ImportError: cannot import name 'build_tour_record'`

- [ ] **Step 3: Implement `build_tour_record` and `__main__`**

Add to `pipeline/phases/graph_building/match_tour_edges.py`:

```python
from lib.edge_output import write_edge_records  # noqa: E402
from lib.tour_geometry import (  # noqa: E402
    assign_hut_position, leg_chain_slice, orient_chain, reassemble_fragments,
)


def build_tour_record(from_hut: int, to_hut: int, from_coord: tuple, to_coord: tuple,
                       path, src_snap, tgt_snap) -> dict:
    """Packs one routed leg into the dict shape lib.edge_output.write_edge_records expects -
    applies the SAME endpoint treatment build_hub_edges.py applies (spec §2.6): snap_m/gap_dz_m
    folded via fold_endpoint_snaps, geometry prefixed/suffixed with the hut's own coordinate."""
    snap_m, ascent_m, descent_m = fold_endpoint_snaps(path, src_snap, tgt_snap)
    geometry = [from_coord, *path.coords, to_coord]
    return {
        "from_id": from_hut, "to_id": to_hut,
        "from_type": binfmt.TYPE_HUT, "to_type": binfmt.TYPE_HUT,
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


def _chain_for_tour(paths: list, break_threshold_m: float, hut_coords_in_order: list, is_loop: bool):
    """Reassembles + orients a tour's fragments (spec §2.2). Returns (chains, oriented_primary) -
    oriented_primary is the single reassembled+oriented chain when reassembly produced exactly
    one, else None (callers fall back to a whole-tour bbox built from ALL chains' points, per
    spec §2.3's mitigation note, and every leg whose two huts don't land in the SAME chain becomes
    a chain_not_reassembled gap - spec §2.5)."""
    chains = reassemble_fragments(paths, break_threshold_m)
    if len(chains) == 1:
        return chains, orient_chain(chains[0], hut_coords_in_order, is_loop)
    return chains, None


if __name__ == "__main__":
    config = load_config()
    tm = config["tourMatch"]
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-graph-dir", default=str(OSM_DIR / "base_graph"))
    parser.add_argument("--out-dir", default=str(OSM_DIR))
    parser.add_argument("--fragment-break-m", type=float, default=tm["fragmentBreakM"])
    parser.add_argument("--corridor-buffer-m", type=float, default=tm["corridorBufferM"])
    parser.add_argument("--max-hut-trace-m", type=float, default=tm["maxHutTraceM"])
    parser.add_argument("--length-divergence-ratio", type=float, default=tm["lengthDivergenceRatio"])
    args = parser.parse_args()

    from lib.grid import Grid

    base_graph_dir = Path(args.base_graph_dir)
    manifest = binfmt.load_manifest(base_graph_dir / "manifest.json")
    grid = Grid(manifest["bbox"], manifest["tile_size_km"])

    with open(OSM_DIR / "tours.json", encoding="utf-8") as fh:
        tours = json.load(fh)
    with open(OSM_DIR / "tour_traces.json", encoding="utf-8") as fh:
        traces_by_tour_id = {t["tourId"]: t["paths"] for t in json.load(fh)}
    with open(OSM_DIR / "huts.geojson", encoding="utf-8") as fh:
        hut_features = json.load(fh)["features"]
    hut_coords = [tuple(f["geometry"]["coordinates"]) for f in hut_features]

    hub_snaps_arr = binfmt.load_array(Path(args.out_dir) / "hub_snaps.npy", mmap=False)
    hub_snap_interior_arr = binfmt.load_array(Path(args.out_dir) / "hub_snap_interior.npy", mmap=False)
    persisted_snaps = hub_snap.load_persisted_snaps(hub_snaps_arr, hub_snap_interior_arr)

    all_records, tour_meta_rows, gaps = [], [], []

    with phase(SCRIPT_NAME, "match_tour_edges", n_tours=len(tours)):
        for tour in tours:
            legs = build_tour_legs(tour)
            if not legs:
                continue
            hut_coords_in_order = [hut_coords[h] for h in tour["hutIndices"] if h != -1]
            paths = traces_by_tour_id.get(tour["tourId"], [])
            chains, oriented = _chain_for_tour(
                paths, args.fragment_break_m, hut_coords_in_order, tour["isLoop"],
            )
            all_points = [p for chain in chains for p in chain]

            for leg_index, from_hut, to_hut in legs:
                from_coord, to_coord = hut_coords[from_hut], hut_coords[to_hut]
                gap_ctx = {"tourId": tour["tourId"], "shortCode": tour["shortCode"], "legIndex": leg_index}

                if oriented is None:
                    gaps.append({**gap_ctx, "reason": "chain_not_reassembled", "detail": {"n_chains": len(chains)}})
                    continue

                from_pos = assign_hut_position(oriented, from_coord, args.max_hut_trace_m)
                to_pos = assign_hut_position(oriented, to_coord, args.max_hut_trace_m)
                if from_pos is None or to_pos is None:
                    gaps.append({**gap_ctx, "reason": "hut_far_from_trace",
                                 "detail": {"from_dist_m": from_pos and from_pos[1],
                                            "to_dist_m": to_pos and to_pos[1]}})
                    continue

                leg_points = leg_chain_slice(oriented, from_pos[0], to_pos[0])
                trace_length_m = sum(
                    _leg_segment_m(leg_points[i], leg_points[i + 1]) for i in range(len(leg_points) - 1)
                )
                bounds = corridor_bounds(leg_points or all_points, args.corridor_buffer_m, grid)
                subgraph = gather_subgraph_for_bounds(base_graph_dir, grid, bounds)

                src_key, tgt_key = (binfmt.TYPE_HUT, from_hut), (binfmt.TYPE_HUT, to_hut)
                result = match_leg(subgraph, src_key, tgt_key, persisted_snaps,
                                    trace_length_m, args.length_divergence_ratio)
                if not result["ok"]:
                    gaps.append({**gap_ctx, "reason": result["reason"], "detail": result["detail"]})
                    continue

                record = build_tour_record(
                    from_hut, to_hut, from_coord, to_coord,
                    result["path"], result["src_snap"], result["tgt_snap"],
                )
                all_records.append(record)
                tour_meta_rows.append((tour["tourId"], leg_index))

    print(f"tour legs matched: {len(all_records)}, gaps: {len(gaps)}")

    out_dir = Path(args.out_dir) / "tour_edges"
    write_edge_records(all_records, out_dir, write_edge_ids=True)
    tour_meta_arr = np.zeros(len(tour_meta_rows), dtype=binfmt.TOUR_META_DTYPE)
    for i, row in enumerate(tour_meta_rows):
        tour_meta_arr[i] = row
    binfmt.save_array(out_dir / "tour_meta.npy", tour_meta_arr)

    gaps_path = Path(args.out_dir) / "tour-match-gaps.json"
    with open(gaps_path, "w", encoding="utf-8") as fh:
        json.dump(gaps, fh)
    print(f"written {out_dir} and {gaps_path}")
```

Add near the top of the file (module-level helper, alongside the other small geometry helpers):

```python
import math


def _leg_segment_m(a, b):
    r = 6_371_000.0
    p1, p2 = math.radians(a[1]), math.radians(b[1])
    dphi = math.radians(b[1] - a[1])
    dlambda = math.radians(b[0] - a[0])
    x = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(x))
```

Also add `import numpy as np` to the top-level imports (used by the `tour_meta_arr` construction).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd pipeline && python -m pytest tests/test_match_tour_edges.py -v`
Expected: PASS (all tests, including `build_tour_record`)

- [ ] **Step 5: Commit**

```bash
git add pipeline/phases/graph_building/match_tour_edges.py pipeline/tests/test_match_tour_edges.py
git commit -m "graph_building: add match_tour_edges.py main orchestration"
```

---

## Task 14: `dag/graph_building.py` — `task_match_tour_edges` wiring

**Files:**
- Modify: `pipeline/dag/graph_building.py`
- Modify: `pipeline/dodo.py`
- Test: `pipeline/tests/test_dodo_wiring.py`

**Interfaces:**
- Produces: `dag.graph_building.task_match_tour_edges()` — `task_dep=["compute_edge_profiles",
  "snap_hubs"]` (not a `file_dep` on `base_graph/edges.npy` — mirrors `task_snap_hubs`/
  `task_gather_route_subgraphs`'s existing reasoning for the same in-place rewrite, spec §2.6),
  `file_dep=[hub_snaps.npy, hub_snap_interior.npy, tours.json, tour_traces.json]`,
  `targets=[tour_edges/records.npy, tour_edges/geometry.npy, tour_edges/edge_ids.npy,
  tour_edges/tour_meta.npy, tour-match-gaps.json]`. No schema-version tracking param (this task
  doesn't own `RECORD_DTYPE`, spec §2.6).

- [ ] **Step 1: Write the failing tests**

Append to `pipeline/tests/test_dodo_wiring.py`:

```python
def test_match_tour_edges_depends_on_profiles_and_snaps_not_edges_npy():
    task = dodo.task_match_tour_edges()
    assert "compute_edge_profiles" in task["task_dep"]
    assert "snap_hubs" in task["task_dep"]
    assert not any(d.endswith("edges.npy") for d in task["file_dep"])


def test_match_tour_edges_targets_tour_edges_directory():
    targets = dodo.task_match_tour_edges()["targets"]
    assert any(t.endswith("tour_edges/records.npy") for t in targets)
    assert any(t.endswith("tour_edges/tour_meta.npy") for t in targets)
    assert any(t.endswith("tour-match-gaps.json") for t in targets)


def test_match_tour_edges_does_not_track_record_schema_version():
    # spec §2.6: this task doesn't own RECORD_DTYPE, so it must never move record_schema_version
    # and never force a build_hub_edges rerun.
    param_names = {p["name"] for p in dodo.task_match_tour_edges().get("params", [])}
    assert "record_schema_version" not in param_names
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd pipeline && python -m pytest tests/test_dodo_wiring.py -k match_tour_edges -v`
Expected: FAIL with `AttributeError`

- [ ] **Step 3: Add `task_match_tour_edges` to `dag/graph_building.py`**

Append to `pipeline/dag/graph_building.py`:

```python
def task_match_tour_edges():
    # Corridor-constrained routing of the AV's 26 official tours onto the base graph (spec
    # 2026-08-29-official-tours-integration-design.md). task_dep, not file_dep, on
    # compute_edge_profiles/snap_hubs: both rewrite their outputs in place without declaring them
    # as targets - same reasoning as task_snap_hubs/task_gather_route_subgraphs above. Never a
    # variants_json tracking param: a tour leg is not a member of graph.variants (spec §5).
    return pipeline_task(
        "phases/graph_building/match_tour_edges.py",
        params=[
            cli_param("fragment_break_m", "fragment-break-m", float, CONFIG["tourMatch"]["fragmentBreakM"]),
            cli_param("corridor_buffer_m", "corridor-buffer-m", float, CONFIG["tourMatch"]["corridorBufferM"]),
            cli_param("max_hut_trace_m", "max-hut-trace-m", float, CONFIG["tourMatch"]["maxHutTraceM"]),
            cli_param("length_divergence_ratio", "length-divergence-ratio", float,
                      CONFIG["tourMatch"]["lengthDivergenceRatio"]),
        ],
        task_dep=["compute_edge_profiles", "snap_hubs"],
        file_dep=[
            OSM_DIR / "hub_snaps.npy", OSM_DIR / "hub_snap_interior.npy",
            OSM_DIR / "tours.json", OSM_DIR / "tour_traces.json",
        ],
        targets=[
            OSM_DIR / "tour_edges" / "records.npy", OSM_DIR / "tour_edges" / "geometry.npy",
            OSM_DIR / "tour_edges" / "edge_ids.npy", OSM_DIR / "tour_edges" / "tour_meta.npy",
            OSM_DIR / "tour-match-gaps.json",
        ],
    )
```

- [ ] **Step 4: Register in `dodo.py`**

In `pipeline/dodo.py`, change the `dag.graph_building` import:

```python
from dag.graph_building import (  # noqa: E402,F401
    task_build_base_graph, task_build_hub_edges, task_gather_route_subgraphs,
    task_match_tour_edges, task_snap_hubs,
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd pipeline && python -m pytest tests/test_dodo_wiring.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pipeline/dag/graph_building.py pipeline/dodo.py pipeline/tests/test_dodo_wiring.py
git commit -m "graph_building: wire match_tour_edges into the doit DAG"
```

---

## Task 15: `build_profiles.py` — parametrize over `tour_edges`

**Files:**
- Modify: `pipeline/phases/elevation/build_profiles.py`
- Modify: `pipeline/dag/elevation.py`
- Modify: `pipeline/dodo.py`
- Test: `pipeline/tests/test_build_profiles.py`
- Test: `pipeline/tests/test_dodo_wiring.py`

**Interfaces:**
- Modifies: `build_profiles.py`'s hardcoded `for name in ("hut_edges", "start_edges")` (line 173)
  → `for name in ("hut_edges", "start_edges", "tour_edges")`, guarded so a missing
  `tour_edges/records.npy` (before Task 13's DAG task has ever run) doesn't crash the other two.
- Produces: `dag.elevation.task_build_profiles()` gaining `tour_edges/records.npy` in `file_dep`,
  `tour_edges/profiles.npy` in `targets`, and a `task_dep` on `match_tour_edges`.

- [ ] **Step 1: Write the failing test**

Append to `pipeline/tests/test_build_profiles.py` (check the file's existing imports/fixtures
first — reuse whatever synthetic `records.npy`/`geometry.npy`/`interior_ele.npy` fixture pattern
is already there):

```python
def test_process_edge_set_handles_a_tour_edges_shaped_directory(tmp_path):
    # tour_edges/ has the exact same records.npy/geometry.npy shape as hut_edges/ - this is a
    # regression guard that _process_edge_set (used for all three directory names) doesn't assume
    # anything hut_edges/start_edges-specific.
    edge_dir = tmp_path / "tour_edges"
    edge_dir.mkdir()
    records = np.zeros(1, dtype=binfmt.RECORD_DTYPE)
    records[0] = _minimal_record(geom_offset=0, geom_count=2)  # reuse whatever helper this file already has
    geometry = np.zeros(2, dtype=binfmt.COORD_DTYPE)
    geometry["lon"] = [10.0, 10.01]
    geometry["lat"] = [47.0, 47.0]
    binfmt.save_array(edge_dir / "records.npy", records)
    binfmt.save_array(edge_dir / "geometry.npy", geometry)

    lookup_keys, lookup_values = _minimal_lookup()  # reuse whatever helper this file already has
    _process_edge_set(edge_dir, lookup_keys, lookup_values, profile_points=5)

    profiles = binfmt.load_array(edge_dir / "profiles.npy", mmap=False)
    assert len(profiles) == 5
```

(This test intentionally references `_minimal_record`/`_minimal_lookup` placeholder names — before
writing it for real, read `pipeline/tests/test_build_profiles.py` in full and swap in whatever
fixture-building helpers that file already defines, e.g. `_records`/`build_elevation_lookup`
called against a tiny synthetic array. The point of the test is "an edges-dir named tour_edges
round-trips through `_process_edge_set` exactly like hut_edges" — adapt to the file's existing
conventions rather than introducing a parallel set of fixture helpers.)

- [ ] **Step 2: Run test to verify it fails or passes for the wrong reason**

Run: `cd pipeline && python -m pytest tests/test_build_profiles.py -k tour_edges_shaped -v`
Expected: This test actually already passes against the CURRENT `_process_edge_set` (it's a
generic function, not hardcoded to a directory name) — its purpose is a regression guard, not a
red/green step. Confirm it passes once written, then move to Step 3's real change (the `main()`
loop).

- [ ] **Step 3: Write the failing test for `main()`'s loop**

Append:

```python
def test_main_processes_tour_edges_when_present(tmp_path, monkeypatch):
    # Regression guard for the hardcoded tuple at build_profiles.py:173 - once tour_edges/ exists,
    # main() must process it too, not just hut_edges/start_edges.
    import elevation.build_profiles as bp

    processed = []
    monkeypatch.setattr(bp, "_process_edge_set", lambda edge_dir, *a, **kw: processed.append(edge_dir.name))
    monkeypatch.setattr(bp, "OSM_DIR", tmp_path)
    for name in ("hut_edges", "start_edges", "tour_edges"):
        (tmp_path / name).mkdir()
    (tmp_path / "base_graph").mkdir()
    for arr_name in ("nodes.npy", "interior.npy", "node_ele.npy", "interior_ele.npy"):
        binfmt.save_array(tmp_path / "base_graph" / arr_name, np.zeros(0, dtype=binfmt.COORD_DTYPE))

    bp.main(["--base-graph-dir", str(tmp_path / "base_graph")])

    assert set(processed) == {"hut_edges", "start_edges", "tour_edges"}
```

(Adjust the `binfmt.save_array` fixture dtypes to whatever minimal arrays actually satisfy
`build_elevation_lookup`'s field access — `nodes`/`interior` need `lon`/`lat` fields via
`COORD_DTYPE`, but `node_ele`/`interior_ele` are plain `f4` arrays via `PROFILE_DTYPE`; check
`binfmt.PROFILE_DTYPE` and use it for those two.)

- [ ] **Step 4: Run test to verify it fails**

Run: `cd pipeline && python -m pytest tests/test_build_profiles.py -k main_processes_tour_edges -v`
Expected: FAIL (`tour_edges` missing from `processed`)

- [ ] **Step 5: Update `build_profiles.py`'s hardcoded loop**

In `pipeline/phases/elevation/build_profiles.py`, change:

```python
        for name in ("hut_edges", "start_edges"):
            edge_dir = OSM_DIR / name
            print(f"processing {edge_dir} ...", flush=True)
            with timer.step(name):
                _process_edge_set(edge_dir, lookup_keys, lookup_values, args.profile_points)
            print(f"written {edge_dir}/records.npy, {edge_dir}/profiles.npy", flush=True)
```

to:

```python
        for name in ("hut_edges", "start_edges", "tour_edges"):
            edge_dir = OSM_DIR / name
            if not (edge_dir / "records.npy").exists():
                print(f"skipping {edge_dir} (not built yet)", flush=True)
                continue
            print(f"processing {edge_dir} ...", flush=True)
            with timer.step(name):
                _process_edge_set(edge_dir, lookup_keys, lookup_values, args.profile_points)
            print(f"written {edge_dir}/records.npy, {edge_dir}/profiles.npy", flush=True)
```

(The existence guard is needed because `main()`'s own test in Step 3 creates all three dirs, but a
real first-time run may have `match_tour_edges` not yet wired into `default_tasks` transiently
during rollout — matches this module's own docstring precedent of never crashing on a partial
run.)

- [ ] **Step 6: Run test to verify it passes**

Run: `cd pipeline && python -m pytest tests/test_build_profiles.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 7: Write the failing dag wiring test**

Append to `pipeline/tests/test_dodo_wiring.py`:

```python
def test_build_profiles_depends_on_match_tour_edges_and_tour_edges_records():
    task = dodo.task_build_profiles()
    assert any(d.endswith("tour_edges/records.npy") for d in task["file_dep"])
    assert any(t.endswith("tour_edges/profiles.npy") for t in task["targets"])
    assert "match_tour_edges" in task["task_dep"]
```

- [ ] **Step 8: Run test to verify it fails**

Run: `cd pipeline && python -m pytest tests/test_dodo_wiring.py -k build_profiles_depends_on_match -v`
Expected: FAIL

- [ ] **Step 9: Update `dag/elevation.py`'s `task_build_profiles`**

In `pipeline/dag/elevation.py`, change `task_build_profiles`'s `task_dep`, `file_dep`, `targets`:

```python
def task_build_profiles():
    return pipeline_task(
        "phases/elevation/build_profiles.py",
        params=[cli_param("profile_points", "profile-points", int,
                          CONFIG["dem"].get("profilePoints", 30))],
        task_dep=["build_hub_edges", "match_tour_edges"],
        file_dep=[
            OSM_DIR / "base_graph" / "interior_ele.npy",
            OSM_DIR / "hut_edges" / "records.npy", OSM_DIR / "start_edges" / "records.npy",
            OSM_DIR / "tour_edges" / "records.npy",
        ],
        targets=[
            OSM_DIR / "hut_edges" / "profiles.npy", OSM_DIR / "start_edges" / "profiles.npy",
            OSM_DIR / "tour_edges" / "profiles.npy",
        ],
    )
```

- [ ] **Step 10: Run tests to verify they pass**

Run: `cd pipeline && python -m pytest tests/test_dodo_wiring.py tests/test_build_profiles.py -v`
Expected: PASS

- [ ] **Step 11: Commit**

```bash
git add pipeline/phases/elevation/build_profiles.py pipeline/dag/elevation.py \
        pipeline/tests/test_build_profiles.py pipeline/tests/test_dodo_wiring.py
git commit -m "elevation: extend build_profiles.py to also process tour_edges"
```

---

## Task 16: `dag/postprocessing.py` — `task_build_tour_edge_tiles`

**Files:**
- Modify: `pipeline/dag/postprocessing.py`
- Modify: `pipeline/dodo.py`
- Test: `pipeline/tests/test_dodo_wiring.py`

**Interfaces:**
- Produces: `dag.postprocessing.task_build_tour_edge_tiles()` — mirrors
  `task_build_hut_edge_tiles`/`task_build_start_edge_tiles` exactly (same
  `build_edge_tiles.py --edges-dir/--layer-name/--id-table` shape), `task_dep=["build_profiles"]`,
  `file_dep=[tour_edges/records.npy]`, `targets=[tour-edges.pmtiles, tour-edge-stats.json,
  tour-edge-geometry.bin, tour-edge-geometry.json]`.

- [ ] **Step 1: Write the failing test**

Append to `pipeline/tests/test_dodo_wiring.py`:

```python
def test_build_tour_edge_tiles_mirrors_hut_edge_tiles_wiring():
    task = dodo.task_build_tour_edge_tiles()
    assert "build_profiles" in task["task_dep"]
    assert any(d.endswith("tour_edges/records.npy") for d in task["file_dep"])
    assert any(t.endswith("tour-edges.pmtiles") for t in task["targets"])
    assert any(t.endswith("tour-edge-geometry.bin") for t in task["targets"])
    assert any("--layer-name tour_edges" in a for a in task["actions"])
    # --id-table is required=True even though tour records are hut-only (spec §3)
    assert any("start_points_id_table.json" in a for a in task["actions"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pipeline && python -m pytest tests/test_dodo_wiring.py -k tour_edge_tiles -v`
Expected: FAIL with `AttributeError`

- [ ] **Step 3: Add `task_build_tour_edge_tiles` to `dag/postprocessing.py`**

Append to `pipeline/dag/postprocessing.py`, after `task_build_start_edge_tiles`:

```python
def task_build_tour_edge_tiles():
    return pipeline_task(
        "phases/postprocessing/build_edge_tiles.py",
        args=[
            f"--edges-dir {OSM_DIR / 'tour_edges'}",
            # --id-table is required=True on build_edge_tiles.py even though tour records are
            # hut-only (spec §3) - the same id table hut/start edges already resolve display ids
            # from.
            f"--id-table {OSM_DIR / 'start_points_id_table.json'}",
            "--layer-name tour_edges",
            f"--out-tiles {OSM_DIR / 'tour-edges.pmtiles'}",
            f"--out-stats {OSM_DIR / 'tour-edge-stats.json'}",
            f"--out-geometry-bin {OSM_DIR / 'tour-edge-geometry.bin'}",
            f"--out-geometry-json {OSM_DIR / 'tour-edge-geometry.json'}",
        ],
        params=_hut_edge_tiles_params(),
        task_dep=["build_profiles"],  # same in-place-rewrite reasoning as the other two edge-tile tasks
        file_dep=[OSM_DIR / "tour_edges" / "records.npy"],
        targets=[
            OSM_DIR / "tour-edges.pmtiles", OSM_DIR / "tour-edge-stats.json",
            OSM_DIR / "tour-edge-geometry.bin", OSM_DIR / "tour-edge-geometry.json",
        ],
    )
```

- [ ] **Step 4: Register in `dodo.py`**

In `pipeline/dodo.py`, change the `dag.postprocessing` import:

```python
from dag.postprocessing import (  # noqa: E402,F401
    task_build_approach_table, task_build_edge_ids, task_build_edge_payload,
    task_build_hut_edge_tiles, task_build_start_edge_tiles, task_build_tour_edge_payload,
    task_build_tour_edge_tiles, task_build_trail_tiles,
)
```

(`task_build_tour_edge_payload` is added in Task 17 — including it in this import now is fine
since Python only needs the name to resolve at import time, and Task 17 defines it in the same
module before this import line is exercised by any test run after Task 17 lands. If running this
task's tests in isolation before Task 17 exists, temporarily drop `task_build_tour_edge_payload`
from this import line and add it back in Task 17.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd pipeline && python -m pytest tests/test_dodo_wiring.py -v`
Expected: PASS (if Task 17 hasn't landed yet, the import-line note above applies — keep the
import scoped to what actually exists at each commit)

- [ ] **Step 6: Commit**

```bash
git add pipeline/dag/postprocessing.py pipeline/dodo.py pipeline/tests/test_dodo_wiring.py
git commit -m "postprocessing: add tour-edges.pmtiles tiling task"
```

---

## Task 17: `build_edge_payload.py` — `tour_meta` extension + `task_build_tour_edge_payload`

**Files:**
- Modify: `pipeline/phases/postprocessing/build_edge_payload.py`
- Modify: `pipeline/dag/postprocessing.py`
- Modify: `pipeline/dodo.py`
- Test: `pipeline/tests/test_build_edge_payload.py`
- Test: `pipeline/tests/test_dodo_wiring.py`

**Interfaces:**
- Modifies: `pack_edges(records, hut_ids, tour_meta=None) -> tuple` — when `tour_meta` (a
  `TOUR_META_DTYPE` array, row-aligned with `records`) is given, folds `tour_id`/`leg_index` in as
  two extra payload columns; `None` (the `hut_edges`/`start_edges` default) leaves the `.bin`
  byte-identical to today's.
- Produces: `dag.postprocessing.task_build_tour_edge_payload()`.

- [ ] **Step 1: Write the failing tests**

Append to `pipeline/tests/test_build_edge_payload.py`:

```python
def test_pack_edges_without_tour_meta_is_unchanged():
    payload, manifest = pack_edges(RECORDS, HUT_IDS)
    assert "tour_id" not in manifest["columns"]
    assert "leg_index" not in manifest["columns"]


def test_pack_edges_with_tour_meta_adds_two_columns():
    tour_meta = np.array([(0, 0), (0, 1), (1, 0)], dtype=binfmt.TOUR_META_DTYPE)
    payload, manifest = pack_edges(RECORDS, HUT_IDS, tour_meta=tour_meta)
    assert "tour_id" in manifest["columns"]
    assert "leg_index" in manifest["columns"]
    tour_id_col = np.frombuffer(
        payload, dtype=manifest["columns"]["tour_id"]["dtype"], count=manifest["rows"],
        offset=manifest["columns"]["tour_id"]["offset"],
    )
    assert tour_id_col.tolist() == [0, 0, 1]


def test_manifest_always_gains_the_official_variant_key():
    # spec §2.6: the manifest gains a VARIANT_OFFICIAL key from binfmt.VARIANT_NAMES regardless of
    # whether tour_meta is present - hut_edges/start_edges payloads are unaffected in their .bin,
    # but the shared variants dict is the same for every payload.
    _, manifest = pack_edges(RECORDS, HUT_IDS)
    assert "OFFICIAL" in manifest["variants"].values()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd pipeline && python -m pytest tests/test_build_edge_payload.py -k "tour_meta or official_variant" -v`
Expected: `test_manifest_always_gains_the_official_variant_key` PASSES already (Task 2 already
updated `VARIANT_NAMES`); the two `tour_meta` tests FAIL with `TypeError: pack_edges() got an
unexpected keyword argument 'tour_meta'`.

- [ ] **Step 3: Update `pack_edges`**

In `pipeline/phases/postprocessing/build_edge_payload.py`, change:

```python
def pack_edges(records: np.ndarray, hut_ids: list) -> tuple:
    columns = {name: (dtype, records[name]) for name, dtype in COLUMNS}
    payload, column_manifest = binfmt.pack_columns(columns)
    manifest = {
        "rows": len(records),
        "columns": column_manifest,
        "variants": binfmt.VARIANT_NAMES,
        "hut_ids": hut_ids,
    }
    return payload, manifest
```

to:

```python
def pack_edges(records: np.ndarray, hut_ids: list, tour_meta: np.ndarray = None) -> tuple:
    """tour_meta: optional TOUR_META_DTYPE array, row-aligned 1:1 with `records` - when given,
    folds tour_id/leg_index in as two extra payload columns (additive) so the client can
    reconstruct "which tour is this leg part of" (spec §3). None (the hut_edges/start_edges
    default, neither of which has a tour_meta.npy) leaves the .bin byte-identical to before this
    parameter existed."""
    columns = {name: (dtype, records[name]) for name, dtype in COLUMNS}
    if tour_meta is not None:
        columns["tour_id"] = ("u1", tour_meta["tour_id"])
        columns["leg_index"] = ("u1", tour_meta["leg_index"])
    payload, column_manifest = binfmt.pack_columns(columns)
    manifest = {
        "rows": len(records),
        "columns": column_manifest,
        "variants": binfmt.VARIANT_NAMES,
        "hut_ids": hut_ids,
    }
    return payload, manifest
```

- [ ] **Step 4: Wire `tour_meta` loading into `__main__`**

In `pipeline/phases/postprocessing/build_edge_payload.py`'s `__main__`, add an optional
`--tour-meta` flag and load it when present:

```python
    parser.add_argument("--tour-meta", default=None)
```

and in the `with phase(...)` block, before calling `pack_edges`:

```python
        tour_meta = None
        if args.tour_meta and Path(args.tour_meta).exists():
            tour_meta = binfmt.load_array(Path(args.tour_meta), mmap=False)

        payload, manifest = pack_edges(records, hut_ids, tour_meta=tour_meta)
```

(Replace the existing bare `payload, manifest = pack_edges(records, hut_ids)` call.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd pipeline && python -m pytest tests/test_build_edge_payload.py -v`
Expected: PASS (all tests — including the pre-existing "no duration column" /
"columns are contiguous" tests, confirming the additive change didn't disturb the
`hut_edges`/`start_edges` path)

- [ ] **Step 6: Write the failing dag wiring test**

Append to `pipeline/tests/test_dodo_wiring.py`:

```python
def test_build_tour_edge_payload_passes_tour_meta_flag():
    task = dodo.task_build_tour_edge_payload()
    assert any("--tour-meta" in a and "tour_meta.npy" in a for a in task["actions"])
    assert any(t.endswith("tour-edge-payload.bin") for t in task["targets"])
    assert "build_profiles" in task["task_dep"]
```

- [ ] **Step 7: Run test to verify it fails**

Run: `cd pipeline && python -m pytest tests/test_dodo_wiring.py -k build_tour_edge_payload -v`
Expected: FAIL

- [ ] **Step 8: Add `task_build_tour_edge_payload` to `dag/postprocessing.py`**

Append to `pipeline/dag/postprocessing.py`:

```python
def task_build_tour_edge_payload():
    return pipeline_task(
        "phases/postprocessing/build_edge_payload.py",
        args=[
            f"--edges-dir {OSM_DIR / 'tour_edges'}",
            f"--huts {OSM_DIR / 'huts.geojson'}",
            f"--tour-meta {OSM_DIR / 'tour_edges' / 'tour_meta.npy'}",
            f"--out-bin {OSM_DIR / 'tour-edge-payload.bin'}",
            f"--out-manifest {OSM_DIR / 'tour-edge-payload.json'}",
        ],
        task_dep=["build_profiles"],
        file_dep=[
            OSM_DIR / "tour_edges" / "records.npy", OSM_DIR / "tour_edges" / "tour_meta.npy",
            OSM_DIR / "huts.geojson",
        ],
        targets=[OSM_DIR / "tour-edge-payload.bin", OSM_DIR / "tour-edge-payload.json"],
    )
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd pipeline && python -m pytest tests/test_dodo_wiring.py -v`
Expected: PASS — this also finalizes the `task_build_tour_edge_payload` import name Task 16's
Step 4 anticipated; confirm `pipeline/dodo.py`'s `dag.postprocessing` import line includes it (add
it now if Task 16 deferred it).

- [ ] **Step 10: Commit**

```bash
git add pipeline/phases/postprocessing/build_edge_payload.py pipeline/dag/postprocessing.py \
        pipeline/dodo.py pipeline/tests/test_build_edge_payload.py pipeline/tests/test_dodo_wiring.py
git commit -m "postprocessing: extend build_edge_payload.py with tour_meta columns"
```

---

## Task 18: `dodo.py` — `PUBLIC_FILES` and `default_tasks`

**Files:**
- Modify: `pipeline/dodo.py`
- Test: `pipeline/tests/test_dodo_wiring.py`

**Interfaces:**
- Produces: `PUBLIC_FILES` gains `tours.json`, `tour-edges.pmtiles`, `tour-edge-stats.json`,
  `tour-edge-geometry.bin`, `tour-edge-geometry.json`, `tour-edge-payload.bin`,
  `tour-edge-payload.json`. `tour_traces.json`/`tour-fetch-gaps.json`/`tour-match-gaps.json` are
  **not** added — the first is internal-only (spec §1), the other two are diagnostic sidecars, not
  client-consumed data (same treatment `unsnapped_huts.json` gets — wait, `unsnapped_huts.json` IS
  in `PUBLIC_FILES` today; re-check spec: §3 explicitly says "Add tour-edges.pmtiles,
  tour-edge-stats.json, tour-edge-geometry.bin/.json, tour-edge-payload.bin/.json, tours.json,
  tour-fetch-gaps.json and tour-match-gaps.json to dodo.py's PUBLIC_FILES" — **follow the spec
  exactly**: all of `tour-fetch-gaps.json`/`tour-match-gaps.json` DO get added, matching
  `unsnapped_huts.json`'s existing precedent of shipping gap reports publicly. `default_tasks`
  gains `fetch_tours`, `match_tour_edges`, `build_tour_edge_tiles`, `build_tour_edge_payload` in
  the correct DAG position.

- [ ] **Step 1: Write the failing tests**

Append to `pipeline/tests/test_dodo_wiring.py`:

```python
def test_public_files_includes_every_tour_output():
    for name in [
        "tours.json", "tour-edges.pmtiles", "tour-edge-stats.json",
        "tour-edge-geometry.bin", "tour-edge-geometry.json",
        "tour-edge-payload.bin", "tour-edge-payload.json",
        "tour-fetch-gaps.json", "tour-match-gaps.json",
    ]:
        assert name in dodo.PUBLIC_FILES, name


def test_public_files_does_not_include_internal_tour_traces():
    # tour_traces.json is the ~3.5MB raw fragment file (spec §1) - internal only, never shipped.
    assert "tour_traces.json" not in dodo.PUBLIC_FILES


def test_default_tasks_includes_the_new_tour_tasks_in_dag_order():
    ordered = dodo.DOIT_CONFIG["default_tasks"]
    for name in ["fetch_tours", "match_tour_edges", "build_tour_edge_tiles", "build_tour_edge_payload"]:
        assert name in ordered, name
    assert ordered.index("fetch_tours") < ordered.index("match_tour_edges")
    assert ordered.index("snap_hubs") < ordered.index("match_tour_edges")
    assert ordered.index("compute_edge_profiles") < ordered.index("match_tour_edges")
    assert ordered.index("match_tour_edges") < ordered.index("build_profiles")
    assert ordered.index("build_profiles") < ordered.index("build_tour_edge_tiles")
    assert ordered.index("build_profiles") < ordered.index("build_tour_edge_payload")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd pipeline && python -m pytest tests/test_dodo_wiring.py -k "public_files or default_tasks_includes" -v`
Expected: FAIL

- [ ] **Step 3: Update `PUBLIC_FILES` and `default_tasks`**

In `pipeline/dodo.py`, append to `PUBLIC_FILES` (after `"partner_betriebe.geojson"`):

```python
    "tours.json",
    "tour-edges.pmtiles",
    "tour-edge-stats.json",
    "tour-edge-geometry.bin",
    "tour-edge-geometry.json",
    "tour-edge-payload.bin",
    "tour-edge-payload.json",
    "tour-fetch-gaps.json",
    "tour-match-gaps.json",
```

In `DOIT_CONFIG["default_tasks"]`, insert `"fetch_tours"` alongside `"fetch_huts"`, and
`"match_tour_edges"` after `"build_hub_edges"` but before `"build_profiles"`, and the two new
postprocessing tasks after `"build_edge_ids"`:

```python
    "default_tasks": [
        "download_extracts", "fetch_huts", "fetch_tours", "compute_hub_range", "filter_trails",
        "merge_trails", "verify_trails",
        "fetch_stations_parking", "filter_start_points",
        "build_base_graph", "fetch_dem", "build_dem_vrt", "sample_base_elevation",
        "compute_edge_profiles", "snap_hubs", "gather_route_subgraphs", "build_hub_edges",
        "match_tour_edges",
        "build_profiles",
        "build_trail_tiles", "build_hut_edge_tiles", "build_start_edge_tiles",
        "build_tour_edge_tiles",
        "build_approach_table", "build_edge_payload", "build_edge_ids", "build_tour_edge_payload",
        "copy_public_data",
    ],
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd pipeline && python -m pytest tests/test_dodo_wiring.py -v`
Expected: PASS (every wiring test in the file)

- [ ] **Step 5: Run the full pipeline test suite one more time**

Run: `cd pipeline && python -m pytest tests/ -v`
Expected: PASS — this is the last wiring-only change; confirm nothing regressed across the whole
suite before moving to the integration test task.

- [ ] **Step 6: Commit**

```bash
git add pipeline/dodo.py pipeline/tests/test_dodo_wiring.py
git commit -m "dodo: publish tour outputs and wire tour tasks into default_tasks"
```

---

## Task 19: Golden end-to-end integration test

**Files:**
- Modify: `pipeline/tests/test_match_tour_edges.py`

**Interfaces:**
- Consumes: everything built in Tasks 3-13, exercised together against a synthetic, LQR-shaped
  fixture (single-part geometry, 4 huts, 3 legs, no unsnapped huts — spec's Testing section names
  `LQR`/`WelserHöhenweg` as "the right shape", explicitly steering away from Chiemgautour's
  45-fragment geometry for a golden test).

- [ ] **Step 1: Write the failing end-to-end test**

Append to `pipeline/tests/test_match_tour_edges.py`:

```python
from lib.hub_snap import pack_hub_snaps, to_persisted  # noqa: E402
from lib.hub_snap import SnapResult  # noqa: E402


def _write_synthetic_base_graph(tmp_path, grid):
    """A single straight 4-node, 3-edge chain (~1km per edge) - LQR/WelserHöhenweg-shaped (single
    part, no unsnapped huts, spec Testing section) rather than Chiemgautour's 45-fragment geometry,
    which belongs in the §2.7 spike, not a golden test."""
    coords = [(0.0, 0.0), (0.009, 0.0), (0.018, 0.0), (0.027, 0.0)]  # ~1km apart at the equator
    nodes = np.zeros(4, dtype=binfmt.NODE_DTYPE)
    cell_ids = [grid.cell_id_for_point(*c) for c in coords]
    for i, (c, cid) in enumerate(zip(coords, cell_ids)):
        nodes[i] = (c[0], c[1], cid)
    _, cell_index = binfmt.build_csr_index(
        np.array(cell_ids, dtype=np.int32), n_groups=len(grid.all_cell_ids())
    )
    edges = np.zeros(3, dtype=binfmt.EDGE_DTYPE)
    for i in range(3):
        edges[i] = (i, i + 1, 1000.0, 0.0, 0.0, 0.0, 1000.0, 20.0, 5.0, -1, False, True, 0, 0, i)
    doubled_nodes = np.concatenate([edges["u"], edges["v"]])
    doubled_edge_ids = np.concatenate([edges["edge_id"], edges["edge_id"]])
    order, node_edge_index = binfmt.build_csr_index(doubled_nodes, n_groups=4)
    node_edge_ids = doubled_edge_ids[order]
    interior = np.zeros(0, dtype=binfmt.COORD_DTYPE)
    node_ele = np.array([1000.0, 1020.0, 1040.0, 1060.0], dtype=np.float32)

    base_graph_dir = tmp_path / "base_graph"
    binfmt.save_array(base_graph_dir / "nodes.npy", nodes)
    binfmt.save_array(base_graph_dir / "cell_index.npy", cell_index)
    binfmt.save_array(base_graph_dir / "node_edge_index.npy", node_edge_index)
    binfmt.save_array(base_graph_dir / "node_edge_ids.npy", node_edge_ids)
    binfmt.save_array(base_graph_dir / "edges.npy", edges)
    binfmt.save_array(base_graph_dir / "interior.npy", interior)
    binfmt.save_array(base_graph_dir / "node_ele.npy", node_ele)
    binfmt.save_array(base_graph_dir / "interior_ele.npy", np.zeros(0, dtype=np.float32))
    binfmt.save_manifest(
        base_graph_dir / "manifest.json", {"bbox": BBOX, "tile_size_km": grid.tile_size_km},
    )
    return base_graph_dir, coords


def test_golden_single_part_tour_matches_all_legs_end_to_end(tmp_path, monkeypatch):
    grid = Grid(BBOX, tile_size_km=60.0)
    base_graph_dir, node_coords = _write_synthetic_base_graph(tmp_path, grid)

    # 4 huts sitting exactly on the 4 graph nodes (LQR-shaped: single part, no unsnapped huts).
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

    persisted_snaps = {}
    for i, node_idx in enumerate((0, 1, 2, 3)):
        result = SnapResult(node_index=node_idx, gap_m=0.0, gap_dz_m=0.0)
        from lib.subgraph import LocalSubgraph

        stand_in_subgraph = LocalSubgraph(
            global_node_ids=np.arange(4), local_nodes=np.zeros(0, dtype=binfmt.NODE_DTYPE),
            local_edges=np.zeros(0, dtype=binfmt.EDGE_DTYPE),
            interior=np.zeros(0, dtype=binfmt.COORD_DTYPE),
            local_node_ele=np.zeros(0, dtype=np.float32), interior_ele=np.zeros(0, dtype=np.float32),
        )
        persisted_snaps[(binfmt.TYPE_HUT, i)] = to_persisted(stand_in_subgraph, result)
    pack_hub_snaps(persisted_snaps, tmp_path)

    tours = [{
        "tourId": 0, "globalId": "{TOUR-LQR}", "name": "LQR-shaped test tour",
        "shortCode": "LQRTEST", "isLoop": False, "homepage": None,
        "hutIndices": [0, 1, 2, 3],
    }]
    (tmp_path / "tours.json").write_text(json.dumps(tours), encoding="utf-8")
    traces = [{"tourId": 0, "paths": [[list(c) for c in node_coords]]}]  # single part
    (tmp_path / "tour_traces.json").write_text(json.dumps(traces), encoding="utf-8")

    import graph_building.match_tour_edges as mte

    monkeypatch.setattr(mte, "OSM_DIR", tmp_path)
    monkeypatch.setattr(
        mte, "load_config",
        lambda: {"tourMatch": {"fragmentBreakM": 150.0, "corridorBufferM": 150.0,
                                "maxHutTraceM": 250.0, "lengthDivergenceRatio": 2.0}},
    )
    mte.main(["--base-graph-dir", str(base_graph_dir), "--out-dir", str(tmp_path)])  # see Step 3

    records = binfmt.load_array(tmp_path / "tour_edges" / "records.npy", mmap=False)
    tour_meta = binfmt.load_array(tmp_path / "tour_edges" / "tour_meta.npy", mmap=False)
    gaps = json.loads((tmp_path / "tour-match-gaps.json").read_text(encoding="utf-8"))

    assert len(records) == 3  # 3 legs, no gaps
    assert gaps == []
    assert list(tour_meta["leg_index"]) == [0, 1, 2]
    assert all(r == binfmt.VARIANT_OFFICIAL for r in records["variant"])
    # touches both huts' own coordinates at the geometry endpoints
    assert (records["geom_offset"] >= 0).all()
    total_distance = records["distance_m"].sum()
    assert 2900.0 < total_distance < 3100.0  # ~3 x 1000m, order-of-magnitude sane
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pipeline && python -m pytest tests/test_match_tour_edges.py -k golden -v`
Expected: FAIL — `mte.main` doesn't exist yet (Task 13's `__main__` block is a bare script, not a
callable `main(argv)` function like `build_profiles.py`'s).

- [ ] **Step 3: Refactor `match_tour_edges.py`'s `__main__` into a callable `main(argv=None)`**

In `pipeline/phases/graph_building/match_tour_edges.py`, wrap everything currently under
`if __name__ == "__main__":` into a `def main(argv=None):` function (matching
`build_profiles.py`'s own `main(argv=None)` convention exactly — see
`pipeline/phases/elevation/build_profiles.py:156-184`), replacing `args = parser.parse_args()`
with `args = parser.parse_args(argv)`, and end the file with:

```python
if __name__ == "__main__":
    main()
```

This is a pure refactor (move code inside a function, no logic change) — re-run every test from
Tasks 11-13 to confirm nothing else broke:

Run: `cd pipeline && python -m pytest tests/test_match_tour_edges.py -v`
Expected: every pre-existing test in the file still PASSES (they exercise `build_tour_legs`/
`corridor_bounds`/`match_leg`/`build_tour_record` directly, not `__main__`, so this refactor
shouldn't touch them at all — if any fail, the refactor moved something it shouldn't have).

- [ ] **Step 4: Run the golden test to verify it passes**

Run: `cd pipeline && python -m pytest tests/test_match_tour_edges.py -k golden -v`
Expected: PASS

- [ ] **Step 5: Write the Rundtour closing-leg + gap-handling integration tests**

Append to `pipeline/tests/test_match_tour_edges.py` (reusing `_write_synthetic_base_graph` from
Step 1):

```python
def test_rundtour_closing_leg_is_matched(tmp_path, monkeypatch):
    # A 4-hut Rundtour on the same synthetic straight chain: closing leg (hut 3 -> hut 0) has no
    # real trail data in this fixture (a straight line, not a loop), so it must land as a gap, NOT
    # a faked/straight-line record - proving isLoop=True actually appends the extra leg and the
    # gap machinery still applies to it like any other leg.
    grid = Grid(BBOX, tile_size_km=60.0)
    base_graph_dir, node_coords = _write_synthetic_base_graph(tmp_path, grid)
    huts_geojson = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"id": f"{{GUID-{i}}}"},
             "geometry": {"type": "Point", "coordinates": list(c)}}
            for i, c in enumerate(node_coords)
        ],
    }
    (tmp_path / "huts.geojson").write_text(json.dumps(huts_geojson), encoding="utf-8")

    persisted_snaps = {}
    from lib.subgraph import LocalSubgraph
    stand_in_subgraph = LocalSubgraph(
        global_node_ids=np.arange(4), local_nodes=np.zeros(0, dtype=binfmt.NODE_DTYPE),
        local_edges=np.zeros(0, dtype=binfmt.EDGE_DTYPE), interior=np.zeros(0, dtype=binfmt.COORD_DTYPE),
        local_node_ele=np.zeros(0, dtype=np.float32), interior_ele=np.zeros(0, dtype=np.float32),
    )
    for i, node_idx in enumerate((0, 1, 2, 3)):
        result = SnapResult(node_index=node_idx, gap_m=0.0, gap_dz_m=0.0)
        persisted_snaps[(binfmt.TYPE_HUT, i)] = to_persisted(stand_in_subgraph, result)
    pack_hub_snaps(persisted_snaps, tmp_path)

    tours = [{
        "tourId": 0, "globalId": "{TOUR-LOOP}", "name": "Loop test tour", "shortCode": "LOOPTEST",
        "isLoop": True, "homepage": None, "hutIndices": [0, 1, 2, 3],
    }]
    (tmp_path / "tours.json").write_text(json.dumps(tours), encoding="utf-8")
    traces = [{"tourId": 0, "paths": [[list(c) for c in node_coords]]}]
    (tmp_path / "tour_traces.json").write_text(json.dumps(traces), encoding="utf-8")

    import graph_building.match_tour_edges as mte
    monkeypatch.setattr(mte, "OSM_DIR", tmp_path)
    monkeypatch.setattr(
        mte, "load_config",
        lambda: {"tourMatch": {"fragmentBreakM": 150.0, "corridorBufferM": 150.0,
                                "maxHutTraceM": 250.0, "lengthDivergenceRatio": 2.0}},
    )
    mte.main(["--base-graph-dir", str(base_graph_dir), "--out-dir", str(tmp_path)])

    records = binfmt.load_array(tmp_path / "tour_edges" / "records.npy", mmap=False)
    tour_meta = binfmt.load_array(tmp_path / "tour_edges" / "tour_meta.npy", mmap=False)
    gaps = json.loads((tmp_path / "tour-match-gaps.json").read_text(encoding="utf-8"))

    # 4 legs total (loop yields N legs, not N-1) - the closing leg 3->0 finds no path (straight
    # chain fixture, not an actual loop) and must be gapped, never faked.
    assert len(records) == 3
    assert list(tour_meta["leg_index"]) == [0, 1, 2]
    assert any(g["legIndex"] == 3 for g in gaps)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd pipeline && python -m pytest tests/test_match_tour_edges.py -k rundtour_closing_leg -v`
Expected: PASS — confirms the closing leg (`leg_index == 3`) is attempted and correctly gapped
(`no_corridor_path`, since the synthetic fixture is a straight chain with no edge from node 3 back
to node 0), never silently dropped or faked.

- [ ] **Step 7: Run the full pipeline test suite**

Run: `cd pipeline && python -m pytest tests/ -v`
Expected: PASS (every test in the repo)

- [ ] **Step 8: Commit**

```bash
git add pipeline/tests/test_match_tour_edges.py pipeline/phases/graph_building/match_tour_edges.py
git commit -m "graph_building: add golden end-to-end and Rundtour closing-leg tests"
```

---

## Task 20 (gated): §2.7 real-data spike — requires explicit user confirmation

**This task must not be executed automatically.** Per root `CLAUDE.md` and this plan's Global
Constraints, running `doit fetch_tours` (a network fetch against the live AV ArcGIS endpoint) or
`doit match_tour_edges` (which needs a real `data/osm/base_graph/` + `hub_snaps.npy`, themselves
multi-hour builds) requires stopping and asking the user first, every time — even though
`fetch_tours` itself is cheap, it is still a `doit` task, and the CLAUDE.md rule draws no
exception for "looks cheap."

**What this task is, once approved:** spec §2.7's validation step — run fragment reassembly
(Task 3) and corridor routing (Tasks 6/12) against the two worst real inputs in the dataset
(Chiemgautour: 45 fragments/771 points; SVR7T: 51 fragments/682 points, 102 m/point), and compare
the routed legs against the AV's own published geometry. If corridor routing holds on those two,
`leuvenmapmatching` (spec §2.4) is not needed and stays out of scope. If it doesn't, that's a
signal to come back and scope a follow-up plan for §2.4 — **do not attempt to implement §2.4
speculatively as part of this task**.

**Steps, once the user has explicitly confirmed running pipeline tasks against real data:**

- [ ] **Step 1:** Ask the user to confirm running `doit fetch_tours` (requires `huts.geojson` to
  already exist locally — check `data/osm/huts.geojson` first; if missing, that's a much bigger
  ask and should be surfaced explicitly, not assumed).
- [ ] **Step 2:** Ask the user to confirm running `doit match_tour_edges` (requires a real,
  already-built `data/osm/base_graph/`, `hub_snaps.npy`, and `compute_edge_profiles` output — if
  any are stale or missing, surface the real cost (per root `CLAUDE.md`, `build_base_graph` alone
  measured ~4 hours) before running anything, and ask again specifically about that cost).
- [ ] **Step 3:** After both tasks complete, inspect `data/osm/tour-match-gaps.json` for
  Chiemgautour (`CGT`) and SVR7T entries, and compare `data/osm/tour_edges/records.npy`'s per-leg
  `distance_m` against the two tours' published stats (spec §0.2's table: CGT 40km/3 legs, SVR7T
  70km/5 legs) — order-of-magnitude, not exact equality.
- [ ] **Step 4:** Report the comparison to the user with a recommendation: ship as-is, retune
  `pipeline.config.json`'s `tourMatch` thresholds (Task 1), or scope a §2.4 follow-up plan. Do not
  make that call unilaterally — this is exactly the kind of "decide on measured match quality, not
  on preference" judgment spec §2.7 reserves for a human looking at the numbers.

---

## Self-Review

**Spec coverage:**
- §0 (source data numbers, `#DUMMY`/empty-hut-list/GUID-resolution facts) → Task 9's tests encode
  every one of these facts as an assertion.
- §0.3 (huts not on trail, unsnapped tour huts) → `maxHutTraceM`/`hut_far_from_trace` (Task 5, 12,
  13), `hut_unsnapped` (Task 12).
- §1 (`fetch_tours.py`, two output files, GUID resolution, doit wiring) → Tasks 9-10.
- §2.1 (legs incl. Rundtour closing leg) → Task 11, tested end-to-end in Task 19.
- §2.2 (fragment reassembly + orientation) → Tasks 3-5.
- §2.3 (corridor-constrained routing, per-leg corridor cut) → Tasks 6, 12, 13.
- §2.4 (leuvenmapmatching fallback) → explicitly out of scope, gated behind Task 20's spike
  outcome — see "Out of scope" below.
- §2.5 (six gap reasons, never faked) → all six are reachable/tested: `hut_unsnapped`,
  `outside_extract`, `no_corridor_path`, `length_divergent` (Task 12); `hut_far_from_trace`,
  `chain_not_reassembled` (Task 13, exercised via Task 19's Rundtour test and the gap-handling
  assertions).
- §2.6 (endpoint treatment, record packing refactor, `tour_meta.npy`) → Tasks 2, 7, 8, 13.
- §2.7 (spike) → Task 20, explicitly gated.
- §3 (postprocessing — `build_profiles.py`, `build_edge_tiles.py`, `build_edge_payload.py`,
  `PUBLIC_FILES`/`default_tasks`) → Tasks 15-18.
- §4 (access edges — no new work) → correctly no task exists for this.
- §5 (filtering scoped to `tour_edges/` only, `VARIANT_OFFICIAL`) → Task 2, and no task touches
  `graph.variants` or `lib/variants.py`.
- Testing section → every named test (`#DUMMY` filter, empty-hut-list, GUID gap-and-split,
  fragment reassembly incl. reversed fragment, leg boundaries incl. 250m threshold, corridor
  gather, golden LQR-shaped end-to-end, Rundtour closing leg, gap handling incl. RFD4T-style
  all-gapped and TT4T-style closing-leg-survives, endpoint treatment, `build_edge_payload.py`
  round-trip) has a corresponding test in Tasks 3-19.

**Placeholder scan:** no `TBD`/"add error handling"/"similar to Task N" patterns — every step has
either literal runnable code or an explicit instruction to adapt to an existing file's already-read
conventions (Task 15's `build_profiles.py` test, which correctly defers to that file's existing
fixture helpers rather than inventing parallel ones).

**Type consistency:** `match_leg` returns a plain `dict` (not a dataclass) consistently across
Tasks 12-13; `build_tour_record`'s keys match exactly what `lib.edge_output.write_edge_records`
(Task 7) destructures; `PathResult`'s field names (`coords`, `distance_m`, `road_m`, `ungraded_m`,
`inferred_m`, `ascent_m`, `descent_m`, `max_ele_m`, `sac_rank`, `via_ferrata`, `base_edge_ids`) are
used identically in Task 13's `build_tour_record` and Task 12's test fixtures, matching
`lib/cell_igraph.py`'s real `PathResult` namedtuple.

## Out of scope (carried from the spec, not to be implemented under this plan)

- `leuvenmapmatching`/spec §2.4 — gated behind Task 20's real-data spike outcome, not implemented
  speculatively.
- Client-side rendering/UI for tours (`huts/`) — spec explicitly defers this to separate follow-up
  work; this plan is pipeline-only.
- `Wiener Höhenweg`/`MontafonerSilvrettarunde` leg-splitting (empty hut lists) — tracked as a known
  gap in `tours.json` (both ship with `hutIndices: []`), no leg-emission work attempted.
- Extending region coverage past `["austria", "bayern"]` to reach Switzerland/South Tyrol legs.
- Fixing the 9 legs lost to `snap_hubs.py`'s own `vertical_offset`/`gap_too_far` rejections — root
  cause belongs to the snapping layer (`pipeline/phases/graph_building/snap_hubs.py`), not this
  feature.
- Mixing official tours into the "avoid overlapping tracks" search — `tour_edges/edge_ids.npy`
  populates the same overlap-check columns as `hut_edges/` (Task 13 passes `write_edge_ids=True`),
  but no search-side feature consumes them yet, matching the spec's explicit deferral.
