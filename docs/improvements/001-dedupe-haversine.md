# Plan 001: Deduplicate the haversine distance formula into `lib/geo.py`

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 3e59f51..HEAD -- pipeline/lib pipeline/phases pipeline/analysis`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: tech-debt
- **Planned at**: commit `3e59f51`, 2026-08-31

## Why this matters

The exact same haversine great-circle-distance formula (Earth radius `6_371_000.0` m, the
standard `2r·asin(√a)` form) is independently copy-pasted in **7 files**, in three shapes (scalar,
one-fixed-point-vs-array, and paired-arrays):

- `pipeline/lib/hub_snap.py` — `_haversine_m`, `_haversine_m_vec`, `_haversine_m_vec_pairs`
- `pipeline/lib/tour_geometry.py` — `_haversine_m`
- `pipeline/lib/edge_split.py` — `_haversine_m`
- `pipeline/phases/graph_building/build_base_graph.py` — `haversine_m_vec`
- `pipeline/phases/graph_building/match_tour_edges.py` — `_leg_segment_m`
- `pipeline/phases/elevation/build_profiles.py` — `_haversine_m_vec_pairs`
- `pipeline/analysis/reconstruct_raw_graph.py` — `_haversine_m_vec` (whose own comment says: "same
  formula and earth radius as build_base_graph.py's haversine_m_vec, so reconstructed segment
  distances sum back to the persisted chain distances")

That last comment is the tell: the codebase already knows these must never drift apart, and is
currently relying on a human remembering to edit 7 places in lockstep instead of one shared
function. A future precision fix (e.g. an ellipsoidal model) or a units bug fix would have to be
applied 7 times by hand, and a missed one would silently desync distance math between, say,
`build_base_graph.py` and the `reconstruct_raw_graph.py` analysis script that's supposed to match
it exactly.

`pipeline/lib/geo.py` already exists as the shared geometry module (currently: `hut_points`,
`circle_polygon`, `hub_range_polygon`) and is imported by multiple phases — it's the natural home.

## Current state

All 7 definitions are byte-identical modulo `math`/`np` prefix and argument names. The three
shapes:

**Scalar** (`lib/hub_snap.py:28-34`, `lib/tour_geometry.py:10-16`, `lib/edge_split.py:12-18`,
`phases/graph_building/match_tour_edges.py:163-169` as `_leg_segment_m(a, b)` — same math, just
takes two `(lon, lat)` tuples instead of 4 scalars):

```python
def _haversine_m(lon1, lat1, lon2, lat2):
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
```

**One fixed point vs. a numpy array** (`lib/hub_snap.py:37-44`, docstring: "used in
snap_hub_to_subgraph's node scan, the hot path"):

```python
def _haversine_m_vec(lon1: float, lat1: float, lon2: np.ndarray, lat2: np.ndarray) -> np.ndarray:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + math.cos(p1) * np.cos(p2) * np.sin(dlambda / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))
```

**Fully paired arrays** (`lib/hub_snap.py:49-58` as `_haversine_m_vec_pairs`,
`phases/graph_building/build_base_graph.py:31-37` as `haversine_m_vec` (no leading underscore, no
type hints), `phases/elevation/build_profiles.py:101-107` as `_haversine_m_vec_pairs`,
`analysis/reconstruct_raw_graph.py:57-64` as `_haversine_m_vec` with the "must match
build_base_graph.py" comment):

```python
def _haversine_m_vec_pairs(lon1: np.ndarray, lat1: np.ndarray,
                            lon2: np.ndarray, lat2: np.ndarray) -> np.ndarray:
    r = 6_371_000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlambda / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))
```

`pipeline/lib/geo.py` today (full file, 82 lines) holds `hut_points`, `HUB_RANGE_SAFETY_MARGIN`,
`circle_polygon`, `hub_range_polygon` — geometry helpers shared across phases, imported as
`from lib.geo import ...`. Its module docstring describes it as hub-range/DEM-coverage geometry;
this addition slightly broadens its scope to "shared geometry helpers" generally, which is
consistent with how it's already used (imported by `compute_hub_range.py` and
`dem_providers/composite.py`, two otherwise-unrelated phases).

Repo convention for this kind of promotion: see commit `0dea278` ("lib: promote OA fetch/parse
helpers out of the spike into lib/oa_geometry.py") and `e468b1f`/`8c3dfbe` ("graph_building:
extract fold_endpoint_snaps/write_edge_records into lib/edge_output.py") — extract to `lib/`,
re-import at every call site, delete the local copy, no behavior change.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Run pipeline tests | `pixi run pytest -q` (from `pipeline/`) | `326 passed` (or more, if plan 007/008 landed first) |
| Run one test file | `pixi run pytest tests/test_hub_snap.py tests/test_edge_split.py -q` | all pass |
| Grep for leftover local defs | `grep -rn "6_371_000" pipeline/` | only `pipeline/lib/geo.py` remains |

(Run all commands from `pipeline/`. `pixi` must already be installed and `pixi install` already
run — see `pipeline/README.md` "Setup" if not.)

## Scope

**In scope** (the only files you should modify):
- `pipeline/lib/geo.py` — add the three functions
- `pipeline/lib/hub_snap.py` — remove `_haversine_m`/`_haversine_m_vec`/`_haversine_m_vec_pairs`, import from `lib.geo`, update call sites
- `pipeline/lib/tour_geometry.py` — remove `_haversine_m`, import, update call sites
- `pipeline/lib/edge_split.py` — remove `_haversine_m`, import, update call sites
- `pipeline/phases/graph_building/build_base_graph.py` — remove `haversine_m_vec`, import as `haversine_m_vec` (or call the shared name directly — see Step 1 naming), update call sites
- `pipeline/phases/graph_building/match_tour_edges.py` — remove `_leg_segment_m`, replace its 2-tuple-argument calls with the shared scalar function (unpacking the tuples), update call sites
- `pipeline/phases/elevation/build_profiles.py` — remove `_haversine_m_vec_pairs`, import, update call sites
- `pipeline/analysis/reconstruct_raw_graph.py` — remove `_haversine_m_vec`, import, update call sites (keep its explanatory comment, moved to note it now imports the shared implementation instead of duplicating it)

**Out of scope**:
- Do not change the numerical formula, Earth radius constant, or output values in any way — this
  is a pure dedup, verified by identical test results before/after.
- Do not touch `pipeline/lib/grid.py`'s `KM_PER_DEG_LAT` (a different, unrelated flat-earth
  constant used for local metric projection, not haversine) even though it's imported alongside
  haversine calls in some of these files.
- Do not touch anything under `pipeline/tours/`, `data/`, or `huts/`.

## Git workflow

- Branch: stay on the current branch (`feat/official-tours-integration`) unless the operator says
  otherwise, or create `improve/001-dedupe-haversine` if the operator prefers isolation — ask if
  unsure rather than assuming.
- Commit message style observed in `git log`: lowercase, `<module-or-scope>: <imperative
  description>`, e.g. `lib: promote OA fetch/parse helpers out of the spike into lib/oa_geometry.py`.
  Use something like `lib: dedupe haversine formula into lib/geo.py`.
- One commit for the whole plan is fine (it's a single mechanical change); split per-file only if
  you prefer smaller reviewable diffs.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add the three shared functions to `lib/geo.py`

Add, using the *exact* existing bodies (copy verbatim, only renaming to drop the leading
underscore since this is now public shared API):

```python
def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance in meters between two (lon, lat) points, in degrees."""
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def haversine_m_vec(lon1: float, lat1: float, lon2: np.ndarray, lat2: np.ndarray) -> np.ndarray:
    """Same formula as haversine_m, vectorized against one fixed point vs. an array of points -
    the hot-path shape used when scanning many candidate points against one query point."""
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + math.cos(p1) * np.cos(p2) * np.sin(dlambda / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def haversine_m_vec_pairs(lon1: np.ndarray, lat1: np.ndarray,
                           lon2: np.ndarray, lat2: np.ndarray) -> np.ndarray:
    """Fully-vectorized haversine over paired arrays (both endpoints vary per element)."""
    r = 6_371_000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlambda / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))
```

Add `import numpy as np` to `lib/geo.py`'s imports (it currently only imports `json`, `math`,
`shapely`). Keep `math` (already imported, still used by `circle_polygon`).

**Verify**: `python -c "import sys; sys.path.insert(0, 'pipeline'); from lib.geo import haversine_m, haversine_m_vec, haversine_m_vec_pairs; print(haversine_m(11.0, 47.0, 11.01, 47.01))"` (run from repo root, using the pixi env's python: `pixi run --manifest-path pipeline/pixi.toml python -c "..."`) → prints a float around `1350` (meters), no error.

### Step 2: Replace each duplicate with an import, one file at a time

For each of the 7 files listed in Scope, in order:

1. Add `from lib.geo import haversine_m[, haversine_m_vec][, haversine_m_vec_pairs]` (only the
   names that file actually uses) to its imports.
2. Delete the local `_haversine_m*`/`haversine_m_vec` function definition.
3. Update every call site in that file to call the imported name instead of the deleted local one.
   - `match_tour_edges.py`'s `_leg_segment_m(a, b)` took two `(lon, lat)` tuples; its call site
     (`_leg_segment_m(leg_points[i], leg_points[i + 1])`) must become
     `haversine_m(leg_points[i][0], leg_points[i][1], leg_points[i + 1][0], leg_points[i + 1][1])`
     — grep `_leg_segment_m` in that file first to find every call site, not just the one shown in
     this plan's excerpts.
   - `build_base_graph.py`'s local was already named `haversine_m_vec` with no underscore — after
     this change the name is imported instead of defined locally; no call-site renaming needed
     there beyond adding the import and deleting the local def.
4. Run the file's own test file (see table below) before moving to the next file.

| File | Test file to run after this file's change |
|---|---|
| `lib/hub_snap.py` | `pixi run pytest tests/test_hub_snap.py -q` |
| `lib/tour_geometry.py` | `pixi run pytest tests/test_tour_geometry.py -q` |
| `lib/edge_split.py` | `pixi run pytest tests/test_edge_split.py -q` |
| `phases/graph_building/build_base_graph.py` | `pixi run pytest tests/test_build_base_graph.py -q` |
| `phases/graph_building/match_tour_edges.py` | `pixi run pytest tests/test_match_tour_edges.py -q` |
| `phases/elevation/build_profiles.py` | `pixi run pytest tests/test_build_profiles.py -q` |
| `analysis/reconstruct_raw_graph.py` | `pixi run pytest tests/test_reconstruct_raw_graph.py -q` |

**Verify** (after each file): the listed test file passes with the same pass count as before your
change (all of these tests exercise distance math indirectly, so a formula transcription mistake
will show up as a numeric assertion failure, not an import error).

## Test plan

No new test cases are needed — this is a pure refactor and the existing per-file test suites
(`test_hub_snap.py`, `test_tour_geometry.py`, `test_edge_split.py`, `test_build_base_graph.py`,
`test_match_tour_edges.py`, `test_build_profiles.py`, `test_reconstruct_raw_graph.py`) already
assert on distance values computed via these functions — if the dedup introduced any numeric
drift, one of them fails. Do not weaken or delete any existing assertion to make this land.

Optionally, add one small direct test to a new `tests/test_geo.py` (or append to an existing one
if `lib/geo.py` already has a test file — check `tests/` first) asserting `haversine_m(11.0, 47.0,
11.0, 47.0) == 0.0` and a known distance (e.g. roughly 111km for 1 degree of latitude at the
equator-adjacent case) — this is optional polish, not required for done criteria.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `grep -rn "6_371_000" pipeline/` returns exactly one match, in `pipeline/lib/geo.py`
- [ ] `grep -rln "_haversine_m\b\|_haversine_m_vec\b\|_haversine_m_vec_pairs\b\|_leg_segment_m\b" pipeline/lib pipeline/phases pipeline/analysis` returns no files with a local `def` for any of these names (call sites importing from `lib.geo` are fine)
- [ ] `pixi run pytest -q` (from `pipeline/`) → all pass, same or greater count than the 326 baseline
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- Any of the 7 "duplicate" function bodies you find in the live code differs from the excerpts
  above by more than the argument names/type hints/underscore-prefix already noted (i.e. a
  genuinely different formula, not just a naming difference) — that means one of them was already
  fixed or diverged for a reason, and blindly unifying it would change behavior. Report which file
  and how it differs.
- A test file listed in the table doesn't exist or doesn't cover the function you're replacing —
  don't skip verification for that file; report and ask how to proceed.
- Any call site takes arguments in a different order/shape than shown here that you can't resolve
  by inspection (e.g. an unexpected wrapper).

## Maintenance notes

- Any future precision/units change to the haversine formula now happens in exactly one place
  (`lib/geo.py`). `analysis/reconstruct_raw_graph.py`'s requirement to match
  `build_base_graph.py`'s formula exactly is now structurally guaranteed (same imported function)
  rather than a comment-enforced convention — a reviewer of a future `lib/geo.py` change should
  re-run `tests/test_reconstruct_raw_graph.py` specifically, since that's the one place a formula
  change could silently break an invariant (reconstructed segment distances summing back to
  persisted chain distances) rather than just shifting a number.
- If `pipeline/tours/`-based GPX ingestion (the in-flight `feat/official-tours-integration` work,
  see `docs/superpowers/specs/2026-08-30-tour-folder-ingestion-design.md`) adds its own distance
  calculations, it should import from `lib/geo.py` from the start rather than adding an 8th
  duplicate.
