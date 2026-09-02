# Exact approach selection via a scalars-only path walk

**Priority:** Low

Follow-up to `docs/superpowers/specs/2026-09-02-hub-edge-scaling-design.md` §B4. Only actionable
**after** that spec's §A+§B have landed — it is a refinement of the selection step that spec
introduces, not a standalone change.

## What §B4 settles for

`build_approach_table.py` ranks approach candidates by `speed.din_duration_h(distance_m, ascent_m,
descent_m)`. Under §B, geometry is only materialized for pairs that were *already* selected, so the
selection cannot see `ascent_m`/`descent_m` — those only exist after a path walk, and the walk is
the expensive thing §B exists to avoid. So the selection ranks on `time_s` (free from the Dijkstra,
it is the routing objective) and over-selects a margin, and `build_approach_table.py` then re-ranks
the survivors by DIN exactly as today.

That is an approximation. Measured over the current run's 74,616 FAST_ANY rows grouped by
(hut, source_type) — 1,348 groups, mean 55 candidates — using `distance_m` as a deliberately worse
stand-in for `time_s` (so an upper bound on the churn):

| over-select | DIN-best-3 falling outside it |
| --- | --- |
| top-3 | 14.9% |
| top-5 | 5.6% |
| top-10 | 1.2% |
| top-20 | 0.23% |

§B4 ships top-20, which makes the residual divergence small but not zero.

## The exact alternative

Run a **scalars-only path walk** in the distance pass: `lib/cell_igraph.py`'s `accumulate_path`
with the `trail_coords` accumulation removed.

The observation that makes this cheap is that **the coordinate list is the entire memory and I/O
problem**, not the walk. §A6 of the spec measures it: 231M coordinate tuples resident in the parent
process today, on the order of 16 GB as live Python objects, against a 23 GB machine — that is what
makes an A-only landing OOM. The walk itself is O(edges traversed) and touches the same igraph edge
attributes the router already loaded.

Dropping the coordinates but keeping the accumulation yields true `ascent_m`/`descent_m` for every
candidate pair, which means:

- The selection ranks on real `din_duration_h` and is **exactly equal to today's output by
  construction** — the over-selection factor, and the open question behind it, disappear rather
  than being bounded.
- `access_distances.npy` (§B3) gains ascent/descent columns. That intermediate is already described
  as "the first cheap, complete answer to *which trailheads can reach which hut*"; with elevation
  aggregates it becomes answerable in DIN duration too, without touching geometry.

## Cost

Roughly the current `paths` step scaled to the denser access-point set — order 25 minutes wall on
12 workers (3,635–3,868 CPU-s measured today at 212,862 records, `data/timings.jsonl`), against a
post-§A+§B `hub_edge_query` of well under 10 minutes. So it is a real, non-trivial addition to the
run, which is why the spec ships the over-selection first and holds this in reserve.

## When to pick it up

Either of:

- §B's validation (spec open question 4) shows the DIN/`time_s` divergence is not where the
  measurement above predicts, or shows it landing on huts that matter (remote huts with few
  candidates, where a single displaced approach is the whole table); or
- something else wants per-pair elevation aggregates without geometry — a data-quality layer, an
  approach-difficulty filter, or a second consumer of `access_distances.npy`.

Absent either, top-20 over-selection is the right trade and this stays parked.
