# Multi-day tour suggestion: cost model, edge variants, client-side chain search

Date: 2026-08-21
Status: approved for planning

Builds on `docs/superpowers/specs/2026-08-19-pipeline-v2-design.md` (base graph / hub edge split,
`RECORD_DTYPE`, `hut_edges/` + `start_edges/`) and
`docs/superpowers/specs/2026-08-18-start-locations-design.md` (station/parking id scheme).
Nothing in those output contracts is replaced; this spec adds fields and variants to them, and
defines a new client-side layer that consumes them.

## Goal

The user states requirements — number of days, difficulty ceiling, ascent per day, objective
("fastest", "least ascent", "least road") — and the app returns multi-day hut-to-hut chains that
satisfy them. A tour starts at a parking lot or station and ends at a parking lot or station,
which may be the same one (a loop) or a different one; the user chooses. A spatial anchor
(region, viewport, "near me") is an **optional filter**, not a requirement — a query with no
anchor must work across all of Austria+Bavaria.

## The core separation

A suggested tour is **not** a shortest path, and shortest paths must not be surfaced as tours.
Two layers, two different problems:

- **Pipeline layer — edge primitives.** For each hut pair within range, the best concrete trail
  path under a given constraint and objective, with its attributes. Precomputed offline. This is
  what `build_hub_edges.py` already produces, extended below.
- **Client layer — sequence search.** A tour is a constrained sequence of huts where every
  *day-leg* fits a time/ascent/difficulty budget and the chain as a whole fits the day count and
  anchors to real start points. This is a search over the hut graph, with pipeline edges as
  inputs. It runs in the browser, per query, against live filter values.

Keeping these separate is what makes arbitrary user filters possible: the pipeline must not bake a
single preference into the one path it stores, because any filter the app later applies can only
delete edges, never substitute a better-suited path.

## Part 1: replace distance-based edge cost with hiking time

### Problem with the current cost

`build_base_graph.py` weights every edge as `dist * roadPenaltyFactor` (1.3) for
`residential`/`service`/`unclassified`/`tertiary`, plain `dist` otherwise. That weight is used
only to choose which geometry becomes a hub edge; it is not persisted (`RECORD_DTYPE` has no
weight field).

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

Sample the DEM at **base graph node** level and store elevation in `NODE_DTYPE`. The base graph is
built and cached once (`data/osm/base_graph/`), so this is a one-time cost that every subsequent
hub-edge run and hyperparameter retune reuses.

Edge weight becomes estimated **hiking time**, DIN 33466 / SAC style:

```
t_horizontal = dist_m / 4000 m/h
t_vertical   = ascent_m / 300 m/h  +  descent_m / 500 m/h
time_h       = max(t_h, t_v) + min(t_h, t_v) / 2
```

`roadPenaltyFactor` survives as a small multiplier on `time_h` for road-tagged segments, retained
as a taste knob rather than the primary lever. Once "least road" is a first-class objective
(Part 2) it may be dropped entirely; that decision is deferred until the objective exists and can
be compared against it.

Consequence: "shortest path" becomes "fastest path", which is the primitive a day-budget search
actually needs — day-legs are budgeted in hours, not kilometres.

### Cost

DEM sampling moves into (or alongside) `build_base_graph.py`. `add_elevation.py`'s existing
`read_dem_window` / `sample_elevations` machinery is reused against the node array.
`add_elevation.py` keeps its current job of producing per-edge ascent/descent profiles for the
*output* records; Part 1 only adds node elevations for *routing*.

## Part 2: edge variants

### Filters vs. objectives vs. variants

Three distinct mechanisms, routinely conflated:

| Mechanism | Evaluated | Examples | Needs a variant? |
|---|---|---|---|
| **Per-edge filter** | Client, at query time, on a shipped column | `sac_rank <= 3`, `via_ferrata == false`, `max_ele_m <= 2500`, `road_m / distance_m < 0.2` | No |
| **Per-day / per-tour constraint** | Client, accumulated during search | hours per day, ascent per day, day count | No |
| **Objective** | Client, as the sort/beam key | fastest, least ascent, least road | No |
| **Routing-relevant threshold** | Pipeline, as a constrained Dijkstra | "the best path that never exceeds T3" | **Yes** |

Variants exist for exactly one failure: a per-edge filter can only *delete* an edge. If the stored
Hut A → Hut B path crosses a T5 scramble and the user caps at T3, filtering deletes A→B entirely —
even when a T3 path exists 400 m longer. A variant routed under that constraint is what lets the
app substitute the easier path instead of losing the connection.

### Variant grid

Variants are the cross product of routing constraints and objectives. The full grid:

| | fastest | least ascent | least road |
|---|---|---|---|
| unconstrained | 0 | 3 | 6 |
| `sac_rank <= 2`, no via ferrata | 1 | 4 | 7 |
| `sac_rank <= 3`, no via ferrata | 2 | 5 | 8 |

There is no coupling between the axes — "least road with `sac<=2`" is cell 7, not a special case.

**Ship phase 1 with four variants** — 0, 1, 2, 3 — measure the real `hub_edge_query` phase time,
then decide whether the remaining five earn their build cost. Rationale under Costs below.

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

## Part 3: new per-edge fields

Added to `RECORD_DTYPE` (`lib/binfmt.py`):

- `time_min` (`f4`) — estimated hiking time from Part 1's formula. Needed client-side because
  day-legs are budgeted in hours.
- `max_ele_m` (`f4`) — highest elevation reached along the path. Derivable from the existing
  `profiles` array; precomputed as a scalar so the client never ships or scans profiles.

`variant` (`u1`) already exists and stops being always-`VARIANT_SHORTEST`.

## Part 4: approach and exit table

27,261 parkings and 3,025 stations are in `huts/public/data/`. Seeding a chain search from every
one of them would dominate the search's complexity.

`start_edges/records.npy` already holds **92,426** of them — 82,251 parking→hut and 10,175
station→hut, all directional into huts (`to_type` is uniformly `TYPE_HUT`). Shipping that set to
the client, or seeding a search from it, is not viable.

It does not need to be. A tour is `approach + hut chain + exit`, so start points can be lifted out
of the combinatorial search entirely:

- Precompute, per hut, the **k best approaches and exits** (k ≈ 3): fastest parking-sourced edge,
  fastest station-sourced edge, reduced from the 92k `start_edges/` records.
- The chain search runs over the **hut graph only** (1173 nodes).
- Each surviving chain attaches `bestApproach[chain[0]]` and `bestExit[chain[-1]]` as an O(1)
  lookup.

Size: 1173 × 3 × 2 ≈ 7k rows, well under 100 KB — a ~13× reduction on the raw start-edge set, and
start-point count drops out of the search complexity completely.

Because start edges are directional into huts, "exit" edges are the same records read backwards.
Hiking time is not symmetric (ascent and descent have different rates in Part 1's formula), so the
exit table must recompute `time_min` with ascent and descent swapped rather than reusing the
approach value.

"Loop" (start and end at the same point) is not a separate mode — it is a post-filter on the
attached pair, or a constraint that `bestExit` is restricted to the approach's own start id.

## Part 5: client payload

Shipped as static files alongside the existing outputs, fetched by the tour UI:

- **Hut graph edges** — packed arrays: `from_id`, `to_id`, `variant`, `time_min`, `distance_m`,
  `ascent_m`, `descent_m`, `max_ele_m`, `sac_rank`, `via_ferrata`, `road_m`. At ~24 B per row and
  4 variants over 6,067 base edges, ≈ 580 KB raw, well under 200 KB gzipped. Nine variants would
  be ≈ 1.3 MB raw / ~400 KB gzipped — still small; the constraint on the grid is build time, not
  payload.
- **Approach/exit table** — Part 4, < 100 KB.
- **Hut metadata** — already shipped as `huts.geojson`.

**Geometry is not shipped.** Path geometry stays in `hut-edges.pmtiles` and is fetched lazily,
only for tours the user actually opens. This is already how `GraphPage.jsx` renders edges.

## Part 6: chain search — beam DP over (hut, day)

### Why not DFS

Naive depth-first enumeration of chains is exponential in day count: with ~6–8 legal continuations
surviving the filters, a 5-day chain from every one of 1173 seed huts is on the order of 9M
partial paths, and each added day multiplies it again.

The redundancy is that two different prefixes arriving at the same hut on the same day have
identical futures — everything reachable on days 3..5 depends only on where you are and how many
days you have used, not on how you got there.

### Structure

**State:** `(hut, day_index)` — ~1173 × 7 ≈ 8,000 cells.

**Value:** up to K (≈50) best partial tours ending at that hut on that day, each carrying its path
and accumulated `totalTime` / `totalAscent`.

**Transition**, one day-layer at a time:

```
for d in 0 .. D-1:
  for each hut h, for each state s in states[h][d]:
    for each edge (h -> h2):
      skip if edge fails per-edge filters (sac_rank, via_ferrata, max_ele_m, road share)
      skip if edge.time_min > dayTimeBudget or edge.ascent_m > dayAscentCap
      skip if h2 already in s.path
      push { path: s.path + [h2], totalTime: ..., totalAscent: ... } into states[h2][d+1]
  states[*][d+1] = topK(states[*][d+1], by: chosen objective)
```

**Init:** day 0, every seed hut, seeded with its cheapest approach edge.
**Finish:** at `d == D`, attach `bestExit[hut]`, score and rank complete tours.

Because the day index strictly increases, the state space is a layered DAG — one pass per layer,
no cycles, nothing recomputed.

### Cost

```
huts × days × K × degree  =  1173 × 7 × 50 × 8  ≈  3.3M edge relaxations
```

Typed arrays, ~100–300 ms in the browser for an unanchored all-of-AT+Bayern query. Linear in day
count rather than exponential: a 7th day takes DP from ~3.3M to ~4.7M relaxations, where DFS goes
from ~9M to ~320M.

### The beam, and what it costs

Exact DP would keep every partial tour per state. The no-revisit rule means two prefixes at the
same `(hut, day)` are not fully interchangeable — they have consumed different huts — so the set
does not collapse to a single best. Capping at K restores the collapse and makes the search **beam
search**: approximate.

The loss is a tour whose prefix ranked K+1 at some intermediate hut. For 3–7 day chains at K=50
this is not a practical concern, and K is a direct dial between result quality and milliseconds.

### Spatial anchor

A region / viewport / radius filter narrows the **seed set** at init. It is the same code path with
fewer day-0 states, and is therefore strictly cheaper than the unanchored case. Optional, as
required.

## Costs and risks

**Build time is the real constraint, not payload or runtime.** The historical v1 path-retrieval
phase (`pass2_paths`) measured **7,630 s ≈ 2.1 h** in `data/timings.jsonl`. Naively, nine variants
is ~19 h of path retrieval.

Softeners:

- Constrained variants route over *smaller* edge subsets — dropping T4+ ways shrinks the graph, so
  those Dijkstras are individually faster than the unconstrained baseline.
- The pair-selection distance pass (`pass1_distances`, 3,227 s in v1) is computed once and reused
  across all variants; only path retrieval multiplies.
- V2's `build_hub_edges.py` is already parallelised per grid cell via `ProcessPoolExecutor`, so the
  v1 numbers are an upper bound on the shape of the cost, not a direct prediction.

Realistic expectation is a 5–8× multiplier on the hub-edge query phase. That is the number the
variant grid should be sized against — hence phase 1 at four variants, measured before expanding.

**Second risk:** Part 1 changes what every existing hut edge *is*. Regenerating hub edges under a
time-based cost invalidates the current `hut_edges/` output and everything downstream of it
(`add_elevation`, tiles, `hut-edge-stats.json`). This is a full rebuild of everything after the
base graph, not an incremental addition.

## Non-goals

- Bed availability as a search input. The OHRS availability API is per-hut, per-date, one request
  each (`docs/alpenverein-api.md`), so it cannot be called across a candidate set during search.
  Treat it as a post-filter on the handful of returned tours, designed separately.
- Any backend. Everything here stays static files plus in-browser computation.
- Multi-objective Pareto results. One objective per query.
- Extending geographic scope past AT+Bayern.

## Open questions

- Does `roadPenaltyFactor` survive at all once "least road" is a first-class objective, or does it
  become redundant? Decide after Part 2 ships and the two can be compared.
- Default K, day-time budget and day-ascent cap: pick provisional values, tune against real results
  rather than in the abstract.
