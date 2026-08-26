# Multi-day tour suggestion: deferred items and future ideas

Date: 2026-08-22
Status: parking lot — nothing here is scheduled

Companion to `2026-08-21-tour-suggestion-design.md`. Everything below was considered during that
design and consciously left out of iteration 1. Each entry records **what it is**, **why it is not in
the first iteration**, and **what would unblock it** — so a later reader can tell a decision from an
oversight.

Nothing here may be implemented by quietly relaxing a rule in the main spec. Where an item would
weaken a stated guarantee, that is called out.

---

## Pipeline / data

### `ROAD_*` variant column

The "least road" objective, defined in the main spec (Part 2) as a multiplicative penalty on the time
of road-tagged segments (factor ~3-5).

**Why deferred:** iteration 1 builds the fastest column only (`FAST_ANY`, `FAST_T2`, `FAST_T3`).
Build time, not payload, is the constraint.

**Unblocked by:** the `road_m / distance_m` distribution measured after the Part 1 rebuild, plus the
sizing probe's substitution rate for the `ROAD_*` cell. If the fastest paths turn out to be mostly
road-free, the column is not worth its build cost; if they are not, this is the highest-value
addition to the grid.

**Note:** with `roadPenaltyFactor` removed in Part 1, this is the *only* road-avoidance mechanism in
the design. Nothing else substitutes a trail for asphalt — `road_m` can only delete an edge.

### `ASC_*` variant column (least ascent)

**Why deferred:** probably redundant. Part 1's speed model prices climb steeply, so the time-optimal
path is already close to ascent-optimal; the column would largely store second copies of the fastest
path.

**Unblocked by:** a substitution rate from the sizing probe high enough to contradict that. If the
probe says otherwise, build it; the argument above is a prediction, not a measurement.

### Fourth passability row — `graded <= T3, ungraded permitted`

Already described in the main spec's Passability section as the fallback if ungraded terrain turns
out to be load-bearing for connectivity.

**Unblocked by:** the sizing probe's **ungraded blocker rate** — for pairs where a constrained row
finds no path at all, how often an ungraded segment, rather than genuine difficulty, was the binding
obstacle.

**Guardrail:** if built, it ships *next to* the strict row with the UI naming the difference in the
result. Relaxing the strict row's definition to restore connectivity is not an option — the guarantee
is the entire reason that row exists.

### Directed routing (direction-optimal stored paths)

The stored graph is undirected, one record per unordered pair. Under Part 1's pointwise speed model
the optimal path is direction-dependent (main spec, Part 3, Direction).

**Why deferred:** fixing it means routing every pair twice and doubling the build phase.

**Note — this got weaker, not stronger.** An earlier draft argued the effect was negligible because
direction shifted every candidate by one shared constant under the DIN blend, leaving only a kink to
flip rankings. A pointwise speed model has no kink and no shared constant: reversing flips the sign
of every segment's slope, and the resulting cost depends on the slope *distribution* along each
candidate, which differs between candidates. The magnitude is now unknown rather than bounded.

**Unblocked by:** the sizing probe's "direction spread" measurement — routing a sample of pairs both
ways and comparing the resulting geometries. If the spread is material, this stops being a deferred
nicety.

### Hut season as a shipped column

Season is static, so it can be a column on `huts.geojson` and a hard filter applied to the node set
before the search runs. Costs the pipeline one column and the search nothing (it shrinks the graph).

**Why deferred:** scoping, not difficulty. This is the cheapest item on the list.

**Unblocked by:** confirming the ArcGIS hut layer actually carries a season/opening field. If it does
not, this needs a data source first, and that is the real work.

**Worth knowing:** until this lands, the search can return a tour through a hut that is shut. That is
a wrong answer, not a partial one.

### Parking legality and overnight restrictions

The approach table already hard-drops `access=private/no` and marks `access_unknown`. Overnight
parking is a separate question: fees, winter closures, overnight bans, avalanche closures. A car user
leaves the vehicle for several days.

**Why deferred:** OSM coverage of these tags is unknown and probably thin.

**Unblocked by:** a coverage measurement over the retained start points. At minimum, ship `fee` and
surface "overnight parking unverified" — the same honesty standard the main spec applies to
`ungraded_m`.

---

## Search / modelling

### Soft leg-time band (leg-balance scoring)

Replace the hard `minLegTime` filter with a scoring term, so one short leg costs a little instead of
deleting the chain:

```
penalty(t) = max(0, minLegTime - t) + max(0, t - maxLegTimeSoft)
score      = sum of penalty(leg) over the chain
```

with a low absolute floor (~1 h) kept as a hard prune to kill degenerate hops, and `maxLegTime`
staying hard. The asymmetry is deliberate: a too-short leg is a preference, a too-long leg is one the
user physically cannot walk.

**Why deferred:** the main spec's measurement says `minLegTime` prunes almost nothing anyway (median
edge length 20.1 km), so the failure this fixes — deleting a legitimate chain that has one short
arrival leg — is currently rare.

**Unblocked by:** real results showing plausible chains being dropped on a single short leg.

**Property worth keeping:** the penalty is additive over legs, so it accumulates monotonically along a
prefix — valid as a beam sort key and as a DFS prune bound.

### Loop relaxation for `car` mode

Today `car` requires exit start point == entry start point, exactly. Real users accept ending at a
*different* trailhead when a bus or train links back, or when it is a 40-minute walk down the same
valley.

**Why deferred:** needs a start-to-start proximity or connection table that does not exist, and the
strict rule is correct-if-narrow rather than wrong.

**Unblocked by:** a precomputed start-point adjacency table (walking distance, and/or public transport
connection). Small — it is start points against start points, not against huts.

**Guardrail:** this and the mixed mode below are **one decision, not two.** Loosening `car`'s closure
piecemeal to approximate "drive out, train back" would produce chains nobody can actually walk, which
is exactly why `either` was removed.

### Mixed mode: drive there, return by public transport

A real and popular pattern, and the only case where a car user legitimately ends somewhere else.

**Why deferred:** requires knowing whether a station near the exit connects back to a station near the
origin parking. No such data in the pipeline.

**Unblocked by:** a transit connectivity source. Until then it does not exist as a mode — and must not
be half-covered by weakening an existing one.

### Client-side `either`: merged listing

If a user genuinely does not care how they get there, run the `car` and `transit` searches separately
and merge the ranked lists, labelling each row by mode. Every row is then individually valid.

**Why deferred:** presentation concern, and it costs two searches (~300 ms each).

**Not to be confused with** the removed `either` *mode*, which unioned the start sets under a free
closure rule and emitted parking-to-different-parking chains that nobody can walk.

### Transit exit-station proximity as a weak tiebreak

`transit` currently leaves the distance between entry and exit station explicitly unconstrained.
Straight-line distance between them is free to compute and a reasonable soft preference — ending 40 km
away beats ending 300 km away, all else equal.

**Why deferred:** it is not a filter and not a guarantee about actual connections, so it adds a knob
for a modest gain. Skip unless the objective set is being touched anyway.

---

## Client / presentation

Everything in this section is frontend work and is listed so the backend contract does not
accidentally grow to accommodate it.

### Pace multiplier

DIN 33466 is a fixed-speed model; real hikers spread roughly ±30% around it. A single pace slider
scaling every computed leg time client-side makes every time budget the user sets meaningful to *their*
legs rather than a stranger's.

**Cost:** one multiplier. This is probably the highest value-per-line item in the whole design.

**Also:** label reported durations as walking time excluding breaks, or users will compare them against
hut signage and mistrust the app.

### Days / nights vocabulary

The search speaks only in legs (`[Lmin, Lmax]`). The client owns the translation to whatever it shows
— "4 days", "3 nights", "5 stages". Recommendation, not a requirement: ask for **nights**, which is
unambiguous and matches how huts are booked.

### Plain-language difficulty labels

Users do not know T2 from T3. Labels plus the consequence of the choice stated while choosing — the
main spec already measures it: a T3 cap leaves 23% of huts unconnected, a T2 cap 39%. Showing that
before the search beats explaining it after an empty result.

### Result card contract

The main spec stops at "~10 visibly different chains" and never says what a result shows. Needed:
leg-by-leg rows (hut, time, ascent, descent, SAC grade, ungraded metres), totals, start point with its
access flags, map preview.

**Note:** the main spec's non-negotiable display rule — any `*_ANY` result must show its ungraded
length — currently has nowhere to live. This is where it goes.

### Bed availability post-filter

Per-hut, per-date OHRS calls cannot run during the search. Applied to the handful of returned chains
only. Called out as a non-goal in the main spec; repeated here because it is the item users will ask
for first.
