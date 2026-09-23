# Tour-hut booking study

## Goal

Settle whether huts on the Alpenverein's official tours are booked more than huts on no tour.

The first analysis (`docs/tour-hut-booking-analysis.md`) used 17 days at the end of the 2026 season and
free/full flags. It found no significant difference and could not separate the effects of season
end, elevation and hut size. This study uses a full season of past bookings and real capacities.

## Decisions

| Question | Decision |
| --- | --- |
| Primary outcome | Mean occupancy on open days: booked beds divided by capacity, closed days dropped |
| Secondary outcome | Share of open days that are sold out |
| Huts in scope | Our own hut set: every hut in `huts.geojson` with an `ohrsHutId` (239 huts, 77 on a tour) |
| Time span | Season 2025 (01.05.–31.10.2025) as primary; season 2026 (01.05.–23.09.2026) as replication |
| Confounders | Regression with controls plus a matched-pair check |
| Code location | Tracked `analysis/tour-huts/`; outputs in gitignored `data/analysis/tour-huts/` |

Not in scope: huts OHRS knows that are not in our hut set, years before 2025, and any change to
`pipeline/`, the doit DAG or the app in `huts/`.

## Background: what the API gives

All endpoints are public and need no authentication. They are on `www.hut-reservation.org` (OHRS).
Details are in `docs/alpenverein-api.md`; the two endpoints below are new and must be added there.

- **`POST /api/v1/reservation/availabilityCalendar/{ohrsHutId}`** with
  `{"arrivalDate":"DD.MM.YYYY","departureDate":"DD.MM.YYYY","nextPossibleReservations":false,"numberOfPeople":1}`
  returns one row per day: `{"date","dayOfWeek","freePlace","hutStatus"}`. `hutStatus` is `SERVICED`
  or `CLOSED`. It works for past dates. A full year in one request worked for hut 179. Unlike the
  `callOHRS_REST.php` proxy, it does not reject past dates.
- **`GET /api/v1/reservation/hutInfo/{ohrsHutId}`** returns `totalBedsInfo` (a string, "60"), per-bed
  category counts in `hutBedCategories`, `altitude`, `coordinates` and `tenantCode`.
- The OpenAPI description is at `/v3/api-docs`.

Findings from probes on 2026-09-23 (huts 179 and 62):

- Summers 2021–2024 show every day at maximum free places (60 and 48), with no bookings. Real
  booking data starts with season 2025 for these huts. Other huts may have joined at other times.
- Requests from Python's default HTTP client got HTTP 403, `curl` did not. The fetch script sets an
  explicit `User-Agent`.
- The calendar shows the state now for a past date. It includes cancellations and excludes bookings
  made outside OHRS.
- Capacity is the current capacity only. A past day's capacity may differ.

## Design

### Layout

Tracked code in `analysis/tour-huts/`, run in this order:

| Script | Reads | Writes (to `data/analysis/tour-huts/`) |
| --- | --- | --- |
| `fetch_tours.py` | `tourSelection.php` | `raw/tours.json` |
| `fetch_capacity.py` | `hutInfo/{id}` per hut | `raw/hut-info/{ohrsHutId}.json` |
| `fetch_calendars.py` | `availabilityCalendar/{id}` per hut and season | `raw/calendar-{season}.json` |
| `link_huts.py` | the three raw sets and `huts/public/data/huts.geojson` | `huts.json` |
| `build_hut_days.py` | `huts.json` and the calendars | `hut-days.parquet` or `hut-days.csv` |
| `analyze.py` | `hut-days` and `huts.json` | `results.json`, plots |

Raw responses are stored unmodified so an analysis change does not need a re-fetch. Every script
can re-run on its own. Fetch scripts skip requests whose raw file already exists unless `--refresh` is
passed. The scripts do not touch `pipeline/` and the doit DAG.

Existing exploratory scripts in `data/analysis/` (`fetch_hut_availability.py`,
`compare_tour_huts.py`) stay where they are and are not part of this study.

### Data acquisition

- **Tours.** `tourSelection.php` returns 26 tours. Each has `Bezeichnung` and `Huettenliste`, a
  comma-separated list of GUIDs in braces. Two tours have an empty list and one has no name. Tour huts
  are the union of all lists, matched case-insensitively to `huts.geojson`'s `properties.id`. Five
  GUIDs have no match in `huts.geojson` and are listed in the output, not dropped silently.
- **Capacity.** One `hutInfo` call per hut in scope. Store the full response. Capacity is
  `totalBedsInfo` as an integer, and the sum of `totalSleepingPlaces` across `hutBedCategories` is
  recorded as a cross-check.
- **Calendars.** One `availabilityCalendar` call per hut and season. Season 2025 is 01.05.2025 to
  31.10.2025 and season 2026 is 01.05.2026 to 23.09.2026, both for `numberOfPeople: 1`. The number of
  calls is about 480.
- **Load.** Requests are spaced by 0.3 s, retried up to three times with backoff, and run one at a
  time. A failed request is stored as an error record with the message, never skipped.

### Linking and eligibility

- **Link key.** `ohrsHutId` (string in `huts.geojson`) to the hut's GUID. One `ohrsHutId` can map to
  two GUIDs (id 73: Höllentaleingangshütte and Höllentalangerhütte). They stay two entries with the
  same calendar and capacity, and the analysis counts them as one hut (see below).
- **Coordinate check.** `hutInfo.coordinates` is compared with the geojson point. A distance above
  1 km is flagged for review. The link is not changed automatically.
- **Huts with API errors.** 14 huts returned `302 Tenant code not found` or `701 No huts found` from
  the older proxy. They are retried once against the new endpoints. Huts that still fail are listed
  in `huts.json` with the error and are excluded from the analysis. The count of excluded huts per
  group (tour, other) is reported.
- **Self-service huts** (`serviced: false`) are excluded. Only one hut in scope is self-service.
- **Eligible hut per season.** Eligibility depends on the calendar's open days only, never on
  bookings: a hut is eligible for a season if it has at least 14 open days (see Metric).
- **No-activity huts.** An eligible hut whose `freePlace` is the same on every open day of a season
  has no OHRS booking in that season. It is marked "no activity". The data cannot tell a hut that
  does not use OHRS from an empty hut, so the primary run excludes these huts, and a sensitivity run
  includes them with occupancy 0. The two runs bound the effect of the exclusion. The share of
  no-activity huts is reported per group and season.

### Metric

Per hut-day, for an open day (`hutStatus == SERVICED`):

- `booked = capacity − freePlace`
- `occupancy = booked / capacity`, with `freePlace` clamped to the range `0..capacity`
- a day with `freePlace == 0` is sold out and counts as occupancy 1
- days with `hutStatus == CLOSED` are dropped

If `freePlace` exceeds `capacity` on any day, the hut is flagged as a capacity mismatch and excluded
from the primary run. It is reported, and the analysis is re-run with these huts included to show
the effect.

Per hut and season:

- **Primary:** mean occupancy over open days.
- **Secondary:** share of open days that are sold out (`freePlace == 0`). A sensitivity run counts a
  day as sold out when `freePlace` is at most 5% of capacity, because some huts may keep a few
  places free and never reach exactly 0.
- `open_days`: the number of open days in the season, kept as a control (see Analysis).
- Huts with fewer than 14 open days in a season are excluded from that season. A short season is too
  noisy.

The two Höllental huts share one calendar. They enter the analysis as one hut. Tour status is true
if either GUID is on a tour.

### Analysis

All models use one row per hut and season.

1. **Raw difference.** Mean primary outcome for tour and non-tour huts, with a bootstrap 95%
   confidence interval on the difference.
2. **Regression.** `occupancy ~ tour + elevation + capacity + operator + region + approach_time +
   open_days`, fitted with OLS and heteroscedasticity-robust errors. The tour effect and its 95%
   interval are reported.
   - `elevation` from `huts.geojson` (`0` means missing: excluded from the model).
   - `capacity` from `hutInfo`, log-transformed.
   - `operator` from `tenantCode`, which is the club (5 = DAV, 8 = ÖAV), with three levels: DAV,
     ÖAV, other. The other codes cover only 1–3 huts each and are grouped as "other".
   - `open_days` from the Metric step. Huts that open only in high summer have a mechanically higher
     mean over open days. This control separates that effect from the tour effect.
   - `region` from the hut coordinates, as a coarse grid or a Bundesland/country lookup. The spec
     leaves the exact binning to the plan, as long as each cell has enough huts.
   - `approach_time` is the shortest approach duration from the pipeline's `approaches` output
     for the hut (minutes). Huts without an approach are excluded from the model and reported.
3. **Matched check.** For each tour hut, find up to three non-tour huts nearest in elevation,
   capacity and `open_days` (standardised distance, same operator level as in step 2). Compare the
   tour hut to the mean of its matches. Report the mean of the paired differences with a bootstrap
   interval, and the number of tour huts that found no match.
4. **Sold-out share.** Repeat 1 to 3 with the secondary outcome. Step 2 becomes a binomial GLM
   (logit link) with sold-out days as successes and open days as trials, and the same covariates
   and robust errors.
5. **Cuts.** Repeat the primary analysis for the whole season, for July and August only, and for
   Friday to Sunday only.
6. **Replication.** Run seasons 2025 and 2026 separately. The result counts as confirmed only if both
   seasons give the same sign and overlapping intervals.

### Validity checks

- **Capacity drift.** Flag huts where `freePlace` exceeds the current capacity (see Metric).
- **Booking channel.** OHRS sees online bookings only. The analysis states this as a limit. If the
  data allows, it also reports the share of huts with booking activity per group, since a group that
  uses OHRS less would look emptier.
- **Coverage.** Report the number of huts and open hut-days per group and season, and the share of
  huts marked "no data".
- **Past-data consistency.** For the huts in `data/analysis/hut-availability-raw.json`, the new
  calendar's `freePlace` for 23.09.–09.10.2026 is compared with the totals from the older per-hut call.
  Report how many days differ by more than one bed.
- **Multiple comparisons.** The primary result is one pre-defined test (regression tour effect, primary
  outcome, season 2025). Everything else is exploratory and is labelled as such.
- **Power.** Before `analyze.py` looks at the tour flag, it computes the minimum detectable
  difference in mean occupancy (two-sided α = 0.05, power 0.8). It uses the eligible group sizes and
  the pooled standard deviation of the primary outcome. The result is reported next to the primary
  result, so "no detectable difference" can be read as "no difference larger than X points". For
  scale: with about 70 tour and 160 other huts and a standard deviation of 0.2, the minimum is about
  8 percentage points.

### Outputs and documentation

- `data/analysis/tour-huts/` holds the raw data, the per-hut table, the per-hut-day table and
  `results.json`.
- `docs/tour-hut-booking-analysis.md` is rewritten with the study's results and links to this spec.
- `docs/alpenverein-api.md` gets a section for `availabilityCalendar` and `hutInfo` (fields,
  history behaviour, the 403 with default HTTP clients).
- `docs/superpowers/STATUS.md` gets a row for this spec.

## Testing

- The linking, metric and matching code has unit tests with small fixtures. The tests need no
  network: fetch scripts are tested against saved responses.
- A test checks that a fully booked day gives occupancy 1, that a closed day is dropped, and that
  `freePlace` above capacity is flagged.
- `link_huts.py` has a test for the shared id (two GUIDs, one calendar).
- A test checks that eligibility uses the open-day count only, and that a calendar with constant
  `freePlace` is marked "no activity".
- A test checks that the operator mapping groups codes other than 5 and 8 as "other".

## Risks

- **Booking channel.** Tour hikers may book online more than other guests. If so, tour huts look
  fuller than they are. This cannot be fixed with the data and stays a stated limit.
- **Capacity.** The current capacity may differ from 2025. The mismatch check catches only one
  direction (free places above capacity).
- **Selection.** No-activity huts drop out of the primary run, and they may differ between the
  groups. The run that includes them as occupancy 0 bounds this effect.
- **Small groups.** Only 77 tour huts have an OHRS id, and some will have no activity. Intervals may
  be wide. The result may still be "no detectable difference", which the power estimate puts into
  numbers.
- **API stability.** These endpoints are undocumented for third parties. They may change, so raw
  responses are kept.

## Open items for the plan

- How to bin `region` (grid, Bundesland/country).
- Whether `hut-days` is Parquet or CSV (depends on the pandas/pyarrow setup in the repo; check before
  planning).
- How to derive `approach_time` per hut from `approaches.bin`/`approaches.json`, whose contract is in
  `docs/tour-suggestion-payload.md`.
