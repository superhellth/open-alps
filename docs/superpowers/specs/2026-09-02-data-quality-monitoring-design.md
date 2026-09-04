# Data Quality Monitoring Layer — Design

**Problem:** Data-quality defects in pipeline output are currently found by accident — a weird
route noticed on the map (the screenshots in `docs/backlog.md`'s "Approach table drops a
reserved source-type slot" item), or by someone reading a bug report like
`docs/backlog/approach-reserved-type-slot-overwrite.md` closely enough to compute the 102/610
figure by hand. There's no standing, cheap way to ask "how much of the current output is broken,
and in which specific ways" after a pipeline run.

One check already exists in this shape (`match_tour_edges.py`'s `tour-match-gaps.json`, spec
`2026-08-30-tour-folder-ingestion-design.md` §5's "never-faked gap reasons"), but it's a file you
have to already know to look for — not part of anything that surveys the output as a whole.

**Goal:** A set of read-only checks over already-persisted pipeline output, **one module per
pipeline phase**, run as part of the normal `doit` DAG, writing compact per-phase JSON reports plus
one aggregate summary — so a pipeline run answers "is the output healthy" the same way it already
answers "how long did each phase take" (`data/timings.jsonl`).

**Every threshold below was measured against the 2026-09-02 run before being written down** (§6
records the numbers). A heuristic check whose false-positive rate nobody has looked at is worse
than no check: the first draft of this spec proposed a straightness rule that flags 0 of 8,238
records, and a loop rule that flags 98.5% of them. Both are corrected here.

**Non-goals:** no dashboard/visualization (backlog scopes this to output files first — a dashboard,
if ever built, is a later phase consuming these same files). No auto-fixing — a check reports, it
never mutates `phases/` output. No hard gate on the DAG — see §3. No checks over `phases/downloads/`
output — validating a fetch belongs to the fetch script's own error handling; hut-catalog coverage
questions are tracked separately in `docs/backlog/hut-catalog-privately-run-inns.md`.

## 1. Placement

A new phase directory, `pipeline/phases/quality/`, with **one module per checked phase**, mirroring
how `dag/` is already split:

| module | reads the output of |
| --- | --- |
| `check_preprocessing.py` | `phases/preprocessing/` (`start_points.npy`, `start_points_id_table.json`, `hub_range.geojson`) |
| `check_graph_building.py` | `phases/graph_building/` (`base_graph/`, `hub_snaps.npy`, `unsnapped_huts.json`, `hut_edges/`, `start_edges/`, `tour_edges/`, `tour-match-gaps.json`) |
| `check_elevation.py` | `phases/elevation/` (`node_ele.npy`, `interior_ele.npy`, `edges.npy`'s time/ascent columns, each layer's `profiles.npy`) |
| `check_postprocessing.py` | `phases/postprocessing/` (`*-payload.*`, `*-geometry.*`, `approaches.*`, `*-ids.*`, and the `huts/public/data/` copies) |

Wired via a new `pipeline/dag/quality.py` (`task_check_preprocessing`, `task_check_graph_building`,
`task_check_elevation`, `task_check_postprocessing`, `task_quality_summary`), matching
`dag/downloads.py`/`dag/preprocessing.py`/`dag/graph_building.py`/`dag/elevation.py`/
`dag/postprocessing.py` — one module per phase, so a task's wiring sits next to the phase it wires.

One task per phase rather than one big task, because `file_dep` then tracks only that phase's
outputs: retuning `approach.k` reruns `check_postprocessing` without re-walking 129 MB of
`hut_edges/geometry.npy`.

These are real DAG tasks (`file_dep`/`targets`, `uptodate`-checked), not `pipeline/analysis/`
scripts — `analysis/` scripts answer one-off measurement questions for a specific design decision
and are never imported by `phases/`; these are standing checks that run on every pipeline run
without anyone remembering to invoke them. They still follow `analysis/`'s "never reimplement the
thing under measurement" discipline: where a check needs logic that already exists in a phase
script it imports that logic — see §4.4.1's required refactor.

Reports land in a new `data/quality/` folder (gitignored with the rest of `data/`, sibling to
`data/analysis/`) — `data/analysis/` stays reserved for one-off analysis scripts' output.

Each module wraps its run in `lib/timing.py`'s `phase(SCRIPT_NAME, ...)` and prints one progress
line per check as it completes, per `pipeline/CLAUDE.md`'s progress-logging rule. The geometry
checks are vectorized per record (numpy over the mmapped `geometry.npy` slice); a per-point Python
loop over `start_edges`' 7.4 GB geometry is not acceptable.

## 2. Report format

Every check writes into its phase's file (`data/quality/<phase>.json`), one entry per check, all
sharing the same envelope:

```json
{
  "phase": "graph_building",
  "generated_at": "2026-09-02T14:03:11Z",
  "checks": [
    {
      "check": "geometry_continuity",
      "params": {"max_vertex_gap_m": 500},
      "summary": {"checked": 8238, "flagged": 700, "baseline": 700},
      "truncated": false,
      "flagged": [
        {"layer": "hut_edges", "from_id": 138, "to_id": 124, "variant": "FAST_ANY",
         "distance_m": 28617.0, "max_gap_m": 3929.0, "gap_at_segment": 570}
      ]
    }
  ]
}
```

Rules for the envelope:

- `flagged` rows are IDs plus the metrics that tripped the check — never embedded coordinate lists.
  Enough to look the record up in `records.npy`/`geometry.npy` by `(layer, from_id, to_id, variant)`
  or find it in `GraphPage`.
- `flagged` is **capped** at `quality.maxFlaggedRows` (default 500), ordered worst-first, with
  `truncated` and the true count in `summary.flagged`. Without a cap, a mis-set threshold on
  `start_edges` (471,196 rows) writes a multi-hundred-MB JSON on every run.
- `summary.baseline` is the count measured in §6. A check whose count moved is the interesting
  event; a check sitting at its known baseline is not.
- `phases/quality/summarize.py` (`task_quality_summary`, `file_dep` on the four phase reports)
  writes `data/quality/summary.json`: every check's `phase`/`check`/`summary` block in one place,
  so one file says whether anything needs follow-up without opening all four.

## 3. Non-blocking

The quality tasks are part of the default `doit` run but nothing depends on their output: none is
a `file_dep` of `copy_public_data`. A flagged record is worth knowing about but is not, by itself,
a reason to stop shipping data that was already shipping yesterday — thresholds are heuristics, and
a hard gate on a heuristic produces exactly the kind of "silent multi-hour rebuild" surprise
`pipeline/CLAUDE.md` warns about. The scripts exit 0 always.

Each task needs **both** `file_dep` (the arrays it reads) and `task_dep`, because several upstream
tasks rewrite their outputs in place without declaring them as targets — `build_profiles` rewrites
`records.npy`'s `profile_offset`/`profile_count`, `compute_edge_profiles` rewrites
`base_graph/edges.npy`'s `time_s`/`ascent_m`/`descent_m`. `task_build_hut_edge_tiles` already
carries `task_dep=["build_profiles"]` for this reason; the quality tasks inherit the same hazard.

## 4. Checks

Thresholds live in a new `"quality"` section of `pipeline.config.json`, one sub-object per phase,
read via `load_config().get("quality", {})` with per-key defaults (following
`dag/postprocessing.py`'s `CONFIG.get("trailTiles", {})` pattern, so a config predating this
section doesn't `KeyError`).

### 4.1 Preprocessing

**4.1.1 Start-point integrity** — over `start_points.npy`: coordinates finite, inside
`config["bbox"]`, and no `(type, osm_id)` appearing twice. *Measured: 86,746 rows, 0 non-finite,
0 outside bbox, but **236 duplicate rows** (200 station, 36 parking) — the same physical access
point entered as several hubs, which duplicates its approach candidates downstream.*

**4.1.2 Id-table coverage** — every `start_points.npy` row's `osm_id` resolvable in the matching
`start_points_id_table.json` layer, since `build_approach_table` reads `access` tags through it.
*Measured: 0 unresolvable across all three layers — a genuine invariant, worth pinning.*

### 4.2 Elevation

**4.2.1 Elevation range** — `node_ele.npy`/`interior_ele.npy`: no NaN, no nodata sentinel, nothing
outside `quality.elevation.plausibleRangeM` (default `[-50, 4300]`). *Measured: node 120.0–3793.5,
interior 119.7–3759.0, 0 NaN, 0 out of range.*

**4.2.2 Unresolved sentinels** — `base_graph/edges.npy` rows still holding `binfmt.UNSET` in
`time_s`/`ascent_m`/`descent_m` after `compute_edge_profiles`. *Measured: 0. This is the check that
catches a half-finished elevation pass, which today is invisible until routing produces nonsense.*

**4.2.3 Implied speed** — `dist / time_s` per base-graph edge, flagged below
`quality.elevation.minSpeedMs` (default 0.05 m/s ≈ 180 m/h). *Measured: implied speed p0.1 = 0.17,
p50 = 0.92, p99.9 = 1.11 m/s — and then a tail that is plainly broken: **1,011 edges below
0.05 m/s, 184 edges with `time_s` over 24 h, 20 over a year, worst 2.95 × 10¹² s (~94,000 years)
for a 1.4 km edge with 345 m of ascent**. These never get chosen by the router, so they have hidden
until now, but they are not real numbers and they make `time_s` unusable as a diagnostic.*

**4.2.4 Profile integrity** — `profile_count == 0` while `geom_count > 0`; `profile_offset +
profile_count` past the end of `profiles.npy`; `profile_count != dem.profilePoints`. *Measured:
0/0/0 across all three layers (every record has exactly 30 points).*

### 4.3 Graph building

**4.3.1 Snap health** — from `unsnapped_huts.json`, counted **by distinct `hub_id`, not by entry**:
the file holds one entry per rejection reason. *Measured: 609 entries but **225 distinct huts**
(`gap_too_far` 508, `vertical_offset` 101). A naive entry count over-reports by 2.7×.*

**4.3.2 Connectivity, per variant** — union-find over each layer's `(from_id, to_id)` pairs,
**separately per `variant`**. Merging variants is meaningless: `binfmt.py`'s
`VARIANT_FAST_T3_UNGRADED` comment records that 31.7%/36.9% of huts lose their last T2/T3
connection, and that structure is exactly what a merged run hides. *Measured over 846 huts:*

| variant | rows | huts with edges | isolated | components | huts outside the largest |
| --- | --- | --- | --- | --- | --- |
| FAST_ANY | 3,519 | 594 | 252 | 11 | 81 |
| FAST_T2 | 1,061 | 417 | 429 | 46 | 294 |
| FAST_T3 | 1,484 | 465 | 381 | 28 | 234 |
| FAST_T3_UNGRADED | 2,174 | 543 | 303 | 16 | 83 |

**4.3.3 Range cap** — `distance_m > graph.maxEdgeKm * 1000`. *Measured: `hut_edges` 25 of 8,238
(max 30,111 m — a benign overshoot, the folded snap gap on top of a 30 km path), but **`start_edges`
100,592 of 471,196 (21%), up to 267,637 m with 12,903 m of ascent**. A 268 km approach leg is not a
threshold judgement call; it is the range cap not being applied on `build_access_edges`' second
routing pass (spec `2026-09-02-hub-edge-scaling-design.md` B5/B6). This check exists to make that
class of regression loud.*

**4.3.4 Geometry continuity** — the longest gap between consecutive vertices of a record's
polyline, flagged over `quality.graphBuilding.maxVertexGapM` (default 500 m). This **replaces** the
whole-record straightness rule of the first draft, which measured 0 flags at every threshold set
tried (straightness p99.9 = 0.917, never reaching the proposed 0.97 — see §6). Per-vertex gap is
also the sharper signature: nothing should insert a long straight hop, since `graph.maxSnapM` is
100 m and `tourMatch.endpointBridgeMaxM` is 250 m. *Measured: `hut_edges` 700 records / 1,438
segments over 500 m, **none of them on an endpoint segment** (so not the snap fold); base graph's
own baseline is 3,362 of 4.73 M edges, p99.9 = 460 m.*

Runs over `hut_edges`, `start_edges`, `tour_edges` **and** `base_graph/edges.npy` — separating
"the base graph has a long straight way here" from "the routed record lost geometry the base graph
has" is the whole diagnostic value. Sampling 200 of the record-level jumps found that 117 of the
119 that resolve to base-graph node pairs are joined by an edge carrying a non-empty interior
polyline, i.e. geometry that exists upstream and is missing downstream. Root-causing that belongs
in a debugging pass, not here; this check is what tells you whether it came back.

**4.3.5 Self-retracing geometry** — a record's own polyline revisiting a
`quality.graphBuilding.snapToleranceM` grid cell (default 5 m) **where the two visits are more than
`quality.graphBuilding.minRetraceSeparationM` (default 200 m) apart along the path**. The
separation term is not optional: without it, the plain 5 m revisit rule flags **8,116 of 8,238
`hut_edges` records (98.5%)**, because real trail geometry revisits a 5 m cell constantly at
switchbacks. *Measured with the separation term: `hut_edges` 270 of 8,214 (3.3%), `tour_edges`
1 of 5 — record 0 (`259→796`, `OFFICIAL`) retraces ~310 m of a 13.5 km leg.*

This is a single edge's own shape self-crossing, deliberately distinct from the cross-leg overlap
machinery (`RECORD_DTYPE`'s `prefix_ids`/`suffix_ids`/`edge_id_offset`), which reasons about a
*chain* of edges and says nothing about whether one stored edge is internally sane.

Note that the one confirmed hit is in `tour_edges` — the layer produced by `match_tour_edges.py`'s
HMM corridor reconstruction, and the layer the first draft of this spec excluded. All geometry
checks run over all three edge layers.

**4.3.6 Scalar sanity** — `max_ele_m` below the DEM's lowest sampled node, `ascent_m` over
`quality.graphBuilding.ascentCapM` (default 5,000 m), and any negative distance/ascent/descent.
*Measured: `max_ele_m == 0` on **82,017 `start_edges` rows and 24 `hut_edges` rows** — impossible,
since the lowest node in the DEM is 120 m. Every one of them turns out to be a degenerate record
(median `distance_m` 30 m, `geom_count` 2–3), where `accumulate_path`'s zero-length branch leaves
`max_ele_m` unset and the writer's `else 0.0` fallback lands sea level in the column the client's
altitude cap reads — so this check doubles as the degenerate-record detector
(`docs/backlog/degenerate-zero-length-start-edges.md`). `ascent_m > 5000`: 6,426 `start_edges` rows
(max 12,903 m). Negative values: 0 everywhere.*

**4.3.7 Tour-ingestion gaps** — reads `match_tour_edges.py`'s existing `tour-match-gaps.json` and
reshapes each entry (`tourId`/`tourName`/`legIndex`/`reason`/`detail`) into the envelope's
`flagged` list. No new detection logic. This closes the *monitoring* half of the backlog's "Settle
invariant: official/third-party tours — dont ship gap legs": gaps were already never faked into
shippable edges, but the count was invisible unless you knew to open that file. The *shipping* half
— `tour-match-gaps.json` is in `dodo.py`'s `PUBLIC_FILES` and `2026-09-01-official-tours-frontend-
design.md` deliberately has the frontend consume it — is untouched here and stays that spec's call.

### 4.4 Postprocessing

**4.4.1 Approach-table coverage** — over `approaches.bin`/`.json` plus the candidate pool: flag any
hut with zero approach rows, and any hut missing a source type (parking/station/partner_betrieb)
that was available among its candidates but didn't survive selection. *Measured on the current run
(`k=3`): **233 of 846 huts have zero approach rows**; **160 of 613 huts with candidates (26%) lose
an available source type** — parking 129, station 28, partner_betrieb 3. Rows-per-hut is
`{1: 1, 2: 2, 3: 610}`, confirming the reservation replaces and never extends. The filed report's
102/610 (17%) was the pre-B3 figure; the symptom is larger now.*

Two implementation constraints:

- `build_approach_table.py` has **no importable candidate-gathering step** — `select_approaches`
  builds its `by_hut` candidate dict inline and returns only the selection. Honouring §1's
  "import, don't copy" means first extracting
  `gather_candidates(records, id_table) -> dict[hut_id, list]` out of it. That refactor is a
  prerequisite of this check, not incidental to it.
- Reading `start_edges/records.npy` as the candidate universe is only valid because
  `select_approach_pairs.py` takes top-k per `(hut_id, start_type)`, so every source type survives
  that stage. *Measured: 0 huts lose a type between `access_distances.npy` and `start_edges`.* That
  is a load-bearing invariant — §5 asserts it, so a regrouping of the selection can't silently
  invalidate this check.

**4.4.2 Manifest/array agreement** — for each shipped family: `records.npy` row count ==
`<layer>-payload.json`'s `rows` == `len(<layer>-geometry.json["point_counts"])`, and
`<layer>-geometry.bin` byte length == `8 * sum(point_counts)`; `edge_id_offset + edge_id_count`
within `edge_ids.npy`. *Measured on `data/osm` today: 8,238 / 8,238 / 8,238, consistent. This is a
staleness detector: `loadLegGeometry.ts` computes `state.offsets[edgeId + 1]` with no bounds check,
so a payload whose row count exceeds its geometry manifest yields `NaN` → a rejected fetch → the
client's straight-line fallback, which is visually indistinguishable from a broken stored geometry.*

**4.4.3 Shipped-geometry sanity** — the straightness rule the first draft proposed, applied where
it actually earns its keep: the **simplified** `*-geometry.bin` the client renders (8.09 M raw
points → 724 k shipped for hut edges). Flag edges ≥ `quality.postprocessing.minLengthM` (300 m) with
straightness ≥ 0.97 and fewer than 4 points. *Measured on the shipped set: 4 hut edges and 10 start
edges, plus 45 hut / 77 start edges collapsed to exactly 2 points (all ≤ 345 m). Small, real, and
invisible in the raw arrays — `build_edge_tiles`' `simplifyToleranceDeg` is the only thing that can
produce it.*

**4.4.4 Public-copy freshness** — every name in `dodo.py`'s `PUBLIC_FILES` present in
`huts/public/data/` and byte-identical to its `data/osm/` source. Cheap (size + hash), and it is
the check that would have said out loud that the shipped set is from an older run than the arrays
the other checks are reading.

## 5. Testing

`pipeline/tests/test_check_<phase>.py`, one per module, following the existing per-phase test
pattern (`test_build_approach_table.py`, `test_match_tour_edges.py` for shape): synthetic
`records.npy`/`geometry.npy` fixtures exercising each check's flag/no-flag boundary — a 600 m
vertex gap flags and a 400 m one does not; a switchback that revisits a 5 m cell 50 m along the
path does not flag while a 300 m retrace does; a hut whose candidates hold a station absent from
its approach rows flags.

Plus `test_dodo_wiring.py`-style coverage asserting, for each quality task, that its `file_dep`
list matches what its module actually opens, that it carries the `task_dep` of §3, and that it is
absent from `copy_public_data`'s `file_dep` — pinning the non-blocking property as a test rather
than as prose.

One test asserts the §4.4.1 invariant directly (every source type present in
`access_distances.npy` for a hut is still present in `start_edges` for that hut), since the
approach-coverage check's correctness depends on it.

## 6. Measured baselines (2026-09-02 run)

Recorded so a future reader can tell "this check has always flagged N" from "this check started
flagging". Every number below came from read-only probes over persisted arrays; no task was rerun.

| check | today | note |
| --- | --- | --- |
| preprocessing / start-point duplicates | 236 rows | 200 station, 36 parking |
| preprocessing / id-table coverage | 0 | clean invariant |
| elevation / range | 0 | node 120–3793 m, interior 120–3759 m |
| elevation / UNSET sentinels | 0 | clean invariant |
| elevation / implied speed < 0.05 m/s | 1,011 edges | 184 over 24 h, 20 over a year, max 2.95e12 s |
| elevation / profile integrity | 0 | all records exactly 30 points |
| graph_building / unsnapped huts | 225 distinct (609 entries) | gap_too_far 508, vertical_offset 101 |
| graph_building / connectivity | see §4.3.2 table | FAST_T2 is 46 components |
| graph_building / range cap | hut 25, start 100,592 | start max 267,637 m |
| graph_building / vertex gap > 500 m | hut 700 records (1,438 segments) | 0 at endpoint segments; base graph 3,362 / 4.73 M |
| graph_building / retrace (5 m, >200 m apart) | hut 270 (3.3%), tour 1 of 5 | naive rule without the separation term: 98.5% |
| graph_building / max_ele_m == 0 | start 82,017, hut 24 | DEM minimum is 120 m; all are degenerate ≤166 m records |
| graph_building / ascent > 5,000 m | start 6,426 | max 12,903 m |
| postprocessing / zero approach rows | 233 of 846 huts | |
| postprocessing / dropped source type | 160 of 613 (26%) | parking 129, station 28, partner 3 |
| postprocessing / manifest agreement | 0 | 8,238 across records/payload/geometry |
| postprocessing / shipped near-straight | 4 hut, 10 start | plus 45/77 two-point edges |

### Traps a check author will otherwise hit

- **`base_edge_ids` are `3n` / `3n+1` / `3n+2`** (`lib/cell_igraph.py:129,163,178` — original edge,
  and the two synthetic halves of a mid-chain split). 416,590 of the 633,795 ids in
  `hut_edges/edge_ids.npy` are above `edges.npy`'s maximum id **by design**; a naive referential
  check flags 66% of them.
- **`inferred_m` is about grading, not geometry** (metres whose SAC grade was inferred). Its median
  is 8.3 km per record and its correlation with vertex-gap length is −0.26 — it does not explain,
  and must not be used to excuse, straight geometry.
- **Variant duplication**: `write_edge_records` dedupes identical polylines across variants, so one
  bad geometry surfaces as up to four flagged rows for the same hut pair. Geometry checks report
  one row per `(layer, from_id, to_id)` with the variant list attached.
- **`unsnapped_huts.json` is one entry per rejection reason**, not per hut (§4.3.1).
- **Raw arrays and shipped geometry are different data** — the shipped `*-geometry.bin` is
  simplified by ~11×, and §4.4.3's findings do not appear in the raw arrays at all.

## 7. Follow-ups explicitly out of scope here

- A dashboard/visualization consuming `data/quality/*.json` (backlog "Idea: Introduce a pipeline
  explanation/visualization").
- Historical trending (appending to a `.jsonl` the way `timings.jsonl` does) — v1 overwrites each
  `data/quality/*.json` on every run, and `summary.baseline` covers the "did it move" question in
  the meantime.
- Checks over `phases/downloads/` output.
- **Fixing** anything §6 measures. Each defect the baseline pass turned up is filed separately and
  needs its own debugging pass; this layer's job is to make them countable, not to repair them:

  | defect | check | backlog entry |
  | --- | --- | --- |
  | `start_edges` over the range cap | §4.3.3 | `backlog/start-edges-range-cap-violation.md` |
  | dropped trail detail in record geometry | §4.3.4 | `backlog/hut-edge-geometry-drops-trail-detail.md` |
  | degenerate zero-length rows / `max_ele_m == 0` | §4.3.6 | `backlog/degenerate-zero-length-start-edges.md` |
  | `time_s` outlier tail | §4.2.3 | `backlog/base-graph-time-s-outliers.md` |
  | duplicate start points | §4.1.1 | `backlog/duplicate-start-points-across-region-extracts.md` |
  | approach-table type loss | §4.4.1 | `backlog/approach-reserved-type-slot-overwrite.md` |
