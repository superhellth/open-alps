# Tour Suggestion Backend (pipeline) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the `pipeline/` precompute so it emits time-costed, elevation-aware, difficulty-constrained hut-to-hut edge variants plus a shippable approach/exit table, as static files a client-side tour search can load once.

**Architecture:** Three sequential rewrites of the existing doit DAG — (1) the base graph learns a *time* cost and a *passability tier* per edge instead of a road-penalised distance, (2) elevation moves from a post-hoc per-record pass to a per-base-edge pass that feeds routing, (3) `build_hub_edges` routes each constraint row over a filtered subgraph and writes variant-keyed records. A read-only sizing probe runs between (2) and (3) and sets the constants and the variant count, so the multi-hour build runs once with settled parameters.

**Tech Stack:** Python 3, numpy structured arrays (`lib/binfmt.py`), pyosmium (OSM streaming), python-igraph (Dijkstra), rasterio/GDAL (DEM), doit (task DAG), pytest.

**Spec:** `docs/superpowers/specs/2026-08-22-tour-suggestion-backend.md` — read it alongside this plan. Section refs below (§A1, §C4, …) point into it.

## Global Constraints

- **Never run a `pipeline/` task (`doit`, `doit <task>`) without explicit user confirmation.** `build_hub_edges` alone is hours. Every step in this plan that runs one is marked **[ASK FIRST]**.
- `analysis/` scripts are read-only, never imported by `phases/`, never modify `phases/` or `dodo.py`, write only into `data/` (gitignored), print progress with `flush=True`, and state their runtime in the module docstring (`pipeline/analysis/README.md`).
- Every `phases/`/`analysis/` script prints one progress line per unit of work, `flush=True` (`pipeline/CLAUDE.md` "Progress logging").
- Expensive blocks are wrapped in `lib/timing.py`'s `phase(SCRIPT_NAME, "name")`; repeating sub-steps use `StepTimer`.
- Config lives in `pipeline/pipeline.config.json`; no hyperparameter is hardcoded in a phase script.
- `maxApproachTime` must never be introduced (§E1). No pipeline code may reference legs, days, or trip budgets (§ scope boundary).
- Routing penalties live in the routing weight only and must never reach a duration shown to a user (§A3).
- Reported duration (DIN 33466) is **not** stored (§D3). `time_min` is not a field.
- Test command: `python -m pytest pipeline/tests -q` from the repo root, inside the `alpen-osm` conda env.
- Commit per task, conventional-commit subject.

## Data already in hand (the decisions below lean on it)

| number | source | used by |
|---|---|---|
| hut edges: aggregate road share 9.7%, median 4.3%, p90 29.0%, 29.4% road-free; start edges: aggregate 19.1%, only 1.4% road-free — **measured under the distance cost with `roadPenaltyFactor: 1.3` still active, so a floor** | `data/analysis/road_share.json` | Task 1, Task 24 (`ROAD_*` decision) |
| 3 variants × 6,067 edges × 13 columns = 693 KB raw, **43.4 KB gzipped**; byte-shuffling made it *worse* (46.4 KB) | `data/analysis/payload_sizing.json` | Task 1, Task 21 — payload is not the constraint; build time is |
| 21,058 of 30,286 start points carry **no `access` tag**; 3,293 `private`, 154 `no`; `motor_vehicle` is not even fetched | `data/analysis/payload_sizing.json` | Task 19 (widen `keep_fields`), Task 20 (`access_unknown`) |
| snap outcomes over 956 hubs: 713 node, 38 mid-chain, **205 unsnapped** | `data/analysis/snap_stats.json` | Task 18 (`unsnapped_huts.json` is not a rare path) |
| base edge length median 49.5 m (p25 19.7, p75 133.7, n=8.34M) | spec §A1 | Task 6 (pointwise speed model) |
| snap vertical offset: <5 m 656 huts, 5-10 m 51, 10-20 m 12, >20 m 5; horizontal 91.8% within 25 m | spec §E3 | Task 18 (`maxSnapAscentM ≈ 25`, `maxSnapM` untouched) |
| `sac_rank <= 3` on a 12 km budget leaves 23% of huts unconnected; `<= 2` leaves 39% | spec §C2 | Phase 4 (rows substitute rather than delete) |
| **missing:** ungraded blocker rate | Task 1 produces it | Task 1 gates 3-row vs 4-row grid |

---

# Phase 0 — Evidence gate

Nothing is built until the one unmeasured decision has a number under it. Two of the three analysis
scripts have already run; the third has not.

### Task 1: Run the grading-coverage measurement and write the findings doc

**Files:**
- Run: `pipeline/analysis/grading_coverage.py` (already written, currently untracked)
- Create: `docs/superpowers/specs/2026-08-22-tour-suggestion-findings.md`
- Modify: `pipeline/analysis/README.md` (verify its three script sections match what is on disk)

**Interfaces:**
- Produces: the findings doc, which Tasks 2, 11 and 24 read for (a) the tier table as measured,
  (b) the 3-row vs 4-row grid decision, (c) the `ROAD_*` go/no-go input.

- [ ] **Step 1: Confirm the two already-collected measurements are present**

```bash
python -c "import json;d=json.load(open('data/analysis/road_share.json'));print(d['hut_edges']['aggregate_road_share'], d['start_edges']['aggregate_road_share'])"
python -c "import json;d=json.load(open('data/analysis/payload_sizing.json'));print(d['hut_edge_payload_3_variants']['gzip_kb'])"
```

Expected: `0.097 0.1905` and `43.4`. If a file is missing, re-run
`python pipeline/analysis/road_share.py` / `python pipeline/analysis/payload_sizing.py` — seconds
each, read-only, not doit tasks, so no confirmation needed.

- [ ] **Step 2: Run the grading coverage script** **[ASK FIRST — ~20-25 min, peak RSS ~3-4 GB]**

```bash
python pipeline/analysis/grading_coverage.py --start-edges
```

Expected: `data/analysis/grading_coverage.json` written. Read the **segment match rate first** — the
script attributes hut-edge polylines back to OSM segments by quantized endpoint-pair key, and a low
match rate invalidates every per-edge number under it.

- [ ] **Step 3: Write the findings doc**

Create `docs/superpowers/specs/2026-08-22-tour-suggestion-findings.md`, one section per open
question, each stating the number, the file it came from, and the decision it settles:

```markdown
# Tour suggestion backend — measured findings

Source of truth for the numbers this work's decisions rest on. Every figure names the script
that produced it and the caveat attached to it.

## 1. Road share (open question 1) — `data/analysis/road_share.json`
...aggregate share, percentiles, the by-sac_rank table, the "floor not prediction" caveat...
**Decision:** ROAD_* deferred to the post-rebuild re-run (Task 24).

## 2. Payload (open question 3) — `data/analysis/payload_sizing.json`
...raw vs gzip per artifact, the zero-column floor caveat, shuffle made it worse...
**Decision:** payload is not a constraint; build time is. No quantisation in scope.

## 3. Ungraded blocker rate (open question 2) — `data/analysis/grading_coverage.json`
...segment match rate FIRST, then network tier mass by length, the per-hut-edge tier split,
and how many huts lose their last connection under `ungraded_m == 0` on top of a sac_rank cap...
**Decision rule (record the outcome, not the rule, once run):**
  - < 5% of huts lose their last connection -> three-row grid as specced (§C3).
  - >= 5% -> build the fourth row (`graded <= T3, ungraded permitted`, §H fallback), with the
    UI naming the difference. The strict row's definition is NOT relaxed either way.
```

- [ ] **Step 4: Record the grid decision as a literal list**

Write the resulting row set out (e.g. `FAST_ANY, FAST_T2, FAST_T3`, or `+ FAST_T3_UNGRADED`).
Task 11 copies this list into `pipeline.config.json`; it must not be re-derived from prose.

- [ ] **Step 5: Commit**

```bash
git add pipeline/analysis/grading_coverage.py pipeline/analysis/payload_sizing.py pipeline/analysis/road_share.py pipeline/analysis/README.md docs/superpowers/specs/2026-08-22-tour-suggestion-findings.md
git commit -m "analysis: grading/road-share/payload measurements + findings doc"
```

---

# Phase 1 — Cost model and passability in the base graph

Rewrites what a base-graph edge *is*. Everything downstream is invalidated by this phase; nothing is
rebuilt until Phase 2 lands, because the elevation pass fills the new fields.

### Task 2: Passability classifier as a production module

**Files:**
- Create: `pipeline/lib/grading.py`
- Test: `pipeline/tests/test_grading.py`
- Reference (do not copy blindly): `pipeline/analysis/grading_coverage.py`'s classifier — this task
  is its promotion to production, exactly as that script's docstring anticipates.

**Interfaces:**
- Produces: `classify_way(tags: dict) -> WayGrade` where
  `WayGrade = namedtuple("WayGrade", "sac_rank tier")` and
  `tier ∈ {TIER_EXPLICIT, TIER_INFERRED, TIER_UNGRADED}`; `sac_rank == -1` only when ungraded.
  Also `excluded_from_constrained(tags) -> bool`. Consumed by Task 4 and (indirectly) Task 13.

- [ ] **Step 1: Write the failing tests**

```python
# pipeline/tests/test_grading.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import grading  # noqa: E402


def test_explicit_sac_scale_wins():
    g = grading.classify_way({"highway": "path", "sac_scale": "alpine_hiking"})
    assert g.sac_rank == 4
    assert g.tier == grading.TIER_EXPLICIT


def test_track_is_physically_implied_t1_even_at_grade5():
    g = grading.classify_way({"highway": "track", "tracktype": "grade5"})
    assert g.sac_rank == 1
    assert g.tier == grading.TIER_INFERRED


def test_steps_imply_t2():
    assert grading.classify_way({"highway": "steps"}).sac_rank == 2


def test_paved_path_implies_t1():
    g = grading.classify_way({"highway": "path", "surface": "asphalt"})
    assert g.sac_rank == 1
    assert g.tier == grading.TIER_INFERRED


def test_bare_path_is_ungraded():
    g = grading.classify_way({"highway": "path"})
    assert g.sac_rank == -1
    assert g.tier == grading.TIER_UNGRADED


def test_good_trail_visibility_is_not_an_upgrade():
    # rejected as an upgrade signal: subjective, on only 8.8% of untagged paths (spec C4)
    g = grading.classify_way({"highway": "path", "trail_visibility": "excellent"})
    assert g.tier == grading.TIER_UNGRADED


def test_downgrade_tags_hard_exclude_from_constrained_rows():
    assert grading.excluded_from_constrained({"highway": "path", "trail_visibility": "horrible"})
    assert grading.excluded_from_constrained({"highway": "path", "informal": "yes"})
    assert grading.excluded_from_constrained({"highway": "path", "ladder": "yes"})
    assert grading.excluded_from_constrained({"highway": "track", "access": "private"})
    assert not grading.excluded_from_constrained({"highway": "path", "sac_scale": "hiking"})


def test_explicit_grade_still_excluded_by_a_downgrade_tag():
    # a downgrade is always honoured, even over an explicit sac_scale (spec C4, "asymmetric")
    assert grading.excluded_from_constrained(
        {"highway": "path", "sac_scale": "hiking", "trail_visibility": "no"}
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest pipeline/tests/test_grading.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'lib.grading'`

- [ ] **Step 3: Write the module**

```python
# pipeline/lib/grading.py
"""Per-way passability grading (spec 2026-08-22-tour-suggestion-backend.md C4).

sac_scale is absent on most of the network, and sac_rank is a MAX over a path with untagged
encoded as -1, which max ignores - so an edge can contain kilometres of ungraded terrain and
still report sac_rank 2. Under a user-stated difficulty ceiling that is a safety defect, not an
accuracy one. This module gives every way a TIER as well as a rank, so "ungraded" becomes a
positive fact that can be summed along a path (ungraded_m) instead of a silence.

Inference is asymmetric on purpose: UPGRADES require physics (a tag that makes alpine terrain
impossible by construction); DOWNGRADES are always honoured. Measured 2026-08-21 over
data/osm/austria-trails.osm.pbf (2.33M ways / 23.1M segments): the implication table below covers
91.3% of untagged segment mass, leaving genuinely unknown terrain at 7.9% of the network - not the
95% a naive sac_scale-coverage figure suggests.
"""

from collections import namedtuple

WayGrade = namedtuple("WayGrade", "sac_rank tier")

TIER_EXPLICIT = "explicit"
TIER_INFERRED = "inferred"
TIER_UNGRADED = "ungraded"

SAC_SCALE_RANK = {
    "strolling": 0, "hiking": 1, "mountain_hiking": 2, "demanding_mountain_hiking": 3,
    "alpine_hiking": 4, "demanding_alpine_hiking": 5, "difficult_alpine_hiking": 6,
}

# highway value -> implied rank. Car-drivable or built surfaces only; each entry is a
# construction fact, not a guess about terrain.
IMPLIED_BY_HIGHWAY = {
    "residential": 1, "service": 1, "unclassified": 1, "tertiary": 1,
    "track": 1,      # including tracktype=grade5 - still a vehicle track
    "footway": 1,
    "steps": 2,
}
PAVED_SURFACES = {"asphalt", "paving_stones", "concrete"}

_BAD_VISIBILITY = {"bad", "horrible", "no"}
_BLOCKED_ACCESS = {"private", "no"}


def classify_way(tags: dict) -> WayGrade:
    explicit = SAC_SCALE_RANK.get(tags.get("sac_scale", ""))
    if explicit is not None:
        return WayGrade(explicit, TIER_EXPLICIT)
    highway = tags.get("highway", "")
    implied = IMPLIED_BY_HIGHWAY.get(highway)
    if implied is not None:
        return WayGrade(implied, TIER_INFERRED)
    if highway == "path" and tags.get("surface", "") in PAVED_SURFACES:
        return WayGrade(1, TIER_INFERRED)
    return WayGrade(-1, TIER_UNGRADED)


def excluded_from_constrained(tags: dict) -> bool:
    """Hard-exclude from every constrained row, regardless of grade. A downgrade signal always
    wins: the constrained rows exist to support the claim "every metre of this route is graded T3
    or easier", and that claim cannot survive a ladder or an unmarked line."""
    if tags.get("trail_visibility", "") in _BAD_VISIBILITY:
        return True
    if tags.get("informal", "") == "yes" or tags.get("ladder", "") == "yes":
        return True
    if tags.get("access", "") in _BLOCKED_ACCESS:
        return True
    return False
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest pipeline/tests/test_grading.py -q`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add pipeline/lib/grading.py pipeline/tests/test_grading.py
git commit -m "feat(pipeline): per-way passability grading module"
```

### Task 3: `EDGE_DTYPE` gains time/elevation/grading columns, loses `weight`

**Files:**
- Modify: `pipeline/lib/binfmt.py:16-21` (`EDGE_DTYPE`) and the `VARIANT_*` constants
- Test: `pipeline/tests/test_binfmt.py`

**Interfaces:**
- Produces: `EDGE_DTYPE` with
  `u, v, dist, road_m, ungraded_m, inferred_m, time_s, ascent_m, descent_m, sac_rank, via_ferrata,
  constrained_ok, interior_offset, interior_count, edge_id` and no `weight`;
  `VARIANT_FAST_ANY = 0`, `VARIANT_FAST_T2 = 1`, `VARIANT_FAST_T3 = 2`, `VARIANT_NAMES`
  (`VARIANT_SHORTEST` removed). Consumed by Tasks 4, 5, 8, 13, 14.

**Two deliberate additions beyond spec §B1** (which lists only `+time_s, +ascent_m, +descent_m,
−weight`): §C4 requires `ungraded_m`/`inferred_m` to be summed along the routed path the way
`road_m` already is, and the spec's own blockers section says so — that sum is only possible if the
base edge carries the metres. `constrained_ok` is the per-edge precomputation of
`excluded_from_constrained OR via_ferrata OR tier == ungraded`, so Task 13's filtered graph build is
one boolean mask rather than a re-derivation per variant per cell.

- [ ] **Step 1: Write the failing test**

```python
# append to pipeline/tests/test_binfmt.py
def test_edge_dtype_has_time_and_grading_columns_and_no_weight():
    names = binfmt.EDGE_DTYPE.names
    for field in ("time_s", "ascent_m", "descent_m", "ungraded_m", "inferred_m", "constrained_ok"):
        assert field in names, field
    # spec A3: dropping the field (not repurposing it) makes a stale cache fail loudly with a
    # KeyError instead of feeding penalised metres to a router reading seconds
    assert "weight" not in names


def test_variant_constants_replace_variant_shortest():
    assert binfmt.VARIANT_FAST_ANY == 0
    assert binfmt.VARIANT_FAST_T2 == 1
    assert binfmt.VARIANT_FAST_T3 == 2
    assert not hasattr(binfmt, "VARIANT_SHORTEST")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest pipeline/tests/test_binfmt.py -q`
Expected: FAIL — `AssertionError: time_s`

- [ ] **Step 3: Edit `binfmt.py`**

```python
EDGE_DTYPE = np.dtype([
    ("u", "i8"), ("v", "i8"), ("dist", "f8"), ("road_m", "f8"),
    ("ungraded_m", "f8"), ("inferred_m", "f8"),
    ("time_s", "f8"), ("ascent_m", "f4"), ("descent_m", "f4"),
    ("sac_rank", "i1"), ("via_ferrata", "bool"), ("constrained_ok", "bool"),
    ("interior_offset", "i8"), ("interior_count", "i4"), ("edge_id", "i8"),
])

TYPE_HUT = 0
TYPE_STATION = 1
TYPE_PARKING = 2

# Variant grid rows (spec C2/C3). Phase 1 builds the "fastest" objective column only; a ROAD_*
# column appends here if the post-rebuild road-share measurement justifies it.
VARIANT_FAST_ANY = 0
VARIANT_FAST_T2 = 1
VARIANT_FAST_T3 = 2
VARIANT_NAMES = {
    VARIANT_FAST_ANY: "FAST_ANY", VARIANT_FAST_T2: "FAST_T2", VARIANT_FAST_T3: "FAST_T3",
}

UNSET = -1.0  # sentinel for time_s/ascent_m/descent_m before add_base_elevation.py runs
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest pipeline/tests/test_binfmt.py -q`
Expected: PASS. Other test modules now fail (they build `EDGE_DTYPE` tuples positionally) — that is
Task 4's job. Do not fix them here.

- [ ] **Step 5: Commit**

```bash
git add pipeline/lib/binfmt.py pipeline/tests/test_binfmt.py
git commit -m "feat(pipeline): EDGE_DTYPE carries time/elevation/grading, drops weight"
```

### Task 4: `WayGraphHandler` emits grading metres; contraction sums them

**Files:**
- Modify: `pipeline/phases/graph_building/build_base_graph.py:40-133` (delete `SAC_SCALE_RANK`,
  rewrite `WayGraphHandler.__init__`/`way`, `stream_osm`, `handler_to_arrays`)
- Modify: `pipeline/lib/contraction.py` (`contract_structural`: drop the `edges_weight` param and
  `w_sum`; add `ungraded_m`/`inferred_m` sums and a `constrained_ok` AND-fold)
- Modify: `pipeline/lib/edge_split.py:44-` (`SplitResult`/`split_edge_at_point`: `weight_m` and
  `weight_to_u/_to_v` replaced by `ungraded_m`/`inferred_m` apportioned by the same distance ratio)
- Modify: `pipeline/analysis/grading_coverage.py` (imports `bbg.SAC_SCALE_RANK`)
- Test: `pipeline/tests/test_build_base_graph.py`, `test_contraction.py`, `test_edge_split.py`

**Interfaces:**
- Consumes: `lib.grading` (Task 2), `binfmt.EDGE_DTYPE` (Task 3).
- Produces: `stream_osm(trails_path, config)` no longer reads `roadPenaltyFactor`;
  `handler_to_arrays(handler)` returns
  `(coords, edges_i, edges_j, edges_dist, edges_road, edges_ungraded, edges_inferred,
  edges_sac_rank, edges_via_ferrata, edges_constrained_ok)` — `edges_w` gone, three arrays new;
  `contract_structural(*those, progress_every=…)` returns a `contracted` object with matching
  `edges_ungraded_m`, `edges_inferred_m`, `edges_constrained_ok`. Consumed by Tasks 5 and 8.

- [ ] **Step 1: Write the failing tests**

```python
# pipeline/tests/test_build_base_graph.py — add (with a _fake_way helper next to the existing
# fixtures: a namedtuple("W", "nodes tags") whose nodes expose .ref and .location.lon/.lat/.valid())
def test_way_handler_accumulates_ungraded_metres():
    h = bbg.WayGraphHandler(road_tags=["service"], progress_every=0)
    h.way(_fake_way(coords=[(0.0, 0.0), (0.001, 0.0), (0.002, 0.0)], tags={"highway": "path"}))
    assert sum(h.edges_ungraded) > 0
    assert sum(h.edges_inferred) == 0
    assert all(rank == -1 for rank in h.edges_sac_rank)
    assert not any(h.edges_constrained_ok)


def test_way_handler_marks_implied_grade_as_inferred_and_passable():
    h = bbg.WayGraphHandler(road_tags=["service"], progress_every=0)
    h.way(_fake_way(coords=[(0.0, 0.0), (0.001, 0.0)], tags={"highway": "track"}))
    assert sum(h.edges_inferred) > 0
    assert sum(h.edges_ungraded) == 0
    assert h.edges_sac_rank == [1]
    assert h.edges_constrained_ok == [True]


def test_via_ferrata_is_never_constrained_passable():
    h = bbg.WayGraphHandler(road_tags=["service"], progress_every=0)
    h.way(_fake_way(coords=[(0.0, 0.0), (0.001, 0.0)],
                    tags={"highway": "path", "sac_scale": "hiking", "via_ferrata_scale": "A"}))
    assert h.edges_constrained_ok == [False]


def test_way_handler_no_longer_takes_a_road_penalty_factor():
    import inspect
    assert "road_penalty_factor" not in inspect.signature(bbg.WayGraphHandler.__init__).parameters
```

```python
# pipeline/tests/test_contraction.py — add
def test_contract_sums_grading_metres_along_a_chain():
    # 3-node chain, middle node degree 2 -> one contracted edge carrying the sums
    contracted = contract_structural(
        coords=np.array([[0.0, 0.0], [0.001, 0.0], [0.002, 0.0]]),
        edges_i=np.array([0, 1]), edges_j=np.array([1, 2]),
        edges_dist=np.array([100.0, 150.0]),
        edges_road=np.array([False, False]),
        edges_ungraded=np.array([100.0, 0.0]),
        edges_inferred=np.array([0.0, 150.0]),
        edges_sac_rank=np.array([-1, 1], dtype=np.int8),
        edges_via_ferrata=np.array([False, False]),
        edges_constrained_ok=np.array([False, True]),
        progress_every=0,
    )
    assert contracted.edges_ungraded_m[0] == 100.0
    assert contracted.edges_inferred_m[0] == 150.0
    # one ungraded segment poisons the whole contracted edge for every constrained row
    assert bool(contracted.edges_constrained_ok[0]) is False
```

```python
# pipeline/tests/test_edge_split.py — add
def test_split_apportions_grading_metres_by_distance_ratio():
    split = split_edge_at_point(
        u_coord=(0.0, 0.0), v_coord=(0.002, 0.0), interior=[],
        dist_m=200.0, road_m=0.0, ungraded_m=200.0, inferred_m=0.0,
        segment_index=0, frac=0.25,
    )
    assert split.ungraded_m_to_u == 50.0
    assert split.ungraded_m_to_v == 150.0
    assert not hasattr(split, "weight_to_u")
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest pipeline/tests/test_build_base_graph.py pipeline/tests/test_contraction.py pipeline/tests/test_edge_split.py -q`
Expected: FAIL — `TypeError: __init__() missing 1 required positional argument: 'road_penalty_factor'`
and `TypeError: contract_structural() got an unexpected keyword argument 'edges_ungraded'`.

- [ ] **Step 3: Implement**

In `build_base_graph.py`, delete the module-level `SAC_SCALE_RANK` (it lives in `lib/grading.py` now;
fix `analysis/grading_coverage.py`'s import in this same commit) and:

```python
from lib import grading  # noqa: E402


class WayGraphHandler(osmium.SimpleHandler):
    def __init__(self, road_tags, progress_every=100_000):
        super().__init__()
        self.road_tags = set(road_tags)
        self.node_id_to_idx = {}
        self.coords = []
        self.edges_i, self.edges_j = [], []
        self.edges_dist = []
        self.edges_road, self.edges_ungraded, self.edges_inferred = [], [], []
        self.edges_sac_rank, self.edges_via_ferrata, self.edges_constrained_ok = [], [], []
        self.progress_every = progress_every
        self.n_ways = 0

    def way(self, w):
        ...  # node / coord / dists block unchanged
        tags = dict(w.tags)
        highway = tags.get("highway", "")
        is_road = highway in self.road_tags
        grade = grading.classify_way(tags)
        is_via_ferrata = highway == "via_ferrata" or "via_ferrata_scale" in tags
        constrained_ok = (
            grade.tier != grading.TIER_UNGRADED
            and not is_via_ferrata
            and not grading.excluded_from_constrained(tags)
        )
        n_edges = len(nodes) - 1
        zeros = [0.0] * n_edges
        ungraded = dists.tolist() if grade.tier == grading.TIER_UNGRADED else zeros
        inferred = dists.tolist() if grade.tier == grading.TIER_INFERRED else zeros
        self.edges_i.extend(idxs[:-1].tolist())
        self.edges_j.extend(idxs[1:].tolist())
        self.edges_dist.extend(dists.tolist())
        self.edges_road.extend([is_road] * n_edges)
        self.edges_ungraded.extend(ungraded)
        self.edges_inferred.extend(inferred)
        self.edges_sac_rank.extend([grade.sac_rank] * n_edges)
        self.edges_via_ferrata.extend([is_via_ferrata] * n_edges)
        self.edges_constrained_ok.extend([constrained_ok] * n_edges)
        ...  # progress print unchanged
```

`stream_osm` drops the second constructor argument. `handler_to_arrays` returns the ten arrays above
(`edges_ungraded`/`edges_inferred` as `float64`, `edges_constrained_ok` as `bool`) and no longer
builds `edges_w` — keep its docstring's point about dropping the handler before contraction.

`lib/contraction.py`: replace the `w_sum` accumulator with `ungraded_sum`/`inferred_sum` (same shape
as the existing `road_m` accumulation) and fold `constrained_ok` with logical AND along each chain.
`pack_and_write` writes the new columns and leaves `time_s`/`ascent_m`/`descent_m` at `binfmt.UNSET`.

`lib/edge_split.py`: signature becomes `split_edge_at_point(u_coord, v_coord, interior, dist_m,
road_m, ungraded_m, inferred_m, segment_index, frac)`; `SplitResult` swaps the weight fields for
`ungraded_m_to_u/_to_v` and `inferred_m_to_u/_to_v`. Keep the module's note that apportionment is
linear — §C9 records this as accepted (13.7 m mean gap, 3.0 m mean vertical offset, far below DEM
noise).

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest pipeline/tests -q`
Expected: PASS. `test_build_hub_edges.py`'s fixtures build `EDGE_DTYPE` tuples positionally and are
updated to the new field order here (fixtures, not behaviour).

- [ ] **Step 5: Commit**

```bash
git add pipeline/phases/graph_building/build_base_graph.py pipeline/lib/contraction.py pipeline/lib/edge_split.py pipeline/analysis/grading_coverage.py pipeline/tests
git commit -m "feat(pipeline): base graph carries grading metres, drops road penalty weight"
```

### Task 5: Remove `roadPenaltyFactor` and every remaining reader

**Files:**
- Modify: `pipeline/pipeline.config.json:9` (delete `roadPenaltyFactor`)
- Modify: `pipeline/analysis/contraction_scaling.py`, `pipeline/analysis/reconstruct_raw_graph.py`
- Modify: `pipeline/phases/graph_building/build_hub_edges.py:212` — `weights =
  subgraph.local_edges["weight"]` routes on `dist` for now; Task 13 switches it to `time_s`
- Create: `pipeline/tests/test_config.py`

**Interfaces:**
- Produces: a config with no `roadPenaltyFactor`. Any code still reading it raises `KeyError` — that
  loud failure is the design (§A3).

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/test_config.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.pipeline import load_config  # noqa: E402


def test_config_has_no_road_penalty_factor():
    assert "roadPenaltyFactor" not in load_config()["graph"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest pipeline/tests/test_config.py -q`
Expected: FAIL — assertion error, the key is still there.

- [ ] **Step 3: Delete the key and fix every reader**

```bash
grep -rn "roadPenaltyFactor\|road_penalty_factor\|\[.weight.\]" pipeline/ --include=*.py --include=*.json
```

Every hit must be resolved; no reader may fall back to a default. `reconstruct_raw_graph.py` already
documents that per-segment road flags are unrecoverable after contraction — extend that same caveat
paragraph to `ungraded_m`/`inferred_m` (chain totals survive, per-segment attribution does not).

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest pipeline/tests -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/pipeline.config.json pipeline/analysis pipeline/phases pipeline/tests
git commit -m "refactor(pipeline): remove roadPenaltyFactor and its readers"
```

---

# Phase 2 — Elevation per base edge, and the time cost

Elevation stops being a display decoration applied after routing and becomes the thing routing is
built on. `add_elevation.py` dies here.

The "this couples elevation to a multi-hour re-route" objection does not survive: once `time_s` is
the routing weight, any elevation change changes which path wins, so re-routing is mandatory either
way. The cheap-rewrite-in-place property was only ever real because elevation did not affect routing.

### Task 6: Speed model and DIN duration as a pure module

**Files:**
- Create: `pipeline/lib/speed.py`
- Modify: `pipeline/pipeline.config.json` (add `graph.speedModel`)
- Test: `pipeline/tests/test_speed.py`

**Interfaces:**
- Produces: `speed_kmh(slope, *, v0, k, s0)`,
  `edge_time_s(dist_m, dz_m, *, v0, k, s0) -> np.ndarray` (§A1) and
  `din_duration_h(distance_m, ascent_m, descent_m) -> float` (§A2). Consumed by Task 8 (fills
  `time_s`), Tasks 10-11 (probe calibration), Task 20 (approach ranking). Never by anything that
  turns a *routing* cost into a displayed duration.

- [ ] **Step 1: Write the failing tests**

```python
# pipeline/tests/test_speed.py
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import speed  # noqa: E402

CONSTANTS = dict(v0=6.0, k=3.5, s0=0.05)  # spec A1 starting point; Task 11 calibrates


def test_speed_peaks_on_a_gentle_descent_not_on_the_flat():
    v_flat = speed.speed_kmh(np.array([0.0]), **CONSTANTS)[0]
    v_peak = speed.speed_kmh(np.array([-0.05]), **CONSTANTS)[0]
    assert v_peak > v_flat
    assert v_peak == pytest.approx(6.0)


def test_time_is_additive_across_a_split_segment():
    # the entire point of a pointwise model: splitting a segment must not change its cost
    whole = speed.edge_time_s(np.array([100.0]), np.array([10.0]), **CONSTANTS).sum()
    halves = speed.edge_time_s(np.array([50.0, 50.0]), np.array([5.0, 5.0]), **CONSTANTS).sum()
    assert whole == pytest.approx(halves)


def test_uphill_is_slower_than_the_same_grade_downhill():
    up = speed.edge_time_s(np.array([100.0]), np.array([20.0]), **CONSTANTS)[0]
    down = speed.edge_time_s(np.array([100.0]), np.array([-20.0]), **CONSTANTS)[0]
    assert up > down


def test_zero_length_segment_costs_nothing_and_does_not_divide_by_zero():
    assert speed.edge_time_s(np.array([0.0]), np.array([0.0]), **CONSTANTS)[0] == 0.0


def test_din_duration_blends_horizontal_and_vertical():
    # 8 km with 600 m up / 500 m down: t_h = 2.0, t_v = 2.0 + 1.0 = 3.0 -> 3.0 + 1.0 = 4.0 h
    assert speed.din_duration_h(8000.0, 600.0, 500.0) == pytest.approx(4.0)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest pipeline/tests/test_speed.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'lib.speed'`

- [ ] **Step 3: Write the module**

```python
# pipeline/lib/speed.py
"""Two quantities that must never be conflated (spec A1/A2).

ROUTING WEIGHT (edge_time_s): additive per base-graph edge, pointwise, Tobler-shaped:
    v(s) = v0 * exp(-k * |s + s0|)   km/h,  s = dz/dx
Base edges have median length 49.5 m (p25 19.7, p75 133.7, n=8.34M). At that granularity DIN's
max+min/2 blend never engages, and a per-edge DIN sum degenerates to t_h + t_v - +33% over the
route-level figure at t_h == t_v. The pointwise integral is additive at ANY granularity, and its
direction asymmetry falls out of the curve rather than a bolted-on rule.

REPORTED DURATION (din_duration_h): DIN 33466 over a whole leg's aggregates. Computed client-side
and NOT stored (spec D3); this implementation exists so the probe can compare the two, and as the
authoritative definition.

The constants are CALIBRATED against DIN on real legs by analysis/routing_probe.py (spec H.4), not
inherited from Tobler. Live values: pipeline.config.json's graph.speedModel.
"""

import numpy as np


def speed_kmh(slope, *, v0: float, k: float, s0: float):
    return v0 * np.exp(-k * np.abs(np.asarray(slope, dtype=np.float64) + s0))


def edge_time_s(dist_m, dz_m, *, v0: float, k: float, s0: float):
    """Seconds per segment. dist_m is horizontal length, dz_m the signed elevation delta."""
    dist_m = np.asarray(dist_m, dtype=np.float64)
    dz_m = np.asarray(dz_m, dtype=np.float64)
    safe = np.where(dist_m > 0, dist_m, 1.0)
    slope = np.where(dist_m > 0, dz_m / safe, 0.0)
    v_ms = speed_kmh(slope, v0=v0, k=k, s0=s0) * (1000.0 / 3600.0)
    return np.where(dist_m > 0, dist_m / v_ms, 0.0)


def din_duration_h(distance_m: float, ascent_m: float, descent_m: float) -> float:
    """DIN 33466. NEVER call this with a routing-penalised distance - a road does not take longer
    to walk (spec A3)."""
    t_h = distance_m / 4000.0
    t_v = ascent_m / 300.0 + descent_m / 500.0
    return max(t_h, t_v) + min(t_h, t_v) / 2.0
```

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest pipeline/tests/test_speed.py -q`
Expected: PASS (5 tests)

- [ ] **Step 5: Add the config block**

Under `graph` in `pipeline/pipeline.config.json`:

```json
"speedModel": { "v0": 6.0, "k": 3.5, "s0": 0.05 },
```

- [ ] **Step 6: Commit**

```bash
git add pipeline/lib/speed.py pipeline/tests/test_speed.py pipeline/pipeline.config.json
git commit -m "feat(pipeline): pointwise speed model and DIN duration module"
```

### Task 7: Per-edge elevation sampling core

**Files:**
- Create: `pipeline/phases/elevation/add_base_elevation.py` (pure functions only; wiring is Task 8)
- Test: `pipeline/tests/test_add_base_elevation.py`

**Interfaces:**
- Consumes: `binfmt.EDGE_DTYPE` (Task 3), `lib.speed.edge_time_s` (Task 6), `lib/grid.py`.
- Produces:
  - `smooth_profile(elevations, seg_len_m, kernel_m) -> np.ndarray` (same length as input)
  - `edge_ascent_descent(smoothed, edge_starts, edge_counts) -> (ascent, descent)` — vectorised
    `reduceat` over all edges at once; no per-edge Python loop, no hysteresis
  - `sample_bilinear(dem_window, transform, lon, lat) -> np.ndarray`

- [ ] **Step 1: Write the failing tests**

```python
# pipeline/tests/test_add_base_elevation.py
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from elevation import add_base_elevation as abe  # noqa: E402


def test_ascent_descent_are_plain_sums_of_signed_deltas():
    # +10, -4, +6 -> ascent 16, descent 4. No threshold, no hysteresis: eleNoiseThresholdM is
    # retired and the smoothing kernel is the replacement tunable (spec B2).
    smoothed = np.array([1000.0, 1010.0, 1006.0, 1012.0])
    asc, desc = abe.edge_ascent_descent(smoothed, np.array([0]), np.array([4]))
    assert asc[0] == pytest.approx(16.0)
    assert desc[0] == pytest.approx(4.0)


def test_ascent_descent_vectorises_over_many_edges_without_bleeding():
    # two edges back to back; the +90 jump BETWEEN them belongs to neither
    smoothed = np.array([100.0, 110.0, 200.0, 190.0])
    asc, desc = abe.edge_ascent_descent(smoothed, np.array([0, 2]), np.array([2, 2]))
    assert asc.tolist() == pytest.approx([10.0, 0.0])
    assert desc.tolist() == pytest.approx([0.0, 10.0])


def test_single_point_edge_has_zero_ascent():
    asc, desc = abe.edge_ascent_descent(np.array([1500.0]), np.array([0]), np.array([1]))
    assert asc[0] == 0.0 and desc[0] == 0.0


def test_smoothing_removes_a_single_point_dem_spike():
    elev = np.full(11, 1000.0)
    elev[5] = 1020.0
    seg = np.full(10, 10.0)          # 10 m spacing, 30 m kernel
    out = abe.smooth_profile(elev, seg, kernel_m=30.0)
    assert out.max() - out.min() < 20.0
    assert len(out) == len(elev)


def test_smoothing_kernel_is_metres_not_points():
    # point spacing varies 7x between p25 (19.7 m) and p75 (133.7 m), so a point-count kernel
    # would smooth wildly different distances on different edges
    dense = abe.smooth_profile(np.array([0.0, 20.0, 0.0]), np.array([5.0, 5.0]), kernel_m=30.0)
    sparse = abe.smooth_profile(np.array([0.0, 20.0, 0.0]), np.array([200.0, 200.0]), kernel_m=30.0)
    assert dense.max() < sparse.max()


def test_bilinear_sampling_interpolates_between_cells():
    from affine import Affine
    window = np.array([[0.0, 10.0], [20.0, 30.0]], dtype=np.float32)
    transform = Affine(1.0, 0.0, 0.0, 0.0, -1.0, 0.0)
    got = abe.sample_bilinear(window, transform, np.array([1.0]), np.array([-1.0]))
    assert got[0] == pytest.approx(15.0)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest pipeline/tests/test_add_base_elevation.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the three functions**

Module docstring:

```python
#!/usr/bin/env python3
"""Samples data/dem/dem.tif per BASE-GRAPH EDGE (spec B2), not per record.

Why per edge and not per node: nodes.npy holds 6.85M post-contraction junctions and the shape
lives in interior.npy (33.1M points). Node elevation gives only the NET delta across a contracted
edge, so a switchback chain over a col would report its endpoint difference and nothing else.

Why a separate process from build_base_graph.py: that script already peaks at 12.4 GB of 15.95 GB
(data/timings.jsonl). This one reads the DEM PER GRID CELL (cell_index.npy + lib/grid.py), never
as one 74008x39276 window.

Sampling is BILINEAR against a pre-smoothed raster (one cached gdal pass), replacing the old
nearest-neighbour np.floor into a 5 m (Bavaria DGM5) / 10 m (AT BEV) DEM. Ascent/descent are plain
sums of positive/negative deltas along the smoothed profile - eleNoiseThresholdM and its hysteresis
loop are retired, and the kernel width (metres) is the replacement tunable.

Persists node_ele.npy (f4 x 6.85M, 27 MB) and interior_ele.npy (f4 x 33.1M, 132 MB) so
build_profiles.py and every display path can avoid reopening the DEM.
"""
```

`edge_ascent_descent`: `np.diff` over the concatenated point array, zero the deltas straddling an
edge boundary (index arithmetic from `edge_starts`/`edge_counts`), then `np.add.reduceat` over the
positive and negative halves. `smooth_profile`: distance-weighted moving average over the cumulative
segment lengths, kernel width in metres. `sample_bilinear`: affine inverse plus
`scipy.ndimage.map_coordinates(order=1)`, or a hand-rolled 4-neighbour blend if scipy is not in
`alpen-osm`.

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest pipeline/tests/test_add_base_elevation.py -q`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add pipeline/phases/elevation/add_base_elevation.py pipeline/tests/test_add_base_elevation.py
git commit -m "feat(pipeline): per-base-edge elevation sampling core"
```

### Task 8: Wire `add_base_elevation` into the DAG, fill `time_s`, delete `add_elevation`

**Files:**
- Modify: `pipeline/phases/elevation/add_base_elevation.py` (add `main()` + the per-cell driver)
- Create: `pipeline/phases/elevation/build_profiles.py`
- Delete: `pipeline/phases/elevation/add_elevation.py`, `pipeline/tests/test_add_elevation.py`
- Modify: `pipeline/dodo.py` (add `task_add_base_elevation`, `task_build_profiles`; delete
  `task_add_elevation`; retarget both tile tasks' `task_dep`; update `default_tasks` and the module
  docstring)
- Modify: `pipeline/pipeline.config.json` (`dem.eleNoiseThresholdM` → `dem.smoothingKernelM: 30`)
- Create: `pipeline/tests/test_dodo_wiring.py`

**Interfaces:**
- Consumes: Task 7's functions, `lib.speed.edge_time_s` (Task 6).
- Produces: `data/osm/base_graph/{node_ele.npy, interior_ele.npy}`, an in-place rewrite of
  `edges.npy` filling `time_s`/`ascent_m`/`descent_m`, and `build_profiles.py` writing
  `hut_edges/profiles.npy` + `start_edges/profiles.npy` from the stored point elevations.

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/test_dodo_wiring.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dodo  # noqa: E402


def test_add_elevation_task_is_gone():
    assert not hasattr(dodo, "task_add_elevation")
    assert "add_elevation" not in dodo.DOIT_CONFIG["default_tasks"]


def test_elevation_pass_sits_between_base_graph_and_hub_edges():
    ordered = dodo.DOIT_CONFIG["default_tasks"]
    assert ordered.index("build_base_graph") < ordered.index("add_base_elevation")
    assert ordered.index("add_base_elevation") < ordered.index("build_hub_edges")


def test_dem_is_a_declared_file_dep_of_the_elevation_pass():
    # spec B5: today the ordering is numbering convention only
    deps = dodo.task_add_base_elevation()["file_dep"]
    assert any(d.endswith("dem.tif") for d in deps)


def test_build_profiles_never_declares_the_dem():
    # spec B4: profilePoints retuning must not force a re-route or a DEM read
    deps = dodo.task_build_profiles()["file_dep"]
    assert not any("dem" in d for d in deps)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest pipeline/tests/test_dodo_wiring.py -q`
Expected: FAIL — `AssertionError` (`task_add_elevation` still exists)

- [ ] **Step 3: Implement**

`add_base_elevation.main()`: mmaps `base_graph/`, iterates cells via `cell_index.npy`, reads one DEM
window per cell, samples node + interior points bilinearly, writes `node_ele.npy` /
`interior_ele.npy`; then per edge reconstructs the point sequence from `u`/`v` +
`interior_offset`/`interior_count`, smooths it, and fills `ascent_m`/`descent_m` (Task 7) and
`time_s` (`speed.edge_time_s(seg_len, seg_dz, **config["graph"]["speedModel"])`, summed per edge by
the same `reduceat`). Wrap in `phase("add_base_elevation.py", "add_base_elevation")` with a
`StepTimer` splitting `read_dem`, `sample`, `smooth`, `ascent_descent`, `time_s`, `write`. One
progress line per cell.

`build_profiles.py`: interpolates the stored point elevations onto `config["dem"]["profilePoints"]`
evenly spaced distances per record, writes `profiles.npy` and the records'
`profile_offset`/`profile_count`. Never opens the DEM.

In `dodo.py`:

```python
def task_add_base_elevation():
    return {
        "actions": [
            f'"{sys.executable}" "{SCRIPT_DIR / "phases" / "elevation" / "add_base_elevation.py"}"'
            " --smoothing-kernel-m %(smoothing_kernel_m)s"
        ],
        "params": [
            {"name": "smoothing_kernel_m", "long": "smoothing-kernel-m", "type": float,
             "default": CONFIG["dem"]["smoothingKernelM"]},
        ],
        # spec B5: the elevation pass genuinely needs the DEM, so declare it - the previous
        # numbering-convention ordering let a stale dem.tif through silently.
        "file_dep": [str(OSM_DIR / "base_graph" / "manifest.json"), str(DEM_DIR / "dem.tif")],
        "targets": [str(OSM_DIR / "base_graph" / "node_ele.npy"),
                    str(OSM_DIR / "base_graph" / "interior_ele.npy")],
        "uptodate": [lambda task, values: config_changed(json.dumps(task.options, sort_keys=True))(task, values)],
    }
```

`task_build_profiles` takes `task_dep: ["build_hub_edges"]`, `file_dep` on `interior_ele.npy` plus
both `records.npy`, `targets` the two `profiles.npy`, and `uptodate: [False]` (seconds; usually run
precisely to retune `--profile-points`). Both tile tasks' `task_dep` moves from `add_elevation` to
`build_profiles`. `default_tasks` becomes `… build_base_graph, fetch_dem, build_dem_vrt,
add_base_elevation, build_hub_edges, build_profiles, build_*_tiles, copy_public_data`.

Update `dodo.py`'s module docstring: the "`add_elevation` is force-rerun because it's cheap" note is
now false — replace it with the `build_profiles` equivalent, and say that `add_base_elevation` is
freshness-checked normally.

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest pipeline/tests -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add -A pipeline/phases/elevation pipeline/dodo.py pipeline/pipeline.config.json pipeline/tests
git commit -m "feat(pipeline): add_base_elevation task replaces add_elevation"
```

### Task 9: Rebuild the base graph and run the elevation pass

**Files:** none — this is a run plus a recorded measurement.

- [ ] **Step 1: Show the user the cost, and check nothing else is stale** **[ASK FIRST]**

`build_base_graph` is ~18 min (stream_osm 963 s + contract_structural 157 s, `data/timings.jsonl`).
`add_base_elevation` is new and unmeasured. `fetch_dem` (1,762 s) and `build_dem_vrt` (930 s) are
cached and should NOT re-run — confirm before starting:

```bash
doit info build_base_graph
doit info add_base_elevation
doit info fetch_dem
```

- [ ] **Step 2: Run** **[ASK FIRST]**

```bash
doit build_base_graph add_base_elevation
```

- [ ] **Step 3: Verify the new columns are populated**

```bash
python -c "
import numpy as np
e = np.load('data/osm/base_graph/edges.npy', mmap_mode='r')
print(len(e), 'edges')
for f in ('time_s','ascent_m','descent_m','ungraded_m','inferred_m'):
    col = np.asarray(e[f][:100000]); print(f, float(col.min()), float(col.max()))
print('constrained_ok share', float(np.asarray(e['constrained_ok'][:1000000]).mean()))
"
```

Expected: no field still sitting at `-1.0` (UNSET); `time_s > 0` wherever `dist > 0`; the
`constrained_ok` share in the ballpark of the network tier mass in the findings doc. A large mismatch
means the production classifier and the measurement disagree — stop and reconcile before Phase 3,
because the probe's conclusions would inherit the discrepancy.

- [ ] **Step 4: Record the timing in the findings doc**

```bash
tail -5 data/timings.jsonl
```

`add_base_elevation`'s wall time feeds Task 11's probe budget and Task 24's rebuild estimate.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-08-22-tour-suggestion-findings.md
git commit -m "docs: record add_base_elevation runtime"
```

---

# Phase 3 — Sizing probe (the gate before the expensive build)

§H: "Probe costs minutes; guessing wrong costs hours of compute." Phase 4's build does not start
until this phase has produced numbers.

**Ordering note:** the probe must call production functions, never copies (`analysis/README.md`
contract). The only production code it needs that does not yet exist is the constrained-row edge
filter and the time-weighted graph build — so **Task 13 is implemented before Task 10's Step 4**.
Task 13 is pure library code with its own tests and requires no rebuild, so this costs nothing.

### Task 10: Write the routing probe

**Files:**
- Create: `pipeline/analysis/routing_probe.py`
- Modify: `pipeline/analysis/README.md` (add its section, with runtime)
- Test: `pipeline/tests/test_routing_probe.py`

**Interfaces:**
- Consumes: `lib.subgraph.gather_padded_subgraph`, `build_hub_edges.snap_hub_to_subgraph`,
  `build_hub_edges._build_igraph_with_snaps`, `build_hub_edges._path_for`, `lib.variants.edge_mask`
  (Task 13), `lib.speed` (Task 6).
- Produces: `data/analysis/routing_probe.json` with the five §H measurements, plus the helpers
  `is_substitution(baseline_coords, candidate_coords) -> bool` and
  `classify_blocker(reachable_ignoring_ungraded, reachable_ignoring_difficulty) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
# pipeline/tests/test_routing_probe.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))

import routing_probe  # noqa: E402


def test_substitution_is_geometry_identity_not_cost_equality():
    # a column earns its build cost by producing a DIFFERENT ROUTE, not a different number
    # (spec C2) - equal-cost different geometry is still a substitution
    baseline = [(0.0, 0.0), (0.001, 0.0), (0.002, 0.0)]
    same = [(0.0, 0.0), (0.001, 0.0), (0.002, 0.0)]
    other = [(0.0, 0.0), (0.001, 0.001), (0.002, 0.0)]
    assert not routing_probe.is_substitution(baseline, same)
    assert routing_probe.is_substitution(baseline, other)


def test_blocker_classification_separates_ungraded_from_difficulty():
    # spec H.3 - the one open question in the passability design
    assert routing_probe.classify_blocker(True, False) == "ungraded"
    assert routing_probe.classify_blocker(False, True) == "difficulty"
    assert routing_probe.classify_blocker(False, False) == "disconnected"
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest pipeline/tests/test_routing_probe.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'routing_probe'`

- [ ] **Step 3: Implement Task 13 now, then return here**

See the ordering note above.

- [ ] **Step 4: Write the probe**

Docstring states: read-only, not in the DAG, requires `base_graph/` **with the elevation pass run**,
runtime "minutes at the default 200-pair sample, linear in `--pairs`".

Sampling: ~200 hut pairs stratified across the grid cells' terrain range (use each cell's node
elevation spread as the strat key), not uniform — a uniform sample over-weights the flat north and
would understate every constrained row's cost.

Per pair, route **all nine grid cells** — three constraint rows × three objective columns — even
though only the fastest column is built, because the other columns' substitution rate is exactly what
decides whether they are ever worth building. Record:

1. **Wall time per cell**, and its ratio to `FAST_ANY` → replaces the guessed 5-8× multiplier.
2. **Substitution rate** per cell (geometry differs from `FAST_ANY`) and, for constrained rows, the
   fraction where `FAST_ANY` itself violates the constraint — i.e. where the row is the difference
   between a *substituted* path and a *deleted* edge.
3. **Ungraded blocker rate** — for every pair a constrained row cannot connect, `classify_blocker`,
   by re-routing once ignoring the ungraded rule and once ignoring the grade ceiling.
4. **Routing cost vs reported duration** — summed `time_s` against `speed.din_duration_h` on the same
   path's aggregates, as a scatter plus fitted `(v0, k, s0)` minimising the residual → **calibrates
   §A1's constants instead of inheriting Tobler's**.
5. **Direction spread** — a subset routed both ways, comparing geometry identity and cost → §D4's
   currently-*unknown* (not bounded) magnitude.

One progress line per pair. Writes `data/analysis/routing_probe.json`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest pipeline/tests/test_routing_probe.py -q`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add pipeline/analysis/routing_probe.py pipeline/analysis/README.md pipeline/tests/test_routing_probe.py
git commit -m "analysis: routing probe for variant cost, substitution and calibration"
```

### Task 11: Run the probe and settle the parameters

**Files:**
- Modify: `pipeline/pipeline.config.json` (`graph.speedModel`, `graph.variants`)
- Modify: `docs/superpowers/specs/2026-08-22-tour-suggestion-findings.md`

- [ ] **Step 1: Run the probe** **[ASK FIRST — minutes, read-only]**

```bash
python pipeline/analysis/routing_probe.py --pairs 200
```

- [ ] **Step 2: Write the calibrated constants into the config**

Replace the placeholder `{v0: 6.0, k: 3.5, s0: 0.05}` with the fitted values. Record old, new and the
residual in the findings doc — §A1 says the constants are calibrated against DIN on real legs, and
that diff is the evidence it happened.

- [ ] **Step 3: Write the variant list into the config**

```json
"variants": ["FAST_ANY", "FAST_T2", "FAST_T3"]
```

Add `FAST_T3_UNGRADED` **only if** Task 1's or the probe's ungraded blocker rate crossed the recorded
threshold; if so, `binfmt.VARIANT_NAMES` and `lib/variants.py` gain the row in the same commit. What
is **not** acceptable either way is quietly relaxing the strict row's definition to restore
connectivity — the guarantee is the entire reason that row exists.

- [ ] **Step 4: Re-run the elevation pass with the calibrated constants** **[ASK FIRST]**

```bash
doit add_base_elevation
```

A constants change does not touch the base graph, so this costs one elevation pass, not a re-stream.

- [ ] **Step 5: Commit**

```bash
git add pipeline/pipeline.config.json docs/superpowers/specs/2026-08-22-tour-suggestion-findings.md
git commit -m "feat(pipeline): calibrate speed model and fix the variant grid from probe data"
```

---

# Phase 4 — Variant routing in `build_hub_edges`

The expensive phase. Everything is written and tested before a single hub edge is rebuilt.

### Task 12: `RECORD_DTYPE` gains the four scalar columns

**Files:**
- Modify: `pipeline/lib/binfmt.py` (`RECORD_DTYPE`)
- Test: `pipeline/tests/test_binfmt.py`

**Interfaces:**
- Produces: `RECORD_DTYPE` with `max_ele_m`, `ungraded_m`, `inferred_m`, `snap_m` (all f4) after
  `descent_m`. Applies to `start_edges/` as well as `hut_edges/` (§D1). Consumed by Tasks 14, 15, 17,
  18, 20, 21.

- [ ] **Step 1: Write the failing test**

```python
def test_record_dtype_carries_the_scalar_filter_columns():
    for field in ("max_ele_m", "ungraded_m", "inferred_m", "snap_m"):
        assert field in binfmt.RECORD_DTYPE.names, field


def test_record_dtype_has_no_stored_duration():
    # spec D3: reported duration is direction-dependent. A stored scalar guarantees something
    # reads it for a leg walked backwards and is wrong by the full ascent/descent rate gap.
    assert "time_min" not in binfmt.RECORD_DTYPE.names
    assert "time_s" not in binfmt.RECORD_DTYPE.names
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest pipeline/tests/test_binfmt.py -q`
Expected: FAIL — `AssertionError: max_ele_m`

- [ ] **Step 3: Edit `RECORD_DTYPE`**

```python
RECORD_DTYPE = np.dtype([
    ("from_id", "i8"), ("to_id", "i8"), ("from_type", "u1"), ("to_type", "u1"),
    ("variant", "u1"), ("distance_m", "f4"), ("road_m", "f4"),
    ("ascent_m", "f4"), ("descent_m", "f4"),
    ("max_ele_m", "f4"),   # scalar, so the client never scans a profile to apply an altitude cap
    ("ungraded_m", "f4"),  # zero by construction on every constrained row (spec C4)
    ("inferred_m", "f4"),  # separate from ungraded_m: they support different claims
    ("snap_m", "f4"),      # hub-to-trail gap, both ends; already folded into distance/ascent
    ("sac_rank", "i1"), ("via_ferrata", "bool"),
    ("geom_offset", "i8"), ("geom_count", "i4"),
    ("profile_offset", "i8"), ("profile_count", "i4"),
])
```

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest pipeline/tests -q`
Expected: PASS — fixtures in `test_build_hub_edges.py` / `test_build_edge_tiles.py` that build
records positionally are updated here.

- [ ] **Step 5: Commit**

```bash
git add pipeline/lib/binfmt.py pipeline/tests
git commit -m "feat(pipeline): record schema gains max_ele/ungraded/inferred/snap columns"
```

### Task 13: Variant definitions and the filtered graph builder

**Files:**
- Create: `pipeline/lib/variants.py`
- Modify: `pipeline/phases/graph_building/build_hub_edges.py:201-268` (`_build_igraph_with_snaps`)
- Test: `pipeline/tests/test_variants.py`, `pipeline/tests/test_build_hub_edges.py`

**Interfaces:**
- Consumes: `binfmt.VARIANT_*` and `EDGE_DTYPE.constrained_ok`/`sac_rank` (Task 3).
- Produces:
  - `Variant = namedtuple("Variant", "code name max_sac_rank require_graded")`, `VARIANTS: dict`
  - `edge_mask(local_edges, variant) -> np.ndarray[bool]`
  - `enabled_variants(config) -> list[Variant]`
  - `_build_igraph_with_snaps(subgraph, hub_snaps, edge_mask=None)` — same return triple, now
    routing on `time_s` and accepting a boolean mask over `subgraph.local_edges`.
  Consumed by Tasks 10, 14, 15.

- [ ] **Step 1: Write the failing tests**

```python
# pipeline/tests/test_variants.py
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import binfmt, variants  # noqa: E402


def _edges(**cols):
    n = len(next(iter(cols.values())))
    arr = np.zeros(n, dtype=binfmt.EDGE_DTYPE)
    for k, v in cols.items():
        arr[k] = v
    return arr


def test_unconstrained_row_keeps_everything():
    edges = _edges(sac_rank=[-1, 2, 6], constrained_ok=[False, True, True],
                   via_ferrata=[False, False, True])
    mask = variants.edge_mask(edges, variants.VARIANTS[binfmt.VARIANT_FAST_ANY])
    assert mask.tolist() == [True, True, True]


def test_t3_row_deletes_ungraded_over_grade_and_via_ferrata():
    edges = _edges(sac_rank=[-1, 2, 3, 4, 3],
                   constrained_ok=[False, True, True, True, False],
                   via_ferrata=[False, False, False, False, True])
    mask = variants.edge_mask(edges, variants.VARIANTS[binfmt.VARIANT_FAST_T3])
    #                       ungraded  T2    T3    T4     via ferrata
    assert mask.tolist() == [False, True, True, False, False]


def test_t2_row_is_strictly_tighter_than_t3():
    edges = _edges(sac_rank=[2, 3], constrained_ok=[True, True], via_ferrata=[False, False])
    t2 = variants.edge_mask(edges, variants.VARIANTS[binfmt.VARIANT_FAST_T2])
    t3 = variants.edge_mask(edges, variants.VARIANTS[binfmt.VARIANT_FAST_T3])
    assert (t2 <= t3).all()


def test_constrained_rows_cannot_admit_an_ungraded_edge():
    # spec C4: `ungraded_m == 0` is what lets the product claim every metre is graded T3 or
    # easier. A row admitting one ungraded edge silently breaks that claim.
    edges = _edges(sac_rank=[2], constrained_ok=[False], via_ferrata=[False], ungraded_m=[500.0])
    for code in (binfmt.VARIANT_FAST_T2, binfmt.VARIANT_FAST_T3):
        assert not variants.edge_mask(edges, variants.VARIANTS[code])[0]


def test_untagged_rank_can_never_satisfy_a_ceiling():
    # spec C5: -1 is "unknown", not "easy" - a <= comparison alone would admit it
    edges = _edges(sac_rank=[-1], constrained_ok=[True], via_ferrata=[False])
    assert not variants.edge_mask(edges, variants.VARIANTS[binfmt.VARIANT_FAST_T3])[0]
```

```python
# pipeline/tests/test_build_hub_edges.py — add
def test_igraph_routes_on_time_not_distance():
    # build a subgraph with a short steep edge and a longer flat one between the same pair,
    # time_s set so the longer path is faster; the routed path must take the flat one
    graph, hub_vertex, coords = _build_igraph_with_snaps(subgraph, snaps)
    assert graph.es["weight"] == graph.es["time_s"]


def test_edge_mask_removes_edges_from_the_built_graph():
    graph_all, _, _ = _build_igraph_with_snaps(subgraph, snaps, edge_mask=None)
    graph_filtered, _, _ = _build_igraph_with_snaps(
        subgraph, snaps, edge_mask=np.array([True, False])
    )
    assert graph_filtered.ecount() < graph_all.ecount()
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest pipeline/tests/test_variants.py pipeline/tests/test_build_hub_edges.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'lib.variants'`

- [ ] **Step 3: Implement**

```python
# pipeline/lib/variants.py
"""The variant grid (spec C2). Rows are hard ROUTING CONSTRAINTS; columns are what "best" means
among the paths that obey them. The axes do not interact.

Why rows are worth their build cost when a client-side filter is not: a per-edge filter can only
DELETE an edge. If the stored A->B path crosses T5 and the user caps at T3, filtering deletes A->B
entirely - even when a T3 path exists 400 m longer. Variants SUBSTITUTE. Measured: applying
sac_rank <= 3 to edges already inside a 12 km leg budget cuts 1,418 edges to 1,006 and leaves 23%
of huts with NO connection at all; under sac_rank <= 2, 39%.

Why columns are cheaper to justify: a column only earns its cost if its path DIFFERS from the
fastest one, otherwise the client re-sorts what it already holds. ASC_* is predicted near-redundant
(the speed model already prices climb steeply) and is not planned. ROAD_*, if the post-rebuild road
share justifies it, is a MULTIPLICATIVE penalty on the time of road-tagged segments (factor ~3-5) -
not lexicographic (buys 40 km detours), not additive time + lambda*road_m (lambda needs cross-unit
calibration). A multiplier is scale-free and its detour is bounded by m x the road's own time.
"""

from collections import namedtuple

import numpy as np

from lib import binfmt

Variant = namedtuple("Variant", "code name max_sac_rank require_graded")

VARIANTS = {
    binfmt.VARIANT_FAST_ANY: Variant(binfmt.VARIANT_FAST_ANY, "FAST_ANY", None, False),
    binfmt.VARIANT_FAST_T2: Variant(binfmt.VARIANT_FAST_T2, "FAST_T2", 2, True),
    binfmt.VARIANT_FAST_T3: Variant(binfmt.VARIANT_FAST_T3, "FAST_T3", 3, True),
}


def edge_mask(local_edges, variant):
    mask = np.ones(len(local_edges), dtype=bool)
    if variant.require_graded:
        # constrained_ok already folds ungraded / via ferrata / downgrade tags, AND-ed along
        # every contracted chain (lib/contraction.py) - one bad segment poisons the edge.
        mask &= local_edges["constrained_ok"]
    if variant.max_sac_rank is not None:
        mask &= local_edges["sac_rank"] >= 0          # spec C5: -1 never satisfies a ceiling
        mask &= local_edges["sac_rank"] <= variant.max_sac_rank
    return mask


def enabled_variants(config):
    by_name = {v.name: v for v in VARIANTS.values()}
    return [by_name[n] for n in config["graph"]["variants"]]
```

In `_build_igraph_with_snaps`: replace `weights = subgraph.local_edges["weight"]` with
`subgraph.local_edges["time_s"]`, carry `ungraded_m`, `inferred_m`, `ascent_m`, `descent_m` and a
per-edge `max_ele_m` as igraph edge attrs alongside `road_m` (Task 15 consumes them), add the
`edge_mask` parameter (ANDed into the existing `_filter` alongside `edges_to_remove`), and set the
igraph `weight` attribute to the time values so `_path_for`'s `weights="weight"` keeps working. The
two synthetic halves of a mid-chain split inherit the parent edge's mask value.

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest pipeline/tests -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/lib/variants.py pipeline/phases/graph_building/build_hub_edges.py pipeline/tests
git commit -m "feat(pipeline): variant grid definitions and time-weighted filtered routing"
```

### Task 14: Variant loop, variant-keyed dedup, `maxEdgeKm` re-check

**Files:**
- Modify: `pipeline/phases/graph_building/build_hub_edges.py:302-440`
  (`compute_hub_edges_for_cell`, `merge_and_dedup`, `_write_edge_output`, `_run_cell`, `__main__`)
- Test: `pipeline/tests/test_build_hub_edges.py`

**Interfaces:**
- Consumes: `lib.variants.enabled_variants`/`edge_mask` (Task 13).
- Produces: `compute_hub_edges_for_cell(subgraph, core_hubs, all_hubs, max_edge_km, max_snap_m,
  variants, timer=None)` returning records that each carry a `variant` key; `merge_and_dedup` and
  `_write_edge_output` keyed by `(pair, variant)`.

- [ ] **Step 1: Write the failing tests**

```python
def test_variant_rows_are_not_collapsed_into_one_record():
    # spec C6: three places key on the hut pair alone and would silently discard variant rows
    records = compute_hub_edges_for_cell(
        subgraph, core_hubs=[hut_a, hut_b], all_hubs=[hut_a, hut_b],
        max_edge_km=30, max_snap_m=100,
        variants=[variants.VARIANTS[binfmt.VARIANT_FAST_ANY],
                  variants.VARIANTS[binfmt.VARIANT_FAST_T3]],
    )
    assert {r["variant"] for r in records} == {binfmt.VARIANT_FAST_ANY, binfmt.VARIANT_FAST_T3}


def test_merge_and_dedup_keys_on_pair_and_variant():
    a = {"from_type": 0, "from_id": 1, "to_type": 0, "to_id": 2, "variant": 0}
    b = {"from_type": 0, "from_id": 2, "to_type": 0, "to_id": 1, "variant": 0}  # same pair reversed
    c = {"from_type": 0, "from_id": 1, "to_type": 0, "to_id": 2, "variant": 2}  # same pair, other row
    assert len(merge_and_dedup([[a], [b], [c]])) == 2


def test_write_edge_output_preserves_each_record_variant(tmp_path):
    _write_edge_output([_rec(variant=0), _rec(variant=2)], tmp_path)
    arr = np.load(tmp_path / "records.npy")
    assert sorted(arr["variant"].tolist()) == [0, 2]


def test_route_exceeding_max_edge_km_is_dropped():
    # spec C8: selection cuts off on `dist`, but the routed path's distance_m can exceed the cap
    records = compute_hub_edges_for_cell(
        long_route_subgraph, core_hubs=[hut_a], all_hubs=[hut_a, hut_b],
        max_edge_km=1.0, max_snap_m=100,
        variants=[variants.VARIANTS[binfmt.VARIANT_FAST_ANY]],
    )
    assert all(r["distance_m"] <= 1000.0 for r in records)


def test_a_variant_with_no_obeying_path_emits_no_record():
    # NOT a fallback to the unconstrained path: a constrained row that cannot connect a pair must
    # produce nothing, or the guarantee it exists for is broken
    records = compute_hub_edges_for_cell(
        ungraded_only_subgraph, core_hubs=[hut_a], all_hubs=[hut_a, hut_b],
        max_edge_km=30, max_snap_m=100,
        variants=[variants.VARIANTS[binfmt.VARIANT_FAST_T3]],
    )
    assert records == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest pipeline/tests/test_build_hub_edges.py -q`
Expected: FAIL — `TypeError: compute_hub_edges_for_cell() got an unexpected keyword argument 'variants'`

- [ ] **Step 3: Implement**

Restructure `compute_hub_edges_for_cell` so the genuinely shared work runs **once** per cell —
`gather_padded_subgraph`, `_build_edge_spatial_index`, the snap loop over `core_hubs + hut_targets`
(§Costs identifies exactly these as shared) — and only `build_igraph`, `distances` and `paths`
multiply per variant.

Reuse the unconstrained `distances()` result as a **prefilter, not a skip**: constrained distance is
always ≥ unconstrained, so the unconstrained pass yields a valid superset of candidate targets, but
each row must still evaluate its own cutoff on its own subgraph — otherwise a pair whose T2 route is
60 km survives a 30 km cap.

`seen_hut_pairs` becomes a set of `(pair_key, variant_code)`. `merge_and_dedup`'s key gains
`r["variant"]`. `_write_edge_output` writes `r["variant"]` instead of the hardcoded constant.

Add the §C8 re-check immediately after `_path_for`:

```python
            # spec C8: the cutoff above ran on `dist`; _path_for walks the TIME-shortest path,
            # whose distance_m can exceed the cap. The old comment claiming max-edge-km stayed a
            # guarantee about actual trail length was already untrue under roadPenaltyFactor, and
            # a time cost widens the gap.
            if distance_m > max_edge_m:
                continue
```

(`_path_for` still returns its current 5-tuple at this point; Task 15 turns it into a `PathResult`
namedtuple and this line becomes `result.distance_m` there.)

Delete the now-false comment above the `distances()` call and replace it with one saying the cutoff
is a *selection prefilter*, re-checked on the routed path below.

Give the `StepTimer` per-variant step labels (`paths_FAST_T3`, …) so the run's own log reports what
each row cost — that number replaces the probe's estimate for the next scope widening.

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest pipeline/tests -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/phases/graph_building/build_hub_edges.py pipeline/tests/test_build_hub_edges.py
git commit -m "feat(pipeline): variant-keyed hub edge routing with routed-path distance re-check"
```

### Task 15: Path attribute accumulation — grading metres, elevation, `max_ele_m`

**Files:**
- Modify: `pipeline/phases/graph_building/build_hub_edges.py:270-300` (`_path_for`) and the record
  construction in `compute_hub_edges_for_cell`
- Test: `pipeline/tests/test_build_hub_edges.py`

**Interfaces:**
- Consumes: the igraph edge attrs added in Task 13.
- Produces: `_path_for(...) -> PathResult`, a namedtuple replacing the current 5-tuple, with
  `coords, distance_m, road_m, ungraded_m, inferred_m, ascent_m, descent_m, max_ele_m, sac_rank,
  via_ferrata`. Consumed by Task 14's record construction and Task 17.

- [ ] **Step 1: Write the failing tests**

```python
def test_path_sums_ungraded_and_inferred_metres_like_road_m():
    result = _path_for(graph, vertex_coords, src_v, tgt_v)
    assert result.ungraded_m == pytest.approx(expected_ungraded)
    assert result.inferred_m == pytest.approx(expected_inferred)


def test_constrained_row_paths_have_zero_ungraded_metres():
    # the invariant the whole passability design rests on (spec C4/D1)
    mask = variants.edge_mask(subgraph.local_edges, variants.VARIANTS[binfmt.VARIANT_FAST_T3])
    graph, _, coords = _build_igraph_with_snaps(subgraph, snaps, edge_mask=mask)
    assert _path_for(graph, coords, src_v, tgt_v).ungraded_m == 0.0


def test_max_ele_is_the_path_maximum_not_an_endpoint():
    # a path over a col must report the col, not the higher of the two huts
    result = _path_for(graph, vertex_coords, src_v, tgt_v)
    assert result.max_ele_m > max(ele_at_src, ele_at_tgt)


def test_ascent_and_descent_swap_on_reverse_traversal():
    fwd = _path_for(graph, vertex_coords, src_v, tgt_v)
    rev = _path_for(graph, vertex_coords, tgt_v, src_v)
    assert rev.ascent_m == pytest.approx(fwd.descent_m)
    assert rev.descent_m == pytest.approx(fwd.ascent_m)


def test_ascent_is_the_sum_the_router_used():
    # spec B3: routing and display cannot disagree, because they are the same numbers
    epath = graph.get_shortest_paths(src_v, to=tgt_v, weights="weight", output="epath")[0]
    result = _path_for(graph, vertex_coords, src_v, tgt_v)
    assert result.ascent_m == pytest.approx(sum(graph.es[e]["ascent_m"] for e in epath))
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest pipeline/tests/test_build_hub_edges.py -q`
Expected: FAIL — `AttributeError: 'tuple' object has no attribute 'ungraded_m'`

- [ ] **Step 3: Implement**

`_path_for` sums `ungraded_m`/`inferred_m` alongside the existing `road_m`, sums `ascent_m`/`descent_m`
**swapping them when `forward` is False** (it already computes `forward` to reverse the interior
polyline), maxes `sac_rank` and `max_ele_m`, and returns the namedtuple. Record construction in
`compute_hub_edges_for_cell` copies the new fields straight through.

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest pipeline/tests -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/phases/graph_building/build_hub_edges.py pipeline/tests/test_build_hub_edges.py
git commit -m "feat(pipeline): accumulate grading, elevation and max altitude along routed paths"
```

### Task 16: Geometry sharing between identical variants

**Files:**
- Modify: `pipeline/phases/graph_building/build_hub_edges.py` (`_write_edge_output`)
- Test: `pipeline/tests/test_build_hub_edges.py`

**Interfaces:**
- Produces: `_write_edge_output` deduplicating identical coordinate runs by hash, so variants whose
  routed path is the same polyline share one `geom_offset`.

**Why this is a task and not an optimisation:** §C7 records that the mechanism does not exist — the
writer appends every record's polyline sequentially — while §F's payload estimate assumes it.
Constrained rows frequently return the unconstrained path unchanged, so without sharing the geometry
file grows linearly in variants for zero new information.

- [ ] **Step 1: Write the failing tests**

```python
def test_identical_variant_geometries_share_one_offset(tmp_path):
    geom = [(0.0, 0.0), (0.001, 0.0)]
    _write_edge_output([_rec(variant=0, geometry=geom), _rec(variant=2, geometry=geom)], tmp_path)
    records = np.load(tmp_path / "records.npy")
    geometry = np.load(tmp_path / "geometry.npy")
    assert records["geom_offset"][0] == records["geom_offset"][1]
    assert len(geometry) == 2   # one shared run, not two copies


def test_differing_geometries_do_not_share(tmp_path):
    _write_edge_output([
        _rec(variant=0, geometry=[(0.0, 0.0), (0.001, 0.0)]),
        _rec(variant=2, geometry=[(0.0, 0.0), (0.001, 0.001)]),
    ], tmp_path)
    records = np.load(tmp_path / "records.npy")
    assert records["geom_offset"][0] != records["geom_offset"][1]
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest pipeline/tests/test_build_hub_edges.py -k geometr -q`
Expected: FAIL — offsets differ and `len(geometry) == 4`

- [ ] **Step 3: Implement**

```python
    seen_geoms = {}   # blake2b of the packed coordinate run -> geom_offset
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
        # No collision re-check against the stored run: blake2b-128 over ~2e4 runs has a
        # collision probability around 1e-30. This is deliberate, not an oversight.
```

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest pipeline/tests -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/phases/graph_building/build_hub_edges.py pipeline/tests/test_build_hub_edges.py
git commit -m "feat(pipeline): share geometry between variants with identical paths"
```

---

# Phase 5 — Snapping honesty

### Task 17: Price the snap gap into distance, ascent and descent

**Files:**
- Modify: `pipeline/phases/graph_building/build_hub_edges.py` (`SnapResult`,
  `snap_hub_to_subgraph`, record construction in `compute_hub_edges_for_cell`)
- Test: `pipeline/tests/test_build_hub_edges.py`

**Interfaces:**
- Produces: `SnapResult` gains `gap_m: float` and `gap_dz_m: float`; every record's `distance_m`,
  `ascent_m`, `descent_m` include both ends' gaps, and `snap_m` is the distance total.

**Why:** §E3 — `_path_for` sums only routed edges, so today the hub-to-snap gap contributes **zero**
distance, ascent and time at *both ends of every edge*. `SnapResult` already knows the gap distance;
this is a bookkeeping omission, not a missing measurement.

- [ ] **Step 1: Write the failing tests**

```python
def test_snap_result_reports_the_gap():
    result = snap_hub_to_subgraph(subgraph, hub_lon=0.0, hub_lat=0.0005, max_snap_m=100.0)
    assert result.gap_m == pytest.approx(55.6, rel=0.05)


def test_record_distance_includes_both_snap_gaps():
    r = compute_hub_edges_for_cell(...)[0]   # both huts offset from the trail
    assert r["snap_m"] > 0
    assert r["distance_m"] == pytest.approx(routed_distance + r["snap_m"])


def test_snap_gap_climb_lands_in_ascent_not_only_distance():
    # a hut 40 m above its snap point adds 40 m of ascent to every edge starting there
    r = compute_hub_edges_for_cell(...)[0]
    assert r["ascent_m"] >= 40.0
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest pipeline/tests/test_build_hub_edges.py -k snap -q`
Expected: FAIL — `AttributeError: 'SnapResult' object has no attribute 'gap_m'`

- [ ] **Step 3: Implement**

`snap_hub_to_subgraph` stores the winning gap (it already computes `d` in the mid-chain branch and
`node_dists[best_i]` in the node branch) plus the elevation delta between the hub and the snap point,
read from `node_ele.npy`/`interior_ele.npy` (Task 8). `compute_hub_edges_for_cell` adds both ends'
`gap_m` to `distance_m`, the positive `gap_dz_m` to `ascent_m` and the negative magnitude to
`descent_m`, and sets `snap_m = gap_m(src) + gap_m(tgt)`.

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest pipeline/tests -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/phases/graph_building/build_hub_edges.py pipeline/tests/test_build_hub_edges.py
git commit -m "fix(pipeline): price the hub-to-trail snap gap into every edge"
```

### Task 18: Vertical snap validation and `unsnapped_huts.json`

**Files:**
- Modify: `pipeline/phases/graph_building/build_hub_edges.py` (`snap_hub_to_subgraph`, `_run_cell`,
  `__main__`)
- Modify: `pipeline/pipeline.config.json` (`graph.maxSnapAscentM: 25`)
- Modify: `pipeline/dodo.py` (`--max-snap-ascent-m` param, `unsnapped_huts.json` target)
- Test: `pipeline/tests/test_build_hub_edges.py`

**Interfaces:**
- Produces: `snap_hub_to_subgraph(..., max_snap_ascent_m, hub_ele_m)` returning `SnapResult` **or**
  `SnapRejection(hub_id, name, gap_m, dz_m, reason)` with
  `reason ∈ {"no_trail_data", "gap_too_far", "vertical_offset"}`; `write_unsnapped_report(path, rejections)`
  emitting `data/osm/unsnapped_huts.json`.

**Why a vertical cap, and why `maxSnapM` is not touched** (§E3 measurements): horizontal gaps are
0-10 m for 351 huts, 10-25 m for 361, 25-50 m for 33, 50-100 m for 6, >100 m for 25 — 91.8% within
25 m. Raising `maxSnapM` to 200 m recovers **one** hut; tightening it to 50 m would delete **six
legitimate** huts. So it is not binding and must stay at 100. The failure that matters is a hut
joined to a trail it cannot reach: vertical offsets are <5 m for 656 huts, 5-10 m for 51, 10-20 m for
12, >20 m for 5, mean 3.0 m — and the decisive case, **Watzmann-Ostwand-Biwak (18 m gap, 17 m above
the trail)**, passes `maxSnapM: 100` comfortably. A horizontal threshold cannot separate "18 m across
a terrace" from "18 m up a wall" at any setting. A slope rule is the wrong shape too: Staufner Haus
and St. Pöltner Hütte snap at slope 0.55-0.57 and are ordinary huts on steep ground.

**Why the report is mandatory:** `snap_hub_to_subgraph` returns `None` today and the hub silently
vanishes — no count, no artifact — and `snap_stats.json` already shows **205 of 956 hubs unsnapped**.
A vertical cap grows that invisible set.

- [ ] **Step 1: Write the failing tests**

```python
def test_vertical_offset_rejects_a_wall_bivouac():
    # Watzmann-Ostwand-Biwak shape: 18 m gap (well inside maxSnapM 100), 17 m above the trail
    result = snap_hub_to_subgraph(subgraph, hub_lon=..., hub_lat=..., max_snap_m=100.0,
                                  max_snap_ascent_m=25.0, hub_ele_m=trail_ele + 17.0)
    assert isinstance(result, SnapRejection)
    assert result.reason == "vertical_offset"


def test_ordinary_hut_on_steep_ground_still_snaps():
    # Staufner Haus shape: slope 0.55, but only ~8 m of vertical offset
    result = snap_hub_to_subgraph(subgraph, ..., max_snap_ascent_m=25.0, hub_ele_m=trail_ele + 8.0)
    assert isinstance(result, SnapResult)


def test_far_hub_is_rejected_with_the_distance_reason():
    result = snap_hub_to_subgraph(sparse_subgraph, ..., max_snap_m=10.0, max_snap_ascent_m=25.0)
    assert result.reason == "gap_too_far"


def test_unsnapped_report_records_every_rejection(tmp_path):
    write_unsnapped_report(tmp_path / "unsnapped_huts.json", [
        SnapRejection(hub_id=7, name="Schuesselkar-Biwak", gap_m=250.0, dz_m=258.0,
                      reason="vertical_offset"),
    ])
    got = json.loads((tmp_path / "unsnapped_huts.json").read_text(encoding="utf-8"))
    assert got[0]["reason"] == "vertical_offset"
    assert got[0]["dz_m"] == 258.0
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest pipeline/tests/test_build_hub_edges.py -k snap -q`
Expected: FAIL — `NameError: name 'SnapRejection' is not defined`

- [ ] **Step 3: Implement**

Add the `SnapRejection` dataclass; apply the vertical check after the winning candidate is chosen in
**both** the node and mid-chain branches. Workers return their rejections alongside `records` in the
`_run_cell` result dict; `__main__` merges them, writes `unsnapped_huts.json` sorted by `dz_m`
descending, and prints the counts by reason in the final summary. Add `--max-snap-ascent-m` to the
script's argparse and to `dodo.py`'s `task_build_hub_edges` params (so a retune reruns through the
existing `config_changed` check) plus `unsnapped_huts.json` to its targets and to `PUBLIC_FILES`.

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest pipeline/tests -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/phases/graph_building/build_hub_edges.py pipeline/dodo.py pipeline/pipeline.config.json pipeline/tests/test_build_hub_edges.py
git commit -m "feat(pipeline): validate snaps vertically and report every rejection"
```

---

# Phase 6 — Shipped payload

### Task 19: Widen start-point fields to carry `access` and `motor_vehicle`

**Files:**
- Modify: `pipeline/phases/downloads/fetch_stations_parking.py:39` (`keep_fields`)
- Modify: `pipeline/phases/preprocessing/filter_start_points.py` (carry the fields into
  `start_points_id_table.json`)
- Test: `pipeline/tests/test_filter_start_points.py`

**Interfaces:**
- Produces: start points carrying `access`, `motor_vehicle` and `barrier` through to
  `start_points_id_table.json`, with `None` (not absent) where the tag is missing. Consumed by Task 20.

**Why now:** `data/analysis/payload_sizing.json` names this a **build prerequisite** — `keep_fields`
is `["name", "capacity", "fee", "access"]` and `filter_start_points.py` drops even those, so
`motor_vehicle` is not merely unmeasured, it is never fetched. §E1's hard-drop rule cannot be built
without it. Measured `access`: 21,058 unknown, 3,293 `private`, 2,973 `yes`, 2,251 `customers`,
154 `no`.

- [ ] **Step 1: Write the failing tests**

```python
def test_start_points_retain_access_tags():
    table = build_id_table([
        {"type": "parking", "id": 1, "lon": 11.0, "lat": 47.0,
         "properties": {"name": "P", "access": "private", "motor_vehicle": "no"}},
    ])
    assert table["parking"]["1"]["access"] == "private"
    assert table["parking"]["1"]["motor_vehicle"] == "no"


def test_missing_access_becomes_none_not_absent():
    # spec E1: absent tag -> keep but mark access_unknown. Dropping the key makes "unknown"
    # and "open" indistinguishable downstream.
    table = build_id_table([{"type": "parking", "id": 2, "lon": 11.0, "lat": 47.0,
                            "properties": {"name": "Q"}}])
    assert table["parking"]["2"]["access"] is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest pipeline/tests/test_filter_start_points.py -q`
Expected: FAIL — `KeyError: 'access'`

- [ ] **Step 3: Implement**

Parking `keep_fields` becomes `["name", "capacity", "fee", "access", "motor_vehicle", "barrier"]`
(`barrier=gate`/`lift_gate` is how gated forest roads present); `filter_start_points.py` carries them
into the id table instead of reducing to coordinates.

- [ ] **Step 4: Run the tests, then refresh the two cheap inputs** **[ASK FIRST — `fetch_stations_parking` re-streams the raw extracts]**

```bash
python -m pytest pipeline/tests -q
doit fetch_stations_parking filter_start_points
```

- [ ] **Step 5: Commit**

```bash
git add pipeline/phases/downloads/fetch_stations_parking.py pipeline/phases/preprocessing/filter_start_points.py pipeline/tests/test_filter_start_points.py
git commit -m "feat(pipeline): keep access/motor_vehicle/barrier tags on start points"
```

### Task 20: Approach/exit table and loop-closure reverse index

**Files:**
- Create: `pipeline/phases/postprocessing/build_approach_table.py`
- Modify: `pipeline/dodo.py` (`task_build_approach_table`, `PUBLIC_FILES`)
- Test: `pipeline/tests/test_build_approach_table.py`

**Interfaces:**
- Consumes: `start_edges/records.npy` (Phases 4-5), `start_points_id_table.json` (Task 19),
  `lib.speed.din_duration_h` (Task 6).
- Produces: `select_approaches(records, id_table, k) -> list[dict]`,
  `build_tables(records, id_table, k) -> (approaches, index)`, and the files
  `data/osm/approaches.bin` + `approaches.json` (column manifest), holding the k-best-per-hut table
  with `access`/`source_type` columns and the reverse index keyed both `hut → starts` and
  `start → huts`.

**Why a reduction rather than shipping `start_edges/`:** 27,261 parkings and 3,025 stations exist and
`start_edges/records.npy` holds 92,426 records (82,251 parking→hut, 10,175 station→hut) — neither is
shippable or seedable. k=3 per hut is 1173 × 3 × 2 ≈ 7k rows, <100 KB: a ~13× reduction that removes
start-point count from the client's search complexity entirely.

**Why not "k fastest":** the fastest edge into a hut is systematically from the highest, most remote
trailhead (forest road, toll road, summer-only pass parking), while a driver wants the valley
trailhead they can actually reach.

**Why the reverse index ships at all:** the client's `car` mode requires exit start-point == entry
start-point, and the k≈3 tables of the first and last hut essentially never share a start id — a
post-filter would annihilate the result set. Size is bounded above by the whole `start_edges/` table
(≤92,426 rows, ~1.9 MB raw at 20 B/row), so it cannot break the payload budget.

- [ ] **Step 1: Write the failing tests**

```python
def test_restricted_access_start_points_are_dropped():
    rows = select_approaches(records, id_table={"parking": {"1": {"access": "private"}}}, k=3)
    assert all(r["start_id"] != 1 for r in rows)


def test_absent_access_is_kept_and_marked_unknown():
    rows = select_approaches(records, id_table={"parking": {"1": {"access": None}}}, k=3)
    assert rows[0]["access_unknown"] is True


def test_gated_forest_road_is_dropped():
    rows = select_approaches(records, id_table={"parking": {"1": {"barrier": "gate"}}}, k=3)
    assert all(r["start_id"] != 1 for r in rows)


def test_k_best_never_fills_every_slot_from_one_source_type():
    # spec E1: the client's car/transit split needs something to work with
    rows = select_approaches(records_with_both_sources, id_table=..., k=3)
    types = {r["source_type"] for r in rows if r["hut_id"] == 7}
    assert binfmt.TYPE_PARKING in types and binfmt.TYPE_STATION in types


def test_no_approach_time_cap_is_applied():
    # spec E1: maxApproachTime is deleted. An approach is a full leg, bounded by the same
    # pipeline range cap as any hut-hut edge and filtered client-side by the same maxLegTime.
    import inspect
    src = inspect.getsource(select_approaches)
    assert "approach_time" not in src and "maxApproachTime" not in src


def test_reverse_index_covers_every_retained_start_point():
    approaches, index = build_tables(records, id_table, k=3)
    for start_id in {r["start_id"] for r in approaches}:
        assert len(index["start_to_huts"][start_id]) >= 1


def test_reverse_index_is_bounded_by_the_start_edge_table():
    approaches, index = build_tables(records, id_table, k=3)
    assert sum(len(v) for v in index["start_to_huts"].values()) <= len(records)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest pipeline/tests/test_build_approach_table.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`select_approaches`: hard-drop `access ∈ {private, no}`, `motor_vehicle ∈ {private, no}` and
`barrier ∈ {gate, lift_gate}` unless an explicit `access ∈ {yes, permissive}` overrides; mark absent
tags `access_unknown` and keep them; rank survivors by `din_duration_h` over the record's aggregates
(so the shipped order matches what the client displays); take k, reserving one slot per source type
where both exist. Emit `access` and `source_type` as columns.

`build_tables` collects `S` = start points appearing in any retained approach and emits every
`start_edges` record with `start_id ∈ S`, keyed both ways. Pack narrowed (`u2` hut ids, `u4` start
ids, `f4` metrics) and print raw + gzipped sizes in the final line — open question 3 wants the real
number, not the bound. Exit edges are these same records read backwards (§D4); nothing extra is
stored.

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest pipeline/tests -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/phases/postprocessing/build_approach_table.py pipeline/dodo.py pipeline/tests/test_build_approach_table.py
git commit -m "feat(pipeline): approach/exit table with loop-closure reverse index"
```

### Task 21: Pack and ship the hut-edge payload

**Files:**
- Create: `pipeline/phases/postprocessing/build_edge_payload.py`
- Modify: `pipeline/dodo.py` (`task_build_edge_payload`, `PUBLIC_FILES`)
- Test: `pipeline/tests/test_build_edge_payload.py`

**Interfaces:**
- Consumes: `hut_edges/records.npy` (Phase 4), `binfmt.RECORD_DTYPE` (Task 12).
- Produces: `pack_edges(records, hut_ids) -> (payload_bytes, manifest)` and the files
  `data/osm/hut-edge-payload.bin` + `hut-edge-payload.json` (column names, dtypes, byte offsets, row
  count, variant list, hut id table), copied to `huts/public/data/` by `copy_public_data`.

**Sizing, measured not assumed** (`data/analysis/payload_sizing.json`): 3 variants × 6,067 edges ×
13 columns = 693 KB raw, **43.4 KB gzipped**; a byte-shuffle filter made it *worse* (46.4 KB), so do
not add one. Both figures are floors — four columns were zeros and the variant copies identical — but
even at 5× this is far under any budget, which is why **quantisation is out of scope**: §F's caveat
says measure after packing, and the measurement says the straightforward packing is fine.

**Geometry is not shipped** — it stays in `hut-edges.pmtiles`, fetched lazily only for tours the user
opens, which is already how `GraphPage.jsx` renders edges.

- [ ] **Step 1: Write the failing tests**

```python
def test_hut_ids_narrow_to_u2():
    _, manifest = pack_edges(records, hut_ids)
    assert manifest["columns"]["from_id"]["dtype"] == "u2"


def test_manifest_round_trips_every_column():
    payload, manifest = pack_edges(records, hut_ids)
    for name, spec in manifest["columns"].items():
        col = np.frombuffer(payload, dtype=spec["dtype"], count=manifest["rows"],
                            offset=spec["offset"])
        assert len(col) == manifest["rows"], name


def test_columns_are_contiguous_not_interleaved():
    # per-column layout is what makes the measured 43.4 KB gzip figure hold
    payload, manifest = pack_edges(records, hut_ids)
    offsets = sorted(s["offset"] for s in manifest["columns"].values())
    assert offsets == sorted(set(offsets))
    assert offsets[0] == 0


def test_no_duration_column_is_shipped():
    # spec D3 - the client computes DIN both ways at load
    _, manifest = pack_edges(records, hut_ids)
    assert not any("time" in c or "duration" in c for c in manifest["columns"])


def test_geometry_offsets_are_not_in_the_payload():
    _, manifest = pack_edges(records, hut_ids)
    assert "geom_offset" not in manifest["columns"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest pipeline/tests/test_build_edge_payload.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

Column set exactly §F's: `from_id, to_id, variant, distance_m, ascent_m, descent_m, max_ele_m,
sac_rank, via_ferrata, road_m, ungraded_m, inferred_m, snap_m`, laid out contiguously per column.
Print the raw and gzipped size in the final line so every rebuild re-measures §F instead of trusting
this plan's number.

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest pipeline/tests -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/phases/postprocessing/build_edge_payload.py pipeline/dodo.py pipeline/tests/test_build_edge_payload.py
git commit -m "feat(pipeline): pack hut edge payload for the client"
```

---

# Phase 7 — Invalidation, docs, and the rebuild

### Task 22: Manifest-based invalidation

**Files:**
- Modify: `pipeline/phases/graph_building/build_base_graph.py` (manifest in `pack_and_write`)
- Modify: `pipeline/phases/graph_building/build_hub_edges.py` (`__main__` writes
  `hut_edges/manifest.json`)
- Modify: `pipeline/dodo.py` (`_base_graph_fingerprint`, `_hub_edges_fingerprint`, both tasks'
  `uptodate`)
- Test: `pipeline/tests/test_dodo_wiring.py`

**Interfaces:**
- Produces: `base_graph/manifest.json` gaining `schema_version` (int) and `cost_model`
  (`{"model": "pointwise_tobler", "v0":…, "k":…, "s0":…, "smoothing_kernel_m":…}`);
  `hut_edges/manifest.json` gaining `schema_version` and `variants`; both fingerprints in the tasks'
  `uptodate` checks.

**Why:** `task_build_base_graph` invalidates only on `trails.osm.pbf` and `--tile-size-km`, and the
manifest records nothing about *how* the arrays were computed — so none of Phases 1-4 would trigger a
rebuild on its own. Symmetrically, without `variants` in `build_hub_edges`'s check, a three-row
rebuild looks up-to-date after a one-row run.

- [ ] **Step 1: Write the failing tests**

```python
def test_base_graph_fingerprint_tracks_the_cost_model():
    cfg = {"graph": {"speedModel": {"v0": 6.0, "k": 3.5, "s0": 0.05}}, "dem": {"smoothingKernelM": 30}}
    other = {"graph": {"speedModel": {"v0": 5.0, "k": 3.5, "s0": 0.05}}, "dem": {"smoothingKernelM": 30}}
    assert dodo._base_graph_fingerprint(cfg, {}) != dodo._base_graph_fingerprint(other, {})


def test_hub_edges_fingerprint_tracks_the_variant_grid():
    one = {"graph": {"variants": ["FAST_ANY"]}}
    three = {"graph": {"variants": ["FAST_ANY", "FAST_T2", "FAST_T3"]}}
    assert dodo._hub_edges_fingerprint(one, {}) != dodo._hub_edges_fingerprint(three, {})


def test_schema_version_is_part_of_both_fingerprints():
    assert "schema_version" in dodo._base_graph_fingerprint({"graph": {"speedModel": {}}, "dem": {}}, {})
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest pipeline/tests/test_dodo_wiring.py -q`
Expected: FAIL — `AttributeError: module 'dodo' has no attribute '_base_graph_fingerprint'`

- [ ] **Step 3: Implement**

```python
SCHEMA_VERSION = 2   # bump on any EDGE_DTYPE / RECORD_DTYPE change


def _base_graph_fingerprint(config, options):
    return json.dumps({
        "schema_version": SCHEMA_VERSION,
        "cost_model": {"model": "pointwise_tobler",
                       **config["graph"].get("speedModel", {}),
                       "smoothing_kernel_m": config["dem"].get("smoothingKernelM")},
        "options": options,
    }, sort_keys=True)


def _hub_edges_fingerprint(config, options):
    return json.dumps({
        "schema_version": SCHEMA_VERSION,
        "variants": config["graph"]["variants"],
        "options": options,
    }, sort_keys=True)
```

Both tasks' `uptodate` becomes `[lambda task, values: config_changed(_fingerprint(CONFIG, task.options))(task, values)]`,
and the same dicts are written into the two manifests so a human can see what a cached directory was
built from.

**Say this in the task docstring:** adding `cost_model` to the freshness check *guarantees* the next
`doit` invocation is the multi-hour job (`.claude/CLAUDE.md`). That is intended — a silently-stale
graph under a changed cost model is worse — but it must not be a surprise.

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest pipeline/tests -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/phases pipeline/dodo.py pipeline/tests/test_dodo_wiring.py
git commit -m "feat(pipeline): invalidate on cost model and variant grid"
```

### Task 23: Documentation

**Files:**
- Modify: `pipeline/CLAUDE.md` (V2 status paragraph — the variant hook is now used; the StepTimer
  table's `add_elevation` row; the `read_dem_window` anecdote, which now describes a deleted script)
- Modify: `pipeline/phases/README.md`, `pipeline/phases/elevation/README.md`,
  `pipeline/phases/graph_building/README.md`, `pipeline/phases/postprocessing/README.md`
- Modify: `pipeline/README.md` (reproduction steps: the new task order)
- Modify: `.claude/CLAUDE.md` (outputs list gains `hut-edge-payload.*`, `approaches.*`,
  `unsnapped_huts.json`)
- Create: `docs/tour-suggestion-payload.md`

- [ ] **Step 1: Write the client-facing payload contract**

`docs/tour-suggestion-payload.md` must state, because nothing else will:

- every shipped file, its columns and dtypes;
- **that duration is not shipped**, plus the exact DIN formula the client must apply (§A2/§D3);
- **the reverse-traversal contract** (§D4): `distance_m`, `road_m`, `sac_rank`, `via_ferrata`,
  `max_ele_m`, `ungraded_m`, `inferred_m` unchanged; `ascent_m ↔ descent_m` swapped; duration
  recomputed; geometry and profile reversed for display;
- **the known approximation**: under the pointwise cost, best A→B is no longer provably best B→A
  (one record per unordered pair, accepted for iteration 1) — cite the probe's measured direction
  spread rather than calling it unknown;
- that `ungraded_m == 0` holds by construction on every constrained row, and what claim that
  supports ("every metre of this route is graded T3 or easier", with no hedge);
- that `max_ele_m` is a per-edge filter, so an edge topping a 2800 m col is *deleted* under a 2500 m
  cap even where a lower path exists (§C9);
- that difficulty resolution between routed thresholds is approximate — exact only at T2/T3.

- [ ] **Step 2: Update the pipeline docs**

Each `phases/*/README.md` gains the new scripts and loses `add_elevation.py`. `pipeline/CLAUDE.md`'s
"no second variant is computed yet" becomes the variant grid as built, with the per-variant timings
from Task 24's run.

- [ ] **Step 3: Verify nothing still references deleted things**

```bash
grep -rn "add_elevation\|roadPenaltyFactor\|eleNoiseThresholdM\|VARIANT_SHORTEST" --include=*.md --include=*.py --include=*.json . | grep -v docs/superpowers/
```

Expected: no hits outside the spec/plan/findings docs, which describe them historically.

- [ ] **Step 4: Commit**

```bash
git add pipeline/CLAUDE.md pipeline/README.md pipeline/phases .claude/CLAUDE.md docs/tour-suggestion-payload.md
git commit -m "docs: pipeline task graph rewrite and client payload contract"
```

### Task 24: The rebuild, and the measurements it makes free

**Files:**
- Modify: `docs/superpowers/specs/2026-08-22-tour-suggestion-findings.md`

- [ ] **Step 1: Present the expected cost and get confirmation** **[ASK FIRST]**

| task | expected |
|---|---|
| `build_base_graph` | ~18 min — should be skipped unless the classifier changed since Task 9 |
| `add_base_elevation` | as measured in Task 9 |
| `build_hub_edges` | **hours × the variant count** — estimate from the probe's per-cell wall-time ratios (Task 11); v1's `pass2_paths` was 7,630 s ≈ 2.1 h for a single variant |
| `build_profiles` | seconds |
| `build_approach_table`, `build_edge_payload` | seconds |
| `build_*_tiles` | ~140 s each |
| `copy_public_data` | ~3 s |

Softeners worth stating so the estimate is not read as 3 × 2.1 h: constrained rows route over
*smaller* edge subsets, the unconstrained `distances()` pass is reused as a prefilter, the shared
per-cell work (subgraph load, spatial index, snap loop) is paid once, and `build_hub_edges` is
already parallelised per grid cell.

- [ ] **Step 2: Run** **[ASK FIRST]**

```bash
doit
```

- [ ] **Step 3: Verify the output invariants**

```bash
python -c "
import numpy as np, json
r = np.load('data/osm/hut_edges/records.npy', mmap_mode='r')
print('records', len(r), 'variants', np.unique(r['variant']))
for v in np.unique(r['variant']):
    m = r['variant'] == v
    print(int(v), 'rows', int(m.sum()), 'max ungraded_m', float(np.asarray(r['ungraded_m'])[m].max()))
print('unsnapped', len(json.load(open('data/osm/unsnapped_huts.json', encoding='utf-8'))))
"
```

Expected: every constrained variant reports `max ungraded_m == 0.0` — that is the guarantee §C4
exists for, and any non-zero value means the filter leaked. Constrained rows will have *fewer* rows
than `FAST_ANY`; that gap is the deletion the rows exist to substitute away from, and its size
belongs in the findings doc next to the 23%/39% pre-measurements.

- [ ] **Step 4: Re-run the post-rebuild measurements** (free now; both feed the `ROAD_*` decision)

```bash
python pipeline/analysis/road_share.py
python pipeline/analysis/payload_sizing.py
```

Compare against the pre-rebuild figures already in the findings doc — hut edges 9.7% aggregate, start
edges 19.1%, both measured with `roadPenaltyFactor: 1.3` active. The time cost both removes that
penalty and rewards roads for being fast, so the new figures can only be higher. Record the delta;
that delta *is* the size of the regression §Risk 3 flags as unknown.

- [ ] **Step 5: Settle open question 1 in writing**

Decide `ROAD_*` from the post-rebuild road share plus the probe's substitution rate for that cell. If
built, it is a **multiplicative** penalty on road-tagged segments' time (factor ~3-5) added as a new
objective column — never a revived `roadPenaltyFactor`, which would put a penalty back inside a
distance the user sees. If not built, write down why, so the next reader does not re-open it from
prose.

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/specs/2026-08-22-tour-suggestion-findings.md huts/public/data
git commit -m "feat: rebuild hut graph on the time cost with variant rows"
```

---

## Deferred (explicitly not in this plan)

From the spec's non-goals and scope boundary, recorded so they are not silently absorbed:

- Any actual backend. Static files + in-browser computation only.
- Bed availability as a search input — the OHRS API is per-hut, per-date, one request each, so it
  cannot be called across a candidate set. A post-filter on returned tours, designed separately.
- Multi-objective Pareto results; geographic scope past AT+Bayern.
- `ASC_*` (the speed model already prices climb steeply) and `ROAD_*` (only on Task 24's evidence).
- Direction-correct routing — one record per unordered pair stands for iteration 1; fixing it doubles
  the build phase. The probe measures the error; the payload contract documents it.
- Every client-side concern: leg budgets, leg counts, day/night vocabulary, transport mode, objective
  selection, diversity, relaxation suggestions, beam `K`, the leg-time band, `legAscentCap`, and
  whether exact DFS suffices.
