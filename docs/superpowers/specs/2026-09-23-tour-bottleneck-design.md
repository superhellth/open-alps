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

The hut order of a tour is the order of its `Huettenliste` in `tourSelection.php`. It is validated
against the five tours that the pipeline matched (`huts/public/data/tours.json`: Lechquellenrunde,
Pitztaltour, Tauernhöhenweg, Verwallrunde, Welser Höhenweg). Their leg sequence is the ground truth.
An API order that equals the pipeline order, or its reverse, counts as valid. The match rate is
reported. If any of the five disagrees, the plan stops and re-decides the order source.

The stage distance between two huts is the difference of their positions in the order (in nights).
The direction of a hiker is unknown, and a circular tour (`Rundtour`) has no fixed direction. So the
offset scheme is direction-free (see Treatment). A tour with no reliable order enters only the
offset-0 test.

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

For a tour hut B (not A) at stage distance m = |position(B) − position(A)| nights, the treatment on
day d is 1 if A is sold out on day d − m or on day d + m (either hiking direction), else 0. For a
circular tour, m is the shorter way round. The primary test uses m ≤ 2, taking each hut's own m. A
hut shared by two tours takes the treatment of each tour as a separate row, and errors cluster by
hut.

The direction-free scheme cannot test "the effect is on later nights only". The offset check (see
Analysis) uses the signed offset instead, for the tours whose order is validated and that are not
circular.

### Controls

For each tour hut B, the controls are the 3 nearest non-tour huts that are open in the same season,
within ±500 m elevation of B and of a similar size (log capacity, standardised, as in the first
study's matching code). There is no distance cap. The distance of every control is reported, and a
tour hut with no control is counted and dropped. A control hut takes the treatment series of the tour
that the tour hut B belongs to, with the same m as B. A control hut matched to two tour huts appears
once per pair.

Sensitivity: the primary run is repeated with a radius cap of 15, 25 and 40 km on the nearest-3
rule. A tour hut with fewer than 3 controls inside the cap keeps those it has.

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
- OLS with standard errors clustered by hut, reported. The primary 95% interval is a pairs cluster
  bootstrap: resample huts with replacement (a tour hut with its controls counts as one unit), refit,
  take the 2.5% and 97.5% percentiles of the coefficient (2000 draws, fixed seed). It uses only numpy
  and statsmodels.

### Analysis steps

1. **Candidates.** Table of tours, eligible huts, chosen bottleneck, capacity ratio, and whether it
   qualifies.
2. **Primary.** The DiD coefficient for season 2025, offsets as above, with 95% interval.
3. **Offsets.** The coefficient per signed offset k from −3 to +3 nights, for non-circular tours with
   a validated order. The thesis predicts an effect at k = 0 and at offsets along the hiking
   direction only. An effect at every offset points to a regional demand confound.
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

## Out of scope, future

- Future extension: daily calendar snapshots from now on would give booking curves and allow the
  "speed over time" reading. Not part of this study.
