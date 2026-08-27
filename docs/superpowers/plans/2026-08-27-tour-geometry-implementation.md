# Real trail geometry on the tour search results map — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Do NOT use
> superpowers:subagent-driven-development or spin up any git worktree in this repo** — the root
> `CLAUDE.md` forbids both here (`git worktree remove` has destroyed multi-hour pipeline outputs
> before). Execute every task directly, in-session, on the current checkout/branch.

**Goal:** Render each selected tour's real routed trail (hut-to-hut legs + start/exit approach
legs) on `ResultsMap.tsx`, fetching only the handful of edges the tour actually uses, by splitting
the pipeline's simplified per-edge geometry into a byte-range-fetchable binary file.

**Architecture:** `build_edge_tiles.py` gains a second output pair
(`<layer>-geometry.bin`/`.json`) alongside its existing pmtiles+stats outputs — a flat `f4` lon/lat
point stream plus a `point_counts` manifest a client turns into byte offsets via prefix sum.
`build_approach_table.py` gains an `edge_id` column so start-edge legs (approach/exit) can address
into `start-edge-geometry.bin` the same way hut-edge legs already can via their record's own array
index. The engine threads `edgeId`/`reversed` through every leg-shaped type so `ResultsMap.tsx` can
resolve `(layer, edgeId, reversed)` per leg and `Range`-fetch just those bytes; `GraphPage.tsx`'s
hover feature migrates from `hut-edge-stats.json`'s inline `positions` field to the same new file,
fetched whole (no `Range`) since it needs every edge at once.

**Tech Stack:** Python (pipeline, pytest), TypeScript/React (`huts/`, vitest).

**Spec:** `docs/superpowers/specs/2026-08-27-tour-geometry-design.md`

## Global Constraints

- `f4` (float32) point encoding for all new geometry binaries — ulp ~7 cm lon / ~42 cm lat at
  AT/Bayern latitudes, far under the simplification tolerance.
- `--simplify-tolerance-deg` / `pipeline.config.json`'s `hutEdgeTiles.simplifyToleranceDeg`
  (renamed from `--hover-simplify-tolerance-deg` / `hoverSimplifyToleranceDeg`) stays at its
  current value, `0.0003` — no behavior change to the simplification itself, only naming.
- No new pipeline task, no change to anything upstream of tiling
  (`build_base_graph`/`build_hub_edges`/elevation phases untouched).
- **Never run any `pipeline/` task (`doit`, `pixi run doit`, or any script under `phases/`)
  against real data in this repo without first asking the user and getting explicit
  confirmation.** All pipeline verification in this plan is static (pytest on synthetic fixtures,
  reading the edited files back) — never a real `doit` run.
- Pipeline tests run with `pytest` from the repo root against `pipeline/tests/` (conda/pixi env
  `alpen-osm` assumed active, matching this repo's other plans — e.g.
  `docs/superpowers/plans/2026-08-20-contraction-measurement-spike.md`). If `pytest` isn't on
  `PATH` in the execution environment, ask the user how test commands should be invoked before
  skipping verification.
- Client tests/typecheck/lint run from `huts/`: `npm test`, `npm run typecheck`, `npm run lint`.
- Per this repo's memory on this topic: do not start the Vite dev server or open a browser to
  visually confirm `GraphPage`/`ResultsMap` changes unless the user asks — verify via the test
  suite, typecheck and lint instead.

---

## Task 1: `build_edge_tiles.py` — split geometry out of `<layer>-stats.json`

**Files:**
- Modify: `pipeline/phases/postprocessing/build_edge_tiles.py`
- Modify: `pipeline/tests/test_build_edge_tiles.py`

**Interfaces:**
- Produces: `build_stats(records, geometry, profiles, id_table, simplify_tolerance_deg) -> (stats: list, point_counts: list[int], geometry_points: np.ndarray)` — `stats` no longer has a `"positions"` key; `geometry_points` is an `(N, 2)` `f4` array of every edge's simplified `[lon, lat]` points concatenated in `edge_id` order; `point_counts[i]` is edge `i`'s point count (`geometry_points[sum(point_counts[:i]):sum(point_counts[:i+1])]` is edge `i`'s geometry).
- Produces (CLI): `--out-geometry-bin PATH`, `--out-geometry-json PATH` (new, required), `--simplify-tolerance-deg FLOAT` (renamed from `--hover-simplify-tolerance-deg`, same default `0.0003`).

- [ ] **Step 1: Write the failing tests**

Replace `test_build_stats_resolves_ids_via_id_table` and add two new tests in
`pipeline/tests/test_build_edge_tiles.py` (keep the two `rdp_keep_indices` tests unchanged):

```python
def test_build_stats_resolves_ids_via_id_table():
    records = np.zeros(1, dtype=binfmt.RECORD_DTYPE)
    records[0] = (1, 2, binfmt.TYPE_HUT, binfmt.TYPE_HUT, 0, 1000.0, 0.0, 50.0, 10.0,
                  1500.0, 0.0, 0.0, 0.0, 2, False,
                  0, 2, 0, 3)
    geometry = np.zeros(2, dtype=binfmt.COORD_DTYPE)
    geometry["lon"], geometry["lat"] = [0.0, 0.01], [0.0, 0.0]
    profiles = np.array([1000.0, 1010.0, 1005.0], dtype=binfmt.PROFILE_DTYPE)
    id_table = {"hut:1": "hut-abc", "hut:2": "hut-xyz"}

    stats, point_counts, geometry_points = build_stats(
        records, geometry, profiles, id_table, simplify_tolerance_deg=0.001
    )

    assert len(stats) == 1
    assert "positions" not in stats[0]
    assert stats[0]["from_hut_id"] == "hut-abc"
    assert stats[0]["to_hut_id"] == "hut-xyz"
    assert stats[0]["ascent_m"] == 50.0
    assert stats[0]["elevation_profile"] == [1000.0, 1010.0, 1005.0]
    assert point_counts == [2]
    assert geometry_points.shape == (2, 2)


def test_geometry_bin_byte_layout_matches_point_counts():
    records = np.zeros(2, dtype=binfmt.RECORD_DTYPE)
    records[0] = (1, 2, binfmt.TYPE_HUT, binfmt.TYPE_HUT, 0, 1000.0, 0.0, 50.0, 10.0,
                  1500.0, 0.0, 0.0, 0.0, 2, False, 0, 4, 0, 0)
    records[1] = (2, 3, binfmt.TYPE_HUT, binfmt.TYPE_HUT, 0, 800.0, 0.0, 30.0, 5.0,
                  1400.0, 0.0, 0.0, 0.0, -1, False, 4, 3, 0, 0)
    geometry = np.zeros(7, dtype=binfmt.COORD_DTYPE)
    geometry["lon"] = [0.0, 1.0, 2.0, 3.0, 10.0, 11.0, 12.0]
    geometry["lat"] = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    profiles = np.zeros(0, dtype=binfmt.PROFILE_DTYPE)

    stats, point_counts, geometry_points = build_stats(
        records, geometry, profiles, {}, simplify_tolerance_deg=0.01
    )

    assert len(point_counts) == 2
    geometry_bin = geometry_points.astype("f4").tobytes()
    assert len(geometry_bin) == sum(point_counts) * 8
    # prefix sums land on real point boundaries: each edge's own point_counts[i] entry is
    # exactly the row-count of the slice build_stats appended for that edge.
    offset = 0
    for i, count in enumerate(point_counts):
        edge_points = geometry_points[offset:offset + count]
        assert len(edge_points) == count
        offset += count
    assert offset == len(geometry_points)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest pipeline/tests/test_build_edge_tiles.py -v`
Expected: `test_build_stats_resolves_ids_via_id_table` fails on `TypeError: cannot unpack
non-iterable` (or similar — `build_stats` still returns a plain `list`) and the new
`test_geometry_bin_byte_layout_matches_point_counts` fails the same way.

- [ ] **Step 3: Refactor `build_stats` and the CLI**

In `pipeline/phases/postprocessing/build_edge_tiles.py`, replace `build_stats` (lines 61-102):

```python
def build_stats(records: np.ndarray, geometry: np.ndarray, profiles: np.ndarray, id_table: dict,
                 simplify_tolerance_deg: float) -> tuple:
    inverse_id_table = {}
    for k, v in id_table.items():
        if ":" in k:
            prefix, raw_id = k.split(":", 1)
            inverse_id_table[(prefix, int(raw_id))] = v
        else:
            # filter_start_points.build_id_table's shape: {type: {str(id): {tag: value, ...}}}.
            # The display id was always the numeric id itself (no separate display value), so
            # resolve to that directly instead of the tag dict.
            for raw_id in v:
                inverse_id_table[(k, int(raw_id))] = int(raw_id)

    def resolve(record_id, record_type):
        return inverse_id_table.get((TYPE_PREFIX[record_type], int(record_id)), int(record_id))

    lons, lats = geometry["lon"], geometry["lat"]
    stats = []
    point_counts = []
    all_points = []
    for edge_id in range(len(records)):
        r = records[edge_id]
        g_off, g_count = int(r["geom_offset"]), int(r["geom_count"])
        coords = np.column_stack([lons[g_off:g_off + g_count], lats[g_off:g_off + g_count]])
        keep = rdp_keep_indices(coords, simplify_tolerance_deg)
        simplified = coords[keep]
        point_counts.append(len(simplified))
        all_points.append(simplified)

        p_off, p_count = int(r["profile_offset"]), int(r["profile_count"])
        profile = profiles[p_off:p_off + p_count].tolist() if p_count else []

        stats.append({
            "edge_id": edge_id,
            "from_hut_id": resolve(r["from_id"], r["from_type"]),
            "to_hut_id": resolve(r["to_id"], r["to_type"]),
            "distance_m": float(r["distance_m"]),
            "road_m": float(r["road_m"]),
            "ascent_m": float(r["ascent_m"]) if r["ascent_m"] != binfmt.UNSET else None,
            "descent_m": float(r["descent_m"]) if r["descent_m"] != binfmt.UNSET else None,
            "elevation_profile": profile,
            "sac_scale": int(r["sac_rank"]) if r["sac_rank"] >= 0 else None,
            "via_ferrata": bool(r["via_ferrata"]),
        })
    geometry_points = (
        np.concatenate(all_points, axis=0).astype("f4") if all_points else np.zeros((0, 2), dtype="f4")
    )
    return stats, point_counts, geometry_points
```

Update the `argparse` block (lines 109-119): drop `--hover-simplify-tolerance-deg`, add the new
flags, and fix the stale hardcoded fallback the spec flags (it disagreed with both the config file
and `dodo.py`):

```python
    parser.add_argument("--out-geometry-bin", required=True)
    parser.add_argument("--out-geometry-json", required=True)
    parser.add_argument("--min-zoom", type=int, default=tiles_config.get("minZoom", 6))
    parser.add_argument("--max-zoom", type=int, default=tiles_config.get("maxZoom", 14))
    parser.add_argument("--simplify-tolerance-deg", type=float,
                         default=tiles_config.get("simplifyToleranceDeg", 0.0003))
```

(`--out-tiles`/`--out-stats` stay as they are today.)

Update the `build_stats` call site and add the geometry-file write, right after the existing
`write_stats` block (lines 150-155):

```python
    with timer.step("build_stats"):
        stats, point_counts, geometry_points = build_stats(
            records, geometry, profiles, id_table, args.simplify_tolerance_deg
        )
    print(f"writing {args.out_stats} ...", flush=True)
    with timer.step("write_stats"), open(args.out_stats, "wb") as f:
        f.write(orjson.dumps(stats))

    print(f"writing {args.out_geometry_bin} and {args.out_geometry_json} ...", flush=True)
    with timer.step("write_geometry"):
        Path(args.out_geometry_bin).write_bytes(geometry_points.tobytes())
        with open(args.out_geometry_json, "wb") as f:
            f.write(orjson.dumps({"point_counts": point_counts}))
```

And update the final summary print (line 178):

```python
    print(f"written {args.out_tiles}, {args.out_stats}, {args.out_geometry_bin} and {args.out_geometry_json}")
```

- [ ] **Step 4: Update `pipeline.config.json`**

In `pipeline/pipeline.config.json`, rename the nested key (the `hutEdgeTiles` bucket name itself is
unchanged, only the misnomer'd inner key):

```json
  "hutEdgeTiles": { "minZoom": 6, "maxZoom": 14, "simplifyToleranceDeg": 0.0003 }
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest pipeline/tests/test_build_edge_tiles.py -v`
Expected: all 4 tests (2 existing `rdp_keep_indices` + the 2 above) PASS.

- [ ] **Step 6: Commit**

```bash
git add pipeline/phases/postprocessing/build_edge_tiles.py pipeline/tests/test_build_edge_tiles.py pipeline/pipeline.config.json
git commit -m "feat(pipeline): split simplified edge geometry out of <layer>-stats.json"
```

---

## Task 2: `build_approach_table.py` — add `edge_id` column

**Files:**
- Modify: `pipeline/phases/postprocessing/build_approach_table.py`
- Modify: `pipeline/tests/test_build_approach_table.py`

**Interfaces:**
- Produces: every dict `select_approaches`/`build_tables` build (approach rows, `hut_to_starts`
  entries, `start_to_huts` entries) gains an `"edge_id"` key — the `start_edges/records.npy` row
  index the row came from (not a per-hut counter).
- Produces (on-disk): `approaches.bin` gains a `u4` `edge_id` column; every `reverse_index` row in
  `approaches.json` gains an `edge_id` field.

- [ ] **Step 1: Write the failing tests**

Add to `pipeline/tests/test_build_approach_table.py`:

```python
def test_edge_id_is_the_true_start_edges_row_index():
    records = _records([
        _record(1, binfmt.TYPE_PARKING, 7, 1000.0, 50.0, 20.0),    # row 0
        _record(2, binfmt.TYPE_PARKING, 7, 1100.0, 60.0, 25.0),    # row 1
        _record(10, binfmt.TYPE_STATION, 7, 5000.0, 200.0, 100.0),  # row 2
    ])
    rows = select_approaches(records, id_table={}, k=3)
    by_start_id = {r["start_id"]: r["edge_id"] for r in rows}
    assert by_start_id[1] == 0
    assert by_start_id[2] == 1
    assert by_start_id[10] == 2


def test_edge_id_round_trips_through_build_tables():
    records = _records([
        _record(1, binfmt.TYPE_PARKING, 7, 1000.0, 50.0, 20.0),    # row 0
        _record(10, binfmt.TYPE_STATION, 7, 5000.0, 200.0, 100.0),  # row 1
    ])
    approaches, index = build_tables(records, id_table={}, k=3)
    approach_edge_id = {r["start_id"]: r["edge_id"] for r in approaches}
    assert approach_edge_id[1] == 0
    assert approach_edge_id[10] == 1
    for start_id, expected_edge_id in approach_edge_id.items():
        for row in index["start_to_huts"][start_id]:
            assert row["edge_id"] == expected_edge_id
        matching = [row for row in index["hut_to_starts"][7] if row["start_id"] == start_id]
        assert matching and all(row["edge_id"] == expected_edge_id for row in matching)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest pipeline/tests/test_build_approach_table.py -v`
Expected: both new tests FAIL with `KeyError: 'edge_id'`.

- [ ] **Step 3: Add `edge_id` through `select_approaches` and `build_tables`**

In `pipeline/phases/postprocessing/build_approach_table.py`, change `select_approaches` (line
50-101) to iterate with `enumerate` and carry `edge_id`:

```python
def select_approaches(records: np.ndarray, id_table: dict, k: int) -> list:
    by_hut = defaultdict(list)
    for edge_id, r in enumerate(records):
        if int(r["variant"]) != binfmt.VARIANT_FAST_ANY:
            continue
        type_name = _SOURCE_TYPE_NAME.get(int(r["from_type"]))
        if type_name is None:
            continue

        start_id = int(r["from_id"])
        tags = id_table.get(type_name, {}).get(str(start_id), {})
        access = tags.get("access")
        motor_vehicle = tags.get("motor_vehicle")
        barrier = tags.get("barrier")
        if access in _DROP_ACCESS or motor_vehicle in _DROP_ACCESS or barrier in _DROP_BARRIER:
            continue

        duration_h = speed.din_duration_h(
            float(r["distance_m"]), float(r["ascent_m"]), float(r["descent_m"])
        )
        by_hut[int(r["to_id"])].append({
            "hut_id": int(r["to_id"]),
            "start_id": start_id,
            "source_type": int(r["from_type"]),
            "edge_id": edge_id,
            "access": access,
            "access_unknown": access is None,
            "distance_m": float(r["distance_m"]),
            "ascent_m": float(r["ascent_m"]),
            "descent_m": float(r["descent_m"]),
            "duration_h": duration_h,
        })

    rows = []
    for candidates in by_hut.values():
        candidates.sort(key=lambda c: c["duration_h"])
        selected = candidates[:k]
        present_types = {c["source_type"] for c in selected}
        for source_type in _SOURCE_TYPE_NAME:
            if source_type in present_types:
                continue
            best_other = next(
                (c for c in candidates if c["source_type"] == source_type), None
            )
            if best_other is None:
                continue
            if selected:
                selected[-1] = best_other
            else:
                selected = [best_other]
            present_types.add(source_type)
        rows.extend(selected)
    return rows
```

Change `build_tables` (line 104-127):

```python
def build_tables(records: np.ndarray, id_table: dict, k: int) -> tuple:
    approaches = select_approaches(records, id_table, k)
    retained_start_ids = {row["start_id"] for row in approaches}

    hut_to_starts = defaultdict(list)
    start_to_huts = defaultdict(list)
    for edge_id, r in enumerate(records):
        type_name = _SOURCE_TYPE_NAME.get(int(r["from_type"]))
        if type_name is None:
            continue
        start_id = int(r["from_id"])
        if start_id not in retained_start_ids:
            continue
        hut_id = int(r["to_id"])
        row = {
            "hut_id": hut_id, "start_id": start_id, "source_type": int(r["from_type"]),
            "edge_id": edge_id,
            "variant": int(r["variant"]), "distance_m": float(r["distance_m"]),
            "ascent_m": float(r["ascent_m"]), "descent_m": float(r["descent_m"]),
        }
        hut_to_starts[hut_id].append(row)
        start_to_huts[start_id].append(row)

    index = {"hut_to_starts": dict(hut_to_starts), "start_to_huts": dict(start_to_huts)}
    return approaches, index
```

- [ ] **Step 4: Add the binary column in `__main__`**

In the `columns` dict inside `if __name__ == "__main__":` (lines 151-161), add `edge_id` (u4,
since `start_edges` has 234,918 rows — u2 tops out at 65,536):

```python
        columns = {
            "hut_id": ("u2", np.array([r["hut_id"] for r in approaches], dtype="u2")),
            "start_id": ("u8", np.array([r["start_id"] for r in approaches], dtype="u8")),
            "source_type": ("u1", np.array([r["source_type"] for r in approaches], dtype="u1")),
            "edge_id": ("u4", np.array([r["edge_id"] for r in approaches], dtype="u4")),
            "access_unknown": (
                "u1", np.array([r["access_unknown"] for r in approaches], dtype="u1")
            ),
            "distance_m": ("f4", np.array([r["distance_m"] for r in approaches], dtype="f4")),
            "ascent_m": ("f4", np.array([r["ascent_m"] for r in approaches], dtype="f4")),
            "descent_m": ("f4", np.array([r["descent_m"] for r in approaches], dtype="f4")),
        }
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest pipeline/tests/test_build_approach_table.py -v`
Expected: all 9 tests (7 existing + 2 new) PASS.

- [ ] **Step 6: Commit**

```bash
git add pipeline/phases/postprocessing/build_approach_table.py pipeline/tests/test_build_approach_table.py
git commit -m "feat(pipeline): add edge_id column so approach/exit legs address their geometry"
```

---

## Task 3: `dodo.py` wiring — new targets, renamed flag, `PUBLIC_FILES`

**Files:**
- Modify: `pipeline/dodo.py`

**Interfaces:**
- Consumes: Task 1's `--out-geometry-bin`/`--out-geometry-json`/`--simplify-tolerance-deg` flags;
  Task 2's `edge_id` column (no CLI-visible change needed there, already unconditional).
- Produces: `task_build_hut_edge_tiles`/`task_build_start_edge_tiles` each declare 4 targets
  (pmtiles, stats, geometry-bin, geometry-json); `PUBLIC_FILES` includes all four new geometry
  files and drops `start-edge-stats.json`.

This task has no dedicated test (`pipeline/tests/test_dodo_wiring.py` asserts nothing about
`targets`/`PUBLIC_FILES`, confirmed by reading it — per spec §"Testing"). Verification is static:
a syntax check plus grepping the edited file for the expected strings. **Do not run `doit` or
`pixi run doit`** against this repo's real `data/` — that's the explicit gate from `pipeline/`'s
`CLAUDE.md` and the root `CLAUDE.md`.

- [ ] **Step 1: Update `_hut_edge_tiles_params()`**

In `pipeline/dodo.py`, replace lines 557-564:

```python
def _hut_edge_tiles_params():
    tiles_cfg = CONFIG.get("hutEdgeTiles", {})
    return [
        {"name": "min_zoom", "long": "min-zoom", "type": int, "default": tiles_cfg.get("minZoom", 6)},
        {"name": "max_zoom", "long": "max-zoom", "type": int, "default": tiles_cfg.get("maxZoom", 14)},
        {"name": "simplify_tolerance_deg", "long": "simplify-tolerance-deg",
         "type": float, "default": tiles_cfg.get("simplifyToleranceDeg", 0.0003)},
    ]
```

- [ ] **Step 2: Update `task_build_hut_edge_tiles`**

Replace lines 567-591:

```python
def task_build_hut_edge_tiles():
    return {
        "actions": [
            py(
                "phases/postprocessing/build_edge_tiles.py",
                f"--edges-dir {OSM_DIR / 'hut_edges'}",
                f"--id-table {OSM_DIR / 'start_points_id_table.json'}",
                "--layer-name hut_edges",
                f"--out-tiles {OSM_DIR / 'hut-edges.pmtiles'}",
                f"--out-stats {OSM_DIR / 'hut-edge-stats.json'}",
                f"--out-geometry-bin {OSM_DIR / 'hut-edge-geometry.bin'}",
                f"--out-geometry-json {OSM_DIR / 'hut-edge-geometry.json'}",
                "--min-zoom %(min_zoom)s",
                "--max-zoom %(max_zoom)s",
                "--simplify-tolerance-deg %(simplify_tolerance_deg)s",
            )
        ],
        "params": _hut_edge_tiles_params(),
        # task_dep (not just file_dep) on build_profiles: records.npy's profile_offset/
        # profile_count are rewritten in place by that task but aren't one of its declared
        # targets (see task_build_profiles's comment), so doit's file-hash freshness check alone
        # wouldn't guarantee this task runs after it.
        "task_dep": ["build_profiles"],
        "file_dep": [str(OSM_DIR / "hut_edges" / "records.npy")],
        "targets": [
            str(OSM_DIR / "hut-edges.pmtiles"), str(OSM_DIR / "hut-edge-stats.json"),
            str(OSM_DIR / "hut-edge-geometry.bin"), str(OSM_DIR / "hut-edge-geometry.json"),
        ],
        "uptodate": [TaskOptionsChanged()],
    }
```

- [ ] **Step 3: Update `task_build_start_edge_tiles`**

Replace lines 594-614:

```python
def task_build_start_edge_tiles():
    return {
        "actions": [
            py(
                "phases/postprocessing/build_edge_tiles.py",
                f"--edges-dir {OSM_DIR / 'start_edges'}",
                f"--id-table {OSM_DIR / 'start_points_id_table.json'}",
                "--layer-name start_edges",
                f"--out-tiles {OSM_DIR / 'start-edges.pmtiles'}",
                f"--out-stats {OSM_DIR / 'start-edge-stats.json'}",
                f"--out-geometry-bin {OSM_DIR / 'start-edge-geometry.bin'}",
                f"--out-geometry-json {OSM_DIR / 'start-edge-geometry.json'}",
                "--min-zoom %(min_zoom)s",
                "--max-zoom %(max_zoom)s",
                "--simplify-tolerance-deg %(simplify_tolerance_deg)s",
            )
        ],
        "params": _hut_edge_tiles_params(),
        "task_dep": ["build_profiles"],  # see task_build_hut_edge_tiles's comment
        "file_dep": [str(OSM_DIR / "start_edges" / "records.npy")],
        "targets": [
            str(OSM_DIR / "start-edges.pmtiles"), str(OSM_DIR / "start-edge-stats.json"),
            str(OSM_DIR / "start-edge-geometry.bin"), str(OSM_DIR / "start-edge-geometry.json"),
        ],
        "uptodate": [TaskOptionsChanged()],
    }
```

- [ ] **Step 4: Update `PUBLIC_FILES`**

Replace lines 109-123:

```python
PUBLIC_FILES = [
    "huts.geojson",
    "hut-edges.pmtiles",
    "hut-edge-stats.json",
    "hut-edge-geometry.bin",
    "hut-edge-geometry.json",
    "start-edges.pmtiles",
    "start-edge-geometry.bin",
    "start-edge-geometry.json",
    "trails.pmtiles",
    "stations.geojson",
    "parking.geojson",
    "unsnapped_huts.json",
    "approaches.bin",
    "approaches.json",
    "hut-edge-payload.bin",
    "hut-edge-payload.json",
]
```

(`"start-edge-stats.json"` is deliberately dropped — per spec §G it has never had a client
consumer; `GraphPage.tsx:10` only reads `hut-edge-stats.json`. It still gets built into
`data/osm/`, just no longer copied into `huts/public/data/`.)

- [ ] **Step 5: Static verification**

Run: `python3 -c "import ast; ast.parse(open('pipeline/dodo.py').read())"`
Expected: no output (parses cleanly).

Run: `grep -n "hut-edge-geometry\|start-edge-geometry\|start-edge-stats" pipeline/dodo.py`
Expected: `hut-edge-geometry.bin`/`.json` and `start-edge-geometry.bin`/`.json` each appear twice
(once in a task's `targets`, once in `PUBLIC_FILES`); `start-edge-stats.json` appears only inside
`task_build_start_edge_tiles`'s `actions`/`targets` (as `--out-stats`), never in `PUBLIC_FILES`.

- [ ] **Step 6: Commit**

```bash
git add pipeline/dodo.py
git commit -m "chore(pipeline): wire new edge-geometry outputs into dodo.py and PUBLIC_FILES"
```

---

## Task 4: `loadHutEdges.ts` — populate `edgeId`

**Files:**
- Modify: `huts/src/tourSearch/types.ts`
- Modify: `huts/src/tourSearch/loadHutEdges.ts`
- Modify: `huts/src/tourSearch/loadHutEdges.test.ts`
- Modify: `huts/src/tourSearch/realData.smoke.test.ts`

**Interfaces:**
- Produces: `HutEdgeRecord` gains `edgeId: number` — for `hut_edges`, this is simply the record's
  own index into `hut-edge-payload.bin`'s rows (verified in the spec: `build_edge_payload.py`'s
  `pack_edges` preserves `records.npy` order 1:1), so no new column is needed on the wire.

- [ ] **Step 1: Write the failing test**

In `huts/src/tourSearch/loadHutEdges.test.ts`, extend the `toMatchObject` assertion:

```ts
    expect(data.records[0]).toMatchObject({
      fromIndex: 0, toIndex: 1, variant: 2, distanceM: 1200, ascentM: 300, descentM: 100,
      maxEleM: 2400, sacRank: 3, viaFerrata: true, roadM: 50, ungradedM: 0, inferredM: 200, snapM: 15,
      edgeId: 0,
    })
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd huts && npx vitest run src/tourSearch/loadHutEdges.test.ts`
Expected: FAIL — `data.records[0]` has no `edgeId` property (TypeScript will also fail to compile
once the type below is added first if you reorder steps; add the type in Step 3 below, then this
assertion, to see the intended red state via the runtime `toMatchObject` mismatch).

- [ ] **Step 3: Add the field to the type and the loader**

In `huts/src/tourSearch/types.ts`, add `edgeId: number` to `HutEdgeRecord`:

```ts
export interface HutEdgeRecord {
  fromIndex: number
  toIndex: number
  variant: number
  distanceM: number
  ascentM: number
  descentM: number
  maxEleM: number
  sacRank: number
  viaFerrata: boolean
  roadM: number
  ungradedM: number
  inferredM: number
  snapM: number
  edgeId: number
}
```

In `huts/src/tourSearch/loadHutEdges.ts`, set it from the loop index (the same index
`loadHutEdgesData` already assigns `records[i]` at):

```ts
  const records = new Array<HutEdgeRecord>(manifest.rows)
  for (let i = 0; i < manifest.rows; i++) {
    records[i] = {
      fromIndex: c.from_id[i], toIndex: c.to_id[i], variant: c.variant[i],
      distanceM: c.distance_m[i], ascentM: c.ascent_m[i], descentM: c.descent_m[i],
      maxEleM: c.max_ele_m[i], sacRank: c.sac_rank[i], viaFerrata: c.via_ferrata[i] === 1,
      roadM: c.road_m[i], ungradedM: c.ungraded_m[i], inferredM: c.inferred_m[i], snapM: c.snap_m[i],
      edgeId: i,
    }
  }
```

Mirror the same one-line addition in `huts/src/tourSearch/realData.smoke.test.ts`'s
`loadHutEdgesFromDisk` (its hand-rolled copy of the same loop):

```ts
      roadM: c.road_m[i], ungradedM: c.ungraded_m[i], inferredM: c.inferred_m[i], snapM: c.snap_m[i],
      edgeId: i,
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd huts && npx vitest run src/tourSearch/loadHutEdges.test.ts`
Expected: PASS.

Run: `cd huts && npm run typecheck`
Expected: no errors from `loadHutEdges.ts`/`types.ts`/`realData.smoke.test.ts` (other files will
still fail to typecheck until later tasks land — that's expected mid-plan; re-run the full
typecheck only after Task 11).

- [ ] **Step 5: Commit**

```bash
git add huts/src/tourSearch/types.ts huts/src/tourSearch/loadHutEdges.ts huts/src/tourSearch/loadHutEdges.test.ts huts/src/tourSearch/realData.smoke.test.ts
git commit -m "feat(ui): thread edgeId through HutEdgeRecord"
```

---

## Task 5: `loadApproaches.ts` — read the new `edge_id` column

**Files:**
- Modify: `huts/src/tourSearch/types.ts`
- Modify: `huts/src/tourSearch/loadApproaches.ts`
- Modify: `huts/src/tourSearch/loadApproaches.test.ts`
- Modify: `huts/src/tourSearch/realData.smoke.test.ts`

**Interfaces:**
- Consumes: Task 2's `edge_id` (`u4`) column on `approaches.bin`/`approaches.json`.
- Produces: `ApproachRecord` gains `edgeId: number`, read from column `edge_id`.

- [ ] **Step 1: Write the failing test**

In `huts/src/tourSearch/loadApproaches.test.ts`, add `edge_id` to the `packColumns` call and
assert it round-trips:

```ts
    const { manifest, buffer } = packColumns(
      { hut_id: 'u2', start_id: 'u8', source_type: 'u1', edge_id: 'u4', access_unknown: 'u1', distance_m: 'f4', ascent_m: 'f4', descent_m: 'f4' },
      { hut_id: [15], start_id: [32854131], source_type: [1], edge_id: [4201], access_unknown: [0], distance_m: [19812.6], ascent_m: [746.2], descent_m: [488.2] },
      1,
    )
```

and extend the result assertion:

```ts
    expect(data.records[0]).toMatchObject({
      hutIndex: 15, startId: 32854131, sourceType: 1, accessUnknown: false, edgeId: 4201,
      distanceM: expect.closeTo(19812.6, 1), access: 'customers',
    })
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd huts && npx vitest run src/tourSearch/loadApproaches.test.ts`
Expected: FAIL — `data.records[0].edgeId` is `undefined`.

- [ ] **Step 3: Add the field to the type and the loader**

In `huts/src/tourSearch/types.ts`, add `edgeId: number` to `ApproachRecord`:

```ts
export interface ApproachRecord {
  hutIndex: number
  startId: number
  sourceType: SourceType
  accessUnknown: boolean
  distanceM: number
  ascentM: number
  descentM: number
  access: string | null
  edgeId: number
}
```

In `huts/src/tourSearch/loadApproaches.ts`:

```ts
  const records = new Array<ApproachRecord>(manifest.rows)
  for (let i = 0; i < manifest.rows; i++) {
    records[i] = {
      hutIndex: c.hut_id[i], startId: c.start_id[i], sourceType: c.source_type[i] as ApproachRecord['sourceType'],
      accessUnknown: c.access_unknown[i] === 1, distanceM: c.distance_m[i],
      ascentM: c.ascent_m[i], descentM: c.descent_m[i],
      access: manifest.access_values ? manifest.access_values[i] : null,
      edgeId: c.edge_id[i],
    }
  }
```

- [ ] **Step 4: Guard the real-data smoke test against currently-shipped (pre-rebuild) data**

`huts/src/tourSearch/realData.smoke.test.ts`'s `loadApproachesFromDisk` reads the real
`huts/public/data/approaches.bin`/`.json` shipped today, which was built by the *old*
`build_approach_table.py` and has no `edge_id` column yet (Task 2's pipeline change hasn't been
run against real data — that's gated on explicit user confirmation per this plan's Global
Constraints). Without a guard, `c.edge_id[i]` throws (`c.edge_id` is `undefined`) and breaks every
other test in this file. Guard it — this is a real, currently-true condition, not a hypothetical:

```ts
function loadApproachesFromDisk(): ApproachesData {
  const manifest = JSON.parse(readFileSync(`${DATA_DIR}approaches.json`, 'utf-8'))
  const buffer = readFileSync(`${DATA_DIR}approaches.bin`).buffer as ArrayBuffer
  const c = readColumns(buffer, manifest)
  const records = new Array<ApproachRecord>(manifest.rows)
  for (let i = 0; i < manifest.rows; i++) {
    records[i] = {
      hutIndex: c.hut_id[i], startId: c.start_id[i], sourceType: c.source_type[i] as ApproachRecord['sourceType'],
      accessUnknown: c.access_unknown[i] === 1, distanceM: c.distance_m[i],
      ascentM: c.ascent_m[i], descentM: c.descent_m[i],
      access: manifest.access_values ? manifest.access_values[i] : null,
      // approaches.bin predating this plan's Task 2 has no edge_id column - guard until
      // huts/public/data/ is rebuilt by a (separately gated) doit run.
      edgeId: c.edge_id ? c.edge_id[i] : -1,
    }
  }
  return { records, reverseIndex: manifest.reverse_index }
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd huts && npx vitest run src/tourSearch/loadApproaches.test.ts src/tourSearch/realData.smoke.test.ts`
Expected: `loadApproaches.test.ts` PASSes. `realData.smoke.test.ts` PASSes with the same result as
before this task (it makes no assertions about `edgeId`, so the `-1` sentinel is invisible to it).

- [ ] **Step 6: Commit**

```bash
git add huts/src/tourSearch/types.ts huts/src/tourSearch/loadApproaches.ts huts/src/tourSearch/loadApproaches.test.ts huts/src/tourSearch/realData.smoke.test.ts
git commit -m "feat(ui): thread edgeId through ApproachRecord"
```

---

## Task 6: `reverseLeg.ts` — propagate `edgeId` and set `reversed`

**Files:**
- Modify: `huts/src/tourSearch/types.ts`
- Modify: `huts/src/tourSearch/reverseLeg.ts`
- Modify: `huts/src/tourSearch/reverseLeg.test.ts`

**Interfaces:**
- Consumes: `HutEdgeRecord.edgeId`/`ApproachRecord.edgeId` (Tasks 4-5).
- Produces: `HutLeg`/`StartLeg` gain `edgeId: number` (copied through unchanged) and
  `reversed: boolean` (`false` from `forward*`, `true` from `reverse*`).

- [ ] **Step 1: Write the failing tests**

In `huts/src/tourSearch/reverseLeg.test.ts`, add `edgeId` to both fixtures and assert the new
fields:

```ts
const record: HutEdgeRecord = {
  fromIndex: 0, toIndex: 1, variant: 2, distanceM: 8000, ascentM: 600, descentM: 500,
  maxEleM: 2400, sacRank: 3, viaFerrata: false, roadM: 100, ungradedM: 0, inferredM: 50, snapM: 5,
  edgeId: 42,
}

describe('reverseHutLeg', () => {
  it('swaps ascent/descent, swaps endpoints, recomputes duration, and leaves everything else unchanged', () => {
    const reversed = reverseHutLeg(record)
    expect(reversed.fromIndex).toBe(1)
    expect(reversed.toIndex).toBe(0)
    expect(reversed.ascentM).toBe(500)
    expect(reversed.descentM).toBe(600)
    expect(reversed.durationH).toBeCloseTo(3.8667, 3)
    expect(reversed.edgeId).toBe(42)
    expect(reversed.reversed).toBe(true)
    const fields: (keyof HutEdgeRecord)[] = ['distanceM', 'roadM', 'sacRank', 'viaFerrata', 'maxEleM', 'ungradedM', 'inferredM']
    for (const field of fields) {
      expect(reversed[field]).toEqual(record[field])
    }
  })
})

describe('forwardHutLeg', () => {
  it('computes duration without altering any other field', () => {
    const forward = forwardHutLeg(record)
    expect(forward.ascentM).toBe(600)
    expect(forward.descentM).toBe(500)
    expect(forward.durationH).toBeCloseTo(4.0, 6)
    expect(forward.edgeId).toBe(42)
    expect(forward.reversed).toBe(false)
  })
})

describe('start-edge reversal (approach/exit)', () => {
  const approach: ApproachRecord = {
    hutIndex: 15, startId: 32854131, sourceType: SOURCE_TYPE_STATION, accessUnknown: false,
    distanceM: 4000, ascentM: 300, descentM: 100, access: null, edgeId: 7,
  }

  it('forwardStartLeg computes duration in the stored (start->hut) direction', () => {
    expect(forwardStartLeg(approach).durationH).toBeCloseTo(1.7, 3)
    expect(forwardStartLeg(approach).edgeId).toBe(7)
    expect(forwardStartLeg(approach).reversed).toBe(false)
  })

  it('reverseStartLeg swaps ascent/descent for the hut->start (exit) direction', () => {
    const exit = reverseStartLeg(approach)
    expect(exit.ascentM).toBe(100)
    expect(exit.descentM).toBe(300)
    expect(exit.startId).toBe(32854131)
    expect(exit.edgeId).toBe(7)
    expect(exit.reversed).toBe(true)
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd huts && npx vitest run src/tourSearch/reverseLeg.test.ts`
Expected: FAIL — `.reversed` is `undefined` on every leg (and the file won't even typecheck yet
since `HutLeg`/`StartLeg` don't have `reversed`/the fixtures' extra `edgeId` field is unused by
the current type — add the types in Step 3 first if your tool run order requires green-to-red-to-green).

- [ ] **Step 3: Add the fields to the types and the functions**

In `huts/src/tourSearch/types.ts`, add `edgeId`/`reversed` to `HutLeg` and `StartLeg`:

```ts
export interface HutLeg extends LegBase {
  fromIndex: number
  toIndex: number
  variant: number
  maxEleM: number
  sacRank: number
  viaFerrata: boolean
  roadM: number
  ungradedM: number
  inferredM: number
  snapM: number
  edgeId: number
  reversed: boolean
}

export interface StartLeg extends LegBase {
  startId: number
  sourceType: SourceType
  hutIndex?: number
  accessUnknown?: boolean
  access?: string | null
  edgeId: number
  reversed: boolean
}
```

In `huts/src/tourSearch/reverseLeg.ts` (the `...record` spread already carries `edgeId` through
from `HutEdgeRecord`/`ApproachRecord`, so only `reversed` needs adding explicitly):

```ts
export function reverseHutLeg(record: HutEdgeRecord): HutLeg {
  return withDuration({
    ...record,
    fromIndex: record.toIndex,
    toIndex: record.fromIndex,
    ascentM: record.descentM,
    descentM: record.ascentM,
    reversed: true,
  })
}

export function forwardHutLeg(record: HutEdgeRecord): HutLeg {
  return withDuration({ ...record, reversed: false })
}

export function reverseStartLeg(record: ApproachRecord): StartLeg {
  return withDuration({ ...record, ascentM: record.descentM, descentM: record.ascentM, reversed: true })
}

export function forwardStartLeg(record: ApproachRecord): StartLeg {
  return withDuration({ ...record, reversed: false })
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd huts && npx vitest run src/tourSearch/reverseLeg.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add huts/src/tourSearch/types.ts huts/src/tourSearch/reverseLeg.ts huts/src/tourSearch/reverseLeg.test.ts
git commit -m "feat(ui): thread edgeId/reversed through HutLeg/StartLeg"
```

---

## Task 7: `approaches.ts` — thread `edge_id` through exit legs

**Files:**
- Modify: `huts/src/tourSearch/types.ts`
- Modify: `huts/src/tourSearch/approaches.ts`
- Modify: `huts/src/tourSearch/approaches.test.ts`

**Interfaces:**
- Consumes: `ReverseIndexEntry.edge_id` (new field, this task), `reverseStartLeg` (Task 6).
- Produces: `getExitLegs` synthesizes an `ApproachRecord` with `edgeId` populated from the reverse
  index entry, so its resulting `StartLeg.edgeId` is correct. **This is the spec's flagged trap:**
  exit legs are not built from `loadApproachesData`'s records — `getExitLegs` builds an
  `ApproachRecord` field-by-field from `reverseIndex.hut_to_starts` entries, so Task 5's change to
  `loadApproaches.ts` does not cover this path.

- [ ] **Step 1: Write the failing test**

In `huts/src/tourSearch/approaches.test.ts`, add `edge_id` to the `hut_to_starts` fixture entries
and assert it lands on the resulting leg:

```ts
const approachesData: ApproachesData = {
  records: [
    { hutIndex: 15, startId: 32854131, sourceType: SOURCE_TYPE_STATION, accessUnknown: false, distanceM: 19812, ascentM: 746, descentM: 488, access: null, edgeId: 1000 },
    { hutIndex: 16, startId: 999, sourceType: SOURCE_TYPE_PARKING, accessUnknown: false, distanceM: 3000, ascentM: 200, descentM: 100, access: null, edgeId: 1001 },
  ],
  reverseIndex: {
    hut_to_starts: {
      15: [
        { hut_id: 15, start_id: 32854131, source_type: SOURCE_TYPE_STATION, variant: 0, distance_m: 19812, ascent_m: 746, descent_m: 488, edge_id: 55001 },
        { hut_id: 15, start_id: 32854131, source_type: SOURCE_TYPE_STATION, variant: 1, distance_m: 20500, ascent_m: 760, descent_m: 500, edge_id: 55002 },
        { hut_id: 15, start_id: 40000000, source_type: SOURCE_TYPE_STATION, variant: 0, distance_m: 9000, ascent_m: 300, descent_m: 250, edge_id: 55003 },
      ],
    },
    start_to_huts: {},
  },
}
```

and add an assertion in `getExitLegs`'s describe block:

```ts
  it('threads edge_id from the reverse-index entry onto the synthesized exit leg', () => {
    const legs = getExitLegs(15, 0, approachesData)
    const toOrigin = legs.find((l) => l.startId === 32854131)
    expect(toOrigin?.edgeId).toBe(55001)
    const toOther = legs.find((l) => l.startId === 40000000)
    expect(toOther?.edgeId).toBe(55003)
  })
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd huts && npx vitest run src/tourSearch/approaches.test.ts`
Expected: FAIL — `toOrigin?.edgeId` is `undefined`.

- [ ] **Step 3: Add `edge_id` to `ReverseIndexEntry` and thread it through `getExitLegs`**

In `huts/src/tourSearch/types.ts`:

```ts
export interface ReverseIndexEntry {
  hut_id: number
  start_id: number
  source_type: SourceType
  variant: number
  distance_m: number
  ascent_m: number
  descent_m: number
  edge_id: number
}
```

In `huts/src/tourSearch/approaches.ts`:

```ts
export function getExitLegs(hutIndex: number, variant: number, approachesData: ApproachesData): StartLeg[] {
  const entries = approachesData.reverseIndex.hut_to_starts[String(hutIndex)] || []
  return entries
    .filter((r) => r.variant === variant)
    .map((r) =>
      reverseStartLeg({
        hutIndex,
        startId: r.start_id,
        sourceType: r.source_type,
        edgeId: r.edge_id,
        accessUnknown: false,
        distanceM: r.distance_m,
        ascentM: r.ascent_m,
        descentM: r.descent_m,
        access: null,
      }),
    )
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd huts && npx vitest run src/tourSearch/approaches.test.ts`
Expected: PASS (all tests in the file, including the new one).

- [ ] **Step 5: Commit**

```bash
git add huts/src/tourSearch/types.ts huts/src/tourSearch/approaches.ts huts/src/tourSearch/approaches.test.ts
git commit -m "fix(ui): thread edge_id from the reverse index onto synthesized exit legs"
```

---

## Task 8: `search.ts` — carry `edgeId`/`reversed` into `LegSummary`

**Files:**
- Modify: `huts/src/tourSearch/types.ts`
- Modify: `huts/src/tourSearch/search.ts`
- Modify: `huts/src/tourSearch/search.test.ts`

**Interfaces:**
- Consumes: `HutLeg.edgeId`/`.reversed`, `StartLeg.edgeId`/`.reversed` (Task 6).
- Produces: `LegSummary` (and therefore `TourResult.legs`, which is typed `LegSummary[]` and needs
  no separate edit) gains `edgeId: number` and `reversed: boolean`. Purely mechanical threading —
  dominance pruning, filters, and sort order are untouched; these fields are never compared or
  branched on inside `search.ts`.

- [ ] **Step 1: Write the failing test**

In `huts/src/tourSearch/search.test.ts`, extend the top-of-file `edge()` helper (used by the main
describe blocks) to carry `edgeId`:

```ts
function edge(fromIndex: number, toIndex: number, distanceM: number) {
  return { fromIndex, toIndex, variant: 0, distanceM, ascentM: 200, descentM: 200, maxEleM: 2000, sacRank: 1, viaFerrata: false, roadM: 0, ungradedM: 0, inferredM: 0, snapM: 0, edgeId: fromIndex * 100 + toIndex }
}
```

add `edgeId` to the top-level `graphData.approaches.records` and `edge_id` to its
`reverseIndex.hut_to_starts` entries:

```ts
  approaches: {
    records: [
      { hutIndex: 0, startId: 100, sourceType: 1, accessUnknown: false, distanceM: 2000, ascentM: 100, descentM: 50, access: null, edgeId: 9000 },
    ],
    reverseIndex: {
      hut_to_starts: {
        2: [{ hut_id: 2, start_id: 200, source_type: 1, variant: 0, distance_m: 2000, ascent_m: 50, descent_m: 100, edge_id: 9001 }],
```

and add a dedicated assertion near the existing `full?.legs` check (around line 158):

```ts
    expect(full?.legs).toHaveLength(4)
    expect(full?.legs[0]).toMatchObject({ edgeId: 9000, reversed: false })
    const summedDuration = full!.legs.reduce((sum, l) => sum + l.durationH, 0)
    expect(summedDuration).toBeCloseTo(full!.totalDurationH, 6)
```

Also update the diamond-graph fixture's local `edge()` helper (inside the `'dominance pruning
(Section B) is exact'` describe block, ~line 273) and its `approaches`/`reverseIndex` literals, and
the second `reverseIndex` literal used by the car-mode test (~line 170), the same way — add
`edgeId`/`edge_id` values (any distinct numbers; they're not asserted on in those blocks, only
needed for the file to typecheck):

```ts
  function edge(fromIndex: number, toIndex: number, distanceM: number) {
    return { fromIndex, toIndex, variant: 0, distanceM, ascentM: 100, descentM: 100, maxEleM: 2000, sacRank: 1, viaFerrata: false, roadM: 0, ungradedM: 0, inferredM: 0, snapM: 0, edgeId: fromIndex * 100 + toIndex }
  }
```

```ts
      records: [{ hutIndex: 0, startId: 100, sourceType: SOURCE_TYPE_STATION, accessUnknown: false, distanceM: 1000, ascentM: 50, descentM: 20, access: null, edgeId: 8000 }],
      reverseIndex: {
        hut_to_starts: {
          3: [{ hut_id: 3, start_id: 200, source_type: SOURCE_TYPE_STATION, variant: 0, distance_m: 1000, ascent_m: 20, descent_m: 50, edge_id: 8001 }],
        },
```

```ts
          hut_to_starts: {
            2: [{ hut_id: 2, start_id: 100, source_type: SOURCE_TYPE_STATION, variant: 0, distance_m: 2000, ascent_m: 50, descent_m: 100, edge_id: 8002 }],
          },
```

Finally, `bruteForceSearchChains`'s own local `legSummary` helper (the reference implementation
that lives only in this test file) must keep typechecking against the now-wider `LegSummary` type:

```ts
  function legSummary(leg: { durationH: number; ascentM: number; descentM: number; distanceM: number; edgeId: number; reversed: boolean }): LegSummary {
    return { durationH: leg.durationH, ascentM: leg.ascentM, descentM: leg.descentM, distanceM: leg.distanceM, edgeId: leg.edgeId, reversed: leg.reversed }
  }
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd huts && npx vitest run src/tourSearch/search.test.ts`
Expected: FAIL to compile/run — `LegSummary` doesn't have `edgeId`/`reversed` yet, and
`full?.legs[0]` doesn't have them either.

- [ ] **Step 3: Add the fields to `LegSummary` and `legSummary()`**

In `huts/src/tourSearch/types.ts`:

```ts
export interface LegSummary {
  durationH: number
  ascentM: number
  descentM: number
  distanceM: number
  edgeId: number
  reversed: boolean
}
```

In `huts/src/tourSearch/search.ts`:

```ts
  function legSummary(leg: { durationH: number; ascentM: number; descentM: number; distanceM: number; edgeId: number; reversed: boolean }): LegSummary {
    return { durationH: leg.durationH, ascentM: leg.ascentM, descentM: leg.descentM, distanceM: leg.distanceM, edgeId: leg.edgeId, reversed: leg.reversed }
  }
```

(`TourResult.legs: LegSummary[]` in `types.ts` needs no separate edit — it already picks up the
new fields through the `LegSummary` type.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd huts && npx vitest run src/tourSearch/search.test.ts`
Expected: PASS.

Run: `cd huts && npx vitest run src/tourSearch/`
Expected: every test in `tourSearch/` PASSes (this exercises `adjacency.test.ts`,
`diversity.test.ts`, `index.test.ts`, `dinDuration.test.ts`, `binaryColumns.test.ts`,
`resolveVariant.test.ts`, `legFilters.test.ts` too — none of them construct the changed types with
literals, so they should already be green from Tasks 4-7, but confirm here).

- [ ] **Step 5: Commit**

```bash
git add huts/src/tourSearch/types.ts huts/src/tourSearch/search.ts huts/src/tourSearch/search.test.ts
git commit -m "feat(ui): carry edgeId/reversed through LegSummary and TourResult.legs"
```

---

## Task 9: `loadLegGeometry.ts` — byte-range leg geometry fetch (new)

**Files:**
- Create: `huts/src/tourSearch/loadLegGeometry.ts`
- Create: `huts/src/tourSearch/loadLegGeometry.test.ts`

**Interfaces:**
- Consumes: `<layer>-geometry.json` (`{ point_counts: number[] }`) and `<layer>-geometry.bin`
  (flat `f4` lon/lat pairs, `edge_id` order) — Task 1/3's pipeline outputs.
- Produces:
  - `type GeometryLayer = 'hut_edges' | 'start_edges'`
  - `loadLegGeometry(layer: GeometryLayer, edgeId: number, reversed: boolean, baseUrl?: string): Promise<[number, number][]>` — resolves to `[lat, lng]` pairs (matching `ResultsMap`'s existing convention), reversed if requested, cached per `` `${layer}:${edgeId}` ``.
  - `_resetLegGeometryCachesForTests(): void` — test-only cache reset (no production caller).

- [ ] **Step 1: Write the failing tests**

Create `huts/src/tourSearch/loadLegGeometry.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { loadLegGeometry, _resetLegGeometryCachesForTests } from './loadLegGeometry.js'

// [lon, lat] pairs per synthetic edge, matching the pipeline's on-disk point order.
const EDGE0: [number, number][] = [[11.0, 47.0], [11.1, 47.1]]
const EDGE1: [number, number][] = [[12.0, 48.0], [12.1, 48.1], [12.2, 48.2]]
const MANIFEST = { point_counts: [EDGE0.length, EDGE1.length] }

function makeBinary(edges: [number, number][][]): ArrayBuffer {
  const points = edges.flat()
  const buffer = new ArrayBuffer(points.length * 8)
  const view = new DataView(buffer)
  points.forEach(([lon, lat], i) => {
    view.setFloat32(i * 8, lon, true)
    view.setFloat32(i * 8 + 4, lat, true)
  })
  return buffer
}

const BINARY = makeBinary([EDGE0, EDGE1])

beforeEach(() => _resetLegGeometryCachesForTests())
afterEach(() => vi.unstubAllGlobals())

describe('loadLegGeometry', () => {
  it('builds the prefix-sum offset table from the manifest and range-fetches the right bytes', async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (url === '/data/hut-edge-geometry.json') {
        return Promise.resolve({ json: () => Promise.resolve(MANIFEST) } as Response)
      }
      if (url === '/data/hut-edge-geometry.bin') {
        // edge_id=1 starts after edge 0's 2 points (16 bytes) and is 3 points (24 bytes) long.
        expect(init?.headers).toMatchObject({ Range: 'bytes=16-39' })
        return Promise.resolve({
          status: 206,
          arrayBuffer: () => Promise.resolve(BINARY.slice(16, 40)),
        } as Response)
      }
      throw new Error(`unexpected fetch ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    const points = await loadLegGeometry('hut_edges', 1, false)

    expect(points).toEqual([[48.0, 12.0], [48.1, 12.1], [48.2, 12.2]])
  })

  it('reverses point order when reversed is true, without mutating the cached forward result', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.endsWith('.json')) return Promise.resolve({ json: () => Promise.resolve(MANIFEST) } as Response)
      return Promise.resolve({ status: 206, arrayBuffer: () => Promise.resolve(BINARY.slice(0, 16)) } as Response)
    }))

    const forward = await loadLegGeometry('hut_edges', 0, false)
    const reversed = await loadLegGeometry('hut_edges', 0, true)

    expect(forward).toEqual([[47.0, 11.0], [47.1, 11.1]])
    expect(reversed).toEqual([[47.1, 11.1], [47.0, 11.0]])
  })

  it('caches by edgeId so a repeated lookup does not refetch', async () => {
    const fetchMock = vi.fn((url: string) => {
      if (url.endsWith('.json')) return Promise.resolve({ json: () => Promise.resolve(MANIFEST) } as Response)
      return Promise.resolve({ status: 206, arrayBuffer: () => Promise.resolve(BINARY.slice(0, 16)) } as Response)
    })
    vi.stubGlobal('fetch', fetchMock)

    await loadLegGeometry('hut_edges', 0, false)
    await loadLegGeometry('hut_edges', 0, false)
    await loadLegGeometry('hut_edges', 0, true)

    const manifestCalls = fetchMock.mock.calls.filter(([url]) => (url as string).endsWith('.json'))
    const binCalls = fetchMock.mock.calls.filter(([url]) => (url as string).endsWith('.bin'))
    expect(manifestCalls).toHaveLength(1)
    expect(binCalls).toHaveLength(1)
  })

  it('falls back to slicing the full body when the server ignores Range and answers 200', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.endsWith('.json')) return Promise.resolve({ json: () => Promise.resolve(MANIFEST) } as Response)
      return Promise.resolve({ status: 200, arrayBuffer: () => Promise.resolve(BINARY) } as Response)
    }))

    const points = await loadLegGeometry('hut_edges', 1, false)

    expect(points).toEqual([[48.0, 12.0], [48.1, 12.1], [48.2, 12.2]])
  })

  it('after one 200 fallback, a later leg on the same layer reuses the whole-file buffer instead of refetching it', async () => {
    let binFetchCount = 0
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.endsWith('.json')) return Promise.resolve({ json: () => Promise.resolve(MANIFEST) } as Response)
      binFetchCount++
      return Promise.resolve({ status: 200, arrayBuffer: () => Promise.resolve(BINARY) } as Response)
    }))

    await loadLegGeometry('hut_edges', 0, false)
    await loadLegGeometry('hut_edges', 1, false)

    expect(binFetchCount).toBe(1)
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd huts && npx vitest run src/tourSearch/loadLegGeometry.test.ts`
Expected: FAIL with a module-not-found error (`loadLegGeometry.ts` doesn't exist yet).

- [ ] **Step 3: Write `loadLegGeometry.ts`**

Create `huts/src/tourSearch/loadLegGeometry.ts`:

```ts
/**
 * Byte-range-fetchable per-edge trail geometry (docs/superpowers/specs/2026-08-27-tour-geometry-design.md
 * §A/§E): <layer>-geometry.bin is every edge's simplified [lon, lat] points, back to back in
 * edge_id order, each point an f4 pair (8 bytes, no framing) - <layer>-geometry.json's
 * point_counts gives each edge's point count, from which a byte range is a prefix sum.
 */
export type GeometryLayer = 'hut_edges' | 'start_edges'

interface GeometryManifest {
  point_counts: number[]
}

interface LayerState {
  offsets: number[] // length point_counts.length + 1, in points (not bytes)
  // Set once a host is discovered to ignore Range and answer 200 with the whole body - every
  // later leg on this layer reuses it instead of re-downloading the whole file (spec §E).
  wholeFileFetch: Promise<ArrayBuffer> | null
}

const POINT_BYTES = 8 // f4 lon + f4 lat

const LAYER_FILES: Record<GeometryLayer, { json: string; bin: string }> = {
  hut_edges: { json: 'hut-edge-geometry.json', bin: 'hut-edge-geometry.bin' },
  start_edges: { json: 'start-edge-geometry.json', bin: 'start-edge-geometry.bin' },
}

let manifestCache = new Map<GeometryLayer, Promise<LayerState>>()
let legCache = new Map<string, Promise<[number, number][]>>()

function loadLayerState(layer: GeometryLayer, baseUrl: string): Promise<LayerState> {
  let cached = manifestCache.get(layer)
  if (!cached) {
    cached = (async () => {
      const manifest: GeometryManifest = await (await fetch(`${baseUrl}/${LAYER_FILES[layer].json}`)).json()
      const offsets = new Array<number>(manifest.point_counts.length + 1)
      offsets[0] = 0
      for (let i = 0; i < manifest.point_counts.length; i++) {
        offsets[i + 1] = offsets[i] + manifest.point_counts[i]
      }
      return { offsets, wholeFileFetch: null }
    })()
    manifestCache.set(layer, cached)
  }
  return cached
}

function decodePoints(buffer: ArrayBuffer, byteOffset: number, pointCount: number): [number, number][] {
  const view = new DataView(buffer, byteOffset, pointCount * POINT_BYTES)
  const points: [number, number][] = new Array(pointCount)
  for (let i = 0; i < pointCount; i++) {
    const lon = view.getFloat32(i * POINT_BYTES, true)
    const lat = view.getFloat32(i * POINT_BYTES + 4, true)
    points[i] = [lat, lon]
  }
  return points
}

async function fetchLegPoints(layer: GeometryLayer, edgeId: number, baseUrl: string): Promise<[number, number][]> {
  const state = await loadLayerState(layer, baseUrl)
  const startPoint = state.offsets[edgeId]
  const pointCount = state.offsets[edgeId + 1] - startPoint
  const byteStart = startPoint * POINT_BYTES
  const byteEnd = byteStart + pointCount * POINT_BYTES - 1

  if (state.wholeFileFetch) {
    return decodePoints(await state.wholeFileFetch, byteStart, pointCount)
  }

  const url = `${baseUrl}/${LAYER_FILES[layer].bin}`
  const res = await fetch(url, { headers: { Range: `bytes=${byteStart}-${byteEnd}` } })
  if (res.status === 206) {
    return decodePoints(await res.arrayBuffer(), 0, pointCount)
  }

  // Host ignored Range and answered 200 with the entire body - do not retry with another Range
  // request. Decode this leg out of the full body, and cache the full body itself so this
  // (large) download happens at most once per layer per session.
  if (!state.wholeFileFetch) state.wholeFileFetch = res.arrayBuffer()
  return decodePoints(await state.wholeFileFetch, byteStart, pointCount)
}

export async function loadLegGeometry(
  layer: GeometryLayer,
  edgeId: number,
  reversed: boolean,
  baseUrl = '/data',
): Promise<[number, number][]> {
  const cacheKey = `${layer}:${edgeId}`
  let cached = legCache.get(cacheKey)
  if (!cached) {
    cached = fetchLegPoints(layer, edgeId, baseUrl)
    legCache.set(cacheKey, cached)
  }
  const points = await cached
  return reversed ? [...points].reverse() : points
}

export function _resetLegGeometryCachesForTests(): void {
  manifestCache = new Map()
  legCache = new Map()
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd huts && npx vitest run src/tourSearch/loadLegGeometry.test.ts`
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add huts/src/tourSearch/loadLegGeometry.ts huts/src/tourSearch/loadLegGeometry.test.ts
git commit -m "feat(ui): add byte-range per-leg trail geometry loader"
```

---

## Task 10: `ResultsMap.tsx` — render real trail geometry per leg

**Files:**
- Modify: `huts/src/tourSearchPage/ResultsMap.tsx`
- Create: `huts/src/tourSearchPage/ResultsMap.test.tsx`

**Interfaces:**
- Consumes: `loadLegGeometry` (Task 9), `TourResult.legs[i].edgeId`/`.reversed` (Task 8).

This task renders each leg as its own `<Polyline>` segment (real geometry once resolved, a
straight dashed fallback otherwise) rather than concatenating into a single polyline — visually
identical to one continuous line (abutting segments share endpoints), but lets each leg switch
from fallback to real independently as its own fetch resolves, exactly matching the spec's
per-leg "while a leg's fetch is in flight... render a straight dashed segment" requirement without
needing to wait for every leg before showing any real geometry.

- [ ] **Step 1: Write the failing tests**

Create `huts/src/tourSearchPage/ResultsMap.test.tsx`:

```tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import ResultsMap from './ResultsMap.js'
import * as loadLegGeometryModule from '../tourSearch/loadLegGeometry.js'
import type { TourResult } from '../tourSearch/types.js'
import type { StartPoint } from './types.js'

afterEach(() => vi.restoreAllMocks())

const chain: TourResult = {
  huts: [0], startId: 100, exitStartId: 200,
  totalDurationH: 3, totalAscentM: 300, totalDescentM: 300, totalDistanceM: 6000,
  legs: [
    { durationH: 1.5, ascentM: 150, descentM: 150, distanceM: 3000, edgeId: 5, reversed: false },
    { durationH: 1.5, ascentM: 150, descentM: 150, distanceM: 3000, edgeId: 6, reversed: true },
  ],
}

const hutNameById = new Map([[0, 'HutA']])
const hutCoordsById = new Map([[0, { lat: 47.1, lng: 11.1 }]])
const startById = new Map<number, StartPoint>([
  [100, { name: 'Start', sourceType: 2, lat: 47.0, lng: 11.0 }],
  [200, { name: 'End', sourceType: 2, lat: 47.2, lng: 11.2 }],
])

function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

const CAPTION = 'Schematische Verbindung, nicht der reale Wegverlauf.'

describe('ResultsMap real geometry integration', () => {
  it('resolves (layer, edgeId, reversed) per leg, keeps the caption while any leg is still a fallback, and hides it once every leg resolves', async () => {
    const d0 = deferred<[number, number][]>()
    const d1 = deferred<[number, number][]>()
    const spy = vi
      .spyOn(loadLegGeometryModule, 'loadLegGeometry')
      .mockImplementationOnce(() => d0.promise)
      .mockImplementationOnce(() => d1.promise)

    render(<ResultsMap selectedChain={chain} hutNameById={hutNameById} hutCoordsById={hutCoordsById} startById={startById} />)

    expect(screen.getByText(CAPTION)).toBeInTheDocument()
    expect(spy).toHaveBeenNthCalledWith(1, 'start_edges', 5, false)
    expect(spy).toHaveBeenNthCalledWith(2, 'start_edges', 6, true)

    d0.resolve([[47.0, 11.0], [47.05, 11.05], [47.1, 11.1]])
    await waitFor(() => expect(screen.getByText(CAPTION)).toBeInTheDocument())

    d1.resolve([[47.1, 11.1], [47.15, 11.15], [47.2, 11.2]])
    await waitFor(() => expect(screen.queryByText(CAPTION)).not.toBeInTheDocument())
  })

  it('a leg whose fetch rejects keeps its straight-line fallback instead of crashing', async () => {
    vi.spyOn(loadLegGeometryModule, 'loadLegGeometry').mockRejectedValue(new Error('range not supported'))

    render(<ResultsMap selectedChain={chain} hutNameById={hutNameById} hutCoordsById={hutCoordsById} startById={startById} />)

    await waitFor(() => expect(screen.getByText(CAPTION)).toBeInTheDocument())
  })

  it('deselecting the tour clears the caption and shows the full hut list again', () => {
    vi.spyOn(loadLegGeometryModule, 'loadLegGeometry').mockReturnValue(new Promise(() => {}))

    render(<ResultsMap selectedChain={null} hutNameById={hutNameById} hutCoordsById={hutCoordsById} startById={startById} />)

    expect(screen.queryByText(CAPTION)).not.toBeInTheDocument()
    expect(screen.getByText('HutA')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd huts && npx vitest run src/tourSearchPage/ResultsMap.test.tsx`
Expected: FAIL — `loadLegGeometryModule.loadLegGeometry` is never called (current `ResultsMap.tsx`
doesn't import it), and the caption logic doesn't yet react to per-leg resolution.

- [ ] **Step 3: Rewrite `ResultsMap.tsx`**

Replace `huts/src/tourSearchPage/ResultsMap.tsx` in full:

```tsx
import { memo, useEffect, useMemo, useState } from 'react'
import { Box, Typography } from '@mui/material'
import { MapContainer, TileLayer, CircleMarker, Tooltip, Polyline, useMap } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { loadLegGeometry, type GeometryLayer } from '../tourSearch/loadLegGeometry.js'
import type { TourResult } from '../tourSearch/types.js'
import type { StartPoint } from './types.js'

const TILE_LAYER = (
  <TileLayer
    url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> | Hüttendaten: Alpenverein / ArcGIS'
  />
)

function chainPositions(
  chain: TourResult,
  hutCoordsById: Map<number, { lat: number; lng: number }>,
  startById: Map<number, StartPoint>,
): [number, number][] {
  const startPoint = startById.get(chain.startId)
  const endPoint = startById.get(chain.exitStartId)
  const hutPoints = chain.huts.map((h) => hutCoordsById.get(h)).filter((p): p is { lat: number; lng: number } => !!p)
  return [
    ...(startPoint ? [[startPoint.lat, startPoint.lng] as [number, number]] : []),
    ...hutPoints.map((p): [number, number] => [p.lat, p.lng]),
    ...(endPoint ? [[endPoint.lat, endPoint.lng] as [number, number]] : []),
  ]
}

// Recenters the map when a tour is selected (or a different one replaces it), but deliberately
// does nothing when selectedChain goes back to null - deselecting/minimizing a tour must leave
// the user's current pan/zoom untouched rather than snapping back to the overview view.
function RecenterOnSelect({
  selectedChain, hutCoordsById, startById,
}: {
  selectedChain: TourResult | null
  hutCoordsById: Map<number, { lat: number; lng: number }>
  startById: Map<number, StartPoint>
}) {
  const map = useMap()
  useEffect(() => {
    if (!selectedChain) return
    const positions = chainPositions(selectedChain, hutCoordsById, startById)
    if (positions.length < 2) return
    map.setView(positions[Math.floor(positions.length / 2)], 11)
    // Only re-run when the selected chain itself changes - hutCoordsById/startById are loaded
    // once and stable, and including them would refire this on unrelated parent re-renders.
  }, [map, selectedChain])
  return null
}

function legLayer(legIndex: number, legCount: number): GeometryLayer {
  return legIndex === 0 || legIndex === legCount - 1 ? 'start_edges' : 'hut_edges'
}

/** Resolves each leg's real trail geometry for the selected chain (spec F). While a leg's fetch
 *  is in flight, or if it rejects, its entry stays null so the caller falls back to a straight
 *  segment between that leg's own endpoints - the tour is never blank while loading. */
function useLegGeometries(
  selectedChain: TourResult | null,
  positions: [number, number][],
): ([number, number][] | null)[] {
  const [geometries, setGeometries] = useState<([number, number][] | null)[]>([])

  useEffect(() => {
    if (!selectedChain || positions.length !== selectedChain.legs.length + 1) {
      setGeometries([])
      return
    }
    const legs = selectedChain.legs
    setGeometries(new Array(legs.length).fill(null))
    let cancelled = false
    legs.forEach((leg, i) => {
      loadLegGeometry(legLayer(i, legs.length), leg.edgeId, leg.reversed).then(
        (points) => {
          if (cancelled) return
          setGeometries((prev) => {
            const next = [...prev]
            next[i] = points
            return next
          })
        },
        () => {
          // Leave this leg's entry null - its straight-line fallback segment stays in place.
        },
      )
    })
    return () => {
      cancelled = true
    }
  }, [selectedChain, positions])

  return geometries
}

interface ChainSegment {
  positions: [number, number][]
  isFallback: boolean
}

function chainSegments(
  positions: [number, number][],
  legGeometries: ([number, number][] | null)[],
): ChainSegment[] {
  return positions.slice(0, -1).map((from, i) => {
    const real = legGeometries[i]
    if (real && real.length >= 2) return { positions: real, isFallback: false }
    return { positions: [from, positions[i + 1]], isFallback: true }
  })
}

// Persistent map pane next to the results list: shows every hut when no tour is selected, and
// the selected tour's route once a result card is expanded - real routed trail geometry per leg
// once it resolves, a straight dashed fallback for legs still loading or that failed to resolve
// - so the map is never replaced by the list. A single MapContainer stays mounted across
// selection changes so the current pan/zoom survives deselecting a tour.
const ResultsMap = memo(function ResultsMap({
  selectedChain, hutNameById, hutCoordsById, startById,
}: {
  selectedChain: TourResult | null
  hutNameById: Map<number, string>
  hutCoordsById: Map<number, { lat: number; lng: number }>
  startById: Map<number, StartPoint>
}) {
  const positions = useMemo(
    () => (selectedChain ? chainPositions(selectedChain, hutCoordsById, startById) : []),
    [selectedChain, hutCoordsById, startById],
  )
  const showChain = selectedChain !== null && positions.length >= 2
  const legGeometries = useLegGeometries(selectedChain, positions)
  const segments = showChain ? chainSegments(positions, legGeometries) : []
  const anyFallback = segments.some((s) => s.isFallback)

  return (
    <Box sx={{ position: 'relative', height: '100%', width: '100%' }}>
      <MapContainer center={[47.3, 12.0]} zoom={7} style={{ height: '100%', width: '100%' }}>
        {TILE_LAYER}
        <RecenterOnSelect selectedChain={selectedChain} hutCoordsById={hutCoordsById} startById={startById} />
        {!showChain &&
          [...hutCoordsById.entries()].map(([id, { lat, lng }]) => (
            <CircleMarker
              key={id}
              center={[lat, lng]}
              radius={4}
              pathOptions={{ color: '#1b5e20', fillColor: '#43a047', fillOpacity: 0.9, weight: 1 }}
            >
              <Tooltip direction="top" offset={[0, -6]}>
                {hutNameById.get(id) ?? id}
              </Tooltip>
            </CircleMarker>
          ))}
        {showChain && (
          <>
            {segments.map((seg, i) => (
              <Polyline
                key={i}
                positions={seg.positions}
                pathOptions={
                  seg.isFallback
                    ? { color: '#e65100', weight: 3, dashArray: '6 8' }
                    : { color: '#e65100', weight: 3 }
                }
              />
            ))}
            {positions.map((pos, i) => (
              <CircleMarker
                key={i}
                center={pos}
                radius={i === 0 || i === positions.length - 1 ? 6 : 5}
                pathOptions={{ color: '#1b5e20', fillColor: '#43a047', fillOpacity: 1 }}
              />
            ))}
          </>
        )}
      </MapContainer>
      {showChain && anyFallback && (
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ position: 'absolute', bottom: 4, left: 4, bgcolor: 'background.paper', px: 0.5, borderRadius: 0.5, zIndex: 1000 }}
        >
          Schematische Verbindung, nicht der reale Wegverlauf.
        </Typography>
      )}
    </Box>
  )
})

export default ResultsMap
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd huts && npx vitest run src/tourSearchPage/ResultsMap.test.tsx`
Expected: all 3 tests PASS.

Run: `cd huts && npx vitest run src/tourSearchPage/`
Expected: `TourSearchPage.test.tsx` still PASSes — it expands a tour and asserts the caption is
shown, which now depends on `loadLegGeometry` never resolving inside that test's mocked-fetch
world (it doesn't mock `loadLegGeometry`, so the real implementation runs and its `fetch` calls hit
the test's `fetch` mock, which throws `unexpected fetch ...` for any URL it doesn't recognize —
that rejection is caught by `useLegGeometries`'s per-leg `.then(..., () => {})`, leaving every leg
on its fallback, so the caption still renders as asserted).

- [ ] **Step 5: Commit**

```bash
git add huts/src/tourSearchPage/ResultsMap.tsx huts/src/tourSearchPage/ResultsMap.test.tsx
git commit -m "feat(ui): render real trail geometry per leg on the tour results map"
```

---

## Task 11: `GraphPage.tsx` — migrate hover geometry off `hut-edge-stats.json`

**Files:**
- Modify: `huts/src/GraphPage.tsx`

**Interfaces:**
- Consumes: `/data/hut-edge-geometry.json` (manifest) + `/data/hut-edge-geometry.bin` (Task 1/3),
  fetched whole (no `Range`) since `HoverInspector` needs every edge's geometry simultaneously and
  `GraphPage.tsx:284` precomputes each edge's `L.latLngBounds` up front.
- `hut-edge-stats.json` stays a dependency for every other field (`ascent_m`, `elevation_profile`,
  `sac_scale`, etc.) — only its `positions` field is gone (per Task 1).

No dedicated test exists for `GraphPage.tsx` today and the spec's Testing section doesn't add one
— verify with typecheck/lint/build. **Do not start the dev server or open a browser** to visually
confirm this change unless the user asks (per this repo's stored guidance on this exact point).

- [ ] **Step 1: Add the manifest/geometry fetch and decode helper**

In `huts/src/GraphPage.tsx`, add the two new URL constants near the top (after line 13):

```tsx
const EDGE_GEOMETRY_MANIFEST_URL = '/data/hut-edge-geometry.json'
const EDGE_GEOMETRY_BIN_URL = '/data/hut-edge-geometry.bin'
```

Remove `positions` from the `EdgeStatsEntry` interface (lines 46-57) — `<layer>-stats.json` no
longer carries it (Task 1):

```tsx
interface EdgeStatsEntry {
  from_hut_id: number
  to_hut_id: number
  distance_m: number
  road_m: number
  ascent_m: number | null
  descent_m: number | null
  elevation_profile: number[] | null
  sac_scale: string | null
  via_ferrata: boolean
}
```

Add the manifest type and a decode helper right after it:

```tsx
interface EdgeGeometryManifest {
  point_counts: number[]
}

/** Decodes hut-edge-geometry.bin's flat f4 [lon, lat] point stream (edge_id order, no framing)
 *  into one Leaflet-ready [lat, lng][] per edge, using point_counts as a prefix-sum offset table.
 *  Fetched whole rather than range-fetched (unlike ResultsMap's per-leg lookups) because
 *  HoverInspector below needs every edge's geometry at once. */
function decodeEdgeGeometry(manifest: EdgeGeometryManifest, buffer: ArrayBuffer): L.LatLngExpression[][] {
  const floats = new Float32Array(buffer)
  const perEdge: L.LatLngExpression[][] = new Array(manifest.point_counts.length)
  let pointOffset = 0
  for (let i = 0; i < manifest.point_counts.length; i++) {
    const count = manifest.point_counts[i]
    const positions: L.LatLngExpression[] = new Array(count)
    for (let p = 0; p < count; p++) {
      const base = (pointOffset + p) * 2
      positions[p] = [floats[base + 1], floats[base]]
    }
    perEdge[i] = positions
    pointOffset += count
  }
  return perEdge
}
```

- [ ] **Step 2: Update the load effect to fetch and zip in the geometry**

Replace the `useEffect` load block (lines 261-298):

```tsx
  useEffect(() => {
    Promise.all([
      fetch(EDGE_STATS_URL).then((r) => r.json()) as Promise<EdgeStatsEntry[]>,
      fetch(EDGE_GEOMETRY_MANIFEST_URL).then((r) => r.json()) as Promise<EdgeGeometryManifest>,
      fetch(EDGE_GEOMETRY_BIN_URL).then((r) => r.arrayBuffer()),
      fetch(HUTS_URL).then((r) => r.json()) as Promise<GeoJSON.FeatureCollection>,
    ])
      .then(([edgeStats, geometryManifest, geometryBuffer, hutsFc]) => {
        // Geometry and stats are built from the same records.npy pass, in the same edge_id
        // order (build_edge_tiles.py's build_stats loop) - zip by index, no id lookup needed.
        const perEdgePositions = decodeEdgeGeometry(geometryManifest, geometryBuffer)
        setEdges(
          edgeStats.map((s, i) => {
            const positions = perEdgePositions[i]
            return {
              fromId: s.from_hut_id,
              toId: s.to_hut_id,
              distanceM: s.distance_m,
              roadM: s.road_m,
              ascentM: s.ascent_m,
              descentM: s.descent_m,
              elevationProfile: s.elevation_profile,
              sacScale: s.sac_scale,
              viaFerrata: s.via_ferrata,
              positions,
              bounds: L.latLngBounds(positions),
            }
          })
        )
        setHuts(
          hutsFc.features.map((f) => ({
            id: (f.properties as { id: number }).id,
            name: (f.properties as { name: string }).name,
            lat: (f.geometry as GeoJSON.Point).coordinates[1],
            lng: (f.geometry as GeoJSON.Point).coordinates[0],
          }))
        )
      })
      .catch((e: Error) => setError(e.message))
  }, [])
```

- [ ] **Step 3: Verify with typecheck, lint, and the full test suite**

Run: `cd huts && npm run typecheck`
Expected: no errors.

Run: `cd huts && npm run lint`
Expected: no errors.

Run: `cd huts && npm test`
Expected: every test suite in the repo PASSes (this is the first point in the plan where every
prior task's changes are all present together — confirm the whole suite, not just `tourSearch/`
and `tourSearchPage/`).

- [ ] **Step 4: Commit**

```bash
git add huts/src/GraphPage.tsx
git commit -m "feat(ui): migrate GraphPage hover geometry off hut-edge-stats.json"
```

---

## Task 12: Final verification pass

**Files:** none (verification only).

- [ ] **Step 1: Full pipeline test suite**

Run: `pytest pipeline/tests/test_build_edge_tiles.py pipeline/tests/test_build_approach_table.py -v`
Expected: all tests PASS (4 + 9 = 13 tests across the two files touched by this plan).

Run: `pytest pipeline/tests/ -v`
Expected: no regressions in any other pipeline test file (this plan touched only
`build_edge_tiles.py`/`build_approach_table.py`/`dodo.py`; if `pytest` isn't available in this
environment, ask the user how to run pipeline tests rather than skipping this step silently).

- [ ] **Step 2: Full client test/typecheck/lint suite**

Run: `cd huts && npm test && npm run typecheck && npm run lint`
Expected: everything PASSes.

- [ ] **Step 3: Confirm what still needs a (separately gated) pipeline rerun**

This plan's pipeline changes (Tasks 1-3) do not take effect on `huts/public/data/` until
`build_hut_edge_tiles`, `build_start_edge_tiles`, `build_approach_table`, and `copy_public_data`
are rerun — **do not run them now**. Tell the user explicitly, at the end of this plan's
execution:

- The code changes are complete and verified against synthetic fixtures + the currently-shipped
  (stale) real data via `realData.smoke.test.ts`'s guarded loader.
- `ResultsMap`'s real-geometry rendering and `GraphPage`'s migrated hover geometry will both
  **404** in the running app until the pipeline is rerun (the new `hut-edge-geometry.*`/
  `start-edge-geometry.*` files don't exist in `huts/public/data/` yet, and `approaches.bin` still
  lacks the `edge_id` column) — `ResultsMap` degrades gracefully to its all-fallback
  straight-line rendering (every leg's fetch 404s and is caught), but `GraphPage` will throw and
  show its error state, since its load effect has no per-source fallback.
  - Rerunning just the affected tasks (not the full DAG, per spec §G — `build_base_graph`/
    `build_hub_edges` are untouched): `pixi run doit build_hut_edge_tiles build_start_edge_tiles
    build_approach_table copy_public_data` — **only after asking the user and getting explicit
    confirmation**, per this repo's `CLAUDE.md`.

- [ ] **Step 4: No commit** — this task is verification-only; nothing to stage.
