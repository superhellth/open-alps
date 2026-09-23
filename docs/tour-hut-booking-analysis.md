# Are official-tour huts booked more than other huts?

Study of the 2025 season (primary) and 2026 season to 23.09.2026 (replication). Design and pre-defined
primary test: `docs/superpowers/specs/2026-09-23-tour-hut-booking-study-design.md`. Code and run order:
`analysis/tour-huts/README.md`. An earlier 17-day pilot on late-season data is superseded by this study.

## Conclusion

**Yes, tour huts are booked more, by about 7.6 percentage points of occupancy.** Primary test (OLS on
mean occupancy of open days, season 2025, controlling for elevation, log capacity, operator, region,
approach time and open days): tour effect **+0.076** (95% CI 0.013 to 0.140, p = 0.018, 62 tour and 125
other huts, one hut dropped for a missing covariate). The minimum detectable difference at 80% power was
0.089, so the estimate sits at the edge of what this sample can resolve: the direction is clear, the size
is imprecise (between about 1 and 14 points).

Raw means are 0.630 (tour) against 0.506 (other), a gap of 0.124 (CI 0.068 to 0.178). Controls cut it to
0.076, so part of the raw gap comes from tour huts being larger, more central, or otherwise different.

**Sold out is a different story.** Tour huts are not sold out more often (2025: 12.5% of open days against
14.5%; adjusted odds ratio 1.04, CI far across 1). Tour huts fill more on average but are not more often
completely full.

## Replication (2026)

Same specification on 2026: tour effect +0.086 (CI 0.026 to 0.146, p = 0.005; 67 tour, 137 other). Sign
and intervals agree with 2025 for all three outcomes (occupancy, sold out, sold out within 5% of
capacity): replicated.

## Data and coverage

238 OHRS huts (one `ohrsHutId` per hut; id 73 is shared by two GUIDs). 227 analysed, 11 excluded:

| Reason | Huts |
| --- | --- |
| calendar request answered HTTP 400 (both seasons) | 9 (1 tour hut: Taschachhaus) |
| self-service hut (Kampthaler-Hütte) | 1 |
| no capacity in hutInfo (Feichtau-Hütte) | 1 |

| Season | Group | Huts | Eligible (≥ 14 open days) | Open hut-days |
| --- | --- | --- | --- | --- |
| 2025 | tour | 76 | 76 | 9365 |
| 2025 | other | 151 | 150 | 21534 |
| 2026 | tour | 76 | 76 | 8045 |
| 2026 | other | 151 | 149 | 17900 |

Open = `hutStatus == "SERVICED"`. Days with status `UNSERVICED` (1209 days, unstaffed) count as not open,
like `CLOSED`. Five tour GUIDs from the catalogue match no hut in `huts.geojson` (listed in
`results.json`). Regions analysed: 109 central, 87 east, 31 west. One analysed hut has no approach time.

"No activity" huts (constant free places on every open day, so probably not booked through OHRS):
2025 5 of 150 other and 2 of 76 tour eligible huts; 2026 none. They are excluded from the primary run.
Huts with free places above capacity (capacity mismatch) are excluded from the primary run too: 20 other
and 12 tour huts in 2025.

## All specifications

Everything except the first row is **exploratory**; with this many looks, single p-values are not
evidence. Model = regression coefficient with 95% CI (occupancy: points of occupancy share; sold-out:
odds ratio). Matched = mean paired difference to the 3 nearest same-operator non-tour huts.

| Spec (season, cut, outcome, variant) | Raw diff | Model | Matched diff |
| --- | --- | --- | --- |
| **2025 season occupancy (primary)** | 0.124 (0.068–0.178) | 0.076 (0.013–0.140) | 0.118 (0.076–0.159) |
| 2025 Jul–Aug occupancy | 0.157 (0.103–0.208) | 0.112 (0.048–0.175) | 0.144 (0.101–0.187) |
| 2025 Fri–Sun occupancy | 0.091 (0.040–0.142) | 0.059 (−0.001–0.118) | 0.095 (0.053–0.136) |
| 2026 season occupancy | 0.151 (0.099–0.203) | 0.086 (0.026–0.146) | 0.084 (0.046–0.123) |
| 2026 Jul–Aug occupancy | 0.168 (0.117–0.219) | 0.115 (0.056–0.174) | 0.094 (0.054–0.134) |
| 2026 Fri–Sun occupancy | 0.109 (0.062–0.157) | 0.061 (0.007–0.114) | 0.054 (0.020–0.090) |
| 2025 season sold out | −0.020 (−0.061–0.021) | OR 1.04 (p = 0.86) | 0.040 (0.013–0.067) |
| 2025 Jul–Aug sold out | −0.008 (−0.050–0.037) | OR 1.18 (p = 0.47) | 0.048 (0.012–0.083) |
| 2025 Fri–Sun sold out | −0.022 (−0.066–0.024) | OR 1.09 (p = 0.68) | 0.044 (0.012–0.077) |
| 2026 season sold out | −0.006 (−0.050–0.038) | OR 1.10 (p = 0.67) | 0.022 (−0.015–0.064) |
| 2025 season sold out ≤ 5% free | 0.021 (−0.026–0.068) | OR 1.20 (p = 0.32) | 0.077 (0.042–0.112) |
| 2026 season sold out ≤ 5% free | 0.060 (0.007–0.113) | OR 1.34 (p = 0.09) | 0.068 (0.023–0.117) |
| 2025 season occupancy, no-activity huts included | 0.124 (0.059–0.184) | 0.053 (−0.018–0.123) | 0.103 (0.055–0.149) |
| 2025 season occupancy, capacity-mismatch huts included | 0.121 (0.071–0.173) | 0.076 (0.017–0.135) | 0.106 (0.062–0.149) |

Reading: the occupancy effect is positive in all eight occupancy rows, larger in July–August than
on Friday to Sunday, and always smaller after adjustment than raw. Including no-activity huts moves the
adjusted 2025 effect to 0.053 with a CI that includes 0, so the primary result is sensitive to that
choice. The sold-out outcomes show no consistent tour effect after adjustment. The matched sold-out
differences are positive while the adjusted odds ratios are near 1, so the sold-out result depends on the
method and is not settled.

## Validity checks

- **Capacity and mismatch.** Capacity is the current `totalBedsInfo`, not the 2025 one. Huts reporting
  more free places than capacity on some day are flagged and left out of the primary run (sensitivity row above).
- **Coordinates.** 6 huts have a hutInfo coordinate more than 1 km from the geojson point (Glungezer
  1.2 km, Mödlinger 1.0 km, Otto-Mayr 9.3 km, Bochumer 22.8 km, Goiserer 32.9 km, Edelweiss-Hütte am
  Schneeberg 60.9 km). The join uses `ohrsHutId`, so these are data-quality notes about one of the two
  sources, not join errors.
- **Past-data consistency.** New calendar free places against the earlier proxy file on 2175 overlapping
  hut-days: 111 (5%) differ by more than one place. The two endpoints do not agree exactly.
- **Booking channel.** OHRS shows only bookings made through OHRS. Bookings by phone or e-mail are not in
  the data, and their share may differ between tour and other huts.
- **Missing data.** One analysed hut has no approach time (dropped from the regression, kept in raw and
  matched comparisons); huts with elevation 0 in the geojson count as missing, not 0 m.

## Limits

- Observational: tour huts differ from other huts in ways the controls capture only partly (popularity,
  location on well-known routes, availability of day trips).
- Past calendars show the state now for a past date. Cancellations are in, bookings outside OHRS are not.
- One season is primary; 2026 runs only to 23.09.2026 and replicates the direction, not the exact size.
- The catalogue tags huts as on-tour or not, without weighing how many tours share a hut.

## Bottleneck huts

Question: on the days the smallest hut of an official tour is sold out, are the other huts of that tour
less occupied than similar non-tour huts? Spec: `docs/superpowers/specs/2026-09-23-tour-bottleneck-design.md`.
Code: `analysis/tour-huts/run_bottleneck.py`. No new fetch.

### Pre-defined test (2025, stage-aligned treatment)

The interaction of "tour hut" and "bottleneck sold out d ± m nights away" (m ≤ 2) on occupancy, with hut
and date fixed effects: **−0.015** occupancy points (bootstrap 95% interval −0.046 to +0.022; cluster-SE
interval −0.051 to +0.022; p = 0.43). It rests on 5 tours, 11 tour-hut units (clusters) and 408 treated
tour hut-days. The minimum detectable effect at 80% power is 0.041, so the interval excludes drops larger
than about 5 points but the study cannot tell an effect of 1–4 points from zero. The sign is negative, the
direction the thesis predicts, but there is no detectable effect.

### Most tours have a bottleneck?

No. 5 of 24 tours qualify (smallest hut at most 0.7 × the median capacity, at least 3 eligible huts):
Karnischer Höhenweg, Inntaler Höhenweg, Berliner Höhenweg, Stubaier Höhenweg, Welser Höhenweg. Order
validation: the API order agrees with the pipeline order for 5 of 5 matched tours. Membership differs for
two: Tauernhöhenweg (the API lists one more hut than the GPX track) and Welser Höhenweg (the API has
Wildensee-Hütte where the GPX track has Albert-Appel-Haus).

### Validity checks

- Placebo A (a non-tour hut of similar size takes the bottleneck's role): 2025 −0.013 (−0.034 to +0.009);
  2026 +0.037 (+0.002 to +0.071). The 2025 placebo is as large as the main estimate; the 2026 placebo is
  positive and nominally significant, so noise of this size occurs without a tour bottleneck.
- Placebo dates (A's sold-out series shuffled within weekday and month, 200 draws): p = 0.88 (2025) and
  0.60 (2026). The observed coefficient is not unusual against shuffled dates.
- Sold-out-near instead of sold-out: −0.009 (2025), +0.019 (2026).
- Ceiling (own hut sold out): tour huts are sold out on 9.8% (2025) and 15.4% (2026) of treated rows.
  Dropping those rows: −0.012 and −0.008.
- Control radius, 2025: no controls within 15 km for any unit (fit skipped); 25 km −0.060 (4 clusters);
  40 km −0.024 (10 clusters). 2026: 15 km −0.021 (3), 25 km +0.017 (6), 40 km −0.007 (12).
- Control distance in the primary run (no cap): median 34 km, maximum 47 km (2025); 31 and 43 km (2026).
  Controls are not local; regional weather and holiday effects are only partly removed.

### Exploratory results (not evidence)

- Offset profile, 2025 (treatment = A sold out on d − k), k = −3…3: −0.043, −0.022, −0.016, +0.008,
  +0.018, −0.012, −0.012. No peak at k = 0. 2026: −0.022, +0.007, −0.005, −0.018, −0.019, −0.022, +0.008.
  No offset stands out.
- Per tour, 2025: Berliner −0.039 (−0.083 to +0.004), Inntaler −0.067 (−0.091 to −0.043), Karnischer
  +0.009 (−0.054 to +0.073); Stubaier and Welser have one unit and are not fitted. 2026: Berliner +0.015,
  Inntaler −0.007, Karnischer −0.049 (−0.070 to −0.028), Stubaier +0.005. The tours that show a drop in
  one season do not show it in the other.
- Rank test (is the chosen bottleneck the hut with the most negative effect among the tour's huts?):
  2025 0 of 3 tours against 22.5% expected by chance; 2026 1 of 4 (25%) against 16.9%. Too few tours to
  say anything.
- Cuts, 2025: Fri–Sun −0.019 (−0.062 to +0.025), July–August −0.032 (−0.055 to −0.008). 2026: Fri–Sun
  −0.046 (−0.080 to −0.011), July–August +0.006 (−0.024 to +0.036). The nominally significant cells
  switch season, which is what chance across many cuts looks like.

### Replication (2026)

Same sign and overlapping bootstrap intervals: yes. 2026 coefficient −0.007 (bootstrap −0.033 to +0.025),
12 units, 415 treated tour hut-days, MDE 0.038.

### Limits

- The calendar shows the final state for a past date. It contains no booking timeline, so "falls off
  quicker" cannot be measured.
- Cancellations are included, offline bookings are not.
- Capacity is the current capacity.
- Only 26 tours exist, 5 with a bottleneck; tours share huts, so units are not independent beyond the
  clustering by tour hut.
