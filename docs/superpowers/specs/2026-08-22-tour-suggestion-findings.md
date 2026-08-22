# Tour suggestion backend — measured findings

Source of truth for the numbers this work's decisions rest on. Every figure names the script
that produced it and the caveat attached to it.

## 1. Road share (open question 1) — `data/analysis/road_share.json`

Hut edges: aggregate road share **9.7%**, median edge share 4.3%, p90 29.0%, 29.4% of edges are
road-free entirely, 4.2% are >50% road. Start edges: aggregate road share **19.1%** (higher —
trailhead access legs lean on forest roads/service tracks more than hut-to-hut legs do). By
`sac_rank`: ungraded (-1) and T1 edges lean heaviest on road (39.0%/34.2% aggregate share), T3
edges lightest (8.8%).

**Caveat:** measured under the *distance* cost with `roadPenaltyFactor: 1.3` still actively
penalising road segments. The time-based cost (spec A1) both removes that penalty and additionally
rewards roads for being fast, so these numbers are a **floor**, not a prediction — the real
post-rebuild share can only be higher.

**Decision:** `ROAD_*` deferred to the post-rebuild re-run (Task 24), per plan.

## 2. Payload (open question 3) — `data/analysis/payload_sizing.json`

3 variants × 6,067 hut edges × 13 columns = 693.2 KB raw, **43.4 KB gzipped** (46.4 KB with a
byte-shuffle filter — shuffling made it *worse*, so it stays out of scope). 1 variant: 231.1 KB
raw / 41.1 KB gzipped. Approach table (k=3, 2,193 rows × 9 columns): 53.5 KB raw / 22.0 KB
gzipped.

**Caveat:** four columns (`max_ele_m`, `ungraded_m`, `inferred_m`, `snap_m`) are still zero-filled
and the three variant copies are byte-identical (no variant routing exists yet), so both gzip
figures are floors — real variant data compresses worse than an all-zero/duplicate column. Even
so, both are far under any plausible payload budget.

**Decision:** payload is not a constraint; build time is. No quantisation in scope.

`access` tag distribution over 27,261+ parking points (`payload_sizing.json`): 21,058 unknown,
3,293 `private`, 2,973 `yes`, 2,251 `customers`, 308 `permissive`, 154 `no`. `motor_vehicle` is not
measurable yet — `fetch_stations_parking.py`'s `keep_fields` doesn't fetch it (Task 19 fixes this).

## 3. Ungraded blocker rate (open question 2) — `data/analysis/grading_coverage.json`

**Segment match rate: 97.8%** (by length, hut edges) — high enough that the per-edge tier numbers
below are trustworthy, not an artifact of failed attribution.

**Network-wide tier mass by length:** explicit 4.56%, inferred 89.52%, ungraded 5.92%. Most of the
network is physically-implied (tracks, footways, paved paths), not literally sac_scale-tagged —
consistent with `lib/grading.py`'s design rationale (91.3% of untagged mass covered by inference).

**Per-hut-edge tier split** (6,067 stored hut-edge paths, 716 huts total): only **768/6,067 edges
(12.7%) are already fully graded** (`ungraded_m == 0`) under the *current* distance-cost routing —
most stored paths cross at least some ungraded terrain somewhere along their length.
`ungraded_share` median 6.2% of edge length, p90 26.8%, p99 54.9%.

**The connectivity gate — the number that gates the row decision:**

| cap | edges in 12 km budget | + fully-graded rule | edges lost | extra huts isolated |
|---|---|---|---|---|
| `sac_rank <= 2` | 702 | 236 | 466 (66.4%) | **227** |
| `sac_rank <= 3` | 994 | 325 | 669 (67.3%) | **264** |

Against 716 huts total: **227/716 = 31.7%** of huts lose their last T2 connection when the strict
`ungraded_m == 0` rule is added on top of a `sac_rank <= 2` cap; **264/716 = 36.9%** for T3. Both
figures are measured on the *existing* stored (unconstrained, distance-routed) paths, so they are
a lower bound — a real constrained re-route may recover some of this by finding a longer-but-graded
detour the unconstrained router never needed to find. Even allowing for that, a lower bound this
far above the threshold is not going to close the gap by re-routing alone.

**Decision rule (per plan §3):**
- < 5% of huts lose their last connection → three-row grid as specced (§C3).
- **>= 5% → build the fourth row (`FAST_T3_UNGRADED`: `graded <= T3, ungraded permitted`, §H
  fallback), with the UI naming the difference. The strict row's definition is NOT relaxed either
  way.**

**Outcome: 31.7% (T2) / 36.9% (T3), both far over 5%. The fourth row is required.**

## 4. Grid decision (literal, for Task 11 to copy verbatim)

```
FAST_ANY, FAST_T2, FAST_T3, FAST_T3_UNGRADED
```

`FAST_T3_UNGRADED` = `graded <= T3` (via `sac_rank <= 3` with `sac_rank >= 0`, same as `FAST_T3`'s
ceiling check) but **without** the `constrained_ok`/`ungraded_m == 0` requirement — i.e. it forbids
T4+ terrain and via ferrata (the ceiling check still applies) but permits routing across genuinely
ungraded (unmapped-difficulty) trail. This is a *relaxation of the ungraded rule*, not a relaxation
of the difficulty ceiling — `FAST_T3`'s own definition (`ungraded_m == 0` guaranteed) is untouched;
`FAST_T3_UNGRADED` is a new, separate, honestly-labelled row for users who'd rather have a route
than a guarantee.

## Task 9 timing

_To be filled in after `doit build_base_graph add_base_elevation` runs._
