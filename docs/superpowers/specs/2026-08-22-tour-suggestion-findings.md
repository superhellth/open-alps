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

**Post-rebuild re-measurement (Task 24 §4, `python pipeline/analysis/road_share.py`, ts
2026-08-26):** the floor above was accurate — removing `roadPenaltyFactor` and routing on `time_s`
(which rewards roads for being fast) pushed the aggregate road share up sharply: hut edges
**9.7% → 22.1%** (median edge 4.3% → 15.8%, road-free share 29.4% → 20.6%), start edges
**19.1% → 39.2%** (median 37.8%, road-free share collapses to 0.8%). Roughly 1 in 5 metres of a
typical hut-to-hut route, and 2 in 5 of a typical trailhead approach, is now road under the fastest
column.

**`ROAD_*` decision (settled):** build it. The regression this rebuild introduced is real and
larger than the pre-rebuild floor suggested, and §5's probe already measured that a road-avoiding
column (`ROAD_AVOID`, ×4 time penalty on road-tagged edges) diverges from `FAST` on 86.9% of pairs
at only 0.96× the routing cost — cheap and frequently a genuinely different route, not a rare
edge case. Per the plan, this is a **multiplicative penalty on road-tagged segments' `time_s`**
(factor ~3-5, `ROAD_AVOID` in the probe used ×4) added as a **new objective/variant column**, never
a revived `roadPenaltyFactor` baked into `dist`/`time_s` itself. Building it means one more
`build_hub_edges` pass (a 5th variant row) — an hours-scale `doit` run — and is scoped as a
follow-up task, not folded into this rebuild's already-committed output; ask before running it.

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

**Post-rebuild re-measurement (Task 24 §4, `python pipeline/analysis/payload_sizing.py`, ts
2026-08-26, real 4-row variant data, not the zero-filled/duplicate-column floor above):** hut edge
payload (4 variants × 12,416 rows × 13 columns): 472.9 KB raw / 140.5 KB gz for 1 variant, 1,418.6
KB raw / 396.6 KB gz for the 3 constrained variants (shuffle still makes it worse — stays out of
scope). Approach table (k=3, 2,142 rows): 52.3 KB raw / 31.6 KB gz — 0 of 714 huts fall short of
k=3 approaches. Loop-closure reverse index: 636.5 KB raw / 330.7 KB gz. **Total client payload
floor (shuffled gzip): 548.3 KB.** Real variant data compresses worse than the pre-rebuild
all-identical-columns estimate predicted (43.4 KB → 396.6 KB for 3 variants), as flagged — still
far under any plausible budget; decision unchanged.

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

`build_base_graph` (re-run after the hub-range clipping work): `stream_osm` 354.0 s, `contract_structural`
106.1 s, total 502.9 s (`data/timings.jsonl`, ts 2026-08-23T07:14). `add_base_elevation` (new task):
**392.0 s** total — `smooth` dominates at 366.0 s (59 grid cells), `read_dem`/`sample`/`write`
combined under 21 s, `ascent_descent` under 1 s. Feeds Task 11's probe budget and Task 24's rebuild
estimate: base graph + elevation together are ~15 min, well under the hours `build_hub_edges` alone
costs.

Verification (`edges.npy`, 4,729,589 edges): no field left at the `UNSET` (-1.0) sentinel;
`time_s`/`ascent_m`/`descent_m`/`ungraded_m`/`inferred_m` all populated with sane ranges.
`constrained_ok` share over the first 1M edges: **92.6%**, consistent with the network tier mass
above (explicit 4.56% + inferred 89.52% = 94.08% graded) — no reconciliation needed with the
production classifier.

## 5. Sizing probe (open questions 1, 2, 4, 5) — `data/analysis/routing_probe.json`

`python pipeline/analysis/routing_probe.py --pairs 200`, seed 42, ~992.6s wall time (~46 distinct
grid cells dominate — `_build_igraph_with_snaps`'s per-edge Python construction on a ~670k-edge
padded cell, ~12-15s each; bounded by cell count, not pair count past that).

**Substitution rate** (fraction of pairs whose path differs from the true production baseline,
`FAST_ANY` routed on `FAST`/`time_s`):

| cell | substitution rate |
|---|---|
| `FAST_ANY` × `SHORT` | 93.4% |
| `FAST_ANY` × `ROAD_AVOID` (×4 time penalty on road-tagged edges) | 86.9% |
| `FAST_T2` × `FAST` | 52.6% |
| `FAST_T3` × `FAST` | 55.5% |

`SHORT`/`ROAD_AVOID` diverge from `FAST` on the large majority of pairs at essentially the same
routing cost (wall-time ratio to `FAST`: `SHORT` 0.94×, `ROAD_AVOID` 0.96×) — a real signal for the
deferred `ROAD_*` decision (open question 1), though not itself a decision: high substitution says
a road-avoiding column would frequently produce a *different* route, not that the difference is
one users would want, and the measured aggregate road share is only 9.7% (§1) — most legs don't
have much road to avoid in the first place. Left for Task 24's post-rebuild re-run, as originally
planned; this is supporting evidence, not new grounds to move it earlier.

**Baseline violation**: `FAST_ANY`/`FAST` itself already violates `FAST_T2`'s constraint on 88.1%
of pairs, `FAST_T3`'s on 87.4% — consistent with §3's 12.7%-fully-graded figure on stored edges.

**Ungraded blocker rate** (open question 2, corroborating §3's connectivity-gate measurement from a
different angle — probe-routed pairs, not stored-edge attribution): of 145 T2/T3 pairs where the
`FAST` column found no path, **66 were blocked by ungraded terrain alone** (relaxing the
`ungraded_m == 0` rule opens a path), 10 by genuine difficulty alone (relaxing the ceiling opens a
path), 1 by both, and 68 were disconnected under either relaxation (no path exists in this padded
cell regardless — a `maxEdgeKm`/connectivity question, not a passability one). Ungraded terrain is
the dominant *passability* blocker (66 vs 10), reinforcing §3/§4's decision: `FAST_T3_UNGRADED` is
required, and the 5% threshold was crossed by a wide margin from two independent measurements.

**Duration calibration (open question 5)** — routed `FAST_ANY` time (`time_s` summed along the
path) vs `speed.din_duration_h` on the same path's aggregates, 137 pairs with `distance_m > 0`:
least-squares scale factor **`routed ≈ 0.6689 × din`** (residual std 2.26h, noisy at n=137 across
widely varying leg lengths, but the central estimate is what matters here). The placeholder
constants (`v0=6.0, k=3.5, s0=0.05`) route **faster** than DIN by that factor — applying the scale
uniformly to `v0` (time ∝ 1/v for a fixed curve shape, so `new_v0 = v0 × scale` reproduces exactly
`new_time = old_time / scale`) gives **`v0 = 6.0 × 0.6689 = 4.013`**, landing almost exactly on DIN
33466's own stated flat-ground rate (`distance_m / 4000` ⇒ 4.0 km/h, `lib/speed.py`'s
`din_duration_h`) — a clean cross-check that the calibration is doing something sensible, not an
artifact. `k`/`s0` (the curve's shape) are unchanged: this is a uniform-scale fit, not a full
nonlinear refit (`routing_probe.py`'s `_fit_speed_constants` docstring records this as a deliberate
probe-scope limitation — a full refit was out of scope for a minutes-long probe).

**Decision:** `graph.speedModel` becomes `{v0: 4.013, k: 3.5, s0: 0.05}` (was
`{v0: 6.0, k: 3.5, s0: 0.05}`). `graph.variants` becomes
`["FAST_ANY", "FAST_T2", "FAST_T3", "FAST_T3_UNGRADED"]`.

**Direction spread (open question 4)**: 30 pairs routed both directions — **100% identical
geometry**, cost ratio 1.0 (undirected graph, as expected; asymmetric ascent/descent is a display
concern, not a routing/storage one — §D4's "one record per unordered pair" stands unmodified).

## 6. Task 24 — full rebuild output invariants

`data/osm/hut_edges/records.npy`, 12,416 records across the 4-row grid:

| variant | rows | max `ungraded_m` |
|---|---|---|
| 0 `FAST_ANY` | 5,074 | 22,186.5 (expected — unconstrained) |
| 1 `FAST_T2` | 1,770 | **0.0** |
| 2 `FAST_T3` | 2,307 | **0.0** |
| 3 `FAST_T3_UNGRADED` | 3,265 | 22,186.5 (expected — ungraded permitted by design) |

The §C4 guarantee holds: every constrained row (`FAST_T2`, `FAST_T3`) has `max ungraded_m == 0.0`,
no leak. `unsnapped_huts.json`: 290 huts. Constrained rows (1,770 / 2,307) are well below `FAST_ANY`
(5,074), consistent with the 31.7%/36.9% connectivity-loss figures in §3 — that gap is the deletion
those rows exist to make explicit rather than the router silently substituting a road/ungraded
detour.
