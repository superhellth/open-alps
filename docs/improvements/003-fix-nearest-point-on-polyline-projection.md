# Plan 003: Latitude-correct `nearest_point_on_polyline`'s planar projection

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 3e59f51..HEAD -- pipeline/lib/edge_split.py pipeline/lib/hub_snap.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: LOW-MED
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `3e59f51`, 2026-08-31

## Why this matters

`lib/edge_split.py`'s `nearest_point_on_polyline(polyline, point)` finds which segment of a
polyline (and where along it) is closest to a query point, using **raw, unprojected `(lon, lat)`
coordinates** — i.e. it treats one degree of longitude and one degree of latitude as the same
real-world distance. They aren't: at Alpine latitudes (~47°N), `cos(47°) ≈ 0.68`, so one degree of
longitude is only ~68% as many real meters as one degree of latitude. The function's own docstring
acknowledges this is a simplification ("fine at the scale of a single chain edge (at most a few
km), where lon/lat behaves near-linearly") — but a base-graph chain edge can be up to
`pipeline.config.json`'s `graph.maxEdgeKm` (default 30 km, not "a few km"), and the distortion
doesn't need a long edge to matter — it needs a polyline whose segments point in different compass
directions near the query point (e.g. a hub sitting near a bend from a mostly-east-west trail
segment to a mostly-north-south one), which can happen on a short edge too.

`nearest_point_on_polyline` has exactly one caller: `lib/hub_snap.py:224`, inside
`snap_hub_to_subgraph` — the function that decides which mid-chain point on the base graph a hut,
station, or parking hub snaps onto when no existing graph node is close enough. A wrong nearest-
segment choice there means:
1. The hub can snap to the wrong point on the polyline (not the geometrically closest one), and
2. `split_edge_at_point` (called immediately after with that `segment_index`/`frac`) apportions
   the edge's `dist_m`/`road_m`/`ungraded_m`/`inferred_m` based on that wrong split point, so the
   error propagates into the persisted edge distances, not just the reported `gap_m` (which is
   separately recomputed via `_haversine_m` on the *chosen* point, so it looks locally consistent
   even when the chosen point isn't the true nearest one).

This is worth fixing now specifically because `lib/edge_split.py` is explicitly the module the
`docs/superpowers/specs/2026-08-30-tour-folder-ingestion-design.md` migration will keep and reuse
for GPX-based tour-leg endpoint snapping ("§2 needs 'nearest *hub* to a given endpoint'... belongs
in lib/hubs.py" — a sibling nearest-point problem to this one, in the same neighborhood of code) —
getting the shared projection primitive right now pays off there too.

**Correction to a prior read of this code**: `lib/hub_snap.py`'s own `_project_m` helper (used by
`_candidate_edges_near` to build a `cKDTree` over candidate edges, applying the `cos(lat)`
correction via `km_per_deg_lng = KM_PER_DEG_LAT * math.cos(math.radians(ref_lat))`) is **not**
applied before the `nearest_point_on_polyline` call at line 224 — that call passes raw `(lon,
lat)` tuples (`polyline` built from `subgraph.local_nodes`/`interior` lon/lat fields directly, and
`(hub_lon, hub_lat)` also raw). `_project_m`'s own docstring says this is "the same simplification
`nearest_point_on_polyline` already relies on" — i.e. `hub_snap.py` is aware of and currently
accepts the unprojected nearest-point search; it does not itself perform any hidden correction
before that call. Do not assume otherwise when reading the code.

## Current state

`lib/edge_split.py:21-40` (full function):

```python
def nearest_point_on_polyline(polyline: list, point: tuple) -> tuple:
    """polyline: [(lon, lat), ...], >=2 points. Returns (segment_index, fraction in [0,1])
    identifying the closest point to `point` using planar projection - fine at the scale of a
    single chain edge (at most a few km), where lon/lat behaves near-linearly."""
    best = (0, 0.0, float("inf"))
    for i in range(len(polyline) - 1):
        ax, ay = polyline[i]
        bx, by = polyline[i + 1]
        dx, dy = bx - ax, by - ay
        seg_len_sq = dx * dx + dy * dy
        if seg_len_sq == 0:
            t = 0.0
        else:
            t = ((point[0] - ax) * dx + (point[1] - ay) * dy) / seg_len_sq
            t = min(max(t, 0.0), 1.0)
        px, py = ax + t * dx, ay + t * dy
        d = (point[0] - px) ** 2 + (point[1] - py) ** 2
        if d < best[2]:
            best = (i, t, d)
    return best[0], best[1]
```

Its only caller, `lib/hub_snap.py:216-227`:

```python
    best_edge = None  # (dist_m, edge_local_index, split)
    for ei in _candidate_edges_near(subgraph, hub_lon, hub_lat, max_snap_m):
        e = subgraph.local_edges[ei]
        interior = [
            (subgraph.interior[j]["lon"], subgraph.interior[j]["lat"])
            for j in range(e["interior_offset"], e["interior_offset"] + e["interior_count"])
        ]
        u = subgraph.local_nodes[e["u"]]
        v = subgraph.local_nodes[e["v"]]
        polyline = [(u["lon"], u["lat"]), *interior, (v["lon"], v["lat"])]
        seg_idx, frac = nearest_point_on_polyline(polyline, (hub_lon, hub_lat))
        px = polyline[seg_idx][0] + frac * (polyline[seg_idx + 1][0] - polyline[seg_idx][0])
        py = polyline[seg_idx][1] + frac * (polyline[seg_idx + 1][1] - polyline[seg_idx][1])
        d = _haversine_m(hub_lon, hub_lat, px, py)
```

`_project_m` (`lib/hub_snap.py:97-100`), the existing lat-correction helper already used elsewhere
in the same file:

```python
def _project_m(lon, lat, km_per_deg_lng: float):
    """Local flat-earth projection to meters, accurate enough at the scale of one grid
    cell (tens of km) - same simplification nearest_point_on_polyline already relies on."""
    return lon * km_per_deg_lng * 1000.0, lat * KM_PER_DEG_LAT * 1000.0
```

`lib/grid.py:10` — `KM_PER_DEG_LAT = 111.320` (imported into `hub_snap.py` at line 24: `from
lib.grid import KM_PER_DEG_LAT, Grid`).

`km_per_deg_lng` in `hub_snap.py` is computed once per subgraph from a reference latitude (line
124: `km_per_deg_lng = KM_PER_DEG_LAT * math.cos(math.radians(ref_lat))`) — the same pattern this
plan should reuse, either by passing an equivalent factor into `nearest_point_on_polyline` or by
projecting the polyline/point before calling it.

Existing tests (`tests/test_edge_split.py:9-19`) use polylines on `y = 0` or with tiny 1-degree
spacing (`[(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]`), which never exercises latitude correction —
that's why this bug has no test coverage today.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Run pipeline tests | `pixi run pytest -q` (from `pipeline/`) | all pass |
| Run just the affected tests | `pixi run pytest tests/test_edge_split.py tests/test_hub_snap.py -q` | all pass |

## Scope

**In scope** (the only files you should modify):
- `pipeline/lib/edge_split.py` — `nearest_point_on_polyline`'s signature and body
- `pipeline/lib/hub_snap.py` — its one call site (pass the latitude-correction factor through)
- `pipeline/tests/test_edge_split.py` — new latitude-correction test cases
- `pipeline/tests/test_hub_snap.py` — if needed, a regression test confirming the corrected call
  site still snaps correctly (see Step 3)

**Out of scope**:
- Do NOT change `split_edge_at_point`'s distance apportionment logic — it already uses
  `_haversine_m` (real distance) along the polyline for its `dist_to_u`/`dist_to_v` split, which
  is correct; only the *segment selection* in `nearest_point_on_polyline` is being fixed.
- Do NOT touch `_candidate_edges_near`/`_build_edge_spatial_index`'s existing `_project_m`-based
  KDTree search — it's already latitude-corrected; this plan brings `nearest_point_on_polyline` up
  to the same standard, not the other way around.
- Do NOT add latitude correction to `lib/geo.py`'s `circle_polygon` or any other module — scope is
  strictly `nearest_point_on_polyline` and its one caller.

## Git workflow

- Branch: stay on the current branch unless the operator says otherwise.
- Commit message style: lowercase, `<module>: <imperative description>`, e.g. `lib: latitude-
  correct nearest_point_on_polyline's segment search`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add an optional latitude-correction factor to `nearest_point_on_polyline`

Change the signature to accept an optional `km_per_deg_lng_ratio` (the ratio of longitude-degree
to latitude-degree real distance, i.e. `cos(radians(ref_lat))`, defaulting to `1.0` so any other
caller — there are none today, but keep the function safely reusable — that genuinely wants raw
planar behavior isn't silently changed):

```python
def nearest_point_on_polyline(polyline: list, point: tuple, lng_scale: float = 1.0) -> tuple:
    """polyline: [(lon, lat), ...], >=2 points. Returns (segment_index, fraction in [0,1])
    identifying the closest point to `point`, using a locally-flat projection where longitude
    distances are scaled by `lng_scale` (pass cos(radians(reference_latitude)) so degrees of
    longitude and latitude compare in real-world proportion - see hub_snap.py's _project_m for
    the same correction applied elsewhere in the snapping path). Defaults to 1.0 (no correction)
    for callers that intentionally want raw degree-space comparison."""
    best = (0, 0.0, float("inf"))
    for i in range(len(polyline) - 1):
        ax, ay = polyline[i]
        bx, by = polyline[i + 1]
        dx, dy = (bx - ax) * lng_scale, by - ay
        seg_len_sq = dx * dx + dy * dy
        if seg_len_sq == 0:
            t = 0.0
        else:
            t = ((point[0] - ax) * lng_scale * dx + (point[1] - ay) * dy) / seg_len_sq
            t = min(max(t, 0.0), 1.0)
        px, py = ax + t * (bx - ax), ay + t * dy
        d = ((point[0] - px) * lng_scale) ** 2 + (point[1] - py) ** 2
        if d < best[2]:
            best = (i, t, d)
    return best[0], best[1]
```

Note `px`/`py` are still returned/reconstructed in **unscaled** `(lon, lat)` space (the caller
needs real coordinates back) — only the internal distance/projection math is scaled; `t` (the
fraction along the segment) is computed consistently in scaled space on both the dot-product
numerator and `seg_len_sq`, so it's unaffected by unscaling `px`/`py` afterward.

**Verify**: `pixi run pytest tests/test_edge_split.py -q` → existing tests still pass unchanged
(default `lng_scale=1.0` preserves current behavior for those tests' `y=0`/tiny-spacing fixtures,
where the correction has no visible effect anyway since latitude is 0).

### Step 2: Pass the correction factor from `hub_snap.py`'s call site

In `snap_hub_to_subgraph`, the KDTree code already computes a per-subgraph `km_per_deg_lng` (line
124, via `_build_edge_spatial_index`, stored in the cached `index` tuple as its 4th element —
see `_candidate_edges_near`'s unpacking: `tree, edge_ids, max_seg_len_m, km_per_deg_lng = index`).
Reuse that same value's *ratio form* by computing `lng_scale = km_per_deg_lng / KM_PER_DEG_LAT`
(equivalently just `math.cos(math.radians(ref_lat))` directly — check which is more convenient
given what's already in scope at that point in the function; `km_per_deg_lng` itself is only
available inside `_candidate_edges_near`'s local scope via the index tuple, so the simplest fix is
to also return `km_per_deg_lng` alongside `edge_ids` from `_candidate_edges_near`, or independently
recompute `math.cos(math.radians(hub_lat))` at the `nearest_point_on_polyline` call site — prefer
the latter (recompute locally) since it avoids changing `_candidate_edges_near`'s return signature
for a value only this one call site needs).

Change:

```python
        seg_idx, frac = nearest_point_on_polyline(polyline, (hub_lon, hub_lat))
```

to:

```python
        lng_scale = math.cos(math.radians(hub_lat))
        seg_idx, frac = nearest_point_on_polyline(polyline, (hub_lon, hub_lat), lng_scale)
```

(`math` is already imported in `hub_snap.py` — check the top-of-file imports to confirm before
assuming.) Using the hub's own latitude (rather than a subgraph-wide reference latitude) matches
`circle_polygon`'s stated preference in `lib/geo.py` for "computed per-hut-locally... not from one
global scale factor" — consistent with this codebase's existing convention.

**Verify**: `pixi run pytest tests/test_hub_snap.py -q` → all pass.

### Step 3: Add a latitude-correction regression test

In `tests/test_edge_split.py`, add a test using a polyline with a real bend at a non-zero latitude
where the uncorrected and corrected answers differ. Example shape: a polyline that goes east then
turns north at high latitude, with a query point near the corner such that raw degree-distance
picks the wrong segment but latitude-corrected distance picks the right one:

```python
def test_nearest_point_on_polyline_applies_longitude_scale_at_high_latitude():
    # At lat=60, cos(60deg)=0.5: 1 degree of longitude is half the real distance of 1 degree of
    # latitude. Polyline bends from east-heading to north-heading at (1.0, 60.0). A query point
    # just north-east of the bend, slightly closer in raw degree-space to the east-heading arm's
    # endpoint than to the north-heading arm - but closer in real-world terms to the north arm,
    # once longitude is properly compressed.
    polyline = [(0.0, 60.0), (1.0, 60.0), (1.0, 60.5)]
    query = (1.05, 60.05)
    lng_scale = 0.5  # cos(radians(60)) rounded for a clean fixture value
    seg_idx, frac = nearest_point_on_polyline(polyline, query, lng_scale)
    assert seg_idx == 1  # the north-heading arm, not the east-heading one
```

Before finalizing this test, verify by hand (or with a small scratch script) that this fixture
genuinely produces `seg_idx == 0` when called with the default `lng_scale=1.0` and `seg_idx == 1`
with `lng_scale=0.5` — i.e. that it actually demonstrates the fix rather than passing either way.
If the numbers above don't produce that split, adjust the query point/polyline coordinates
(keeping the same "bend at high latitude" shape) until they do, and note the final values you used
in the test's comment.

**Verify**: `pixi run pytest tests/test_edge_split.py -k longitude_scale -v` → new test passes.

## Test plan

- New test: `test_nearest_point_on_polyline_applies_longitude_scale_at_high_latitude` (Step 3),
  demonstrating the fix changes the segment choice at high latitude.
- Existing tests: `tests/test_edge_split.py`'s current two `nearest_point_on_polyline` tests and
  all `test_split_*` tests must still pass unchanged (default `lng_scale=1.0` preserves current
  behavior when unspecified).
- `tests/test_hub_snap.py`'s existing snapping tests must still pass — if any of them assert on an
  exact `segment_index`/split-point value near a bend, double check after this change that the new
  (correct) answer is what the test expects; if a test's fixture happens to sit near a real bend
  where the answer changes, that's expected and the test's assertion should be updated to the
  correct value, with a one-line comment noting why.
- Verification: `pixi run pytest tests/test_edge_split.py tests/test_hub_snap.py -q` → all pass.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `pixi run pytest -q` (from `pipeline/`) → all pass, same or greater count than baseline
- [ ] `nearest_point_on_polyline`'s signature includes `lng_scale` with default `1.0`
- [ ] `lib/hub_snap.py`'s call site passes a computed `lng_scale`, not the default
- [ ] New latitude-correction test exists and passes
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- The live `nearest_point_on_polyline` or its call site in `hub_snap.py` differs from the excerpts
  above in a way that changes the fix's shape (e.g. someone already added latitude correction, or
  the function signature has already changed).
- The fixture in Step 3 can't be made to demonstrate a segment-choice difference after reasonable
  adjustment — report the numbers you tried and ask for guidance rather than committing a test
  that doesn't actually exercise the fix.
- Updating an existing `test_hub_snap.py` assertion to match a new (correct) answer feels like it's
  masking an unrelated problem rather than reflecting the intended fix — stop and describe what you
  see rather than adjusting the assertion.

## Maintenance notes

- If a second caller of `nearest_point_on_polyline` is ever added (e.g. by the tour-folder-
  ingestion migration's planned `lib/hubs.py` nearest-hub work), it should pass its own
  latitude-appropriate `lng_scale` rather than relying on the `1.0` default, which is only correct
  at the equator.
- A reviewer should sanity-check that `d` returned internally by `nearest_point_on_polyline` is
  only ever used for *comparison* (finding the minimum), never surfaced as an actual distance in
  meters — the caller (`hub_snap.py`) already recomputes the real distance via `_haversine_m` on
  the resolved point, so this fix only needs to get the *ordering* of candidate segments right, not
  produce a metrically correct distance itself.
