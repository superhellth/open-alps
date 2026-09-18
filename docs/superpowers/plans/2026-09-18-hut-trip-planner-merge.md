# Hut-trip-planner merge (GPX-only official tours) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task, in-session, on the current checkout. (Repo rule: no worktrees, no subagent-driven development.) Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Official tours are matched from their raw GPX trace + DEM only (no OSM graph), the GPX editor and alpenvereinaktiv fetch tool ship in open-alps, free routing is untouched.

**Architecture:** Port hut-trip-planner's `match_tour_edges.py` (+ `dem_sample`/`elevation_profile` libs, `TOUR_LEG_DTYPE`, `build_tour_tiles.py`, `check_tour_matching.py`) into open-alps by copying files from `~/hut-trip-planner`, then extend `tours.json` with `edgeId`/`maxEleM`/null gap legs, cut every dependency from tour tasks onto base-graph tasks, delete the HMM matcher, and repoint the frontend from `tour-edge-payload.*` to `tours.json`.

**Tech Stack:** Python (doit, numpy, rasterio, pytest via `pixi run test` in `pipeline/`), TypeScript/React/MUI/Vite/Vitest in `huts/`.

**Spec:** `docs/superpowers/specs/2026-09-18-hut-trip-planner-merge-design.md`

## Global Constraints

- **Never run any `pipeline/` doit task** (`doit <task>`, full `doit`) without asking the user and getting explicit confirmation. Only `pixi run test`, `pixi run doit info <task>`/`doit list`-style read-only introspection, and pytest are allowed. (`doit info` does not execute tasks; still prefer the wiring tests.)
- Work on branch `feat/gpx-only-official-tours`; never commit to `main`.
- No git worktrees, no subagents.
- No historical comments: comments state what the code does now, never "was/used to/replaces the old …".
- Do NOT bump `binfmt.RECORD_SCHEMA_VERSION` (forces the multi-hour free-routing rebuild). Add a separate `TOUR_LEG_SCHEMA_VERSION`.
- Tours never snap to OSM ways: geometry = raw GPX points, unmodified. **No RDP** for tours anywhere.
- Free routing (`hut_edges`, `start_edges`, approach table, variants grid, `build_edge_tiles.py`, `hutEdgeTiles.simplifyToleranceDeg`) is unchanged.
- `lib/speed.py` in open-alps keeps `technical_time_s` (free routing uses it): never overwrite it from hut-trip-planner.
- Every task ends with `pixi run test` green in `pipeline/` (and `npm test`/`npm run typecheck` in `huts/` for frontend tasks).
- Commit messages end with `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- Paths: `HTP=~/hut-trip-planner`, `OA=~/open-alps`. Run pipeline tests from `$OA/pipeline` with `pixi run test`.
- The two repos share no history, so all "port" steps are `cp` from `$HTP`, then the listed edits.

## File Structure

Pipeline (`pipeline/`):
- Create: `lib/dem_sample.py`, `lib/elevation_profile.py`, `lib/alpenvereinaktiv.py`, `tools/fetch_alpenvereinaktiv_tour.py`, `phases/postprocessing/build_tour_tiles.py`, `phases/quality/check_tour_matching.py` + tests for each.
- Rewrite: `phases/graph_building/match_tour_edges.py`, `tests/test_match_tour_edges.py`.
- Modify: `lib/binfmt.py`, `dag/graph_building.py`, `dag/elevation.py`, `dag/postprocessing.py`, `dag/quality.py`, `dodo.py`, `pipeline.config.json`, `phases/elevation/build_profiles.py`, `phases/postprocessing/build_edge_payload.py`, `phases/quality/check_graph_building.py`, `phases/quality/check_elevation.py`, `phases/quality/check_postprocessing.py`, the matching tests, `CLAUDE.md` + phase READMEs.
- Delete: `lib/hmm_match.py`, `lib/hmm_reconstruct.py`, `analysis/corridor_match_quality.py`, `tests/test_hmm_match.py`, `tests/test_hmm_reconstruct.py`.
- Copy data: `tours/{Lechquellenrunde,Pitztaltour,Silvretta-Runde,Tauernhöhenweg}`.

Frontend (`huts/`):
- Create: `src/gpxEditor/*`, `gpx-editor.html`, `tools/gpxEditorPlugin.ts` (+ test), `tsconfig.tools.json`.
- Modify: `vite.config.js`, `vitest.config.js`, `package.json` (typecheck script), `src/tourSearch/loadOfficialTours.ts`, `src/tourSearch/officialTours.ts` (+tests), `src/tourSearchPage/TourSearchPage.tsx` (+test), `OfficialTourList` tests, `helpers.test.ts`.
- Delete: `src/tourSearch/loadTourEdges.ts`, `loadTourEdges.test.ts`.

Docs: `docs/gpx-editor.md`, ported specs, `docs/superpowers/STATUS.md`, `pipeline/CLAUDE.md`, phase READMEs, `docs/backlog.md`.

---

### Task 1: Branch and baseline

**Files:** none new.

- [ ] **Step 1: Create the branch (carries the uncommitted spec/backlog/STATUS edits)**

```bash
cd ~/open-alps && git checkout -b feat/gpx-only-official-tours
git add docs/backlog.md docs/superpowers/STATUS.md docs/superpowers/specs/2026-09-18-hut-trip-planner-merge-design.md docs/superpowers/plans/2026-09-18-hut-trip-planner-merge.md
git commit -m "docs: hut-trip-planner merge spec and plan

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

- [ ] **Step 2: Record the baseline**

Run: `cd ~/open-alps/pipeline && pixi run test 2>&1 | tail -5` and `cd ~/open-alps/huts && npm test 2>&1 | tail -8 && npm run typecheck 2>&1 | tail -5`
Expected: note pass/fail counts. Any pre-existing failure is reported to the user, not "fixed" here.

---

### Task 2: Port DEM sampling + elevation profile libs

**Files:**
- Create: `pipeline/lib/dem_sample.py`, `pipeline/lib/elevation_profile.py`, `pipeline/tests/test_dem_sample.py`, `pipeline/tests/test_elevation_profile.py`

**Interfaces:**
- Produces: `dem_sample.sample_points(dem_path, points: list[(lon,lat)]) -> np.ndarray`; `elevation_profile.smooth_profile(elev, seg_len_m, kernel_m)`, `ascent_descent(smoothed) -> (float,float)`, `merge_segments(seg_len, dz, min_seg_m) -> (len, dz)`, `resample_to_points(lons, lats, smoothed, n) -> list[float]`.

- [ ] **Step 1: Copy the files verbatim**

```bash
cd ~/open-alps/pipeline
for f in lib/dem_sample.py lib/elevation_profile.py tests/test_dem_sample.py tests/test_elevation_profile.py; do cp ~/hut-trip-planner/pipeline/$f $f; done
```

- [ ] **Step 2: Check the comments for historical/htp-specific references**

Run: `grep -n "hut-trip-planner\|deleted\|used to\|no longer\|HMM" lib/dem_sample.py lib/elevation_profile.py tests/test_dem_sample.py tests/test_elevation_profile.py`
Expected: reword any hit so it states current behaviour only (spec paths under `docs/superpowers/specs/` are fine once ported in Task 11).

- [ ] **Step 3: Run the new tests**

Run: `cd ~/open-alps/pipeline && pixi run pytest tests/test_dem_sample.py tests/test_elevation_profile.py -v 2>&1 | tail -15`
Expected: PASS. (If `rasterio` import fails, `pixi.toml` differs — it should be identical; stop and report.)

- [ ] **Step 4: Commit**

```bash
git add pipeline/lib/dem_sample.py pipeline/lib/elevation_profile.py pipeline/tests/test_dem_sample.py pipeline/tests/test_elevation_profile.py
git commit -m "feat(pipeline): port DEM sampling and elevation profile libs

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: `TOUR_LEG_DTYPE` and its schema version

**Files:**
- Modify: `pipeline/lib/binfmt.py` (after `RECORD_DTYPE`, ~line 86; schema versions ~line 122)
- Test: `pipeline/tests/test_binfmt.py`

**Interfaces:**
- Produces: `binfmt.TOUR_LEG_DTYPE` (fields `from_id i8, to_id i8, from_type u1, to_type u1, distance_m f4, ascent_m f4, descent_m f4, duration_s f4, max_ele_m f4, geom_offset i8, geom_count i4, profile_offset i8, profile_count i4`), `binfmt.TOUR_LEG_SCHEMA_VERSION = 1`. `TOUR_META_DTYPE`/`VARIANT_OFFICIAL` stay until Task 8 (still referenced).

- [ ] **Step 1: Write failing tests** (append to `tests/test_binfmt.py`; taken from hut-trip-planner's, minus its "removed constants" test which does not apply here)

```python
def test_tour_leg_dtype_has_no_road_or_grading_fields():
    names = binfmt.TOUR_LEG_DTYPE.names
    for field in ("road_m", "sac_rank", "via_ferrata", "snap_m", "ungraded_m", "inferred_m"):
        assert field not in names, field


def test_tour_leg_dtype_carries_the_scalar_leg_fields():
    for field in ("distance_m", "ascent_m", "descent_m", "duration_s", "max_ele_m"):
        assert field in binfmt.TOUR_LEG_DTYPE.names, field


def test_tour_leg_dtype_carries_endpoint_identity():
    for field in ("from_id", "to_id", "from_type", "to_type"):
        assert field in binfmt.TOUR_LEG_DTYPE.names, field


def test_tour_leg_dtype_carries_geometry_and_profile_offsets():
    for field in ("geom_offset", "geom_count", "profile_offset", "profile_count"):
        assert field in binfmt.TOUR_LEG_DTYPE.names, field


def test_tour_leg_schema_version_is_separate_from_record_schema_version():
    assert isinstance(binfmt.TOUR_LEG_SCHEMA_VERSION, int)
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/open-alps/pipeline && pixi run pytest tests/test_binfmt.py -k tour_leg -v 2>&1 | tail -8`
Expected: FAIL `AttributeError: module 'lib.binfmt' has no attribute 'TOUR_LEG_DTYPE'`.

- [ ] **Step 3: Implement** — add to `lib/binfmt.py` right after `TOUR_META_DTYPE`:

```python
# tour_edges/records.npy - one row per matched official-tour leg. Geometry and profile are slices
# (offset/count) of tour_edges/geometry.npy (COORD_DTYPE) and tour_edges/profiles.npy (PROFILE_DTYPE).
TOUR_LEG_DTYPE = np.dtype([
    ("from_id", "i8"), ("to_id", "i8"), ("from_type", "u1"), ("to_type", "u1"),
    ("distance_m", "f4"), ("ascent_m", "f4"), ("descent_m", "f4"), ("duration_s", "f4"),
    ("max_ele_m", "f4"),
    ("geom_offset", "i8"), ("geom_count", "i4"),
    ("profile_offset", "i8"), ("profile_count", "i4"),
])
```

and next to `ACCESS_DISTANCE_SCHEMA_VERSION`:

```python
TOUR_LEG_SCHEMA_VERSION = 1  # tracking param of match_tour_edges only; bump on TOUR_LEG_DTYPE changes
```

- [ ] **Step 4: Run tests** — `pixi run pytest tests/test_binfmt.py -v 2>&1 | tail -8` → PASS.

- [ ] **Step 5: Commit** — `git add pipeline/lib/binfmt.py pipeline/tests/test_binfmt.py && git commit -m "feat(pipeline): add TOUR_LEG_DTYPE"` (with Co-Authored-By trailer).

---

### Task 4: GPX-only `match_tour_edges` with `edgeId`, `maxEleM`, null gap legs

**Files:**
- Rewrite: `pipeline/phases/graph_building/match_tour_edges.py`, `pipeline/tests/test_match_tour_edges.py`
- Modify: `pipeline/pipeline.config.json` (delete `tourMatch` block), `pipeline/tests/test_config.py` (delete `test_tour_match_config_has_expected_keys`)

**Interfaces:**
- Consumes: `dem_sample.sample_points`, `elevation_profile.*` (Task 2), `binfmt.TOUR_LEG_DTYPE` (Task 3), `lib.hubs.nearest_hub_to_point/load_all_hubs/HUB_TYPE_JSON_NAMES`, `lib.tour_folder.load_all_tour_folders/load_tour_folder`, `lib.speed.edge_time_s`, `lib.geo.haversine_m_vec_pairs`.
- Produces (used by Tasks 5–9 and the frontend): `tours.json` = `[{tourId, name, numDays, legs:[leg,…]}]`; matched leg = `{legIndex, edgeId, distanceM, ascentM, descentM, durationS, maxEleM, from:{type,id}, to:{type,id}}`; gap leg = `{legIndex, edgeId: null, from: {type,id}|null, to: {type,id}|null}`; `legs.length == numDays`; `edgeId` = row index in `tour_edges/records.npy`. Also `write_hubs_json(hubs, out_dir)`, `_resolve_endpoint`, `match_leg`, `_pack_tour_legs`.

- [ ] **Step 1: Copy htp's script and tests as the starting point**

```bash
cd ~/open-alps/pipeline
cp ~/hut-trip-planner/pipeline/phases/graph_building/match_tour_edges.py phases/graph_building/match_tour_edges.py
cp ~/hut-trip-planner/pipeline/tests/test_match_tour_edges.py tests/test_match_tour_edges.py
```

- [ ] **Step 2: Add the new failing tests** — append to `tests/test_match_tour_edges.py`. They need a shared fixture helper; add above the tests:

```python
def _run_main(tmp_path, monkeypatch, huts_coords, legs, dem_kwargs):
    """huts_coords: [(lon, lat), ...] as huts; legs: {leg_number: [(lon, lat), ...]}. Returns osm_dir."""
    osm_dir = tmp_path / "osm"
    osm_dir.mkdir()
    tours_dir = tmp_path / "tours"
    huts = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": f"Hut {i}"},
         "geometry": {"type": "Point", "coordinates": list(c)}}
        for i, c in enumerate(huts_coords)
    ]}
    (osm_dir / "huts.geojson").write_text(json.dumps(huts), encoding="utf-8")
    binfmt.save_array(osm_dir / "start_points.npy", np.zeros(0, dtype=np.dtype(
        [("osm_id", "i8"), ("type", "u1"), ("lon", "f8"), ("lat", "f8")])))
    _write_tour_folder(tours_dir, "T", legs)
    dem_path = _flat_dem(tmp_path, **dem_kwargs)

    import lib.pipeline as pipeline_lib
    monkeypatch.setattr(pipeline_lib, "OSM_DIR", osm_dir)
    monkeypatch.setattr(pipeline_lib, "TOURS_DIR", tours_dir)
    monkeypatch.setattr(mte, "OSM_DIR", osm_dir)
    monkeypatch.setattr(mte, "TOURS_DIR", tours_dir)
    mte.main([
        "--dem", str(dem_path), "--out-dir", str(osm_dir), "--max-snap-m", "100",
        "--smoothing-kernel-m", "0", "--min-slope-segment-m", "10", "--profile-points", "5",
        "--speed-v0", "4.013", "--speed-k", "3.5", "--speed-s0", "0.05", "--min-speed-ms", "0.15",
    ])
    return osm_dir


_DEM = dict(elevation=1500.0, origin=(10.9, 47.1), size=300, pixel_deg=0.001)


def test_geometry_equals_raw_gpx_points_exactly(tmp_path, monkeypatch):
    leg1 = [(11.0, 47.0), (11.0003, 47.004), (11.0, 47.01)]
    leg2 = [(11.0, 47.01), (11.0002, 47.015), (11.0, 47.02)]
    osm_dir = _run_main(tmp_path, monkeypatch, [(11.0, 47.0), (11.0, 47.01), (11.0, 47.02)],
                        {1: leg1, 2: leg2}, _DEM)
    records = binfmt.load_array(osm_dir / "tour_edges" / "records.npy", mmap=False)
    geometry = binfmt.load_array(osm_dir / "tour_edges" / "geometry.npy", mmap=False)
    for r, expected in zip(records, (leg1, leg2)):
        sl = geometry[int(r["geom_offset"]):int(r["geom_offset"]) + int(r["geom_count"])]
        assert list(zip(sl["lon"].tolist(), sl["lat"].tolist())) == expected


def test_tours_json_scalars_match_records_via_edge_id(tmp_path, monkeypatch):
    osm_dir = _run_main(
        tmp_path, monkeypatch, [(11.0, 47.0), (11.0, 47.01), (11.0, 47.02)],
        {1: [(11.0, 47.0), (11.0, 47.005), (11.0, 47.01)],
         2: [(11.0, 47.01), (11.0, 47.015), (11.0, 47.02)]}, _DEM)
    records = binfmt.load_array(osm_dir / "tour_edges" / "records.npy", mmap=False)
    tours = json.loads((osm_dir / "tours.json").read_text(encoding="utf-8"))
    legs = tours[0]["legs"]
    assert tours[0]["numDays"] == len(legs) == 2
    for leg in legs:
        r = records[leg["edgeId"]]
        assert leg["distanceM"] == pytest.approx(float(r["distance_m"]), rel=1e-6)
        assert leg["ascentM"] == pytest.approx(float(r["ascent_m"]), abs=1e-3)
        assert leg["descentM"] == pytest.approx(float(r["descent_m"]), abs=1e-3)
        assert leg["durationS"] == pytest.approx(float(r["duration_s"]), rel=1e-6)
        assert leg["maxEleM"] == pytest.approx(float(r["max_ele_m"]), rel=1e-6)
        assert leg["from"]["type"] == "hut" and leg["to"]["type"] == "hut"


def test_unsnappable_endpoint_keeps_the_leg_with_null_edge_id(tmp_path, monkeypatch):
    # leg 1's end / leg 2's start (11.5, 47.5) is far from every hut.
    osm_dir = _run_main(
        tmp_path, monkeypatch, [(11.0, 47.0), (11.0, 47.02)],
        {1: [(11.0, 47.0), (11.2, 47.2), (11.5, 47.5)],
         2: [(11.5, 47.5), (11.2, 47.3), (11.0, 47.02)]},
        dict(elevation=1500.0, origin=(10.9, 47.6), size=700, pixel_deg=0.001))
    tours = json.loads((osm_dir / "tours.json").read_text(encoding="utf-8"))
    legs = tours[0]["legs"]
    assert len(legs) == tours[0]["numDays"] == 2
    assert legs[0] == {"legIndex": 0, "edgeId": None, "from": {"type": "hut", "id": 0}, "to": None}
    assert legs[1] == {"legIndex": 1, "edgeId": None, "from": None, "to": {"type": "hut", "id": 1}}
    records = binfmt.load_array(osm_dir / "tour_edges" / "records.npy", mmap=False)
    assert len(records) == 0


def test_edge_id_counts_only_matched_legs(tmp_path, monkeypatch):
    # leg 1 gapped (end unsnappable), leg 2 (a tour-last leg) matched -> edgeId 0 for leg 2.
    osm_dir = _run_main(
        tmp_path, monkeypatch, [(11.0, 47.0), (11.0, 47.02)],
        {1: [(11.0, 47.0), (11.2, 47.2), (11.5, 47.5)],
         2: [(11.0, 47.005), (11.0, 47.01), (11.0, 47.02)]},
        dict(elevation=1500.0, origin=(10.9, 47.6), size=700, pixel_deg=0.001))
    tours = json.loads((osm_dir / "tours.json").read_text(encoding="utf-8"))
    assert tours[0]["legs"][0]["edgeId"] is None
    # leg 2 starts at (11.0, 47.005): 555 m from any hut -> also a gap; assert consistency instead
    for leg in tours[0]["legs"]:
        assert leg["edgeId"] is None or leg["edgeId"] < len(
            binfmt.load_array(osm_dir / "tour_edges" / "records.npy", mmap=False))
```

Also change the two existing `test_main_*` tests in the copied file: in `test_main_records_a_gap_for_an_unresolvable_interior_endpoint` keep the gaps assertions and add `assert len(json.load(open(osm_dir / "tours.json", encoding="utf-8"))[0]["legs"]) == 2`.

- [ ] **Step 3: Run to verify failure**

Run: `pixi run pytest tests/test_match_tour_edges.py -v 2>&1 | tail -20`
Expected: the new tests FAIL (`KeyError: 'edgeId'` / `len(legs) == 1` because gap legs are dropped by htp's version).

- [ ] **Step 4: Edit the script** (`phases/graph_building/match_tour_edges.py`). Replace the module docstring's tours.json sentence with: `data/osm/tours.json` (per tour, `numDays` legs; a matched leg carries `edgeId` = its row in `tour_edges/records.npy` plus its scalars, a leg with an unresolved endpoint carries `edgeId: null` and a `null` for each unresolved endpoint) and add `hubs.json` to the outputs list.

Replace the per-leg loop body's gap handling and the append logic (inside `for position, (leg_number, points) in enumerate(legs):` after computing `from_chosen`/`to_chosen`) with:

```python
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
                    tour_legs_json.append({
                        "legIndex": leg_index, "edgeId": None,
                        "from": _hub_json(from_chosen), "to": _hub_json(to_chosen),
                    })
                    continue

                result = match_leg(
                    points, args.dem, args.smoothing_kernel_m, args.min_slope_segment_m,
                    speed_model, args.min_speed_ms, args.profile_points,
                )

                tour_legs_json.append({
                    "legIndex": leg_index, "edgeId": len(matched_legs),
                    "distanceM": result["distance_m"], "ascentM": result["ascent_m"],
                    "descentM": result["descent_m"], "durationS": result["duration_s"],
                    "maxEleM": result["max_ele_m"],
                    "from": _hub_json(from_chosen), "to": _hub_json(to_chosen),
                })

                matched_legs.append({ ...unchanged... })
```

`_hub_json(None)` already returns `None`. (If both endpoints are unresolved, both are `null`; the gap detail reports the first failing one, as before.)

Note the `edgeId` is taken before `matched_legs.append`, so it equals the row index.

Then delete the `tourMatch` block from `pipeline.config.json` (lines ~47–55) and the `test_tour_match_config_has_expected_keys` test in `tests/test_config.py`.

- [ ] **Step 5: Run the tests**

Run: `pixi run pytest tests/test_match_tour_edges.py tests/test_config.py -v 2>&1 | tail -20`
Expected: PASS. The `test_edge_id_counts_only_matched_legs` test intentionally asserts only consistency; if the DEM window (`origin=(10.9, 47.6), size=700`) cannot cover the far point, fix `origin/size` so the DEM contains every trace point (otherwise `sample_points` raises).

- [ ] **Step 6: Full pipeline suite**

Run: `pixi run test 2>&1 | tail -15`
Expected: failures only in tests that still reference the old tour wiring (`test_dodo_wiring`, `test_build_profiles` tour cases, `test_hmm_*` still pass) — those are fixed in Tasks 5–7. Any other failure: stop and investigate.

- [ ] **Step 7: Commit** — message `feat(pipeline): match official tour legs from raw GPX + DEM`.

---

### Task 5: DAG wiring — tour tasks free of base-graph dependencies

**Files:**
- Modify: `pipeline/dag/graph_building.py` (`task_match_tour_edges`, lines ~145–178), `pipeline/dag/elevation.py` (`task_build_profiles`), `pipeline/phases/elevation/build_profiles.py:167`, `pipeline/tests/test_dodo_wiring.py`, `pipeline/tests/test_build_profiles.py`

**Interfaces:**
- Consumes: `binfmt.TOUR_LEG_SCHEMA_VERSION` (Task 3), `tracking_param` (already imported in `dag/graph_building.py`).
- Produces: `task_match_tour_edges` with `task_dep` absent, targets `tour_edges/{records,geometry,profiles}.npy`, `tours.json`, `tour-match-gaps.json`, `hubs.json`.

- [ ] **Step 1: Replace wiring tests.** In `tests/test_dodo_wiring.py` delete `test_match_tour_edges_depends_on_profiles_and_snaps_not_edges_npy`, `test_match_tour_edges_targets_tour_edges_directory`, `test_match_tour_edges_does_not_track_record_schema_version`, `test_build_profiles_depends_on_match_tour_edges_and_tour_edges_records`. Add (`GRAPH_TASKS` names the free-routing chain):

```python
GRAPH_TASKS = {"build_base_graph", "snap_hubs", "compute_edge_profiles", "sample_base_elevation",
               "gather_route_subgraphs", "build_hub_edges", "build_access_edges", "build_profiles"}


def test_match_tour_edges_has_no_base_graph_task_dependency():
    task = dodo.task_match_tour_edges()
    assert not (GRAPH_TASKS & set(task.get("task_dep", [])))
    assert not any(str(d).endswith(("base_graph/nodes.npy", "hub_snaps.npy", "edges.npy"))
                   for d in task["file_dep"])


def test_match_tour_edges_declares_dem_huts_and_start_points():
    deps = [str(d) for d in dodo.task_match_tour_edges()["file_dep"]]
    for name in ("dem.tif", "huts.geojson", "start_points.npy"):
        assert any(d.endswith(name) for d in deps), name


def test_match_tour_edges_targets_include_profiles_and_hubs_json():
    targets = [str(t) for t in dodo.task_match_tour_edges()["targets"]]
    for name in ("tour_edges/records.npy", "tour_edges/geometry.npy", "tour_edges/profiles.npy",
                 "tours.json", "tour-match-gaps.json", "hubs.json"):
        assert any(t.endswith(name) for t in targets), name
    assert not any(t.endswith(("tour_meta.npy", "edge_ids.npy")) for t in targets)


def test_match_tour_edges_tracks_only_its_own_schema_version():
    names = {p["name"] for p in dodo.task_match_tour_edges().get("params", [])}
    assert "tour_leg_schema_version" in names
    assert not names & {"record_schema_version", "edge_schema_version", "snap_schema_version"}
    assert {"max_snap_m", "smoothing_kernel_m", "min_slope_segment_m", "profile_points",
            "speed_v0", "speed_k", "speed_s0", "min_speed_ms"} <= names


def test_build_profiles_no_longer_owns_tour_edges():
    task = dodo.task_build_profiles()
    assert "match_tour_edges" not in task["task_dep"]
    assert not any("tour_edges" in str(x) for x in (*task["file_dep"], *task["targets"]))
```

(If `tracking_param` params are exposed differently from `cli_param` in `task["params"]`, inspect an existing test — e.g. `test_build_hub_edges_tracks_all_three_schema_versions` at `tests/test_dodo_wiring.py:69` — and mirror how it reads the tracking-param names.)

In `tests/test_build_profiles.py` replace the two tour cases (`test_process_edge_set_handles_a_tour_edges_shaped_directory`, `test_main_processes_tour_edges_when_present`) with:

```python
def test_main_processes_only_hut_and_start_edges(tmp_path, monkeypatch):
    # same fixture setup as the deleted test, but the processed-names set must exclude tour_edges
    ...
    assert set(processed) == {"hut_edges", "start_edges"}
```

Reuse the existing test's fixture code unchanged except the expected set and the loop over `("hut_edges", "start_edges", "tour_edges")` → `("hut_edges", "start_edges", "tour_edges")` still creating a `tour_edges/` dir (to prove it is ignored).

- [ ] **Step 2: Run to verify failure** — `pixi run pytest tests/test_dodo_wiring.py tests/test_build_profiles.py -v 2>&1 | tail -20` → new tests FAIL.

- [ ] **Step 3: Implement.** Replace `task_match_tour_edges` in `dag/graph_building.py`:

```python
_TOUR_LEG_SCHEMA_VERSION_PARAM = tracking_param(
    "tour_leg_schema_version", int, binfmt.TOUR_LEG_SCHEMA_VERSION
)


def task_match_tour_edges():
    # Reads only huts.geojson, start_points.npy, the DEM and the GPX files: no base-graph task or
    # file is a dependency, so tour iteration never triggers build_base_graph.
    speed = CONFIG["graph"]["speedModel"]
    tour_files = sorted(TOURS_DIR.glob("*/*.gpx"))  # computed at DAG-build time
    return pipeline_task(
        "phases/graph_building/match_tour_edges.py",
        params=[
            cli_param("max_snap_m", "max-snap-m", float, CONFIG["graph"]["maxSnapM"]),
            cli_param("smoothing_kernel_m", "smoothing-kernel-m", float, CONFIG["dem"]["smoothingKernelM"]),
            cli_param("min_slope_segment_m", "min-slope-segment-m", float, CONFIG["dem"]["minSlopeSegmentM"]),
            cli_param("profile_points", "profile-points", int, CONFIG["dem"].get("profilePoints", 30)),
            cli_param("speed_v0", "speed-v0", float, speed["v0"]),
            cli_param("speed_k", "speed-k", float, speed["k"]),
            cli_param("speed_s0", "speed-s0", float, speed["s0"]),
            cli_param("min_speed_ms", "min-speed-ms", float, speed["minSpeedMs"]),
        ],
        tracking_params=[_TOUR_LEG_SCHEMA_VERSION_PARAM],
        file_dep=[
            OSM_DIR / "huts.geojson", OSM_DIR / "start_points.npy", DEM_DIR / "dem.tif",
            *tour_files,
        ],
        targets=[
            OSM_DIR / "tour_edges" / "records.npy", OSM_DIR / "tour_edges" / "geometry.npy",
            OSM_DIR / "tour_edges" / "profiles.npy",
            OSM_DIR / "tours.json", OSM_DIR / "tour-match-gaps.json", OSM_DIR / "hubs.json",
        ],
    )
```

(`tracking_params=` is the kwarg the other tasks in this file already use, e.g. `dag/graph_building.py:60`; `DEM_DIR` is already imported.)

`dag/elevation.py::task_build_profiles`: `task_dep=["build_hub_edges", "build_access_edges"]`; drop `OSM_DIR / "tour_edges" / "records.npy"` from `file_dep` and `OSM_DIR / "tour_edges" / "profiles.npy"` from `targets`; rewrite the comments so they no longer mention `match_tour_edges`.

`phases/elevation/build_profiles.py:167`: `for name in ("hut_edges", "start_edges"):`.

- [ ] **Step 4: Run** — `pixi run pytest tests/test_dodo_wiring.py tests/test_build_profiles.py tests/test_match_tour_edges.py -v 2>&1 | tail -20`. Expected PASS except tour tile/payload/quality wiring tests (Tasks 6–8).

- [ ] **Step 5: Commit** — `feat(pipeline): decouple match_tour_edges from the base graph DAG`.

---

### Task 6: `build_tour_tiles.py` without RDP

**Files:**
- Create: `pipeline/phases/postprocessing/build_tour_tiles.py`, `pipeline/tests/test_build_tour_tiles.py`
- Modify: `pipeline/dag/postprocessing.py` (replace `task_build_tour_edge_tiles`, delete `task_build_tour_edge_payload`), `pipeline/dodo.py`, `pipeline/tests/test_dodo_wiring.py`

**Interfaces:**
- Consumes: `TOUR_LEG_DTYPE` files from Task 4.
- Produces: `build_tour_tiles.build_stats(records, geometry, profiles, id_table) -> (stats, point_counts, geometry_points, profile_counts, elevation_values)` (no tolerance parameter); files `tour-edges.pmtiles`, `tour-edge-stats.json`, `tour-edge-geometry.bin/json`, `tour-edge-elevation.bin/json`.

- [ ] **Step 1: Copy and rewrite tests first.** `cp ~/hut-trip-planner/pipeline/{phases/postprocessing/build_tour_tiles.py,tests/test_build_tour_tiles.py} ` to the same paths. In the copied test file delete `test_rdp_keep_indices_collapses_straight_line` and `test_rdp_keep_indices_preserves_a_corner`, and drop the `simplify_tolerance_deg` argument from every `build_stats(...)` call. Add:

```python
def test_build_stats_keeps_every_raw_geometry_point():
    records = np.zeros(1, dtype=binfmt.TOUR_LEG_DTYPE)
    pts = [(11.0, 47.0), (11.0001, 47.0001), (11.0002, 47.0002), (11.0003, 47.0003)]  # collinear
    geometry = np.zeros(len(pts), dtype=binfmt.COORD_DTYPE)
    geometry["lon"] = [p[0] for p in pts]
    geometry["lat"] = [p[1] for p in pts]
    records[0]["geom_offset"], records[0]["geom_count"] = 0, len(pts)
    stats, point_counts, geometry_points, _, _ = tbt.build_stats(
        records, geometry, np.zeros(0, dtype=binfmt.PROFILE_DTYPE), {})
    assert point_counts == [4]
    assert geometry_points.shape == (4, 2)
```

(Use the module alias/imports already present at the top of the copied test file for `tbt`, `binfmt`, `np`.)

- [ ] **Step 2: Run to verify failure** — `pixi run pytest tests/test_build_tour_tiles.py -v 2>&1 | tail -12` → FAIL (`build_stats() ... simplify`/count 2 != 4).

- [ ] **Step 3: Edit `build_tour_tiles.py`**: delete `rdp_keep_indices` and the `import math`; change `build_stats(records, geometry, profiles, id_table)` (remove the param), replace the RDP lines (`keep = rdp_keep_indices(...)`, `simplified = coords[keep]`) with `point_counts.append(len(coords))` and `all_points.append(coords)`; remove the `--simplify-tolerance-deg` argparse flag and its use in `main`; keep `tiles_config.get("minZoom"/"maxZoom")`. Rewrite the module docstring to: builds tour_edges' PMTiles + stats from TOUR_LEG_DTYPE records; geometry is every raw GPX point (no simplification); non-hut endpoint display ids resolve through the start-point id table.

- [ ] **Step 4: Rewire the tile task.** In `dag/postprocessing.py` replace `task_build_tour_edge_tiles`:

```python
def task_build_tour_edge_tiles():
    tiles = CONFIG["hutEdgeTiles"]
    return pipeline_task(
        "phases/postprocessing/build_tour_tiles.py",
        args=[
            f"--edges-dir {OSM_DIR / 'tour_edges'}",
            f"--id-table {OSM_DIR / 'start_points_id_table.json'}",
            f"--out-tiles {OSM_DIR / 'tour-edges.pmtiles'}",
            f"--out-stats {OSM_DIR / 'tour-edge-stats.json'}",
            f"--out-geometry-bin {OSM_DIR / 'tour-edge-geometry.bin'}",
            f"--out-geometry-json {OSM_DIR / 'tour-edge-geometry.json'}",
            f"--out-elevation-bin {OSM_DIR / 'tour-edge-elevation.bin'}",
            f"--out-elevation-json {OSM_DIR / 'tour-edge-elevation.json'}",
        ],
        params=[
            cli_param("min_zoom", "min-zoom", int, tiles["minZoom"]),
            cli_param("max_zoom", "max-zoom", int, tiles["maxZoom"]),
        ],
        task_dep=["match_tour_edges"],
        file_dep=[OSM_DIR / "tour_edges" / "records.npy", OSM_DIR / "start_points_id_table.json"],
        targets=[
            OSM_DIR / "tour-edges.pmtiles", OSM_DIR / "tour-edge-stats.json",
            OSM_DIR / "tour-edge-geometry.bin", OSM_DIR / "tour-edge-geometry.json",
            OSM_DIR / "tour-edge-elevation.bin", OSM_DIR / "tour-edge-elevation.json",
        ],
    )
```

Match the existing style in this file for how `CONFIG`/`cli_param` are already imported/used by `_hut_edge_tiles_params()` (read it and reuse its min/max-zoom entries, minus the simplify entry). Delete `task_build_tour_edge_payload`.

`dodo.py`: remove the `task_build_tour_edge_payload` import; remove `"build_tour_edge_payload"` from `default_tasks`; remove `"tour-edge-payload.bin"`, `"tour-edge-payload.json"` from `PUBLIC_FILES`. Do not add `hubs.json` to `PUBLIC_FILES` (the editor reads `data/osm/hubs.json` directly).

- [ ] **Step 5: Wiring tests** in `tests/test_dodo_wiring.py`: delete `test_build_tour_edge_tiles_mirrors_hut_edge_tiles_wiring`, `test_build_tour_edge_payload_passes_tour_meta_flag`; in `test_public_files_includes_every_tour_output` remove the two payload names; add:

```python
def test_build_tour_edge_tiles_depends_on_match_tour_edges_only():
    task = dodo.task_build_tour_edge_tiles()
    assert "match_tour_edges" in task["task_dep"]
    assert "build_profiles" not in task["task_dep"]
    assert any(str(d).endswith("tour_edges/records.npy") for d in task["file_dep"])
    assert any(str(d).endswith("start_points_id_table.json") for d in task["file_dep"])
    assert any("build_tour_tiles.py" in a for a in task["actions"])
    assert not any("simplify" in a for a in task["actions"])
    assert not any(p["name"].startswith("simplify") for p in task.get("params", []))


def test_no_tour_edge_payload_task_or_public_file():
    assert not hasattr(dodo, "task_build_tour_edge_payload")
    assert "tour-edge-payload.bin" not in dodo.PUBLIC_FILES
    assert "tour-edge-payload.json" not in dodo.PUBLIC_FILES
    assert "build_tour_edge_payload" not in dodo.DOIT_CONFIG["default_tasks"]
```

(If `test_default_tasks_includes_the_tour_tasks_in_dag_order` or an existing `test_edge_tile_tasks_track_zoom_and_hover_tolerance` names the tour task, adjust so it no longer expects `simplifyToleranceDeg` on the tour task.) 

- [ ] **Step 6: Run** — `pixi run test 2>&1 | tail -15`. Expected: PASS except payload/quality tests handled in Tasks 7–8.

- [ ] **Step 7: Commit** — `feat(pipeline): build tour tiles from raw GPX geometry (no simplification)`.

---

### Task 7: `check_tour_matching` and quality split

**Files:**
- Create: `pipeline/phases/quality/check_tour_matching.py`, `pipeline/tests/test_check_tour_matching.py`
- Modify: `pipeline/phases/quality/check_graph_building.py`, `check_elevation.py`, `check_postprocessing.py`, `pipeline/dag/quality.py`, `pipeline/tests/test_check_graph_building.py`, `test_check_elevation.py`, `test_check_postprocessing.py`, `test_dodo_wiring.py`, `pipeline/lib/quality_report.py`/`phases/quality/summarize.py` only if they list check names (grep first)

**Interfaces:**
- Produces: `check_tour_matching.{check_endpoint_types, check_leg_scalars, check_gap_reasons, check_profile_integrity, check_tours_json_agreement}`; report `data/quality/tour_matching.json`.
- Consumes: `tours.json` shape from Task 4; `tour_edges/{records,profiles}.npy`.

- [ ] **Step 1: Copy, then extend tests first.** Copy `phases/quality/check_tour_matching.py` and `tests/test_check_tour_matching.py` from htp. Append tests:

```python
from phases.quality.check_tour_matching import check_leg_scalars, check_tours_json_agreement  # adjust to the import style already used at the top of the copied test


def test_leg_scalars_skips_gap_legs():
    tours = [{"tourId": 0, "name": "T", "numDays": 2, "legs": [
        {"legIndex": 0, "edgeId": None, "from": None, "to": None},
        {"legIndex": 1, "edgeId": 0, "distanceM": 1.0, "ascentM": 0.0, "descentM": 0.0,
         "durationS": 1.0, "maxEleM": 1000.0, "from": {"type": "hut", "id": 1},
         "to": {"type": "hut", "id": 2}},
    ]}]
    check = check_leg_scalars(tours, max_flagged=500)
    assert check["summary"]["checked"] == 1
    assert check["summary"]["flagged"] == 0


def test_leg_scalars_flags_non_finite_max_ele():
    tours = [{"tourId": 0, "name": "T", "numDays": 1, "legs": [
        {"legIndex": 0, "edgeId": 0, "distanceM": 1.0, "ascentM": 0.0, "descentM": 0.0,
         "durationS": 1.0, "maxEleM": float("nan"), "from": None, "to": None}]}]
    assert check_leg_scalars(tours, max_flagged=500)["summary"]["flagged"] == 1


def test_tours_json_agreement_flags_edge_id_out_of_range_and_row_count_mismatch():
    tours = [{"tourId": 0, "name": "T", "numDays": 2, "legs": [
        {"legIndex": 0, "edgeId": 0}, {"legIndex": 1, "edgeId": 5}]}]
    check = check_tours_json_agreement(tours, n_records=2, max_flagged=500)
    reasons = {r["reason"] for r in check["flagged"]}
    assert reasons == {"edge_id_out_of_range", "matched_leg_count_mismatch"}


def test_tours_json_agreement_clean_case():
    tours = [{"tourId": 0, "name": "T", "numDays": 2, "legs": [
        {"legIndex": 0, "edgeId": 0}, {"legIndex": 1, "edgeId": None}]}]
    assert check_tours_json_agreement(tours, n_records=1, max_flagged=500)["summary"]["flagged"] == 0
```

`check_profile_integrity` stays defined in `check_elevation.py` (see Step 3); its existing tests in `tests/test_check_elevation.py` stay too.

- [ ] **Step 2: Run to verify failure** — `pixi run pytest tests/test_check_tour_matching.py -v 2>&1 | tail -20` → FAIL (gap-leg `KeyError: 'distanceM'`; missing functions).

- [ ] **Step 3: Implement.** In `check_tour_matching.py`:
  - `check_leg_scalars`: skip legs with `leg.get("edgeId") is None`; check fields `("distanceM","ascentM","descentM","durationS","maxEleM")`.
  - Import `check_profile_integrity` from `check_elevation.py` (signature `(records, profiles, profile_points, layer_name, max_flagged)`); do not duplicate it.
  - Add:

```python
def check_tours_json_agreement(tours: list, n_records: int, max_flagged: int) -> dict:
    """Every non-null edgeId indexes a row of tour_edges/records.npy, and the number of matched
    legs equals that row count."""
    flagged = []
    matched = 0
    for tour in tours:
        for leg in tour["legs"]:
            edge_id = leg.get("edgeId")
            if edge_id is None:
                continue
            matched += 1
            if not 0 <= edge_id < n_records:
                flagged.append({"tourId": tour["tourId"], "tourName": tour["name"],
                                "legIndex": leg["legIndex"], "edgeId": edge_id,
                                "reason": "edge_id_out_of_range"})
    if matched != n_records:
        flagged.append({"reason": "matched_leg_count_mismatch", "matched_legs": matched,
                        "records_rows": n_records})
    return build_check("tours_json_agreement", {}, checked=matched, flagged_rows=flagged,
                       baseline=0, max_flagged_rows=max_flagged)
```

  - `main`: also load `tour_edges/records.npy` + `profiles.npy` (when both exist), run `check_profile_integrity(records, profiles, config["dem"]["profilePoints"], "tour_edges", ...)` and `check_tours_json_agreement`, append both to `checks`.
  - `check_endpoint_types`: the leg dict for gap legs has no scalar fields but does have `from`/`to` (possibly `None`), already handled by `hub is not None`.

`check_elevation.py`: `EDGE_LAYERS = ["hut_edges", "start_edges"]`; keep `check_profile_integrity` defined there and import it from `check_tour_matching.py` (scripts put `pipeline/` on `sys.path`, so `from phases.quality.check_elevation import check_profile_integrity`; match sibling scripts' import style). Add one `check_tour_matching` test that runs the imported check on a tour-shaped records array.

`check_graph_building.py`: `EDGE_LAYERS = ["hut_edges", "start_edges"]`; delete `check_tour_gaps` and the block at lines ~356–364 that reads `tour-match-gaps.json`; remove the docstring mention at line 6. `test_check_graph_building.py`: delete `test_tour_gaps_reshapes_gap_entries_into_flagged_rows` and the `check_tour_gaps` import.

`check_postprocessing.py`: `EDGE_PAYLOAD_LAYERS` tour row becomes `("tour_edges", None, "tour-edge-geometry.json", "tour-edge-geometry.bin")`; add a call to `check_tours_json_agreement`? No — that lives in `check_tour_matching`. Instead add to `check_postprocessing` one check tying `tours.json` to shipped geometry:

```python
def check_tours_json_geometry(tours: list, point_counts: list, max_flagged: int) -> dict:
    """tours.json's matched legs (edgeId != null) equal the tour geometry manifest's row count."""
    matched = sum(1 for t in tours for leg in t["legs"] if leg.get("edgeId") is not None)
    flagged = [] if matched == len(point_counts) else [{
        "reason": "matched_legs_vs_geometry_rows", "matched_legs": matched,
        "geometry_rows": len(point_counts)}]
    return build_check("tours_json_geometry", {}, checked=matched, flagged_rows=flagged,
                       baseline=0, max_flagged_rows=max_flagged)
```

wire it in `main` after the layer loop for `tour_edges` (read `tours.json` from `osm_dir` if present) with a test in `test_check_postprocessing.py` for both the clean case and the mismatch.

`dag/quality.py`: 
- `task_check_elevation`: drop `OSM_DIR / "tour_edges" / "records.npy"` from `file_dep`.
- `task_check_graph_building`: `task_dep=["build_hub_edges", "build_access_edges", "build_profiles"]`; drop `tour_edges/records.npy`, `tour_edges/geometry.npy`, `tour-match-gaps.json` from `file_dep`.
- `task_check_postprocessing`: `task_dep` drops `"build_tour_edge_payload"`; `file_dep` drops `tour-edge-payload.json`, adds `OSM_DIR / "tours.json"`.
- Add (copy from htp `dag/quality.py:45-52`, extending file deps):

```python
def task_check_tour_matching():
    return pipeline_task(
        "phases/quality/check_tour_matching.py",
        args=[f"--osm-dir {OSM_DIR}", f"--out {QUALITY_DIR / 'tour_matching.json'}"],
        params=[_max_flagged_param()],
        task_dep=["match_tour_edges"],
        file_dep=[OSM_DIR / "tours.json", OSM_DIR / "tour-match-gaps.json",
                  OSM_DIR / "tour_edges" / "records.npy", OSM_DIR / "tour_edges" / "profiles.npy"],
        targets=[QUALITY_DIR / "tour_matching.json"],
    )
```

  and include `"check_tour_matching"` + `QUALITY_DIR / "tour_matching.json"` in `task_quality_summary`'s `task_dep`/`file_dep`. `dodo.py`: import `task_check_tour_matching`; add `"check_tour_matching"` to `default_tasks` after `"match_tour_edges"`. Check `phases/quality/summarize.py` for a hard-coded list of report names and add `tour_matching` if so.

Wiring tests to add in `test_dodo_wiring.py`:

```python
def test_check_tour_matching_depends_only_on_tour_outputs():
    task = dodo.task_check_tour_matching()
    assert task["task_dep"] == ["match_tour_edges"]
    assert not any("base_graph" in str(d) for d in task["file_dep"])


def test_graph_and_elevation_checks_no_longer_read_tour_outputs():
    for name in ("task_check_graph_building", "task_check_elevation"):
        task = getattr(dodo, name)()
        assert "match_tour_edges" not in task["task_dep"]
        assert not any("tour" in str(d) for d in task["file_dep"]), name


def test_check_postprocessing_reads_tours_json_not_tour_payload():
    task = dodo.task_check_postprocessing()
    assert "build_tour_edge_payload" not in task["task_dep"]
    assert any(str(d).endswith("tours.json") for d in task["file_dep"])
    assert not any("tour-edge-payload" in str(d) for d in task["file_dep"])
```

- [ ] **Step 4: Run** — `pixi run test 2>&1 | tail -15` → PASS (excluding Task 8's payload tests if not yet done).

- [ ] **Step 5: Commit** — `feat(pipeline): tour-only quality checks, split from graph checks`.

---

### Task 8: Deletions

**Files:**
- Delete: `pipeline/lib/hmm_match.py`, `pipeline/lib/hmm_reconstruct.py`, `pipeline/analysis/corridor_match_quality.py`, `pipeline/tests/test_hmm_match.py`, `pipeline/tests/test_hmm_reconstruct.py`
- Modify: `pipeline/lib/binfmt.py`, `pipeline/phases/postprocessing/build_edge_payload.py`, `pipeline/tests/test_binfmt.py`, `pipeline/tests/test_build_edge_payload.py`

- [ ] **Step 1: Grep every remaining caller before deleting**

```bash
cd ~/open-alps/pipeline
grep -rn "hmm_match\|hmm_reconstruct\|corridor_match_quality\|TOUR_META_DTYPE\|VARIANT_OFFICIAL\|tour_meta\|tourMatch" --include=*.py --include=*.json --include=*.md . | grep -v "^./tests/test_hmm"
grep -rn "hub_snap\|edge_output" --include=*.py -l . | sort
```
Expected: no remaining production reference to the HMM modules; `lib/edge_output.py` and `lib/hub_snap.py` are still imported by `build_hub_edges`/`build_access_edges`/`snap_hubs` (keep both). Fix any unexpected caller before deleting.

- [ ] **Step 2: Write/adjust tests first.** `tests/test_build_edge_payload.py`: delete `test_pack_edges_with_tour_meta_adds_two_columns`, `test_pack_edges_without_tour_meta_is_unchanged` (rename remaining tests' intent: the `.bin` shape assertion at ~line 86 stays as "no tour columns"), and any `tour_meta` argument. `tests/test_binfmt.py`: delete `test_tour_meta_dtype_fields`; add

```python
def test_tour_meta_dtype_and_official_variant_are_gone():
    assert not hasattr(binfmt, "TOUR_META_DTYPE")
    assert not hasattr(binfmt, "VARIANT_OFFICIAL")
    assert "OFFICIAL" not in binfmt.VARIANT_NAMES.values()
```

- [ ] **Step 3: Run to verify failure** — `pixi run pytest tests/test_binfmt.py -k official -v` → FAIL.

- [ ] **Step 4: Delete/edit.**

```bash
git rm lib/hmm_match.py lib/hmm_reconstruct.py analysis/corridor_match_quality.py tests/test_hmm_match.py tests/test_hmm_reconstruct.py
```
`lib/binfmt.py`: remove `TOUR_META_DTYPE` (+ its comment), `VARIANT_OFFICIAL` (+ comment), and its `VARIANT_NAMES` entry → `VARIANT_NAMES = {VARIANT_FAST_ANY: "FAST_ANY", VARIANT_FAST_T2: "FAST_T2", VARIANT_FAST_T3: "FAST_T3", VARIANT_FAST_T3_UNGRADED: "FAST_T3_UNGRADED"}`.
`build_edge_payload.py`: `pack_edges(records, hut_ids)` — delete the `tour_meta` parameter, its docstring and the two `columns["tour_id"/"leg_index"]` lines; delete the `--tour-meta` argparse flag and the `tour_meta` load block in `main`; adjust `pack_edges(...)` call.
Update comments in `lib/subgraph.py:41,122-124`, `lib/edge_output.py:3,106-107`, `lib/cell_igraph.py:70` that name `match_tour_edges.py` as a caller: reword to describe the remaining callers only (`grep -n match_tour_edges lib/*.py`).

- [ ] **Step 5: Run** — `pixi run test 2>&1 | tail -15` → all PASS. Also `grep -rn "RECORD_SCHEMA_VERSION" lib/binfmt.py` shows value still `4`.

- [ ] **Step 6: Verify the no-base-graph claim** (read-only): `pixi run python -c "import dodo; t=dodo.task_match_tour_edges(); print(t.get('task_dep'), [str(d) for d in t['file_dep'] if 'gpx' not in str(d)])"` → no graph task, no base_graph file.

- [ ] **Step 7: Commit** — `refactor(pipeline): delete HMM tour matcher and tour_meta/OFFICIAL plumbing`.

---

### Task 9: Tooling and tour data

**Files:**
- Create: `pipeline/lib/alpenvereinaktiv.py`, `pipeline/tools/fetch_alpenvereinaktiv_tour.py`, `pipeline/tests/test_alpenvereinaktiv.py`, `pipeline/tests/test_fetch_alpenvereinaktiv_tour.py`, `pipeline/tours/{Lechquellenrunde,Pitztaltour,Silvretta-Runde,Tauernhöhenweg}/`

- [ ] **Step 1: Copy**

```bash
cd ~/open-alps/pipeline && mkdir -p tools
for f in lib/alpenvereinaktiv.py tools/fetch_alpenvereinaktiv_tour.py tests/test_alpenvereinaktiv.py tests/test_fetch_alpenvereinaktiv_tour.py; do cp ~/hut-trip-planner/pipeline/$f $f; done
for d in Lechquellenrunde Pitztaltour Silvretta-Runde "Tauernhöhenweg"; do cp -r ~/hut-trip-planner/pipeline/tours/"$d" tours/; done
ls tours/*/ | head -40
```

- [ ] **Step 2: Diff shared files before trusting the copy.** `for f in lib/speed.py phases/downloads/fetch_stations_parking.py tests/test_binfmt.py; do diff ~/hut-trip-planner/pipeline/$f $f | head -20; done` — record any *improvement* in htp (not deletions of free-routing code) and port it by hand; `speed.py` keeps `technical_time_s`. Report the outcome to the user (spec "Shared-file drift").

- [ ] **Step 3: Confirm `tools/` imports resolve** (`sys.path` bootstrap in the copied tool matches open-alps' layout: `pipeline/` root). Run: `pixi run pytest tests/test_alpenvereinaktiv.py tests/test_fetch_alpenvereinaktiv_tour.py tests/test_tour_folder.py -v 2>&1 | tail -12` → PASS.

- [ ] **Step 4: Confirm `tourId` sort order note.** `ls -1 tours` lists 6 folders; add a line to `pipeline/CLAUDE.md` in Task 12, not here.

- [ ] **Step 5: Commit** — `feat(pipeline): alpenvereinaktiv tour fetch tool and four more tours`.

---

### Task 10: GPX editor

**Files:**
- Create: `huts/src/gpxEditor/` (all), `huts/gpx-editor.html`, `huts/tools/gpxEditorPlugin.ts`, `huts/tools/gpxEditorPlugin.test.ts`, `huts/tsconfig.tools.json`, `pipeline/tests/fixtures/snap_cases.json`, `pipeline/tests/fixtures/gpx_edited/`, `pipeline/tests/test_snap_cases.py`, `pipeline/tests/test_gpx_editor_roundtrip.py`, `docs/gpx-editor.md`
- Modify: `huts/vite.config.js`, `huts/vitest.config.js`, `huts/package.json`, `huts/tsconfig.json`

**Interfaces:** the editor's only outward imports are `../theme.js` (exists in open-alps) and `leaflet`. The plugin serves `data/osm/hubs.json` + tours dir from the repo root passed to `gpxEditorPlugin(repoRoot)`.

- [ ] **Step 1: Copy files**

```bash
cd ~/open-alps
cp -r ~/hut-trip-planner/huts/src/gpxEditor huts/src/gpxEditor
cp ~/hut-trip-planner/huts/gpx-editor.html huts/
mkdir -p huts/tools && cp ~/hut-trip-planner/huts/tools/gpxEditorPlugin*.ts huts/tools/
cp ~/hut-trip-planner/docs/gpx-editor.md docs/
cp ~/hut-trip-planner/pipeline/tests/{test_snap_cases.py,test_gpx_editor_roundtrip.py} pipeline/tests/
cp ~/hut-trip-planner/pipeline/tests/fixtures/snap_cases.json pipeline/tests/fixtures/
cp -r ~/hut-trip-planner/pipeline/tests/fixtures/gpx_edited pipeline/tests/fixtures/
```

- [ ] **Step 2: Adapt configs (do not copy htp's).**
  - `huts/vite.config.js`:
    ```js
    import { fileURLToPath } from 'node:url'
    import { defineConfig } from 'vite'
    import react from '@vitejs/plugin-react'
    import { gpxEditorPlugin } from './tools/gpxEditorPlugin.ts'

    export default defineConfig({
      plugins: [react(), gpxEditorPlugin(fileURLToPath(new URL('..', import.meta.url)))],
    })
    ```
    (Vite's config loader bundles TS imports from a `.js` config; if it rejects the `.ts` extension use `'./tools/gpxEditorPlugin.js'` exactly as htp's `vite.config.ts` does — try `.ts` first, fall back on the error.)
  - `huts/vitest.config.js`: `test: { environment: 'node', include: ['src/**/*.test.{ts,tsx}', 'tools/**/*.test.ts'] }`. If editor component tests (`Sidebar.test.tsx`) need jsdom, they already run under the existing per-file `// @vitest-environment jsdom` convention in open-alps — check `head -3 src/tourSearchPage/OfficialTourList.test.tsx` and mirror; add that pragma to `huts/src/gpxEditor/Sidebar.test.tsx` if the copy lacks it. If it needs `vitest-setup.ts` (htp's jest-dom setup), check how open-alps' component tests import matchers and mirror.
  - `huts/tsconfig.json`: `"include": ["src", "tools"]` is enough since it has no `noUncheckedIndexedAccess`; `tools/` uses `node:` imports — `@types/node` is already a devDependency. Skip `tsconfig.tools.json` unless `npm run typecheck` fails on `tools/`; if it does, create `tsconfig.tools.json` (`extends ./tsconfig.json`, `module: NodeNext`, `include: ["tools"]`) and change the `typecheck` script to `tsc --noEmit && tsc --noEmit -p tsconfig.tools.json`.
  - `vite build` builds only `index.html`: leave `vite.config.js` without extra rollup inputs.

- [ ] **Step 3: Drop dev-only test deps that don't exist in open-alps.** `grep -rn "@types/leaflet" huts/package.json` — the editor imports `leaflet` types; add `@types/leaflet` to devDependencies (`cd huts && npm i -D @types/leaflet`) if `npm run typecheck` reports TS7016.

- [ ] **Step 4: Run frontend checks**

```bash
cd ~/open-alps/huts && npm test 2>&1 | tail -20 && npm run typecheck 2>&1 | tail -20 && npm run build 2>&1 | tail -8
cd ../pipeline && pixi run pytest tests/test_snap_cases.py tests/test_gpx_editor_roundtrip.py -v 2>&1 | tail -12
```
Expected: all PASS. The htp editor targets React 18 / react-leaflet 4 / MUI 6; open-alps is React 19 / MUI 9. Fix real type or API breaks (do not silence with `any`); report substantive changes.

- [ ] **Step 5: `test_snap_cases.py`** imports `mte` helpers — confirm it uses `_resolve_endpoint`/`nearest_hub_to_point` names that exist after Task 4 (they do; copied from htp).

- [ ] **Step 6: Commit** — `feat(ui): dev-only GPX editor` (include both pipeline fixtures/tests and huts files; one commit).

---

### Task 11: Frontend — official tours from `tours.json`

**Files:**
- Modify: `huts/src/tourSearch/loadOfficialTours.ts`, `officialTours.ts`, `officialTours.test.ts`, `huts/src/tourSearchPage/TourSearchPage.tsx`, `TourSearchPage.test.tsx`, `OfficialTourList.test.tsx`, `helpers.test.ts`, `huts/src/tourSearch/realData.smoke.test.ts` (only if it references tour payload)
- Delete: `huts/src/tourSearch/loadTourEdges.ts`, `loadTourEdges.test.ts`

**Interfaces:**
- Produces: `RawTourLeg = { legIndex; edgeId: number | null; distanceM?; ascentM?; descentM?; durationS?; maxEleM?; from: RawTourEndpoint | null; to: RawTourEndpoint | null }`, `RawTour = { tourId; name; numDays: number; legs: RawTourLeg[] }`; `buildOfficialTourViews(tours: RawTour[]): OfficialTourView[]` (single argument now); `OfficialTourLeg` without `sacRank`/`viaFerrata`.

- [ ] **Step 1: Rewrite `officialTours.test.ts` first (failing)**

```ts
import { describe, it, expect } from 'vitest'
import { buildOfficialTourViews } from './officialTours.js'
import type { RawTour } from './loadOfficialTours.js'

const scalars = (d: number, up: number, down: number, s: number, max: number) =>
  ({ distanceM: d, ascentM: up, descentM: down, durationS: s, maxEleM: max })

const completeTour: RawTour = {
  tourId: 1, name: 'Welser Höhenweg', numDays: 2,
  legs: [
    { legIndex: 0, edgeId: 0, ...scalars(6000, 800, 100, 7200, 1400), from: { type: 'parking', id: 1 }, to: { type: 'hut', id: 302 } },
    { legIndex: 1, edgeId: 1, ...scalars(10000, 1000, 800, 10800, 2000), from: { type: 'hut', id: 302 }, to: { type: 'hut', id: 376 } },
  ],
}

describe('buildOfficialTourViews', () => {
  it('builds a view from tours.json scalars, using durationS for durationH', () => {
    const [view] = buildOfficialTourViews([completeTour])
    expect(view.legs[0]).toMatchObject({
      legIndex: 0, edgeId: 0, reversed: false, distanceM: 6000, ascentM: 800, descentM: 100,
      durationH: 2, maxEleM: 1400, from: { type: 'parking', id: 1 }, to: { type: 'hut', id: 302 },
    })
    expect(view.legs[0]).not.toHaveProperty('sacRank')
    expect(view.legs[0]).not.toHaveProperty('viaFerrata')
    expect(view.totalDistanceM).toBe(16000)
    expect(view.totalAscentM).toBe(1800)
    expect(view.totalDescentM).toBe(900)
    expect(view.totalDurationH).toBe(5)
  })

  it.each([
    ['null from', { from: null }],
    ['null to', { to: null }],
    ['null edgeId', { edgeId: null }],
  ])('drops a tour with a %s leg entirely', (_name, patch) => {
    const tour: RawTour = { ...completeTour, legs: [completeTour.legs[0], { ...completeTour.legs[1], ...patch }] }
    expect(buildOfficialTourViews([tour])).toHaveLength(0)
  })

  it('drops a tour whose legs.length differs from numDays', () => {
    expect(buildOfficialTourViews([{ ...completeTour, numDays: 3 }])).toHaveLength(0)
  })

  it('keeps a partner_betrieb endpoint', () => {
    const tour: RawTour = {
      tourId: 3, name: 'Mixed', numDays: 1,
      legs: [{ legIndex: 0, edgeId: 0, ...scalars(1000, 10, 20, 900, 900), from: { type: 'hut', id: 1 }, to: { type: 'partner_betrieb', id: 99 } }],
    }
    expect(buildOfficialTourViews([tour])[0].legs[0].to).toEqual({ type: 'partner_betrieb', id: 99 })
  })
})
```

(The old "real shipped payload" block is deleted: `public/data/` is regenerated by the pipeline, and its shape changes only after the user-approved pipeline run in Task 13.)

- [ ] **Step 2: Run** — `cd ~/open-alps/huts && npx vitest run src/tourSearch/officialTours.test.ts 2>&1 | tail -15` → FAIL (signature / `sacRank` present).

- [ ] **Step 3: Implement.**

`loadOfficialTours.ts`:

```ts
export interface RawTourLeg {
  legIndex: number
  edgeId: number | null
  distanceM?: number
  ascentM?: number
  descentM?: number
  durationS?: number
  maxEleM?: number
  from: RawTourEndpoint | null
  to: RawTourEndpoint | null
}

export interface RawTour {
  tourId: number
  name: string
  numDays: number
  legs: RawTourLeg[]
}
```

`officialTours.ts` (drop `dinDurationH` and `TourEdgeRecord` imports; drop `sacRank`/`viaFerrata` from `OfficialTourLeg`):

```ts
export function buildOfficialTourViews(tours: RawTour[]): OfficialTourView[] {
  const views: OfficialTourView[] = []

  for (const tour of tours) {
    if (tour.legs.length !== tour.numDays) continue
    const legs: OfficialTourLeg[] = []
    let complete = true

    for (const leg of tour.legs) {
      if (
        !leg.from || !leg.to || leg.edgeId == null ||
        leg.distanceM == null || leg.ascentM == null || leg.descentM == null ||
        leg.durationS == null || leg.maxEleM == null
      ) {
        complete = false
        break
      }
      legs.push({
        legIndex: leg.legIndex, from: leg.from, to: leg.to, edgeId: leg.edgeId, reversed: false,
        distanceM: leg.distanceM, ascentM: leg.ascentM, descentM: leg.descentM,
        durationH: leg.durationS / 3600, maxEleM: leg.maxEleM,
      })
    }

    if (!complete) continue

    views.push({
      tourId: tour.tourId, name: tour.name, legs,
      totalDistanceM: legs.reduce((s, l) => s + l.distanceM, 0),
      totalAscentM: legs.reduce((s, l) => s + l.ascentM, 0),
      totalDescentM: legs.reduce((s, l) => s + l.descentM, 0),
      totalDurationH: legs.reduce((s, l) => s + l.durationH, 0),
    })
  }

  return views
}
```

`TourSearchPage.tsx`: remove `import { loadTourEdgesData }` (line 23) and `import type { TourEdgeRecord }` (line 26); remove the `tourEdgeRecords` state (line 50), the `loadTourEdgesData()` entry in `Promise.all` and its destructured `tourEdges` name plus `setTourEdgeRecords(tourEdges)` (lines 64–69); the memo at ~182 becomes:

```tsx
    () => (officialTours ? buildOfficialTourViews(officialTours) : null),
    [officialTours],
```

`git rm src/tourSearch/loadTourEdges.ts src/tourSearch/loadTourEdges.test.ts`.

Tests: `TourSearchPage.test.tsx` — delete `emptyTourEdgePayload`/`tourEdgePayload` and every `tour-edge-payload` fetch branch (lines ~12, 82–84, 142–144, 172–174, 231–252); in the official-tour test replace the fixture by

```tsx
    const officialTour = {
      tourId: 1, name: 'Welser Höhenweg', numDays: 1,
      legs: [{ legIndex: 0, edgeId: 0, distanceM: 5000, ascentM: 400, descentM: 100, durationS: 7200,
               maxEleM: 1800, from: { type: 'hut', id: 0 }, to: { type: 'parking', id: 100 } }],
    }
```
`OfficialTourList.test.tsx` and `helpers.test.ts`: remove `sacRank: 3, viaFerrata: false` from the `OfficialTourLeg` literals (lines cited by `grep -n "sacRank" src/tourSearchPage/*.test.*`). Leave `killCounters.viaFerrata` and free-search `sacRank`/`viaFerrata` (`tourSearch/types.ts`, `legFilters.ts`, `HutEdgeRecord`) untouched: they belong to free routing.

- [ ] **Step 4: Run**

```bash
cd ~/open-alps/huts && npm test 2>&1 | tail -20 && npm run typecheck 2>&1 | tail -10 && npm run build 2>&1 | tail -6
grep -rn "loadTourEdges\|tour-edge-payload\|TourEdgeRecord" src | grep -v "^src/gpxEditor"
grep -rn "sacRank\|viaFerrata" src/tourSearch/officialTours.ts src/tourSearch/loadOfficialTours.ts src/tourSearchPage/OfficialTourList.tsx
```
Expected: tests/typecheck/build pass; both greps print nothing.

- [ ] **Step 5: Geometry loaders.** `loadLegGeometry.ts`/`loadLegElevation.ts` keep their formats. Confirm their tests still pass unchanged and that no comment claims tour geometry is simplified: `grep -n "simplif" src/tourSearch/loadLegGeometry.ts src/tourSearch/loadLegElevation.ts` → reword if it applies to tours.

- [ ] **Step 6: Availability diff (reconcile only real improvements).** `diff -r ~/hut-trip-planner/availability ~/open-alps/huts/src/availability | head -60`. Port only genuine bug fixes/improvements with their tests; otherwise leave. Report the outcome.

- [ ] **Step 7: Commit** — `feat(ui): official tours read scalars from tours.json`.

---

### Task 12: Docs and STATUS

**Files:**
- Modify: `pipeline/CLAUDE.md`, `pipeline/phases/graph_building/README.md`, `phases/elevation/README.md`, `phases/postprocessing/README.md`, `pipeline/phases/README.md`, root `.claude/CLAUDE.md` (the "Hut-to-hut routing graph"/"App structure" paragraphs that mention `tour-edge-payload`, `GraphPage`, HMM), `docs/superpowers/STATUS.md`, `docs/backlog.md`
- Create: `docs/superpowers/specs/2026-09-14-gpx-hut-snap-design.md`, `docs/superpowers/specs/2026-09-18-gpx-editor-design.md` (copied from htp)

- [ ] **Step 1: Port the two specs**

```bash
cd ~/open-alps
cp ~/hut-trip-planner/docs/superpowers/specs/{2026-09-14-gpx-hut-snap-design.md,2026-09-18-gpx-editor-design.md} docs/superpowers/specs/
```
Fix references inside them that point to htp-only files (`pipeline-trim-design`) so they don't dangle: `grep -n "pipeline-trim" docs/superpowers/specs/2026-09-1*-*.md`.

- [ ] **Step 2: Update pipeline docs.** In `pipeline/CLAUDE.md` and the three phase READMEs: describe tour matching as GPX+DEM only (endpoints by nearest hub within `graph.maxSnapM`; interior endpoints must be huts; distance/ascent/descent/duration/maxEle/geometry from the trace; `tours.json` with `edgeId`; no base-graph dependency; `profiles.npy` written by `match_tour_edges`; `build_profiles` covers only hut/start edges); document `build_tour_tiles.py` (unsimplified geometry), `check_tour_matching`, `tools/fetch_alpenvereinaktiv_tour.py`, `hubs.json`; note `tourId` is the sorted folder index (six folders now). Remove mentions of `tourMatch.*`, HMM, `tour_meta.npy`, `tour-edge-payload.*`. Fix the stale `pipeline/CLAUDE.md` "Deferred" note mentioned in root `CLAUDE.md` only if trivially adjacent.
  In `.claude/CLAUDE.md` replace the `tour-edge-payload`-adjacent claims (the hut-edge payload list is correct; only remove tour-edge-payload if listed) and add the GPX editor line: dev-only via `npm run dev` → `/gpx-editor.html`, see `docs/gpx-editor.md`.

- [ ] **Step 3: `STATUS.md`.** Mark `2026-08-30-tour-folder-ingestion` → `done (matching superseded by 2026-09-14-gpx-hut-snap)` and `2026-09-01-corridor-hmm-map-matching` → `superseded by 2026-09-14-gpx-hut-snap`; add rows for the two ported specs (`done`) and set the merge spec's row to `done`. Follow the table's existing status wording (`superseded by X`).

- [ ] **Step 4: Backlog + plan cleanup.** Remove the merge task from `docs/backlog.md` if it is listed. Per the repo rule, delete this plan file once the work has shipped (Task 13's end).

- [ ] **Step 5: Verify docs grep** — `grep -rn "hmm_match\|tour_meta\|tour-edge-payload\|tourMatch" pipeline/CLAUDE.md pipeline/phases .claude/CLAUDE.md` → nothing.

- [ ] **Step 6: Commit** — `docs: GPX-only tour matching, port gpx specs, update STATUS`.

---

### Task 13: Final verification and data regeneration (needs user approval)

- [ ] **Step 1: Full test suites**

```bash
cd ~/open-alps/pipeline && pixi run test 2>&1 | tail -8
cd ../huts && npm test 2>&1 | tail -8 && npm run typecheck 2>&1 | tail -4 && npm run build 2>&1 | tail -4
```
Expected: all green (compare against the Task 1 baseline).

- [ ] **Step 2: Wiring check.** `cd ~/open-alps/pipeline && pixi run doit info match_tour_edges 2>&1 | head -40` (read-only: does not execute). Expected: no `build_base_graph`/`snap_hubs`/`compute_edge_profiles` dependency. The wiring tests from Task 5 already assert this; if `doit info` would need to run tasks in your environment, skip it and rely on those tests.

- [ ] **Step 3: Ask the user for permission** to run `pixi run doit match_tour_edges build_tour_edge_tiles check_tour_matching copy_public_data`, stating that it should touch no graph task and that free-routing tasks should stay up to date. Do **not** run without an explicit yes. On approval, run it, then confirm with `pixi run doit info build_base_graph` (or `doit list -s` status) that the graph tasks are still up to date, and open `data/quality/tour_matching.json` to report gap counts (expect new interior-endpoint gaps per the spec's "Stricter endpoint rule" risk; hubs missing from `huts.geojson` such as Heidelberger Hütte).

- [ ] **Step 4: With regenerated data**, run `cd huts && npm test` again and load the app once (only if the user asks for a visual check — see saved feedback: no unrequested dev server/browser): official tours use `tours.json`; `grep -rn "sacRank\|viaFerrata" src/tourSearch/officialTours.ts src/tourSearchPage/OfficialTourList.tsx` empty.

- [ ] **Step 5: Delete this plan file** (work shipped) and commit: `git rm docs/superpowers/plans/2026-09-18-hut-trip-planner-merge.md && git commit -m "docs: remove shipped merge plan"`. Then use superpowers:finishing-a-development-branch.

---

## Self-review notes

- **Spec coverage:** Goals 1–4 → Tasks 4, 5/8, (unchanged free routing verified Task 8/13), 9/10. Decisions (HMM deleted → Task 8; lost fields → Tasks 3/4/11; no RDP → Task 6). Design sections: match_tour_edges (Task 4), binfmt (Tasks 3, 8), DAG wiring (Tasks 5–7), output side (Task 6), deletions (Task 8), quality (Task 7), tooling/data/editor (Tasks 9–10), frontend (Task 11), docs (Task 12), verification (Tasks 5, 8, 13), risks (drift diff in Task 9, availability diff in Task 11, endpoint rule surfaced in Task 13).
- **Spec gap resolved:** the spec never says where profile-integrity for `hut_edges`/`start_edges` lives; `check_elevation` keeps them and `check_tour_matching` reuses `check_profile_integrity` for the tour layer instead of duplicating it.
- **Spec inconsistency flagged:** the spec's "unsnapped-hub flag" in "Ordering §3" has no definition; it maps to htp commit `68e3b61` (`check_gap_reasons` flags every gap with its detail), which arrives with the `check_tour_matching` copy in Task 7.
- **Type consistency:** `edgeId` (`number | null`), `numDays`, `durationS`, `maxEleM` are named identically in Tasks 4, 7, 11; `buildOfficialTourViews` takes one argument in Tasks 11 tests and implementation; `build_stats` loses the tolerance parameter in both the test and script edits of Task 6.
