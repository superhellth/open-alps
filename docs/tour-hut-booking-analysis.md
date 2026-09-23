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
