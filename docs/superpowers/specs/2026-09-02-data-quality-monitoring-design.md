# Data Quality Monitoring Layer — Design

**Problem:** Data-quality defects in pipeline output are currently found by accident — a weird
route noticed on the map (the two screenshots in `docs/backlog.md`'s "Approach table drops a
reserved source-type slot" item: a hut-edge whose geometry is a straight line ignoring the trail
network, and another whose geometry loops back on itself), or by someone reading a bug report like
`docs/backlog/approach-reserved-type-slot-overwrite.md` closely enough to compute the 102/610
figure by hand. There's no standing, cheap way to ask "how much of the current output is broken,
and in which specific ways" after a pipeline run.

One check already exists in this shape (`match_tour_edges.py`'s `tour-match-gaps.json`, spec
`2026-08-30-tour-folder-ingestion-design.md` §5's "never-faked gap reasons"), but it's a file you
have to already know to look for — not part of anything that surveys the output as a whole.

**Goal:** A small set of read-only checks over already-persisted pipeline output, run as part of
the normal `doit` DAG, writing compact per-check JSON reports plus one aggregate summary — so a
pipeline run answers "is the output healthy" the same way it already answers "how long did each
phase take" (`data/timings.jsonl`).

**Non-goals:** no dashboard/visualization (backlog explicitly scopes this to output files first —
a dashboard, if ever built, is a later phase consuming these same files, see backlog's "Idea:
Introduce a pipeline explanation/visualization"). No auto-fixing — a check reports, it never
mutates `phases/` output. No hard gate on the DAG — see §3.

## 1. Placement

A new phase, `pipeline/phases/quality/check_data_quality.py`, wired via a new
`pipeline/dag/quality.py` (`task_check_data_quality`) — one module per phase, matching
`dag/downloads.py`/`dag/preprocessing.py`/`dag/graph_building.py`/`dag/elevation.py`/
`dag/postprocessing.py`. It is a real DAG task (`file_dep`/`targets`, `uptodate`-checked like every
other task), not a `pipeline/analysis/` script — `analysis/` scripts answer one-off measurement
questions for a specific design decision and are never imported by `phases/`; this is a standing
check that should run on every pipeline run without anyone remembering to invoke it by hand. It
does still follow `analysis/`'s "never reimplement the thing under measurement" discipline: where a
check needs logic that already exists in a phase script (e.g. `approach-reserved-type-slot-overwrite`
requires re-deriving "was a type available but dropped"), it imports that logic rather than copying
it — see §4.3.

Reports land in a new `data/quality/` folder (gitignored, sibling to `data/analysis/`) —
`data/analysis/` stays reserved for one-off analysis scripts' output, keeping the two folders'
purposes distinguishable at a glance.

## 2. Report format

Every check writes its own file (`data/quality/<check>.json`) with the same envelope:

```json
{
  "check": "geometry_sanity",
  "generated_at": "2026-09-02T14:03:11Z",
  "params": {"min_length_m": 300, "straightness_ratio_min": 0.97, "min_geom_count": 4},
  "summary": {"checked": 95482, "flagged": 37},
  "flagged": [
    {"from_id": 12, "from_type": "hut", "to_id": 88, "to_type": "hut", "variant": "FAST_ANY",
     "distance_m": 3120.5, "straightness_ratio": 0.981, "geom_count": 3}
  ]
}
```

`flagged` rows are IDs and the metrics that tripped the check only — never embedded coordinate
lists (per decision below). Enough to look the record up by hand in `records.npy`/`geometry.npy`
(by `from_id`/`to_id`/`variant`) or find it in `GraphPage`; a full geometry dump would make these
files large for no benefit over just reopening the source array with the given ids.

`check_data_quality.py` also writes `data/quality/summary.json`: every check's `check`/`summary`
block in one place, so a glance at one file says whether anything needs follow-up, without opening
all five.

## 3. Non-blocking

`task_check_data_quality` is part of the default `doit` run (`task_dep` covers everything it
reads — see §4) but nothing depends on *its* output: it is not a `file_dep` of
`copy_public_data`. A flagged record is worth knowing about but is not, by itself, a reason to stop
shipping data that was already shipping yesterday — thresholds are heuristics (a genuinely straight
forest-road edge is not a bug), and a hard gate on a heuristic produces exactly the kind of "silent
multi-hour rebuild" surprise `pipeline/CLAUDE.md` already warns about elsewhere. The script still
exits 0 always; findings are for a human reading `data/quality/summary.json` after the run, same as
`data/timings.jsonl` today.

## 4. Checks

Thresholds live in a new `"quality"` section of `pipeline.config.json`, following the existing
`approach`/`tourMatch` sections' pattern (plain key-value, read via `load_config()["quality"]`).

### 4.1 Geometry sanity (straight-line edges)

Over every `hut_edges/`+`start_edges/` record: `straightness_ratio = haversine(from_point,
to_point) / distance_m`. A record is flagged only when **all three** hold:

- `distance_m >= quality.geometrySanity.minLengthM` (default 300) — a short hop is innocently
  near-straight; only long "as the crow flies" edges are suspicious.
- `straightness_ratio >= quality.geometrySanity.straightnessRatioMin` (default 0.97).
- `geom_count < quality.geometrySanity.minGeomCount` (default 4) — genuinely straight terrain
  (a long forest road) still accumulates DEM-sampled vertices; a near-straight *and* vertex-sparse
  edge is the actual "this isn't following any trail" signature from the `image.png` case.

All three together, not any one alone, because each has an innocent-looking exception on its own —
this is stated explicitly since a future edit tempted to "simplify" to one condition would
reintroduce false positives on real straight roads.

### 4.2 Edge-geometry loops

Over the same records' `geometry.npy` polylines: flag a record whose geometry revisits a
coordinate — rounded to a `quality.edgeLoops.snapToleranceM` grid (default 5m) — more than once.
This is a single edge's *own* shape self-crossing, deliberately distinct from the already-shipped
cross-leg overlap machinery (`RECORD_DTYPE`'s `prefix_ids`/`suffix_ids`/`edge_id_offset`, the
"avoid overlapping tracks" design) which reasons about a *chain* of edges in a suggested tour, not
one edge's own geometry — this check exists because that machinery says nothing about whether a
single stored edge is internally sane, which is the `image-1.png` case.

### 4.3 Approach-table coverage

Over `approaches.bin`/`.json` plus the same candidate pool `build_approach_table.py`'s
`select_approaches` computed from: flag any hut with zero approach rows, and any hut missing a
source type (parking/station/partner_betrieb) that was actually available among its candidates but
didn't survive selection — re-deriving the same "was a type available but dropped" computation the
filed bug report (`docs/backlog/approach-reserved-type-slot-overwrite.md`) used to reach 102/610,
by importing `build_approach_table.py`'s candidate-gathering step rather than recomputing it
independently. This check is written to catch the *symptom* regardless of whether that specific bug
is ever fixed, so a future regression in the same area re-trips it.

### 4.4 Tour-ingestion gaps

Reads `match_tour_edges.py`'s existing `tour-match-gaps.json` and reshapes each entry
(`tourId`/`tourName`/`legIndex`/`reason`/`detail`) into the standard envelope's `flagged` list — no
new detection logic. This closes the backlog's "Settle invariant: official/third-party tours -
dont ship gap legs" item's monitoring half: gaps were already never faked into shippable edges
(spec `2026-08-30-tour-folder-ingestion-design.md` §5), but the count was invisible unless someone
already knew to open that file. Folding it into `summary.json` makes it visible next to every other
check.

### 4.5 Snap/connectivity health

- **Unsnapped huts**: count from `unsnapped_huts.json` (already produced by `snap_hubs.py`).
- **Isolated huts**: huts with zero `hut_edges` rows in either direction.
- **Disconnected pockets**: union-find over `hut_edges/records.npy`'s `(from_id, to_id)` pairs
  (huts only, `from_type == to_type == TYPE_HUT`); any component smaller than the largest is
  flagged, listing its member hut ids — these are huts technically snapped and edged, but only to
  each other, cut off from the main network.

## 5. Testing

`pipeline/tests/test_check_data_quality.py`, following the existing per-phase test pattern
(`test_build_approach_table.py`, `test_match_tour_edges.py` for shape): synthetic `records.npy`/
`geometry.npy` fixtures exercising each check's flag/no-flag boundary (a straight long edge with
few vertices flags; a straight *short* edge does not; a long winding edge with straightness just
under threshold does not), plus `test_dodo_wiring.py`-style coverage confirming
`task_check_data_quality`'s `file_dep` list matches what §4 actually reads and that it is absent
from `copy_public_data`'s `file_dep` (asserting the non-blocking property in §3, not just documenting
it in prose).

## 6. Follow-ups explicitly out of scope here

- A dashboard/visualization consuming `data/quality/*.json` (backlog "Idea: Introduce a pipeline
  explanation/visualization").
- Historical trending (e.g. appending to a `.jsonl` the way `timings.jsonl` does, to see flagged
  counts move release over release) — v1 overwrites each `data/quality/*.json` on every run.
- Any check not listed in §4 (e.g. trail-tag/grading distribution checks) — the report envelope in
  §2 is designed so a new check is one new file following the same shape, not a framework change.
