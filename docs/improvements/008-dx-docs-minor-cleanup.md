# Plan 008: Argparse help text, a stale doc pointer, and two unindexed lib modules

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 3e59f51..HEAD -- pipeline/phases pipeline/analysis pipeline/lib/tippecanoe.py pipeline/README.md pipeline/phases/README.md`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P3
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: dx
- **Planned at**: commit `3e59f51`, 2026-08-31

## Why this matters

Three small, independent, low-risk documentation/DX gaps, bundled into one plan because each is
too small to warrant its own:

1. **No `argparse` script in `pipeline/` has any `help=` text.** `--help` output for any of the 25
   scripts using `argparse` (`phases/` and `analysis/`) shows only the flag name and default value
   — the one place a human or agent would expect self-documenting parameter semantics gives
   nothing. The content already exists in prose form in `pipeline/README.md`'s "Config" section
   (which documents what `maxSnapM`/`maxEdgeKm`/`tileSizeKm`/etc. mean) — this plan surfaces a
   short version of that at the point of use.
2. **`lib/tippecanoe.py`'s docstring points at a README section that doesn't exist.** It says "See
   pipeline/README.md's 'Displaying the raw OSM trails' section for how the WSL-side micromamba env
   was created" — `pipeline/README.md` has no such heading (confirmed: its only `##` headings are
   "Config", "Setup: the `alpen-osm` pixi env", "Reproducing from scratch", "Rejected: buffer-clip
   and OSMnx"). The actual WSL/tippecanoe setup instructions live under "Setup: the `alpen-osm`
   pixi env" — a reader following the current pointer hits a dead end.
3. **`lib/geo.py` and `lib/edge_output.py` aren't listed in `phases/README.md`'s "Shared library
   code" index**, even though every other `lib/` module with cross-phase-script consumers is
   (`pipeline.py`, `timing.py`, `grid.py`, `binfmt.py`, `grading.py`, `speed.py`, `variants.py`,
   `contraction.py`, `edge_split.py`, `subgraph.py`). Both modules have good docstrings, so this is
   a minor index-completeness gap, not a missing-documentation gap.

## Current state

**Argparse scripts with no `help=` on any flag** (confirmed via `grep -rl argparse
pipeline/phases pipeline/analysis`):

```
analysis/contraction_scaling.py       phases/graph_building/build_base_graph.py
analysis/grading_coverage.py          phases/graph_building/build_hub_edges.py
analysis/oa_corridor_spike.py         phases/graph_building/gather_route_subgraphs.py
analysis/payload_sizing.py            phases/graph_building/match_tour_edges.py
analysis/reconstruct_raw_graph.py     phases/graph_building/snap_hubs.py
analysis/road_share.py                phases/postprocessing/build_approach_table.py
analysis/routing_probe.py             phases/postprocessing/build_edge_ids.py
analysis/snap_stats.py                phases/postprocessing/build_edge_payload.py
phases/downloads/fetch_dem.py         phases/postprocessing/build_edge_tiles.py
phases/elevation/build_profiles.py    phases/postprocessing/build_trail_tiles.py
phases/elevation/compute_edge_profiles.py
phases/elevation/sample_base_elevation.py
phases/preprocessing/compute_hub_range.py
phases/preprocessing/filter_start_points.py
phases/preprocessing/filter_trails.py
```

(Re-run the grep yourself before starting — this list is a snapshot; a file added/removed since
`3e59f51` should be picked up or dropped from your worklist accordingly, not blindly trusted.)

Example of the current shape, `phases/graph_building/build_hub_edges.py:293-300`:

```python
if __name__ == "__main__":
    config = load_config()
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-graph-dir", default=str(OSM_DIR / "base_graph"))
    parser.add_argument("--route-subgraphs-dir", default=str(OSM_DIR / "route_subgraphs"))
    parser.add_argument("--out-dir", default=str(OSM_DIR))
    parser.add_argument("--max-edge-km", type=float, default=config["graph"]["maxEdgeKm"])
    parser.add_argument("--workers", type=int, default=None)
    args = parser.parse_args()
```

`lib/tippecanoe.py:1-7` (module docstring, full):

```python
"""Shells out to tippecanoe for the two postprocessing tiling scripts (build_edge_tiles.py,
build_trail_tiles.py), natively if it's on PATH (Linux/macOS) or via WSL otherwise - tippecanoe
has no Windows build on conda-forge (linux-64/osx-64 only). See pipeline/README.md's "Displaying
the raw OSM trails" section for how the WSL-side micromamba env was created.

Also owns build_pmtiles(), the geojsonseq -> mbtiles -> pmtiles conversion shared by both of
those scripts, so the tippecanoe flags and cleanup step live in one place instead of two."""
```

`pipeline/README.md`'s actual `##` headings (confirmed via `grep -n "^## " README.md`): `Config`,
`` Setup: the `alpen-osm` pixi env ``, `Reproducing from scratch`, `Rejected: buffer-clip + OSMnx`.
The WSL/tippecanoe setup steps (micromamba install, `tippecanoe`'s lack of a Windows conda-forge
build) live under "Setup: the `alpen-osm` pixi env" today.

`phases/README.md:81-105` (the "Shared library code" section, current entries — full excerpt):

```markdown
## Shared library code (`pipeline/lib/`)

Not a phase — code imported across phases:

- **`pipeline.py`** — `load_config()`, path constants (`OSM_DIR`, `DEM_DIR`, `PUBLIC_DATA_DIR`,
  ...), `materialize_geotiff()`, `normalize_colorinterp()`, `build_dem_vrt()`, `run_tippecanoe()`
  (native-or-WSL dispatch), `hut_points()` / `edge_points()` / `bbox_from_huts()`.
- **`timing.py`** — `phase(script, name, **meta)` context manager, appends one JSON line to
  `data/timings.jsonl` per completed phase. Used by `graph_building/build_base_graph.py` and
  `elevation/build_dem_vrt.py`/`sample_base_elevation.py`/`compute_edge_profiles.py` to track
  which step stops scaling first as regional scope grows past AT+Bayern.
- **`grid.py`** — `Grid`, the row-major spatial grid `graph_building/` partitions the bbox into.
- **`binfmt.py`** — shared binary array formats (dtypes, `save_array()`/`load_array()`,
  `save_manifest()`/`load_manifest()`, `build_csr_index()`, `SCHEMA_VERSION`).
- **`grading.py`** — `classify_way()`/`excluded_from_constrained()`, per-way passability grading
  (`sac_rank` + `ungraded_m`/`inferred_m` tier) consumed by `build_base_graph.py`'s streaming pass.
- **`speed.py`** — `edge_time_s()`/`speed_kmh()` (the pointwise Tobler-shaped routing weight,
  calibrated by `analysis/routing_probe.py`) and `din_duration_h()` (the reported-duration formula
  the client applies — never stored, spec D3).
- **`variants.py`** — the `graph.variants` row definitions and `edge_mask()`, turning one row's
  constraint into a boolean mask over a subgraph's edges for `build_hub_edges.py`.
- **`contraction.py`** — `contract_structural()`, chain-contraction used by `build_base_graph.py`.
- **`edge_split.py`** — mid-chain edge splitting for snapping a hub onto a trail's interior.
- **`subgraph.py`** — `gather_padded_subgraph()`, the padded-region mmap gather used by
  `build_hub_edges.py`'s per-cell workers.
```

Note this list's `pipeline.py` bullet is itself stale (describes `materialize_geotiff`/
`hut_points`/etc. as living in `lib/pipeline.py`; per this plan's own recon, `lib/pipeline.py`
today only holds `load_config()` and path constants — those other functions have moved to
`lib/geo.py` (`hut_points`) and elsewhere). **Do not fix that in this plan** — it's a separate,
larger doc-accuracy pass not in scope here (see "Out of scope"); only *add* the two missing
bullets without rewriting the existing (stale) ones.

`lib/geo.py`'s module docstring (already read in full earlier in this audit): "Hub-range geometry:
extracting the lng/lat points a DEM-tile buffer or trail clip is built from (hut_points), and the
real-world-radius circle/union math (circle_polygon, hub_range_polygon)..."

`lib/edge_output.py`'s module docstring: "Packs a routed leg/edge (a plain dict with
distance/ascent/descent/geometry/base_edge_ids) into binfmt.RECORD_DTYPE + a flat geometry.npy -
the record-packing half of build_hub_edges.py's old _write_edge_output, extracted so
match_tour_edges.py ... can emit the exact same on-disk shape without duplicating this logic."

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Run pipeline tests | `pixi run pytest -q` (from `pipeline/`) | all pass |
| Check a script's `--help` output | `pixi run python phases/graph_building/build_hub_edges.py --help` (from `pipeline/`) | shows help text for every flag |

## Scope

**In scope** (the only files you should modify):
- Every file in the "Argparse scripts with no `help=` text" list above (add `help=` to each
  `add_argument` call; no other changes to these files)
- `pipeline/lib/tippecanoe.py` (fix the docstring's dead section pointer)
- `pipeline/phases/README.md` (add two bullets to "Shared library code")

**Out of scope**:
- Do NOT fix the already-stale `pipeline.py` bullet in `phases/README.md` described above under
  "Current state" — that's a larger doc-accuracy correction (auditing what actually lives in
  `lib/pipeline.py` today vs. `lib/geo.py`/`lib/dem.py`/etc.) better handled as its own follow-up,
  not bundled into this plan's narrow scope.
- Do NOT restructure any script's argument parsing, add new flags, or change any default value —
  this plan only adds `help=` strings.
- Do NOT touch `pipeline/README.md`'s heading structure (e.g. don't restore a "Displaying the raw
  OSM trails" heading) — fix the pointer in `tippecanoe.py` to reference the section that actually
  has this content today.

## Git workflow

- Branch: stay on the current branch unless the operator says otherwise.
- Commit message style: lowercase, `<module>: <imperative description>`. Suggest three commits
  (one per concern, since they're unrelated): `phases: add help text to every argparse script`,
  `lib: fix tippecanoe.py's stale README section pointer`, `docs: index lib/geo.py and
  lib/edge_output.py in phases/README.md`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add `help=` text to every flag in every listed script

For each file in the list above, open it and add a `help="..."` kwarg to every `add_argument`
call. Source the wording from:
1. That flag's own name/default (often self-explanatory: `--workers` → "number of worker
   processes (default: CPU count)"),
2. The corresponding entry in `pipeline/README.md`'s "Config" section if the flag mirrors a
   `pipeline.config.json` key (e.g. `--max-edge-km` should reuse language close to the README's
   own `maxEdgeKm` explanation),
3. The script's own module docstring if neither of the above covers it.

Keep each `help=` string to one line, matching argparse's own convention (a longer explanation
belongs in the script's module docstring, not repeated in `--help` output). Example, applying this
to `build_hub_edges.py`'s block shown in "Current state":

```python
    parser.add_argument("--base-graph-dir", default=str(OSM_DIR / "base_graph"),
                         help="directory holding the persisted base graph (build_base_graph.py's output)")
    parser.add_argument("--route-subgraphs-dir", default=str(OSM_DIR / "route_subgraphs"),
                         help="directory holding gather_route_subgraphs.py's persisted per-cell gathers")
    parser.add_argument("--out-dir", default=str(OSM_DIR),
                         help="directory to write hut_edges/ and start_edges/ into")
    parser.add_argument("--max-edge-km", type=float, default=config["graph"]["maxEdgeKm"],
                         help="longest hut-to-hut trail distance kept as an edge (see pipeline.config.json's graph.maxEdgeKm)")
    parser.add_argument("--workers", type=int, default=None,
                         help="number of worker processes for the per-cell routing pass (default: os.cpu_count())")
```

Work through the file list in the order given above; there's no dependency between files, so any
order is fine, but don't skip any — the done criteria check every file in the list.

**Verify** (after each file): `pixi run python <file> --help` (from `pipeline/`) → every listed
flag shows non-empty help text, and the script doesn't error (a syntax mistake in one
`add_argument` call would surface here immediately).

**Verify** (after all files): `pixi run pytest -q` (from `pipeline/`) → all pass (help text
changes shouldn't affect any test, but confirms nothing was broken).

### Step 2: Fix `lib/tippecanoe.py`'s stale doc pointer

Change:

```python
"""Shells out to tippecanoe for the two postprocessing tiling scripts (build_edge_tiles.py,
build_trail_tiles.py), natively if it's on PATH (Linux/macOS) or via WSL otherwise - tippecanoe
has no Windows build on conda-forge (linux-64/osx-64 only). See pipeline/README.md's "Displaying
the raw OSM trails" section for how the WSL-side micromamba env was created.
```

to:

```python
"""Shells out to tippecanoe for the two postprocessing tiling scripts (build_edge_tiles.py,
build_trail_tiles.py), natively if it's on PATH (Linux/macOS) or via WSL otherwise - tippecanoe
has no Windows build on conda-forge (linux-64/osx-64 only). See pipeline/README.md's "Setup: the
`alpen-osm` pixi env" section for how the WSL-side micromamba env was created.
```

(Keep the rest of the docstring's second paragraph, about `build_pmtiles()`, unchanged.)

**Verify**: `grep -n "Setup: the" pipeline/lib/tippecanoe.py` → matches; `grep -n "Displaying the raw OSM trails" pipeline/lib/tippecanoe.py` → no match.

### Step 3: Index `lib/geo.py` and `lib/edge_output.py` in `phases/README.md`

Add two new bullets to the "Shared library code" list (`phases/README.md`, after the existing
`subgraph.py` bullet, keeping alphabetical-ish grouping loose consistency with the existing list's
rough order — exact position doesn't matter, just add them to the list):

```markdown
- **`geo.py`** — `hut_points()`/`circle_polygon()`/`hub_range_polygon()`, hub-range coverage
  geometry shared by `preprocessing/compute_hub_range.py` and
  `downloads/dem_providers/composite.py` (both must derive the same radius from
  `HUB_RANGE_SAFETY_MARGIN` or their coverage shapes silently drift apart).
- **`edge_output.py`** — `write_edge_records()`/`fold_endpoint_snaps()`, the record-packing shape
  (`binfmt.RECORD_DTYPE` + `geometry.npy`) shared by `build_hub_edges.py` and
  `match_tour_edges.py` so both emit identical on-disk edge records.
```

Before committing, re-read `lib/edge_output.py`'s actual exported function names (grep `^def ` in
that file) and correct the bullet's function names if they differ from `write_edge_records`/
`fold_endpoint_snaps` shown here (this plan's recon found those names via `git log` commit
subjects — "extract fold_endpoint_snaps into lib/edge_output.py",
"extract write_edge_records into lib/edge_output.py" — but confirm against the live file rather
than trusting commit-message naming alone).

**Verify**: `grep -n "geo.py\|edge_output.py" pipeline/phases/README.md` → both present.

## Test plan

No new test files — this plan changes only help text and documentation, none of it covered by (or
needing) pytest. Verification is via `--help` inspection and `grep`, per the Steps above.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] For every file in the "Argparse scripts" list, `pixi run python <file> --help` shows
      non-empty help text for every flag (spot-check at least 5 of the 25 files by hand; the rest
      via `grep -c "help=" <file>` matching `grep -c "add_argument" <file>` for each)
- [ ] `pixi run pytest -q` (from `pipeline/`) → all pass
- [ ] `grep -n "Displaying the raw OSM trails" pipeline/lib/tippecanoe.py` → no match
- [ ] `grep -n "Setup: the" pipeline/lib/tippecanoe.py` → match
- [ ] `grep -n "geo.py\|edge_output.py" pipeline/phases/README.md` → both present
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- A script's argparse setup is more complex than a flat list of `add_argument` calls (e.g.
  subparsers, mutually exclusive groups) in a way that makes adding `help=` ambiguous — add it to
  the straightforward calls and report which ones you skipped and why, rather than guessing at an
  unusual structure.
- The file list from recon is significantly wrong when you re-run the grep (e.g. several files no
  longer use argparse, or several new ones do) — proceed with the corrected live list, but note the
  discrepancy when reporting done.
- `lib/edge_output.py`'s actual function names differ from `write_edge_records`/
  `fold_endpoint_snaps` in a way that changes what the README bullet should say beyond a simple
  rename — use the correct live names either way; only stop if the module's actual purpose seems to
  have changed from what its docstring (quoted in this plan) describes.

## Maintenance notes

- The `phases/README.md` "Shared library code" list's stale `pipeline.py` bullet (noted under
  "Current state") is a good candidate for a future, separately-scoped doc-accuracy plan — this
  plan deliberately doesn't touch it to keep this batch low-risk and mechanical.
- Any new `lib/` module added later that's imported by more than one `phases/` script should get a
  bullet in this same list at the time it's added, per the list's own evident convention.
