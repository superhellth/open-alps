# Multi-day tour suggestion: cost model, edge variants, client-side chain search

Date: 2026-08-21
Status: approved for planning

Builds on `docs/superpowers/specs/2026-08-19-pipeline-v2-design.md` (base graph / hub edge split,
`RECORD_DTYPE`, `hut_edges/` + `start_edges/`) and
`docs/superpowers/specs/2026-08-18-start-locations-design.md` (station/parking id scheme).
Nothing in those output contracts is replaced; this spec adds fields and variants to them, and
defines a new client-side layer that consumes them.

Everything consciously left out of this iteration is recorded in
`2026-08-21-tour-suggestion-deferred.md`, together with what would unblock it.

## Goal

The user states requirements and the app returns multi-day hut-to-hut chains that satisfy them.
A tour starts at a parking lot or station and ends at a parking lot or station, which may be the
same one (a loop) or a different one. A spatial anchor (region, viewport, "near me") is an
**optional filter**, not a requirement — a query with no anchor must work across all of
Austria+Bavaria.

### Query inputs

| Input | Type | Notes |
|---|---|---|
| **Transport mode** | `car` \| `transit` | First-class, not a post-filter — it decides the start-point set *and* whether the tour must return to its origin. See below. |
| **Leg count** | range `[Lmin, Lmax]` | Legs, not days. The search has no notion of days or nights; the client translates. See Part 6, "The backend contract". |
| **Leg time budget** | range `[minLegTime, maxLegTime]` | Applies to *every* leg, approach and exit included. See Part 6, "Leg shaping". |
| **Leg ascent cap** | max metres | Upper bound only. Applies to every leg. |
| **Difficulty ceiling** | SAC rank | Resolves to a variant row, Part 2. |
| **Objective** | `fastest` | Sort key only. One per query. `least road` arrives only with the `ROAD_*` column (Part 2); `least ascent` is likely redundant. |
| **Spatial anchor** | optional | Narrows the seed set, Part 6. |

### Transport mode

Exactly two modes. They are not two flavours of the same query:

- **`car`** — start set is parkings only. The car stays at the trailhead, so the tour **must be a
  loop**: exit start-point == entry start-point. This is the constraining case and the common one;
  Part 4 exists to make it work.
- **`transit`** — start set is stations only. Point-to-point is free; entry and exit stations are
  unrelated. Distance between them is explicitly not constrained — a long ride home is acceptable.

There is deliberately **no `either` mode**. A union of both start sets under a free closure rule
emits parking to different-parking chains, which are walkable by nobody: a driver cannot retrieve
the car, and someone without a car never reached the trailhead. It would be a mode that manufactures
results by relaxing a rule that exists for a physical reason. A combined listing, if wanted, is a
client concern — run both searches and merge the ranked lists, so every row stays individually
valid. See the deferred doc.

Loop is therefore a mode, decided up front, not a filter applied to finished chains. The two modes
also differ in state shape (Part 6), so running them as two searches is cheaper than one widened
search carrying a `start_id` it does not need.

## The core separation

A suggested tour is **not** a shortest path, and shortest paths must not be surfaced as tours.
Two layers, two different problems:

- **Pipeline layer — edge primitives.** For each hut pair within range, the best concrete trail
  path under a given constraint and objective, with its attributes. Precomputed offline. This is
  what `build_hub_edges.py` already produces, extended below.
- **Client layer — sequence search.** A tour is a constrained sequence of huts where every
  *leg* fits a time/ascent/difficulty budget and the chain as a whole fits the requested leg count
  and anchors to real start points. This is a search over the hut graph, with pipeline edges as
  inputs. It runs in the browser, per query, against live filter values.

Keeping these separate is what makes arbitrary user filters possible: the pipeline must not bake a
single preference into the one path it stores, because any filter the app later applies can only
delete edges, never substitute a better-suited path.

## Part 1: replace distance-based edge cost with hiking time

### Problem with the current cost

`build_base_graph.py` weights every edge as `dist * roadPenaltyFactor` (1.3) for
`residential`/`service`/`unclassified`/`tertiary`, plain `dist` otherwise. That weight is persisted
on `EDGE_DTYPE` and summed along contracted chains, but it exists only to choose which geometry
becomes a hub edge — it never reaches the output records (`RECORD_DTYPE` has no weight field).

Three defects, worst first:

1. **Cost ignores ascent.** Hiking effort is dominated by climb, not planar distance. The
   distance-shortest path between two huts can be the direct climb up a slope while a switchback
   trail 300 m longer is an hour faster. Elevation is currently sampled in `add_elevation.py`,
   *after* the routing decision, so it cannot influence it.
2. **Cost ignores `sac_scale`.** The chosen path may be `difficult_alpine_hiking` when a
   `mountain_hiking` trail exists 200 m longer. Also known only post-hoc.
3. **`roadPenaltyFactor: 1.3` is an uncalibrated constant.** As a plain distance multiplier it is
   too weak to actually avoid asphalt (a 5 km road still beats a 6.5 km trail) and too strong to
   be a no-op. It is not worth tuning while (1) and (2) stand.

### Change

Two quantities, and conflating them is the mistake to avoid:

- **Routing weight** — additive per base-graph edge, so Dijkstra and chain contraction can sum it.
- **Reported leg duration** — DIN 33466 over a whole leg, shown to the user.

**Routing weight is a pointwise speed model, not DIN.** The DIN blend
`max(t_h, t_v) + min(t_h, t_v) / 2` is an aggregate estimator and does not survive decomposition.
Contracted base edges have a **median length of 49.5 m** (p25 19.7 m, p75 133.7 m, over 8.34M
edges), and at that scale an edge is either flat or climbing, never both — so the blend never
engages and the per-edge sum degenerates to `t_h + t_v`. At `t_h == t_v`, the ordinary alpine leg,
that overestimates the route-level figure by **33%**. The discount the blend expresses (you cover
ground while you climb) exists only at aggregate scale.

So the routing weight is the integral of a slope-dependent speed, Tobler-shaped:

```
v(s)   = 6 * exp(-3.5 * |s + 0.05|)   km/h,   s = dz / dx
t_edge = dist_m / v(s_edge)
```

Additive by construction, valid at any granularity, no kink, and the direction asymmetry falls out
of the curve instead of being bolted on. The constants are calibrated so aggregate totals agree
with DIN on real legs — Tobler's raw numbers are not inherited unexamined.

**Reported duration stays DIN 33466**, applied to a leg's aggregated distance/ascent/descent:

```
t_horizontal = dist_m / 4000 m/h
t_vertical   = ascent_m / 300 m/h  +  descent_m / 500 m/h
time_h       = max(t_h, t_v) + min(t_h, t_v) / 2
```

Routing weight and reported duration are therefore **not the same quantity**, from iteration 1
onward. That is the rule the `ROAD_*` column obeys later — a penalty is a routing preference, not a
duration — and it simply applies from the start. The client cannot rederive the pipeline's ranking
from the shipped scalars, and does not need to.

**`roadPenaltyFactor` is removed.** It was trying to be two settings of one idea at once: too weak
to avoid asphalt, too strong to be a no-op, because a single global value has to serve both the user
who cares about road walking and the user who does not. The mechanism returns in Part 2 as the
`ROAD_*` column — the same multiplicative penalty, turned up to where it bites, stored as its own
variant instead of compromised into every path.

What iteration 1 gives up: the stored fastest path will sometimes take a forest road where a
parallel trail exists a few minutes slower, and the client can then only *delete* that edge via
`road_m`, not substitute the trail. The loss is narrow — a forest road genuinely is the fastest way
to many huts — but it is real, and it needs a number rather than an opinion.

**Compensating measurement:** after the Part 1 rebuild, record the `road_m / distance_m` distribution
across the stored edges. That figure, with the sizing probe's substitution rate for the `ROAD_*`
cell, is what decides whether the column gets built. Both are free once the rebuild has run.

Any future penalty belongs in the routing weight only and must never reach a time shown to the
user — a road does not take longer to walk.

Consequence: "shortest path" becomes "fastest path", which is the primitive a leg-budget search
actually needs — legs are budgeted in hours, not kilometres.

### Elevation: where it is computed

Elevation has to exist per **base-graph edge**, not per node. `nodes.npy` holds 6.85M
post-contraction junction nodes; the shape lives in `interior.npy` (33.1M points). Node-level
elevation gives only the net delta across a contracted edge, so a switchback chain over a col
reports its endpoint difference and nothing else.

`EDGE_DTYPE` gains `time_s`, `ascent_m`, `descent_m` (`UNSET` until the elevation pass runs) and
**loses `weight`**. With `roadPenaltyFactor` gone that field has no meaning of its own, and it
cannot be repurposed for time because contraction runs before any elevation exists. Dropping it
also makes a stale cache fail loudly (`KeyError`) rather than feeding old penalised metres to a
router that now reads them as seconds.

Knock-on removals: `contract_structural`'s `edges_weight` parameter and `w_sum` accumulator,
`WayGraphHandler`'s `road_penalty_factor`, `roadPenaltyFactor` in `pipeline.config.json`, and its
uses in `analysis/contraction_scaling.py` and `analysis/reconstruct_raw_graph.py`.

**New task `add_base_elevation`**, between `build_base_graph` and `build_hub_edges`:

- reads `base_graph/` and reconstructs each edge's ordered polyline from `u`/`v` plus
  `interior_offset`/`interior_count`. No OSM re-stream, so the ~18 min stream+contract stays cached.
- samples the DEM **bilinearly against a pre-smoothed raster** (~30 m kernel, one cached gdal pass).
  Today's sampler is nearest-neighbour `np.floor` into a 5 m (Bavaria DGM5) / 10 m (AT BEV) DEM,
  which is the noise source `eleNoiseThresholdM: 4` exists to patch.
- reads the DEM **per grid cell** (`cell_index.npy` + `lib/grid.py`) instead of as one
  74008 x 39276 window, bounding peak memory. `build_base_graph` already peaks at 12.4 GB of
  15.95 GB, so this must be a separate process, not a step inside it.
- accumulates ascent/descent as plain sums of positive/negative deltas along the smoothed profile.
  With smoothing doing the noise work there is no hysteresis, so this is a vectorised `reduceat`
  rather than a Python loop over 8.34M edges. `eleNoiseThresholdM` retires; the smoothing kernel
  width replaces it as the tunable.
- persists point elevations (`node_ele.npy`, f4 x 6.85M = 27 MB; `interior_ele.npy`, f4 x 33.1M =
  132 MB) so display profiles never need the DEM again.

**`add_elevation.py` is deleted.** `_build_igraph_with_snaps` already carries `dist`, `road_m`,
`sac_rank` and `via_ferrata` as igraph edge attributes, and `_path_for` sums or maxes them along
the routed path; `time_s`, `ascent_m` and `descent_m` join that list and are filled in the same
loop. The record's ascent then *is* the sum of the per-edge values the router summed to choose that
path, so routing and display cannot disagree. This is also what fixes the defect named above -
elevation sampled after the routing decision — instead of preserving the split that caused it.

The objection that this couples elevation changes to a multi-hour re-route does not survive: once
`time_s` is the routing weight, any change to how elevation is computed changes which path wins, so
re-routing is mandatory either way. The cheap-rewrite-in-place property was only ever real because
elevation did not affect routing.

What genuinely remains is the 30-point display profile, which should not force a re-route when
`profilePoints` changes. A small **`build_profiles`** task gathers it from the stored point
elevations; it never opens the DEM and runs in seconds.

One DAG consequence: the elevation pass depends on `dem.tif`, so `fetch_dem` (1,762 s) and
`build_dem_vrt` (930 s) move onto the critical path ahead of `build_hub_edges`. Declare that
dependency — today the ordering is numbering convention, not a `file_dep`.

### Rebuild scope and invalidation

`task_build_base_graph` invalidates only on `trails.osm.pbf` and `--tile-size-km`, so none of the
above triggers a rebuild on its own, and `manifest.json` records nothing about how the arrays were
computed. Add `schema_version` and `cost_model` to `base_graph/manifest.json` and put both in the
task's `uptodate` check. Do the same for `build_hub_edges` with the variant grid it was built for,
or a three-row rebuild will look up to date after a one-row run.

The rebuild is everything *from* the base graph down, not everything after it:

```
build_base_graph      ~18 min   (stream_osm 963 s + contract_structural 157 s)
add_base_elevation    new       (one DEM read, per-cell windows)
build_hub_edges       hours, x the variant grid
build_profiles        new, seconds
build_*_tiles         ~140 s each
copy_public_data      ~3 s
```

Downloads, `filter_trails` / `merge_trails` and the DEM fetch survive. Per `.claude/CLAUDE.md` this
is a scheduled, explicitly confirmed run — adding `cost_model` to the freshness check guarantees
that the next `doit` invocation is that multi-hour job.

## Part 2: edge variants

### Filters vs. objectives vs. variants

Three distinct mechanisms, routinely conflated:

| Mechanism | Evaluated | Examples | Needs a variant? |
|---|---|---|---|
| **Per-edge filter** | Client, at query time, on a shipped column | `via_ferrata == false`, `max_ele_m <= 2500`, `road_m / distance_m < 0.2`, `ungraded_m == 0` | No |
| **Per-leg / per-tour constraint** | Client, accumulated during search | hours per leg, ascent per leg, leg count | No |
| **Objective** | Client, as the sort/beam key | fastest, least ascent, least road | No |
| **Routing-relevant threshold** | Pipeline, as a constrained Dijkstra | "the best path that never exceeds T3" | **Yes** |

`sac_rank` is deliberately absent from the filter examples. It is still applied client-side when
resolving which variant to use, but it is not sufficient on its own: on an unconstrained edge it
reports a max that silently skips ungraded segments, so filtering on it alone claims a difficulty
ceiling the pipeline never established. Pair it with `ungraded_m` or take the guarantee from a
constrained row — see Passability below.

Variants exist for exactly one failure: a per-edge filter can only *delete* an edge. If the stored
Hut A → Hut B path crosses a T5 scramble and the user caps at T3, filtering deletes A→B entirely —
even when a T3 path exists 400 m longer. A variant routed under that constraint is what lets the
app substitute the easier path instead of losing the connection.

### Variant grid

Variants are the cross product of routing constraints (rows) and objectives (columns):

| row (routing constraint) | fastest | least ascent | least road |
|---|---|---|---|
| unconstrained — may traverse ungraded terrain | `FAST_ANY` | `ASC_ANY` | `ROAD_ANY` |
| **fully graded** ≤ T2, no via ferrata | `FAST_T2` | `ASC_T2` | `ROAD_T2` |
| **fully graded** ≤ T3, no via ferrata | `FAST_T3` | `ASC_T3` | `ROAD_T3` |

Rows are hard rules the path may not break; columns are what "best" means among the paths that
obey them. The axes do not interact — `ROAD_T2` is an ordinary cell, not a special case.

"Fully graded" is a load-bearing part of the row definition, not a detail — see Passability below.

### Rows and columns are not worth the same

This asymmetry, not the raw cell count, decides what gets built.

**Rows are why variants exist.** Each constrained row is a rescue from a deleted connection, and
the two rows correspond to the difficulty thresholds users actually pick: "keep me on waymarked
paths" and "alpine terrain, but no cable-protected climbing". They earn their cost structurally,
before any measurement.

**Columns delete nothing.** A column stores a different path for a pair that already has one, so it
only earns its cost if that path is meaningfully different from the fastest one. Otherwise the
client reproduces the same ranking by re-sorting the paths it already holds, using the `ascent_m`
and `road_m` columns shipped on every edge.

By that test the two objective columns are not equal:

- **Least ascent is close to redundant.** Part 1's cost prices climb steeply — the speed model
  collapses toward zero as slope rises — so the time-optimal path is already near-ascent-optimal.
  This column would largely store second copies of the fastest path. A prediction, not a
  measurement; the sizing probe's substitution rate is what confirms or kills it.
- **Least road is not.** Roads are *fast*, so the time cost actively steers onto them — this is the
  one objective the fastest path cannot stand in for, and with `roadPenaltyFactor` gone (Part 1)
  nothing else avoids asphalt at all.

  `ROAD_*` is defined as a **multiplicative penalty on the time of road-tagged segments**, factor
  ~3-5. Not lexicographic ("minimise road metres, time as tiebreak"), which buys a 40 km detour to
  dodge 100 m of tarmac; and not additive `time + lambda * road_m`, whose lambda has to be
  calibrated across units. A multiplier is scale-free, and the detour it will accept is bounded by
  `m x` the road's own time, so it cannot run away. This is `roadPenaltyFactor`'s mechanism at a
  setting that works, isolated in a variant so the speed-seeking user still gets a clean fastest
  path.

Two further points favour spending on rows first. The relaxation suggestions of Part 6 ("no
waymarked loop at this length; alpine grade works") are only useful if the two constrained rows
give genuinely different answers. And the difficulty cap is measurably brutal on the current
graph: applying `sac_rank <= 3` to edges already inside a 12 km leg budget cuts 1,418 edges to
1,006 and leaves 23% of huts with no connection at all — under `sac_rank <= 2`, 39%. Every one of
those deletions is a candidate for a variant to rescue.

### Passability: what a constrained row may traverse

`sac_scale` is absent on most of the network, and `sac_rank` on a stored edge is the **max** over
its path with untagged segments encoded as `-1` — which the max ignores. An edge can therefore
contain kilometres of ungraded terrain of unknown real difficulty and still report `sac_rank = 2`.
The current filter does not merely approximate; it reports a grade it has not established. Under a
user-stated difficulty ceiling that is a safety defect, not an accuracy one.

**Measured, 2026-08-21** (`data/osm/austria-trails.osm.pbf`, 2.33M ways / 23.1M segments, the nine
highway types in `trailTagFilter`):

| highway | % of segments | `sac_scale` present (by segment) |
|---|---|---|
| track | 44.9% | 2.2% |
| path | 16.2% | **51.4%** |
| service | 14.5% | 0.1% |
| residential | 9.1% | 0.1% |
| unclassified | 7.1% | 0.2% |
| footway | 4.9% | 0.5% |
| tertiary | 3.0% | 0.0% |
| steps | 0.2% | 6.5% |
| via_ferrata | 0.1% | 60.4% |

The ambiguous type is the *best* tagged one; everything else is untagged because nobody grades a
service road. Of 20.9M untagged segments only **8.7% are `highway=path`** — genuinely unknown
terrain is **7.9% of the network**, not the 95% a naive coverage figure suggests.

#### Grading tiers

**Explicit** — `sac_scale` present. Trusted.

**Physically implied** — the tag makes alpine terrain impossible by construction, not by a mapper's
judgement:

| tag | implied |
|---|---|
| `residential`, `service`, `unclassified`, `tertiary` | T1 — car-drivable |
| `track` | T1 — tractor-drivable, including `tracktype=grade5` |
| `footway` | T1 |
| `steps` | T2 |
| `path` + `surface ∈ {asphalt, paving_stones, concrete}` | T1 — a T4 traverse cannot be paved |

**Ungraded** — everything else; almost entirely `highway=path` without `sac_scale`.

#### Inference is asymmetric on purpose

- **Upgrades require physics.** Only the table above promotes an untagged way to a grade. Type
  inference alone covers 91.3% of the untagged mass, so this tier does nearly all the work.
- **Downgrades are always honoured.** `trail_visibility ∈ {bad, horrible, no}`, `informal=yes`,
  `ladder=yes`, and `access` restrictions hard-exclude a way from constrained rows whatever else it
  carries. Downgrades can only strengthen the guarantee, so they cost nothing.
- **Nothing else upgrades.** An earlier draft promoted ways on `trail_visibility ∈ {good,
  excellent}`. Rejected: that tag is present on only 8.8% of untagged paths, so it would rescue
  roughly 1% of the network while introducing the one inference in the system resting on a
  subjective call rather than on construction. Absence of evidence is not evidence of ease.

#### What this buys

Constrained rows enforce `ungraded_m == 0` **in the pipeline**, so a constrained variant supports a
claim with no hedge in it: *every metre of this route is graded T3 or easier*. `sac_rank <= 3` as a
client-side filter cannot make that claim.

This is also why ungraded terrain does **not** get its own row. A safety constraint needs
substitution, not deletion — but the constrained rows already substitute, so the guarantee rides on
the axis that exists. Doubling the grid would pay twice for it.

#### Client-side exposure

Two new columns (Part 3) let the client be honest about the unconstrained row, where the guarantee
does not hold:

1. **Display, non-negotiable.** Any `*_ANY` result shows its ungraded length — "4.2 km of this route
   is ungraded". The current `max` semantics actively conceals this.
2. **Filter.** A "fully graded only" toggle → `ungraded_m == 0 && inferred_m == 0`. This one deletes
   rather than substitutes, acceptable only because the constrained rows already offer the
   substituting path. A user who accepts T5 terrain but demands explicit grading everywhere is rare
   enough to serve with deletions.

The same columns and the same rules apply to the approach/exit table of Part 4 — an ungraded walk-in
is exactly as hazardous as an ungraded mid-tour leg.

### Phase 1: the fastest column

**Build `FAST_ANY`, `FAST_T2`, `FAST_T3`.** Three stored paths per hut pair, no objective variants.
If one objective column is added later it is least road, not least ascent.

#### The output path assumes one record per pair

Three places in `build_hub_edges.py` key on the hut pair alone and will silently discard the extra
variant rows. All three need `variant` in the key:

- `seen_hut_pairs`, the in-shard collapse of a pair visited from both ends;
- `merge_and_dedup`, the cross-shard dedup;
- `_write_edge_output`, which hardcodes `binfmt.VARIANT_SHORTEST`.

Geometry sharing between identical variants ("a variant identical to another writes the same offset
rather than a copy") also has no mechanism today — `_write_edge_output` appends each record's
polyline sequentially. It needs a hash of the packed coordinate run mapping to an existing
`geom_offset`. Cheap at this row count, but it is code that does not exist, and the Part 5 payload
estimate leans on it.

### Sizing probe — run before building

The 5–8× multiplier under Costs is an estimate with nothing under it, and the substitution rates
argued above are predictions. Both are cheap to measure:

Sample ~200 hut pairs spread across the grid cells' terrain range, route all nine combinations, and
record per cell:

- wall time per pair, against the `FAST_ANY` baseline;
- **substitution rate** — the fraction of pairs where the cell yields a path different from
  `FAST_ANY` (and, for constrained rows, the fraction where `FAST_ANY` violates the constraint, so
  the row is the difference between a substituted path and a deleted edge);
- **ungraded blocker rate** — for every pair where a constrained row finds *no* path at all, whether
  an ungraded segment was the binding obstacle, as opposed to genuine difficulty. This is the one
  open question in the Passability design and the probe is what closes it.
- **routing cost vs reported duration** — per sampled pair, the summed pointwise routing time
  against DIN 33466 applied to the pair's aggregated distance/ascent/descent (Part 1). This is what
  calibrates the speed-model constants, rather than inheriting Tobler's.
- **direction spread** — route a subset of pairs in both directions and compare the resulting
  geometries. Under the pointwise cost the direction asymmetry is genuine rather than bounded by a
  formula kink (Part 3, Direction), so this is the measurement that says whether one record per
  unordered pair is still defensible.

Substitution rate is the number that says whether a cell is worth its build cost. The probe costs
minutes; guessing wrong costs hours of compute.

#### The fallback if ungraded terrain proves load-bearing

Ungraded path is 7.9% of the network by segment, but that is a network-wide figure, not a
hut-to-hut one — it says nothing about whether those segments sit on the only link between two huts.
Connectivity is already the weak point: mean degree drops to ~2.8 under a 12 km budget and a T3 cap
before any passability rule is applied.

If the probe shows a high ungraded blocker rate, the honest response is a **fourth row** —
`graded ≤ T3, ungraded permitted` — shipped next to the strict one, with the UI naming the
difference in the result rather than burying it ("2.1 km of this route is ungraded; a fully graded
alternative exists at +50 min"). What is *not* acceptable is quietly relaxing the strict row's
definition to restore connectivity, because the guarantee is the entire reason the row exists.

If the blocker rate is low, the three-row design stands as specified.

Variants that resolve to the same path share geometry: `RECORD_DTYPE`'s `geom_offset` is already
an indirection, so a variant identical to another writes the same offset rather than a copy. For
most hut pairs the fastest path is already `sac<=2` and already road-free, so the on-disk and
on-wire multiplier is well below the nominal variant count.

Query resolution: given a difficulty cap, keep the variants whose own `sac_rank` satisfies it,
then pick the best surviving one by the chosen objective. This is exact only at the thresholds
actually routed for, and approximate between them. Acceptable, because difficulty thresholds
cluster in practice around "easy / moderate / alpine" rather than spreading across all seven SAC
levels.

**Known approximation:** max-altitude is handled as a plain per-edge filter, not a variant. An
edge whose path tops a 2800 m col is dropped under a 2500 m cap even if a lower path exists.
Accepted rather than adding an altitude-constrained variant row.

**`maxEdgeKm` must be re-checked on the routed path.** Pair selection runs the cutoff on `dist`,
then `_path_for` walks the *weight*-shortest path — a different path, whose `distance_m` can exceed
the cap. The code comment claiming "max-edge-km stays a guarantee about actual trail length" is
already untrue under `roadPenaltyFactor`, and a time cost widens the gap because the fastest route
can be materially longer than the shortest one. Decision: keep the distance cutoff for selection and
**re-check `distance_m <= maxEdgeKm` on the routed path, dropping the record if it fails**. A few
pairs are lost; the guarantee holds, and Part 6's leg-budget measurements stay valid against the
stored distribution.

## Part 3: new per-edge fields

Added to `RECORD_DTYPE` (`lib/binfmt.py`):

- `max_ele_m` (`f4`) — highest elevation reached along the path. Derivable from the existing
  `profiles` array; precomputed as a scalar so the client never ships or scans profiles.
- `ungraded_m` (`f4`) — metres of path carrying neither an explicit `sac_scale` nor a physically
  implied grade (Part 2, Passability). **Zero by construction on every constrained row**; non-zero
  only on `*_ANY`. This is the column that stops `sac_rank` from reporting a grade the pipeline
  never established.
- `inferred_m` (`f4`) — metres whose grade came from the physical-implication table rather than an
  explicit tag. Separated from `ungraded_m` because the two support different claims: inferred
  terrain is graded by construction, ungraded terrain is not graded at all.
- `snap_m` (`f4`) — total hub-to-trail snap gap across both ends of the edge (Part 4, Snapping).
  Shipped so the client can surface or filter on it; the gap's distance and climb are already
  folded into `distance_m` / `ascent_m` / `descent_m`.

Both apply to `start_edges/` records as well as `hut_edges/`.

`sac_rank` keeps its meaning — max over the path — but now maxes over explicit *and* physically
implied grades, so `-1` in a constrained row's path is impossible rather than silently skipped.

`variant` (`u1`) already exists and stops being always-`VARIANT_SHORTEST`.

### `time_min` is deliberately not a field

The *reported* duration is DIN 33466 over `distance_m`, `ascent_m` and `descent_m` (Part 1), and it
is **direction-dependent** (below). Shipping it as a stored scalar creates exactly one trap:
something reads the stored value for a leg walked backwards and is wrong by the full ascent/descent
rate gap. The client computes it instead, both ways, at load — 6k rows times three variants is
trivial.

The pipeline's *routing* time is a different quantity (Part 1) and is deliberately not shipped
either. The client does not reproduce the pipeline's ranking; it consumes the path the pipeline
chose and reports how long walking it takes.

### Direction

The stored graph is **undirected**. Verified against `data/osm/hut_edges/records.npy`: 6,067 records,
6,067 unique unordered pairs, zero cases where both `u -> v` and `v -> u` are present.
`build_hub_edges.py`'s `merge_and_dedup` keys hut-hut records on `tuple(sorted(...))` by
construction. `start_edges/` is one-directional in the same way: all 92,426 records are
`* -> TYPE_HUT`.

So the client synthesises the reverse of every edge it traverses backwards:

| field | reverse traversal |
|---|---|
| `distance_m`, `road_m` | unchanged |
| `sac_rank`, `via_ferrata` | unchanged (max over the path) |
| `max_ele_m`, `ungraded_m`, `inferred_m` | unchanged |
| `ascent_m` <-> `descent_m` | **swapped** |
| hiking time | **recomputed** from the swapped values |
| geometry, profile | reversed order (display only) |

This is one mechanism, not two: Part 4's exit edges are the same operation applied to
`start_edges/`.

**Known approximation — direction-dependent optimality.** Under the old distance cost the best path
A->B was also the best path B->A, so one record per unordered pair lost nothing. Under Part 1's
pointwise speed model that no longer holds, and the earlier draft's argument that the effect is
negligible does not survive the change of cost function.

That argument rested on the DIN blend: every candidate between the same two huts shares a net
elevation change, so direction shifted all candidates by one common constant and the ranking could
only flip near the kink in `max(t_h, t_v) + min(t_h, t_v) / 2`. A pointwise model has no kink and no
shared constant. Reversing flips the sign of every segment's slope, and `v(s)` is asymmetric about
zero, so the reverse cost is `sum(dist_i / v(-s_i))` — which depends on the *distribution* of slopes
along each candidate, and that distribution differs between candidates. Direction asymmetry is
therefore genuine, not an artifact.

Still accepted for iteration 1, because fixing it means routing every pair twice and doubling the
build phase. But it is now an approximation with an unknown magnitude rather than a bounded one, so
the sizing probe measures it (Part 2, "direction spread") and the deferred doc's entry on directed
routing is upgraded accordingly.

Note that the large, user-visible asymmetry — a leg's *duration* differing by direction — is not an
approximation at all. It is fully handled by recomputing time per direction, and the client must
report it.

## Part 4: approach and exit table

27,261 parkings and 3,025 stations are in `huts/public/data/`. Seeding a chain search from every
one of them would dominate the search's complexity.

`start_edges/records.npy` already holds **92,426** of them — 82,251 parking→hut and 10,175
station→hut, all directional into huts (`to_type` is uniformly `TYPE_HUT`). Shipping that set to
the client, or seeding a search from it, is not viable.

It does not need to be. A tour is `approach + hut chain + exit`, so start points can be lifted out
of the combinatorial search entirely:

- Precompute, per hut, the **k best approaches** (k ≈ 3, see "What counts as a good approach"),
  reduced from the 92k `start_edges/` records.
- The chain search runs over the **hut graph only** (1173 nodes).
- Each surviving chain attaches `bestApproach[chain[0]]` and an exit for `chain[-1]` as an O(1)
  lookup — for `car`, constrained to the origin start point, see "Loops" below.

Size: 1173 × 3 × 2 ≈ 7k rows, well under 100 KB — a ~13× reduction on the raw start-edge set, and
start-point count drops out of the search complexity completely.

### What counts as a good approach

"k fastest start edges" is the wrong selection rule and would visibly degrade results. The fastest
edge into a hut is systematically the one from the highest, most remote trailhead: a forest road, a
private or toll road, a pass parking reachable only in summer. Users arriving by car want the
valley trailhead they can actually drive to and park at.

Selection rule for the k retained approaches per hut:

- **Hard drop** start points whose access is restricted — OSM `access=private/no`, `motor_vehicle`
  likewise, gated forest roads. If the tag is absent, keep but mark `access_unknown`.
- **No separate approach time cap.** An approach *is* a leg (Part 6), so it is bounded by the same
  pipeline range cap as every hut-hut edge and filtered client-side by the same `maxLegTime`. The
  earlier `maxApproachTime` constant is gone: a second, tighter budget for approaches would have
  baked a UI assumption into the pipeline.
- Among survivors, keep the k best by time, but **never fill all k from one start point cluster** —
  retain at least one parking-sourced and one station-sourced edge where both exist, so the
  transport-mode split above has something to work with.

`access` and the source type must be shipped as columns on the approach/exit table; the client
surfaces "toll road" / "access unknown" rather than silently routing the user to a locked gate.

### Loops need start points in the state, not a post-filter

Restricting `bestExit` to the approach's own start id does not work against a k≈3 per-hut table:
the top-3 exits of the *last* hut and the top-3 approaches of the *first* hut are different huts'
neighbourhoods and essentially never share a start id. Under `car` mode — where the loop is
mandatory — that filter would annihilate the result set.

The loop mode therefore changes the search, not the output filter:

- **Seed by start point.** First-layer states become `(hut, 1, start_id)` rather than `(hut, 1)`, one
  per retained approach edge — ~1173 × 3 ≈ 3.5k seeds instead of 1173. `start_id` is carried through
  every transition unchanged. Cost is a ~3× wider first layer, which the DFS's pruning (or, in the
  fallback, the beam) absorbs. `transit` does not pay it: the two modes run as separate searches.
- **Ship the reverse index.** Let `S` be the set of start points appearing in any hut's retained
  approaches. Ship *all* `start_edges/` records whose `start_id ∈ S`, keyed both ways:
  `hut → starts` and `start → huts`. This is the extra data the loop closure needs — the
  k-best-per-hut table alone cannot answer "can I walk down from hut Z to the parking I left the car
  at".
- **Finish** for `car`: require an edge `(chain[-1], start_id)` in that index. For `transit`: any
  exit edge from `chain[-1]`.

**Size is bounded above by the whole `start_edges/` table.** `S` is a subset of the start points, so
the reverse index cannot exceed the 92,426 records already produced — roughly 1.9 MB raw at 20 B per
row, a few hundred KB compressed. The exact figure is still worth measuring, but the payload budget
in Part 5 cannot fail on it, and the earlier "order 10-20k rows" guess is simply superseded rather
than being an open risk. If a future range widening does make it large, prune by a payload-driven
rule (top-N huts per start point) — **not** by reintroducing a time budget, which would put the UI
assumption straight back into the pipeline.

Because start edges are directional into huts, "exit" edges are the same records read backwards,
with ascent and descent swapped and hiking time recomputed — the same reversal the client already
applies to hut edges (Part 3, Direction). Exit records are the reverse index described above, read
in that direction; nothing extra is stored.

### Snapping: the gap has to be priced, and validated vertically

A hub is joined to the graph by `snap_hub_to_subgraph`, which finds the nearest node or splits the
nearest edge within `maxSnapM: 100`. Two defects, both measured below.

**The gap is currently free.** `_path_for` sums only `dist` over the routed edges, so the
hub-to-snap-point gap contributes zero distance, zero ascent and zero time, at both ends of every
edge. `SnapResult` already knows the gap distance; fold it, and its vertical component, into the
record's `distance_m` / `ascent_m` / `descent_m`, and ship the total as `snap_m` (Part 3).

**Measured, 2026-08-22** (nearest trail vertex over `base_graph` nodes + interior, then DEM
elevation at both the hut and its snap point; nearest-vertex slightly overstates the true
perpendicular gap). Restricted to the huts that have trail data at all:

| snap gap | huts |
|---|---|
| 0-10 m | 351 |
| 10-25 m | 361 |
| 25-50 m | 33 |
| 50-100 m | 6 |
| > 100 m | 25 |

91.8% land within 25 m. **`maxSnapM` is not binding and should not be touched**: raising it to 200 m
recovers exactly one hut, 500 m recovers nine, and everything beyond that is a trail-coverage
artifact rather than a snapping one. Tightening it to 50 m would delete six legitimate huts.

**But `maxSnapM` is also not the safeguard it looks like.** The failure that matters is a hut joined
to a trail it cannot actually reach — across a gorge, or up a face. Vertical offset between hut and
snap point:

| \|dz\| | huts |
|---|---|
| < 5 m | 656 |
| 5-10 m | 51 |
| 10-20 m | 12 |
| 20-50 m | 2 |
| 50-100 m | 1 |
| > 100 m | 2 |

Mean is 3.0 m, and the outliers are exactly the expected class — bivouac boxes on walls:
Schüsselkar-Biwak (250 m gap, 258 m drop), Glockner-Biwak (896 m / 608 m), Babenstuberhütte
(41 m / 36 m), Böseckhütte (26 m / 20 m), **Watzmann-Ostwand-Biwak (18 m gap, 17 m above the
trail)**. The last one is the point: it passes `maxSnapM: 100` comfortably. A horizontal threshold
cannot tell "18 m across a terrace" from "18 m up a wall", at any setting.

So add **`maxSnapAscentM`** alongside `maxSnapM`, and validate the snap by vertical offset:

- At a 25 m cap it rejects the genuinely broken cases and touches nothing else — 707 of 724 huts
  with valid DEM coverage sit under 10 m.
- A slope-based rule is the wrong shape. Staufner Haus and St. Pöltner Hütte snap at slope 0.55-0.57
  and are ordinary huts on steep ground; an absolute vertical cap separates them from a bivouac on a
  face, a ratio does not.

**Rejected snaps must be reported.** `snap_hub_to_subgraph` returns `None` and the hub silently
vanishes from the graph — no count, no artifact, nothing downstream knows. Adding a vertical cap
grows that invisible set. Emit `unsnapped_huts.json` (id, name, gap, dz, and a reason of
`no_trail_data` / `gap_too_far` / `vertical_offset`). This is the same honesty standard this spec
demands for `ungraded_m`.

**Known approximation:** `lib/edge_split.py` apportions a split edge's attributes by distance ratio,
so the two synthetic halves get ascent split linearly rather than by their actual profile. With a
13.7 m mean gap and a 3.0 m mean vertical offset this is far below DEM noise. Recorded next to the
max-altitude and direction approximations, not fixed.

## Part 5: client payload

Shipped as static files alongside the existing outputs, fetched by the tour UI:

- **Hut graph edges** — packed arrays: `from_id`, `to_id`, `variant`, `distance_m`,
  `ascent_m`, `descent_m`, `max_ele_m`, `sac_rank`, `via_ferrata`, `road_m`, `ungraded_m`,
  `inferred_m`, `snap_m`. One row per unordered pair per variant; the client derives the reported
  duration and the reverse direction at load (Part 3, Direction). At ~32 B per row and the three
  phase-1 variants over 6,067 base edges, ≈ 580 KB raw. The full nine-cell grid would be ≈ 1.7 MB
  raw — still small; the constraint on the grid is build time, not payload.

  Both figures assume a packing that does not exist yet: 32 B per row requires hut ids narrowed to
  `u2` (`RECORD_DTYPE` carries `i8`), and raw `f4` columns compress poorly without quantisation or
  byte-shuffling, so the earlier "under 200 KB gzipped" is optimistic. Measure after packing. It
  does not change the conclusion — build time is the binding constraint either way.
- **Approach/exit table** — Part 4: the k-best-per-hut table (< 100 KB) plus the `start_id ∈ S`
  reverse index needed for loop closure (bounded by the `start_edges/` table, ~1.9 MB raw — see
  Part 4), with `access` and source-type columns.
- **Hut metadata** — already shipped as `huts.geojson`.

**Geometry is not shipped.** Path geometry stays in `hut-edges.pmtiles` and is fetched lazily,
only for tours the user actually opens. This is already how `GraphPage.jsx` renders edges.

## Part 6: chain search — layered search over (hut, leg)

### The backend contract

The search takes `[Lmin, Lmax]` in **legs** and returns chains of legs. It has no notion of days,
nights, or of what the user typed. A chain over huts `h1..hn` is `n + 1` legs:

```
leg 1        start point -> h1
leg 2..n     h(i) -> h(i+1)
leg n+1      hn -> exit start point
```

so `n` huts, `n` nights, `n + 1` legs. Whether the client presents that as "4 days", "3 nights" or
"5 stages" is a presentation decision. Putting it in the search was the mistake the earlier draft
made, and it leaked a UI assumption all the way down into the pipeline via `maxApproachTime`.

**An approach is a full leg**, not a special case with a budget of its own. It is filtered by the
same `[minLegTime, maxLegTime]` and the same `legAscentCap` as every hut-to-hut leg; it merely draws
from a different edge table. Same for the exit. That is why `maxApproachTime` no longer exists
(Part 4).

Consequences:

- **The layer index is the leg index.** No `D - 2` translation anywhere, at any level.
- **Three edge sources, one filter predicate:** `start_edges/` forward at the first layer,
  `hut_edges/` in between, `start_edges/` reversed at the last. Direction handling is Part 3.
- `Lmin = 2` is the shortest chain the search can return — walk in, walk out, one hut, one night.
  Whether that counts as a "tour" is the client's call, not the search's.

### Search strategy: exact DFS, beam DP as documented fallback

Naive depth-first enumeration is exponential in chain length, and an earlier draft assumed ~6-8 legal
continuations per hut, which would make a 5-leg chain from every one of 1173 seeds around 9M partial
paths.

**Measured branching contradicts that premise — build DFS first.** On the current hut graph, edges
inside a 12 km leg budget and a `sac_rank <= 3` cap leave a mean degree of **2.8** (median 2), not
6-8. Exact enumeration is then 716 reachable seed huts x ~3^5 ≈ **170k** partial paths at five legs,
~1.6M at seven. Both are trivial in typed arrays.

So the implementation order is:

1. **Exact DFS with pruning.** No beam, no `K`, no approximation. This removes the beam's quality
   loss, the `K` tuning knob, and the beam-induced spatial collapse that per-cell `topK` exists to
   patch — all at once.
2. **Beam DP as the documented fallback**, kept below, if branching turns out higher than measured
   once real time-based budgets replace the distance proxy, or if widening the pipeline's edge-range
   cap densifies the graph.

The DP structure below stays authoritative for the fallback, and its filter/objective semantics apply
unchanged to the DFS: the two differ only in whether partial results are capped per state.

The measurement carries a caveat: `ascent_m` was UNSET in the records sampled, so the degree figures
use a distance proxy for the leg budget. Real time-based degree is **lower**, never higher — ascent
only adds time — so the DFS case is if anything stronger than stated.

The redundancy the DP exploits is that two different prefixes arriving at the same hut at the same
leg index have identical futures — what is reachable later depends only on where you are and how many
legs you have spent, not on how you got there.

### Structure

**State:** `(hut, n)` for `transit`; `(hut, n, start_id)` for `car`, so the loop closure of Part 4 has
the origin available at finish time. Here `n` is the number of huts visited so far, which is also the
number of legs walked. ~1173 x 6 ≈ 7,000 cells, or ~3x that in the `car` case. Running the two modes
as separate searches (Transport mode, above) is what keeps `transit` on the narrow state.

**Value:** in the DFS, every surviving partial chain; in the beam fallback, up to K (≈50) best partial
chains per state, each carrying its path and accumulated `totalTime` / `totalAscent`.

**Transition**, one layer at a time:

```
Nmin, Nmax = Lmin - 1, Lmax - 1        # legs -> huts (= nights)

states[h][1] = one state per retained approach edge into h that passes the leg filters

for n in 1 .. Nmax-1:
  for each hut h, for each state s in states[h][n]:
    for each hut edge e incident to h:
      h2 = the other end
      orient e as h -> h2                        # Part 3, Direction: swap ascent/descent, recompute time
      skip if e fails per-edge filters (sac_rank, via_ferrata, max_ele_m, road share)
      skip if e.time > maxLegTime or e.time < minLegTime
      skip if e.ascent_m > legAscentCap
      skip if h2 already in s.path
      push { path: s.path + [h2], totalTime + e.time, totalAscent + e.ascent_m } into states[h2][n+1]
  beam fallback only: states[h][n+1] = topK(states[h][n+1], by: chosen objective)   # per cell
  if n+1 >= Nmin: collect finished chains from layer n+1 (see Finish)
```

`topK`, in the fallback, is applied **per state cell**, never globally across the layer. A global
top-K collapses the whole beam into whichever valley happens to hold the cheapest partial chains, and
every result the user sees comes from one massif. Per-cell K is what keeps the frontier spread over
the map.

**Init:** layer 1, one state per retained approach edge of each seed hut. That edge is leg 1 and is
filtered exactly like any other leg.
**Finish:** at every layer `n ∈ [Nmin, Nmax]`, attach a legal exit as leg `n + 1` — for `car`, an
exit edge back to `s.start_id`; for `transit`, any exit edge — subject to the same leg filters, then
score and rank. Chains of different lengths compete in one ranked list; leg count is a range, not an
equality.

Because the layer index strictly increases, the state space is a layered DAG — one pass per layer, no
cycles, nothing recomputed.

### Leg shaping: why the time budget needs a lower bound

With an upper-bound-only budget and `fastest` as the objective, the optimum for a six-leg chain is six
45-minute hops between adjacent huts in the same basin. It satisfies every stated constraint and is
worthless. The same degeneracy would hit `least ascent` (flat traverses) and `least road`.

So:

- **`minLegTime` is a hard per-leg filter**, alongside `maxLegTime`. Provisional default: a band of
  4-7 h rather than "<= 7 h".
- **Objectives rank within that band**, they do not define it. `fastest` minimises `totalTime`
  *given* that every leg already clears `minLegTime`; it is a tie-break among plausible chains, not
  the thing that decides what a chain is.

**Measured, 2026-08-21 (`data/osm/hut_edges/records.npy`, n = 6,067):** the lower bound prunes almost
nothing. Hut pairs in the stored graph are far apart, not close — median edge length **20.1 km**, mean
18.7 km, hard cap 31.6 km, with only 5% under 3.9 km. `minLegTime` at any plausible value removes a
handful of edges.

`maxLegTime` is the binding constraint instead: a <= 12 km cap (roughly a 5 h leg once ascent is
counted) keeps 1,418 of 6,067 edges; <= 15 km keeps 1,957. So the band's real job is the upper bound,
and the degenerate-chain risk the lower bound guards against is much smaller than the shape of the
objective suggests. Keep `minLegTime` — it is nearly free and the failure it prevents is embarrassing
— but do not expect it to shape the search.

This also means the *chain length* a user can ask for is bounded by geometry: at ~20 km median
spacing, long chains of short legs do not exist in this graph.

A softer treatment — replacing the hard `minLegTime` with a leg-balance penalty, so one short leg
costs a little rather than deleting the chain — is a real improvement and is deferred; see the
deferred doc.

### Result diversity

Per-cell `topK` fixes the beam's spatial collapse but not the *output*. The top 10 chains by any
objective are typically the same chain with one hut swapped — the user reads them as one result
presented ten times.

Final ranking therefore needs an explicit diversity pass before display: suppress a candidate that
shares more than a threshold fraction of its huts (or its start point) with an already-accepted,
better-ranked chain. Greedy, applied to the finished list, cheap. Target is ~10 visibly *different*
chains, not the 10 best-scoring.

**Two steps, two different keys.** The earlier draft used one unordered hut-set key for both jobs.
That is wrong in both directions:

1. **Exact-duplicate removal, on the ordered hut sequence.** A chain and its reverse are generated
   independently — the search runs from every seed — and to a user they are one tour walked two ways.
   Remove one, keeping whichever direction scored better under the active objective; the two
   genuinely differ in time (Part 3, Direction). This step is mandatory and has no threshold. It
   must compare *sequences*, not sets: `h1 -> h2 -> h3` and `h1 -> h3 -> h2` share 100% of their
   huts but are different tours with different legs and possibly different exits — for `car` loops
   round a massif, that is the common case, not a corner.
2. **Similarity suppression, on the unordered hut set.** Greedy, applied afterwards: drop a
   candidate sharing more than a threshold fraction of its huts (or its start point) with an
   already-accepted, better-ranked chain.

Keeping them separate matters because the overlap threshold is a tunable listed under "provisional
constants". Letting reverse-duplicate removal ride on it means a later retune can make the same tour
appear twice.

Note the reverse may legitimately not exist: per-leg time differs by direction, so a chain can clear
`maxLegTime` one way and fail it the other. Correct behaviour — the dedup is a pure filter and must
not assume a pair.

### When nothing matches

7 legs, T2 ceiling, <= 800 m ascent per leg, loop, no anchor -> zero chains. This is a common outcome,
not an edge case, and "no results" is a dead end for the user.

The search already knows why: instrument the transition loop with a **per-filter kill counter** — how
many candidate relaxations each of `sac_rank`, `via_ferrata`, `max_ele_m`, road share, `maxLegTime`,
`minLegTime`, `legAscentCap`, and the loop closure rejected. The dominant counter is the binding
constraint.

On an empty (or near-empty) result set, report it as an actionable suggestion — "no T2 loop exists at
7 legs in this region; 5 works, or raise the ceiling to T3" — and offer the relaxed query as one
click. Re-running the search with one loosened value costs another ~300 ms, so candidate relaxations
can simply be tried rather than predicted.

### Cost

```
huts x layers x K x degree  =  1173 x 6 x 50 x 8  ~  2.8M edge relaxations
```

for the beam fallback at pessimistic degree; typed arrays, ~100-300 ms in the browser for an
unanchored all-of-AT+Bayern query. The `car` mode's wider first layer is capped by the beam and does
not multiply this. Linear in chain length rather than exponential: each extra leg adds one layer.
Exact DFS at the measured degree of 2.8 is cheaper still (~170k partial paths at five legs).

### The beam, and what it costs

Exact DP would keep every partial chain per state. The no-revisit rule means two prefixes at the same
`(hut, n)` are not fully interchangeable — they have consumed different huts — so the set does not
collapse to a single best. Capping at K restores the collapse and makes the search **beam search**:
approximate.

The loss is a chain whose prefix ranked K+1 at some intermediate hut. For chains of this length at
K=50 this is not a practical concern, and K is a direct dial between result quality and milliseconds.
The DFS path above avoids the question entirely; this section applies only if the fallback is needed.

### Spatial anchor

A region / viewport / radius filter narrows the **seed set** at init. It is the same code path with
fewer first-layer states, and is therefore strictly cheaper than the unanchored case. Optional, as
required.

## Costs and risks

**Build time is the real constraint, not payload or runtime.** The historical v1 path-retrieval
phase (`pass2_paths`) measured **7,630 s ≈ 2.1 h** in `data/timings.jsonl`. Naively, nine variants
is ~19 h of path retrieval.

Softeners:

- Constrained variants route over *smaller* edge subsets — dropping T4+ ways shrinks the graph, so
  those Dijkstras are individually faster than the unconstrained baseline.
- The pair-selection distance pass (`pass1_distances`, 3,227 s in v1) is reused across variants as a
  **prefilter, not a skip**. A constrained row's distances differ from the unconstrained ones, and
  its cutoff has to be evaluated on its own subgraph — otherwise a pair whose T2 route is 60 km
  survives. But constrained distance is always >= unconstrained distance, so the unconstrained pass
  yields a valid superset of candidate pairs and each row's `distances()` call runs against a much
  smaller target set.
- What is genuinely shared per cell is the expensive part: the `LocalSubgraph` load,
  `_build_edge_spatial_index`, and the snap loop over `core_hubs + hut_targets`. Only
  `build_igraph` (once per row, on the filtered edge set), `distances` and `paths` multiply.
- V2's `build_hub_edges.py` is already parallelised per grid cell via `ProcessPoolExecutor`, so the
  v1 numbers are an upper bound on the shape of the cost, not a direct prediction.

Realistic expectation is a 5–8× multiplier on the hub-edge query phase for the full grid, but this
is a guess and the sizing probe in Part 2 replaces it with a measurement before anything is built.
Phase 1 is three variants — the fastest column — expanded only on probe evidence.

**Second risk:** Part 1 changes what every existing hut edge *is*. Regenerating hub edges under a
time-based cost invalidates the current `hut_edges/` output and everything downstream of it
(`add_elevation`, tiles, `hut-edge-stats.json`). This is a full rebuild of everything after the
base graph, not an incremental addition.

**Third risk:** dropping `roadPenaltyFactor` (Part 1) means iteration 1 ships with nothing steering
paths off asphalt. The `road_m / distance_m` distribution measured after the rebuild is what says how
bad that is; until it exists, the size of the regression is unknown rather than small.

## Non-goals

Deliberate omissions with a route back in are in `2026-08-21-tour-suggestion-deferred.md`. The items
below are out of scope for the design, not merely postponed.

- Bed availability as a search input. The OHRS availability API is per-hut, per-date, one request
  each (`docs/alpenverein-api.md`), so it cannot be called across a candidate set during search.
  Treat it as a post-filter on the handful of returned tours, designed separately.
- Any backend. Everything here stays static files plus in-browser computation.
- Multi-objective Pareto results. One objective per query.
- Extending geographic scope past AT+Bayern.

## Open questions

- **Does the measured road share justify building `ROAD_*`?** This replaces the old
  "does `roadPenaltyFactor` survive" question, which was malformed: the factor and the objective were
  never alternatives to compare, they are the same mechanism at two settings. Answered by the
  `road_m / distance_m` distribution (Part 1) plus the sizing probe's substitution rate for that cell.
- **How large is the loop-closure reverse index** in practice (Part 4)? Worth measuring, but it is
  bounded above by the `start_edges/` table, so it cannot break the Part 5 payload budget.
- **Provisional constants**, to be tuned against real results rather than in the abstract: the leg-time
  band (`minLegTime` / `maxLegTime`), `legAscentCap`, the diversity overlap threshold, `k` in the
  per-hut approach table, and — only if the beam fallback is needed — `K`.
- **Is exact DFS actually enough** at real time-based budgets? The measured degree of 2.8 says yes,
  but it was measured with `ascent_m` UNSET against a distance proxy. Confirm after the Part 1
  rebuild; the beam fallback stays documented until then.
