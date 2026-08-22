# Tour suggestion — backend (pipeline) spec

Date: 2026-08-22
Status: distilled from `2026-08-21-tour-suggestion-design.md`, for planning
Scope: everything that is **not** client-side chain search or UI. Deferred items:
`2026-08-21-tour-suggestion-deferred.md`.

## Scope boundary

"Backend" here means the offline `pipeline/` precompute plus the static-file contract it emits.
There is no server. The pipeline's job in this feature is exactly three things:

1. Produce **edge primitives** — for each hut pair (and each start-point→hut pair) within range,
   the best concrete trail path under a stated routing constraint and objective, with attributes.
2. Reduce the 92k start-point edges to a **shippable approach/exit table** plus the reverse index
   the client's loop closure needs.
3. Emit those as **packed static arrays** the client loads once per session.

Explicitly out of the pipeline: leg budgets, leg counts, day/night vocabulary, transport mode,
objective selection, diversity, relaxation suggestions. The pipeline must not learn what a "leg"
or a "day" is — that leak is what `maxApproachTime` was, and it is removed.

Section numbers below reference the source design's Parts.

---

## A. Cost model (Part 1)

Two quantities, never conflated:

**A1. Routing weight** — additive per base-graph edge, pointwise speed model, Tobler-shaped:

```
v(s)   = 6 * exp(-3.5 * |s + 0.05|)   km/h,  s = dz/dx
t_edge = dist_m / v(s_edge)
```

Rationale: contracted base edges have median length 49.5 m (p25 19.7, p75 133.7, n=8.34M). At that
granularity DIN's `max+min/2` blend never engages, and the per-edge sum degenerates to `t_h + t_v`
— +33% over the route-level figure at `t_h == t_v`. The pointwise integral is additive at any
granularity and yields direction asymmetry from the curve rather than a bolted-on rule.

Constants are **calibrated against DIN on real legs** by the sizing probe (H), not inherited from
Tobler.

**A2. Reported duration** — DIN 33466 over a whole leg's aggregates. **Computed client-side, not
stored** (see D3). Definition kept here as the authority:

```
t_h = distance_m / 4000;  t_v = ascent_m / 300 + descent_m / 500
time_h = max(t_h, t_v) + min(t_h, t_v) / 2
```

**A3. `roadPenaltyFactor` is removed.** Delete from `pipeline.config.json`. Knock-on removals:
`EDGE_DTYPE["weight"]`, `contract_structural`'s `edges_weight` param and `w_sum` accumulator,
`WayGraphHandler.road_penalty_factor`, and uses in `analysis/contraction_scaling.py` and
`analysis/reconstruct_raw_graph.py`. Dropping the field (rather than repurposing it) makes a stale
cache fail loudly with `KeyError` instead of feeding penalised metres to a router reading seconds.

Rule going forward: **any routing penalty lives in the routing weight only and must never reach a
duration shown to the user.** A road does not take longer to walk.

**A4. Consequence:** "shortest path" becomes "fastest path".

---

## B. Elevation moves ahead of routing (Part 1)

Elevation must exist **per base-graph edge**, not per node: `nodes.npy` holds 6.85M
post-contraction junctions and the shape lives in `interior.npy` (33.1M points); node elevation
gives only the net delta across a contracted edge, so a switchback chain over a col reports its
endpoint difference and nothing else.

**B1. `EDGE_DTYPE` gains** `time_s`, `ascent_m`, `descent_m` (`UNSET` until the elevation pass runs)
and **loses** `weight`.

**B2. New task `add_base_elevation`**, between `build_base_graph` and `build_hub_edges`:

- reads `base_graph/`, reconstructs each edge polyline from `u`/`v` + `interior_offset`/
  `interior_count`. No OSM re-stream — the ~18 min stream+contract stays cached.
- samples the DEM **bilinearly against a pre-smoothed raster** (~30 m kernel, one cached gdal pass),
  replacing today's nearest-neighbour `np.floor` into a 5 m (Bavaria DGM5) / 10 m (AT BEV) DEM.
- reads the DEM **per grid cell** (`cell_index.npy` + `lib/grid.py`), not as one 74008×39276 window.
  Must be a separate process: `build_base_graph` already peaks at 12.4 GB of 15.95 GB.
- ascent/descent = plain sums of positive/negative deltas along the smoothed profile, vectorised
  `reduceat` over 8.34M edges — no hysteresis loop. **`eleNoiseThresholdM` retires**; the smoothing
  kernel width is the replacement tunable.
- persists point elevations so display never reopens the DEM: `node_ele.npy` (f4 × 6.85M, 27 MB),
  `interior_ele.npy` (f4 × 33.1M, 132 MB).

**B3. `phases/elevation/add_elevation.py` is deleted.** `build_hub_edges._build_igraph_with_snaps`
already carries `dist`, `road_m`, `sac_rank`, `via_ferrata` as igraph edge attributes and
`_path_for` sums/maxes them; `time_s`, `ascent_m`, `descent_m` join that list. The record's ascent
then *is* the sum the router used to pick the path — routing and display cannot disagree.

The "this couples elevation to a multi-hour re-route" objection does not survive: once `time_s` is
the routing weight, any elevation change changes which path wins, so re-routing is mandatory either
way. The cheap-rewrite-in-place property was only ever real because elevation did not affect routing.

**B4. New task `build_profiles`** — gathers the 30-point display profile from stored point
elevations. Never opens the DEM, runs in seconds, so `profilePoints` retuning no longer forces a
re-route.

**B5. DAG:** the elevation pass depends on `dem.tif`, so `fetch_dem` (1,762 s) and `build_dem_vrt`
(930 s) move onto the critical path ahead of `build_hub_edges`. **Declare that `file_dep`** — today
the ordering is numbering convention only.

---

## C. Variant grid and passability (Part 2)

### C1. What justifies a variant

| mechanism | evaluated | needs a variant? |
|---|---|---|
| per-edge filter (`via_ferrata`, `max_ele_m`, road share, `ungraded_m`) | client | no |
| per-leg / per-tour constraint (hours, ascent, leg count) | client | no |
| objective (sort key) | client | no |
| routing-relevant threshold ("best path never exceeding T3") | pipeline, constrained Dijkstra | **yes** |

A per-edge filter can only **delete** an edge. If the stored A→B path crosses T5 and the user caps
at T3, filtering deletes A→B entirely — even when a T3 path exists 400 m longer. Variants
**substitute**.

### C2. Grid

| row (routing constraint) | fastest | least ascent | least road |
|---|---|---|---|
| unconstrained (may traverse ungraded) | `FAST_ANY` | `ASC_ANY` | `ROAD_ANY` |
| fully graded ≤ T2, no via ferrata | `FAST_T2` | `ASC_T2` | `ROAD_T2` |
| fully graded ≤ T3, no via ferrata | `FAST_T3` | `ASC_T3` | `ROAD_T3` |

Rows are hard rules; columns are what "best" means among obeying paths. Axes do not interact.

**Rows earn their cost structurally** — each is a rescue from a deleted connection, and matches the
thresholds users actually pick. Measured brutality of the cap: applying `sac_rank <= 3` to edges
already inside a 12 km leg budget cuts 1,418 edges to 1,006 and leaves **23% of huts with no
connection at all**; under `sac_rank <= 2`, **39%**.

**Columns delete nothing** — a column only earns its cost if its path differs from the fastest one;
otherwise the client re-sorts what it already holds. `ASC_*` is predicted near-redundant (the speed
model already prices climb steeply). `ROAD_*` is not, because roads are *fast* and nothing else
avoids asphalt once `roadPenaltyFactor` is gone. If `ROAD_*` is built, it is a **multiplicative
penalty on the time of road-tagged segments, factor ~3-5** — not lexicographic (buys 40 km detours),
not additive `time + λ·road_m` (λ needs cross-unit calibration). A multiplier is scale-free and its
detour is bounded by m× the road's own time.

### C3. Phase 1 = the fastest column only

Build `FAST_ANY`, `FAST_T2`, `FAST_T3`. If one objective column is added later it is `ROAD_*`, not
`ASC_*` — and only on probe evidence (H).

### C4. Passability — what a constrained row may traverse

`sac_scale` is absent on most of the network, and `sac_rank` is the **max** over the path with
untagged encoded as `-1`, which max ignores. An edge can contain kilometres of ungraded terrain and
still report `sac_rank = 2`. Under a user-stated difficulty ceiling that is a **safety defect**, not
an accuracy one.

Measured 2026-08-21 (`data/osm/austria-trails.osm.pbf`, 2.33M ways / 23.1M segments): `track` 44.9%
of segments (2.2% graded), `path` 16.2% (**51.4% graded**), `service` 14.5%, `residential` 9.1%,
`unclassified` 7.1%, `footway` 4.9%, `tertiary` 3.0%, `steps` 0.2%, `via_ferrata` 0.1% (60.4%).
Of 20.9M untagged segments only 8.7% are `highway=path` → **genuinely unknown terrain is 7.9% of the
network**, not the 95% a naive coverage figure suggests.

Tiers:

- **Explicit** — `sac_scale` present. Trusted.
- **Physically implied** — the tag makes alpine terrain impossible by construction:
  `residential`/`service`/`unclassified`/`tertiary` → T1 (car-drivable); `track` → T1 (incl.
  `tracktype=grade5`); `footway` → T1; `steps` → T2; `path` + `surface ∈ {asphalt, paving_stones,
  concrete}` → T1.
- **Ungraded** — everything else, almost entirely `highway=path` without `sac_scale`.

Inference is **asymmetric on purpose**: upgrades require physics (the table above covers 91.3% of
untagged mass); downgrades are always honoured and hard-exclude from constrained rows
(`trail_visibility ∈ {bad, horrible, no}`, `informal=yes`, `ladder=yes`, `access` restrictions);
**nothing else upgrades** — `trail_visibility ∈ {good, excellent}` is rejected as an upgrade signal
(present on only 8.8% of untagged paths, ~1% network rescue, and it is a subjective call rather than
a construction fact).

**Constrained rows enforce `ungraded_m == 0` in the pipeline.** That is what lets the product claim
*every metre of this route is graded T3 or easier* with no hedge. `sac_rank <= 3` client-side cannot
make that claim.

Ungraded terrain does **not** get its own row — a safety constraint needs substitution, and the
constrained rows already substitute. Doubling the grid would pay twice for it.

### C5. `sac_rank` semantics change

`sac_rank` keeps "max over the path" but now maxes over explicit **and** physically implied grades,
so `-1` inside a constrained row's path is impossible rather than silently skipped.

### C6. One-record-per-pair assumptions must be keyed by variant

Three places in `build_hub_edges.py` key on the hut pair alone and will silently discard variant rows:

- `seen_hut_pairs` (in-shard collapse of a pair visited from both ends),
- `merge_and_dedup` (cross-shard dedup),
- `_write_edge_output` (hardcodes `binfmt.VARIANT_SHORTEST`).

All three need `variant` in the key.

### C7. Geometry sharing does not exist yet

"A variant identical to another writes the same `geom_offset` rather than a copy" has no mechanism —
`_write_edge_output` appends each record's polyline sequentially. Needs a hash of the packed
coordinate run → existing `geom_offset`. Cheap at this row count, but it is code to write, and the
payload estimate (F) leans on it.

### C8. `maxEdgeKm` must be re-checked on the routed path

Pair selection runs the cutoff on `dist`; `_path_for` then walks the *weight*-shortest path, whose
`distance_m` can exceed the cap. The code comment claiming "max-edge-km stays a guarantee about
actual trail length" is already untrue under `roadPenaltyFactor`, and a time cost widens the gap.
**Decision:** keep the distance cutoff for selection, and **re-check `distance_m <= maxEdgeKm` on
the routed path, dropping the record if it fails.**

### C9. Accepted approximations (recorded, not fixed)

- **Max altitude** is a per-edge filter, not a variant row — an edge topping a 2800 m col is dropped
  under a 2500 m cap even if a lower path exists.
- **Difficulty resolution between routed thresholds** is approximate; exact only at T2/T3.
- **Direction-dependent optimality** — see D4.
- **`lib/edge_split.py`** apportions a split edge's attributes by distance ratio, so ascent splits
  linearly rather than by profile. With a 13.7 m mean gap and 3.0 m mean vertical offset this is far
  below DEM noise.

---

## D. Record schema (Part 3)

### D1. `RECORD_DTYPE` additions

| field | dtype | meaning |
|---|---|---|
| `max_ele_m` | f4 | highest elevation on the path; scalar so the client never scans profiles |
| `ungraded_m` | f4 | metres with neither explicit `sac_scale` nor implied grade. **Zero by construction on every constrained row** |
| `inferred_m` | f4 | metres graded via the physical-implication table. Separate from `ungraded_m` because they support different claims |
| `snap_m` | f4 | total hub-to-trail snap gap across both ends (E3); the gap's distance and climb are already folded into `distance_m`/`ascent_m`/`descent_m` |

All four apply to `start_edges/` as well as `hut_edges/`. `variant` (u1) already exists and stops
being always `VARIANT_SHORTEST`.

### D2. `EDGE_DTYPE` — see B1 (`+time_s, +ascent_m, +descent_m, −weight`).

### D3. `time_min` is deliberately **not** a field

Reported duration is direction-dependent (D4). Shipping it as a scalar creates exactly one trap:
something reads the stored value for a leg walked backwards and is wrong by the full
ascent/descent rate gap. The client computes it both ways at load — 6k rows × 3 variants is trivial.
The pipeline's *routing* time is a different quantity and is not shipped either; the client does not
reproduce the pipeline's ranking.

### D4. Direction

The stored graph is **undirected**, verified: `hut_edges/records.npy` has 6,067 records / 6,067
unique unordered pairs, zero cases with both `u→v` and `v→u`. `merge_and_dedup` keys on
`tuple(sorted(...))`. `start_edges/` is one-directional: all 92,426 records are `* → TYPE_HUT`.

Reverse traversal is a **client-side synthesis** and is therefore a contract the pipeline must
document, not implement: `distance_m`, `road_m`, `sac_rank`, `via_ferrata`, `max_ele_m`,
`ungraded_m`, `inferred_m` unchanged; `ascent_m ↔ descent_m` swapped; duration recomputed; geometry
and profile reversed for display.

**Known approximation:** under the old distance cost, best A→B was best B→A, so one record per
unordered pair lost nothing. Under A1's pointwise model it no longer holds — reversing flips the
sign of every segment slope and `v(s)` is asymmetric, so reverse cost depends on the *distribution*
of slopes along each candidate, which differs between candidates. Accepted for iteration 1 (fixing
it doubles the build phase), but with **unknown** rather than bounded magnitude → the probe measures
it (H, "direction spread").

The large user-visible asymmetry — a leg's duration by direction — is not an approximation; it is
fully handled by recomputing per direction.

---

## E. Approach / exit table (Part 4)

27,261 parkings and 3,025 stations exist; `start_edges/records.npy` holds 92,426 records (82,251
parking→hut, 10,175 station→hut). Neither is shippable or seedable.

### E1. Reduce to k best per hut

Precompute the **k best approaches per hut (k ≈ 3)**. Size: 1173 × 3 × 2 ≈ 7k rows, < 100 KB — a
~13× reduction, and start-point count leaves the client's search complexity entirely.

**Selection rule** — "k fastest" is wrong and would visibly degrade results: the fastest edge into a
hut is systematically from the highest, most remote trailhead (forest road, toll road, summer-only
pass parking), while a driver wants the valley trailhead they can actually reach.

- **Hard drop** restricted access: OSM `access=private/no`, `motor_vehicle` likewise, gated forest
  roads. If the tag is absent, **keep but mark `access_unknown`**.
- **No approach time cap.** An approach is a full leg, bounded by the same pipeline range cap as any
  hut-hut edge and filtered client-side by the same `maxLegTime`. **`maxApproachTime` is deleted** —
  a second, tighter budget would bake a UI assumption into the pipeline.
- Among survivors keep the k best by time, but **never fill all k from one start-point cluster**:
  retain at least one parking-sourced and one station-sourced edge where both exist, so the client's
  `car`/`transit` split has something to work with.
- Ship `access` and source type as **columns**, so the client can surface "toll road" / "access
  unknown" rather than routing someone to a locked gate.

### E2. Loop-closure reverse index

The client's `car` mode requires exit start-point == entry start-point, and the k≈3 per-hut tables
of the first and last hut essentially never share a start id — a post-filter would annihilate the
result set. So the backend ships the index that makes closure answerable:

Let `S` = the set of start points appearing in any hut's retained approaches. **Ship all
`start_edges/` records with `start_id ∈ S`, keyed both ways: `hut → starts` and `start → huts`.**

Size is **bounded above by the whole `start_edges/` table** — ≤ 92,426 records, ~1.9 MB raw at 20 B
per row, a few hundred KB compressed. Worth measuring, but it cannot break the payload budget. If a
future range widening does make it large, prune by a payload-driven rule (top-N huts per start
point) — **not** by reintroducing a time budget.

Exit edges are these same records read backwards (D4). Nothing extra is stored.

### E3. Snapping — price the gap, validate vertically

**The gap is currently free.** `_path_for` sums only `dist` over routed edges, so the hub-to-snap
gap contributes zero distance, ascent and time at **both ends of every edge**. `SnapResult` already
knows the gap distance; fold it and its vertical component into `distance_m`/`ascent_m`/`descent_m`
and ship the total as `snap_m`.

**`maxSnapM: 100` is not binding — do not touch it.** Measured 2026-08-22 (nearest trail vertex over
base-graph nodes + interior): 0-10 m: 351 huts, 10-25 m: 361, 25-50 m: 33, 50-100 m: 6, >100 m: 25.
91.8% within 25 m. Raising to 200 m recovers one hut, 500 m recovers nine; tightening to 50 m would
delete six legitimate huts.

**But it is not the safeguard it looks like.** The failure that matters is a hut joined to a trail it
cannot reach — across a gorge or up a face. Vertical offset: <5 m: 656 huts, 5-10: 51, 10-20: 12,
20-50: 2, 50-100: 1, >100: 2. Mean 3.0 m; outliers are bivouac boxes on walls — Schüsselkar-Biwak
(250 m gap / 258 m drop), Glockner-Biwak (896/608), Babenstuberhütte (41/36), Böseckhütte (26/20),
and the decisive one, **Watzmann-Ostwand-Biwak (18 m gap, 17 m above the trail)** — which passes
`maxSnapM: 100` comfortably. A horizontal threshold cannot tell "18 m across a terrace" from "18 m
up a wall", at any setting.

**Add `maxSnapAscentM`** (config) and validate snaps by vertical offset. At a 25 m cap it rejects the
genuinely broken cases and touches nothing else (707 of 724 huts with valid DEM coverage are under
10 m). A slope-based rule is the wrong shape — Staufner Haus and St. Pöltner Hütte snap at slope
0.55-0.57 and are ordinary huts on steep ground; an absolute vertical cap separates them from a
bivouac on a face, a ratio does not.

**Rejected snaps must be reported.** `snap_hub_to_subgraph` returns `None` today and the hub silently
vanishes — no count, no artifact. A vertical cap grows that invisible set. Emit
**`unsnapped_huts.json`** (id, name, gap, dz, reason ∈ `no_trail_data` / `gap_too_far` /
`vertical_offset`). Same honesty standard as `ungraded_m`.

---

## F. Shipped payload contract (Part 5)

Static files alongside existing outputs, copied by `copy_public_data`:

- **Hut graph edges** — packed arrays: `from_id`, `to_id`, `variant`, `distance_m`, `ascent_m`,
  `descent_m`, `max_ele_m`, `sac_rank`, `via_ferrata`, `road_m`, `ungraded_m`, `inferred_m`,
  `snap_m`. One row per unordered pair per variant. At ~32 B/row × 3 phase-1 variants × 6,067 base
  edges ≈ **580 KB raw**; the full nine-cell grid ≈ 1.7 MB raw.
  **Caveat:** 32 B/row assumes a packing that does not exist — hut ids narrowed to `u2`
  (`RECORD_DTYPE` carries `i8`), and raw `f4` columns compress poorly without quantisation or
  byte-shuffling, so "under 200 KB gzipped" is optimistic. **Measure after packing.** It does not
  change the conclusion: build time is the binding constraint, not payload.
- **Approach/exit table** — E1 (< 100 KB) plus the E2 reverse index (~1.9 MB raw bound), with
  `access` and source-type columns.
- **Hut metadata** — already shipped as `huts.geojson`.
- **`unsnapped_huts.json`** — E3.

**Geometry is not shipped.** Path geometry stays in `hut-edges.pmtiles`, fetched lazily only for
tours the user opens — already how `GraphPage.jsx` renders edges.

---

## G. Task DAG, config and invalidation

### G1. Task changes

| task | change |
|---|---|
| `build_base_graph` | cost-model rewrite; `weight` dropped; `time_s`/`ascent_m`/`descent_m` added as UNSET |
| `add_base_elevation` | **new**, between base graph and hub edges |
| `build_hub_edges` | variant loop; `time_s` routing; variant-keyed dedup; `maxEdgeKm` re-check; snap gap folded in; new columns; `unsnapped_huts.json` |
| `build_profiles` | **new**, seconds, from stored point elevations |
| `add_elevation` | **deleted** |
| `fetch_dem`, `build_dem_vrt` | now real `file_dep` ancestors of the elevation pass |
| `build_*_tiles`, `copy_public_data` | unchanged in shape, rerun |

### G2. Config (`pipeline.config.json`)

Remove `roadPenaltyFactor`, `eleNoiseThresholdM`. Add `maxSnapAscentM` (≈25), the smoothing kernel
width, the variant grid, and the `ROAD_*` penalty factor if that column is built. `maxEdgeKm` and
`maxSnapM` keep their current values. `maxApproachTime` must not be introduced.

### G3. Invalidation

`task_build_base_graph` invalidates only on `trails.osm.pbf` and `--tile-size-km`, and
`manifest.json` records nothing about how the arrays were computed — so none of this triggers a
rebuild on its own. **Add `schema_version` and `cost_model` to `base_graph/manifest.json` and put
both in the task's `uptodate` check.** Do the same for `build_hub_edges` **with the variant grid it
was built for**, or a three-row rebuild will look up-to-date after a one-row run.

### G4. Rebuild scope

Everything *from* the base graph down. Downloads, `filter_trails`/`merge_trails` and the DEM fetch
survive.

```
build_base_graph      ~18 min   (stream_osm 963 s + contract_structural 157 s)
add_base_elevation    new       (one DEM read, per-cell windows)
build_hub_edges       hours × variant grid
build_profiles        new, seconds
build_*_tiles         ~140 s each
copy_public_data      ~3 s
```

Per `.claude/CLAUDE.md` this is a scheduled, explicitly confirmed run — and adding `cost_model` to
the freshness check **guarantees** the next `doit` invocation is that multi-hour job.

---

## H. Sizing probe — gate, runs before anything is built

An `analysis/` script (read-only, not in the DAG). Sample ~200 hut pairs spread across the grid
cells' terrain range, route all nine grid combinations, record per cell:

1. **Wall time per pair**, against the `FAST_ANY` baseline → replaces the guessed 5-8× multiplier.
2. **Substitution rate** — fraction of pairs where the cell yields a path different from `FAST_ANY`;
   for constrained rows, also the fraction where `FAST_ANY` violates the constraint (i.e. the row is
   the difference between a substituted path and a deleted edge). This is the number that says
   whether a cell is worth its build cost.
3. **Ungraded blocker rate** — for every pair where a constrained row finds no path, whether an
   ungraded segment was the binding obstacle rather than genuine difficulty. **This is the one open
   question in the passability design and the probe is what closes it.**
4. **Routing cost vs reported duration** — summed pointwise routing time vs DIN 33466 on the pair's
   aggregates → **calibrates the A1 constants** instead of inheriting Tobler's.
5. **Direction spread** — route a subset both ways and compare geometries → says whether one record
   per unordered pair is still defensible (D4).

Probe costs minutes; guessing wrong costs hours of compute.

**Fallback if ungraded terrain proves load-bearing:** ship a **fourth row** — `graded ≤ T3, ungraded
permitted` — next to the strict one, with the UI naming the difference in the result ("2.1 km of
this route is ungraded; a fully graded alternative exists at +50 min"). What is **not** acceptable is
quietly relaxing the strict row's definition to restore connectivity — the guarantee is the entire
reason the row exists. Note 7.9% is a network-wide figure, not a hut-to-hut one, and connectivity is
already weak (mean degree ~2.8 under a 12 km budget and T3 cap before any passability rule).

**Post-rebuild measurements** (free once the rebuild has run, both feed the `ROAD_*` decision):

- `road_m / distance_m` distribution across stored edges — sizes the regression from dropping
  `roadPenaltyFactor`.
- Actual packed payload size (F) and actual reverse-index size (E2).

---

## Costs and risks

**Build time is the binding constraint** — not payload, not client runtime. V1's `pass2_paths`
measured 7,630 s ≈ 2.1 h (`data/timings.jsonl`); naively nine variants ≈ 19 h of path retrieval.

Softeners:

- Constrained rows route over *smaller* edge subsets, so those Dijkstras are individually faster.
- `pass1_distances` (3,227 s in v1) is reused across variants as a **prefilter, not a skip**. A
  constrained row's distances differ and its cutoff must be evaluated on its own subgraph (else a
  pair whose T2 route is 60 km survives) — but constrained distance is always ≥ unconstrained, so
  the unconstrained pass yields a valid superset and each row's `distances()` runs against a much
  smaller target set.
- Genuinely shared per cell is the expensive part: `LocalSubgraph` load,
  `_build_edge_spatial_index`, the snap loop over `core_hubs + hut_targets`. Only `build_igraph`
  (once per row, on the filtered edge set), `distances` and `paths` multiply.
- V2's `build_hub_edges.py` is already parallelised per grid cell, so v1 numbers bound the *shape*
  of the cost, not the value.

**Risk 2 — Part 1 changes what every existing hut edge *is*.** A time-based cost invalidates the
current `hut_edges/` output and everything downstream (tiles, `hut-edge-stats.json`). Full rebuild
below the base graph, not an incremental addition.

**Risk 3 — nothing steers paths off asphalt in iteration 1.** Size of the regression is *unknown*
until the `road_m / distance_m` distribution exists. The stored fastest path will sometimes take a
forest road where a parallel trail exists a few minutes slower, and the client can then only delete
that edge via `road_m`, not substitute the trail.

---

## Non-goals (backend)

- **Any actual backend.** Static files + in-browser computation only.
- **Bed availability as a search input.** The OHRS availability API is per-hut, per-date, one request
  each — it cannot be called across a candidate set. Post-filter on returned tours, designed
  separately.
- Multi-objective Pareto results.
- Geographic scope past AT+Bayern.

---

## Blockers and open questions

**Hard gate (blocks build, not planning):**

- **H must run and be read before `build_hub_edges` is rebuilt.** The variant count, the A1 speed
  constants, and the three-row-vs-four-row passability decision are all probe outputs. Building
  first means paying hours to learn the same thing.

**Blockers on the pipeline itself:**

- **Geometry sharing (C7) does not exist.** The payload estimate assumes it. Either write it or
  restate F's numbers without it.
- **`ungraded_m` / `inferred_m` require a per-segment grading classifier** that does not exist today
  — the tier tables in C4 have to become code inside the way handler, and the metres have to be
  accumulated along the routed path in `_path_for` the way `road_m` already is.
- **Constrained routing needs a filtered `build_igraph`** — edge-subset selection by
  grade/via-ferrata/downgrade-tag before Dijkstra. Also does not exist.

**Open questions:**

1. **Does the measured road share justify building `ROAD_*`?** Answered by the `road_m/distance_m`
   distribution plus the probe's substitution rate for that cell. (This replaces the malformed
   "does `roadPenaltyFactor` survive" — the factor and the objective are the same mechanism at two
   settings, not alternatives.)
2. **Is the ungraded blocker rate high enough to force the fourth row?** (H.3.)
3. **How large is the E2 reverse index in practice?** Bounded, so it cannot break the budget, but
   the number is unknown.
4. **Does direction asymmetry (D4) invalidate one-record-per-unordered-pair?** Magnitude is now
   unknown rather than bounded. (H.5.)
5. **A1's constants are unset** until H.4 calibrates them. The formula shape is decided; the numbers
   are not.
6. **Smoothing kernel width (~30 m)** is a guess inheriting `eleNoiseThresholdM`'s job with no
   measurement behind it.
7. **`k` in the per-hut approach table (≈3)** and **`maxSnapAscentM` (≈25)** are provisional; the
   latter has measurement behind it, the former does not.

**Not a backend concern, listed so it does not get filed here:** the leg-time band, `legAscentCap`,
diversity threshold, beam `K`, and whether exact DFS suffices. All client-side.
