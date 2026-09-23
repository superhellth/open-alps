# Tour bottleneck-hut study

## Goal

Test this thesis: most official tours have a bottleneck hut. When it is sold out, the other huts of
the tour have lower occupancy than nearby huts that are not on the tour.

The mechanism: a hiker who cannot get a bed in the bottleneck hut cannot walk the tour, so the
hiker does not book, or cancels, the other huts of the tour. Non-tour huts do not have this
dependence.

This study extends `2026-09-23-tour-hut-booking-study-design.md`. It reuses that study's
`hut-days.csv`, `huts.json` and `raw/tours.json`. It needs no new fetch and no change to
`pipeline/`, the doit DAG or the app in `huts/`.

## Decisions

| Question | Decision |
| --- | --- |
| Thesis reading | Occupancy level on the same dates. Booking speed over time is out of scope |
| Bottleneck choice | Fixed before the effect is computed: the smallest-capacity hut of the tour |
| Method | Pooled difference-in-differences with hut and date fixed effects. A per-tour table is exploratory |
| Outcome | Occupancy per hut-day, as defined in the first study (closed days dropped) |
| Time span | Season 2025 primary, season 2026 replication |
| Code location | `analysis/tour-huts/bottleneck.py` and tests. Outputs in gitignored `data/analysis/tour-huts/` |

## Limits of the data

- The calendar shows the final state for a past date. It contains no booking timeline, so "falls off
  quicker" cannot be measured. Only "is lower on the same dates" can.
- Cancellations are included, offline bookings are not.
- Capacity is the current capacity.
- Only 26 tours exist, some with few huts that have OHRS activity. Tours share huts.

## Design

### Inputs

- `hut-days.csv` (per `ohrs_id` and date: `open`, `occupancy`, `sold_out`, `sold_out_near`).
- `huts.json` (`on_tour`, `capacity`, `operator`, `elevation`, `lon`, `lat`, `guids`).
- `raw/tours.json` (per tour the hut GUID list) and the GPX tracks in `pipeline/tours/`.

Each tour's hut set is the tour's GUID list mapped to `ohrs_id` through `huts.json`. Huts that are
excluded in the first study (no OHRS id, error, self-service, no activity, capacity mismatch) are
excluded here too.

### Stage order

The direction of a tour and the order of its huts are needed to give the offset a sign. The plan
checks which source is reliable: the order of `Huettenliste`, or the order in which the GPX track
passes the huts (the pipeline's tour matching gives the hut sequence). If a tour has no reliable
order, it enters only the offset-0 test.

### Bottleneck per tour

A tour has a bottleneck candidate if it has at least 3 eligible huts and its smallest-capacity hut
has a capacity of at most 0.7 times the median capacity of the tour's eligible huts. Ties go to the
hut with the higher sold-out share, decided by the first season only. A tour without a candidate
leaves the primary test. The number of tours with and without candidate is a result: it answers
"most tours have a bottleneck".

The bottleneck is chosen from capacity only. It is never chosen by the size of its effect.

### Treatment

`A_full(d)` is 1 on a day d when the tour's bottleneck hut A is sold out (`sold_out`, sensitivity
`sold_out_near`), else 0.

For a tour hut B (not A) at stage offset k nights from A, the treatment on day d is
`A_full(d − k)`, with the sign of k given by the stage order. The primary test uses k = 0 and the
offsets that a stage order allows within one to two nights. A hut shared by two tours takes the
treatment of each tour as a separate row, and errors cluster by hut.

### Controls

For every bottleneck A, control huts are non-tour huts within a radius R of A (default 25 km, the
plan may tune it) that are open in the same season. Matching by elevation band, log capacity and
operator follows the first study's matching code. A control hut takes the `A_full` series of the
tour bottleneck nearest to it, and the same offset schedule as the tour huts. A control hut that is
near two bottlenecks appears once per bottleneck.

Regional demand (weather, weekend, holidays) hits tour huts and controls alike, so it cancels in the
comparison. The design fails when the controls do not share the region, so the check "no tour
effect when A is a non-tour hut" (see Checks) is part of the primary result.

### Model

One row per hut-day-bottleneck pair, for tour huts B and controls C:

`occupancy ~ tour × A_full + hut FE + date FE`

- `tour` is 1 for a tour hut and 0 for a control. Its main effect is absorbed by hut FE.
- `A_full` main effect is absorbed by date FE where both groups share dates. It stays in the model
  if a bottleneck's dates make it not collinear.
- The coefficient of `tour × A_full` is the result: the extra occupancy change of tour huts when the
  bottleneck is sold out. The thesis predicts a negative value.
- OLS with standard errors clustered by hut. With few clusters (fewer than about 40 tour huts)
  the plan adds a wild cluster bootstrap interval.

### Analysis steps

1. **Candidates.** Table of tours, eligible huts, chosen bottleneck, capacity ratio, and whether it
   qualifies.
2. **Primary.** The DiD coefficient for season 2025, offsets as above, with 95% interval.
3. **Offsets.** The coefficient per offset k from −3 to +3 nights. The thesis predicts an effect at
   k = 0 and on the nights after A only. An effect at every offset points to a regional demand
   confound.
4. **Per-tour effects.** The coefficient per tour, exploratory, in a table and a forest plot.
5. **Bottleneck stands out.** For each tour, the effect with each of its huts as A. A permutation
   test asks whether the chosen bottleneck's effect is more negative than that of a random hut of the
   same tour (share of tours where it ranks first, against the share expected by chance).
6. **Cuts.** Weekends only, July and August only.
7. **Replication.** Season 2026 separately. Confirmed only if the sign matches and the intervals
   overlap.

### Validity checks

- **Placebo A.** Repeat the primary test with a non-tour hut of similar size as the "bottleneck". The
  effect should be zero.
- **Placebo dates.** Shuffle `A_full` within the same weekday and month. The effect should be zero.
- **Sold-out threshold.** Repeat with `sold_out_near`.
- **Ceiling.** Days where B is also sold out cannot fall further. Report the share, and repeat the test
  with days on which B was sold out dropped.
- **Power.** Before the treatment coefficient is inspected, compute the minimum detectable effect
  (two-sided α = 0.05, power 0.8) from the residual variance and the number of treated hut-days.
  Report it beside the result.
- **Multiple comparisons.** One pre-defined test: the primary DiD, season 2025, offset 0, bottleneck by
  capacity. All other results are exploratory and labelled so.

### Outputs and documentation

- `data/analysis/tour-huts/bottleneck-results.json`, the candidate table, and plots (offset profile,
  per-tour forest plot).
- `docs/tour-hut-booking-analysis.md` gets a section with the result and the stated limits.
- `docs/superpowers/STATUS.md` gets a row for this spec.

## Testing

- Unit tests with small fixtures, no network.
- Bottleneck choice: smallest capacity wins, the 0.7 ratio and the 3-hut rule exclude tours, ties are
  resolved by sold-out share.
- Offset treatment: a hand-built 5-day series gives the expected `A_full(d − k)` for both signs.
- DiD: a synthetic data set with a known negative effect returns the effect. One with none returns a
  zero within the interval.
- Shared hut: a hut on two tours produces two rows per day and one cluster.
- Placebo shuffle keeps the weekday and month counts.

## Risks

- **Regional confound.** A sold-out bottleneck marks high regional demand. If controls are not close
  enough, this biases the effect upward, against the thesis. The placebo and the offset profile
  detect it.
- **Ceiling.** Busy tour huts near capacity have no room to fall, which hides an effect.
- **Weak candidates.** Few tours may have a clear smaller hut, which shrinks the sample.
- **Timing.** A one-night shift of tour hikers is in the offset test, but hikers on tours of different
  pace or direction are not.
- **Small sample.** With 26 tours the result can be "no detectable effect". The power estimate puts
  that into numbers.

## Open items for the plan

- Which source gives the reliable hut order and direction per tour.
- Radius R and the elevation band for controls.
- Whether the wild cluster bootstrap is available in the pixi env, else a plain cluster bootstrap.
- Future extension: daily calendar snapshots from now on would give booking curves and allow the
  "speed over time" reading. Not part of this study.
