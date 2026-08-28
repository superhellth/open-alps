# Tour suggestion payload contract

What `pipeline/`'s tour-suggestion backend ships into `huts/public/data/`, and the rules a client
consuming it must follow. This is the contract those files exist under — nothing else states it, so
read this before writing any code against `hut-edge-payload.*`, `approaches.*` or
`unsnapped_huts.json`. Design rationale: `docs/superpowers/specs/2026-08-22-tour-suggestion-backend.md`
(section refs below point there). Pipeline internals (how these are built): `pipeline/CLAUDE.md`,
`pipeline/phases/postprocessing/README.md`.

As of this writing the client-side tour search that would consume these files does not exist yet —
`GraphPage.jsx`/`App.jsx` only read the older `huts.geojson`/`trails.pmtiles`/`hut-edges.pmtiles`/
`hut-edge-stats.json` outputs. This document describes what the pipeline produces regardless.

## 1. `hut-edge-payload.bin` + `hut-edge-payload.json`

Built by `pipeline/phases/postprocessing/build_edge_payload.py` from `hut_edges/records.npy`. One
row per `(unordered hut pair, variant)` — see §3 "Direction" for why unordered.

`hut-edge-payload.json` is the manifest: `rows` (row count), `columns` (`{name: {dtype, offset}}`,
byte offset into the sibling `.bin`), `variants` (`{variant_code: variant_name}`,
`binfmt.VARIANT_NAMES`), `hut_ids` (index → real hut id, the same enumeration `huts.geojson`'s
feature order uses). `hut-edge-payload.bin` is the raw column data: each column is a contiguous
run of `rows` values at its own dtype, laid out **per-column, not interleaved** — that layout is
what the measured 43.4 KB gzipped figure (`data/analysis/payload_sizing.json`) depends on; parse
each column separately, don't assume a struct-of-rows layout.

| column | dtype | meaning |
|---|---|---|
| `from_id` | u2 | hut index (into `hut_ids`), narrowed from `RECORD_DTYPE`'s internal `i8` — safe, well under 65,536 huts |
| `to_id` | u2 | same |
| `variant` | u1 | one of `binfmt.VARIANT_*` — see `variants` in the manifest for the name |
| `distance_m` | f4 | real trail distance, not beeline, not road-penalized |
| `ascent_m` / `descent_m` | f4 | signed elevation sums along the routed path, u→v direction as stored |
| `max_ele_m` | f4 | highest point on the path (scalar — see §4, this is a filter input, not a display aggregate) |
| `sac_rank` | i1 | max SAC difficulty rank walked (`-1` = ungraded — see §5 for why this can't happen on a constrained row) |
| `via_ferrata` | u1 | 1 if any segment on the path is a via ferrata |
| `road_m` | f4 | metres of the path on a road-tagged way |
| `ungraded_m` | f4 | metres with neither an explicit `sac_scale` nor an implied grade (spec C4) |
| `inferred_m` | f4 | metres graded via the physical-implication table, not an explicit tag — kept separate from `ungraded_m` because the two support different claims |
| `snap_m` | f4 | total hub-to-trail snap gap across both ends — already folded into `distance_m`/`ascent_m`/`descent_m`; shipped so a client can flag a large-snap edge as approximate |

**Geometry is not in this payload.** Path polylines stay in `hut-edges.pmtiles`, fetched lazily
only for tours the user actually opens — the payload above is metadata-only, meant to be loaded
whole, up front.

## 2. Duration is not shipped — compute it client-side

There is no `time_min`/`duration` column anywhere in this payload, deliberately (spec D3). Two
different things are easy to confuse:

- **Routing weight** (`time_s` on the internal base graph, `lib/speed.py`'s pointwise Tobler-shaped
  model) — what the pipeline used to *choose* the path. Never shipped, never meant to be shown to a
  user; it exists to rank candidate paths, not to report a duration.
- **Reported duration** — DIN 33466, computed from the shipped `distance_m`/`ascent_m`/`descent_m`.
  This is what the client must compute itself:

```
t_h = distance_m / 4000       # hours, horizontal component
t_v = ascent_m / 300 + descent_m / 500   # hours, vertical component
duration_h = max(t_h, t_v) + min(t_h, t_v) / 2
```

(`pipeline/lib/speed.py`'s `din_duration_h()` is the authoritative implementation, used by
`build_approach_table.py` and the pipeline's own `analysis/routing_probe.py` — mirror it exactly,
not an approximation of it.)

Shipping a stored duration creates exactly one trap: something reads it for a leg walked backwards
and is wrong by the full ascent/descent-rate gap (see §3). Computing it at load time is cheap (a
few thousand rows) and can't go stale relative to direction.

## 3. Direction: the graph is undirected, reversal is a client-side synthesis

`hut_edges/records.npy` stores **one record per unordered pair per variant** — for AT+Bayern,
6,067 unique unordered pairs, zero cases with both `u→v` and `v→u` stored. `start_edges/` (feeding
the approach table, §6) is one-directional: every record is `access-point → hut`.

Reversing a hut-edge record for display (B→A when the stored record is A→B) is the client's job.
The reverse-traversal contract:

- **Unchanged**: `distance_m`, `road_m`, `sac_rank`, `via_ferrata`, `max_ele_m`, `ungraded_m`,
  `inferred_m`.
- **Swapped**: `ascent_m` ↔ `descent_m`.
- **Recomputed**: duration (§2, from the swapped ascent/descent).
- **Reversed for display**: geometry and elevation profile (both fetched separately, from
  `hut-edges.pmtiles` and `hut_edges/profiles.npy` respectively — neither lives in this payload).

**Known approximation, not a bug to fix here:** under the old road-penalized *distance* cost, the
cheapest A→B path was provably the cheapest B→A path, so one stored record was lossless in both
directions. Under the current pointwise time cost that no longer holds — reversing a path flips
the sign of every segment's slope, and the speed curve `v(s)` is asymmetric (uphill and downhill at
the same |slope| take different time), so which path is fastest can differ by direction. Iteration
1 accepts one record per unordered pair anyway (fixing it doubles the routing build); the
magnitude of the resulting error is **measured, not assumed** — see `data/analysis/routing_probe.json`
("direction spread") and `docs/superpowers/specs/2026-08-22-tour-suggestion-findings.md` for the
actual figure once the probe has run. Do not describe this as "unknown" in client-facing copy once
that number exists — cite it.

The large, obviously user-visible asymmetry — a leg's *duration* depends on which way you walk it —
is not this approximation. That part is fully and exactly handled by recomputing duration per
direction (§2); the approximation above is narrower: it's about whether the stored *path itself*
(the specific route, not just its cost) is still the best choice in reverse.

## 4. `max_ele_m` is a per-edge filter, not a per-route aggregate

`max_ele_m` is the highest elevation reached anywhere on the record's path — computed once, at
build time, over both endpoints and every interior point. If a client is implementing an altitude
ceiling ("avoid routes above 2500 m"), filtering on `max_ele_m <= cap` is correct **per edge**, but
has a known blind spot: an edge whose path tops a 2800 m col is dropped entirely under a 2500 m cap
even where a lower alternative path between the same two huts exists as a *different* edge or a
multi-hop route — the pipeline does not search for that alternative on the filtered-out edge's
behalf (spec C9). A route search stitching multiple edges together will naturally route around
this by trying other edges; a single-edge lookup will not.

## 5. `ungraded_m == 0` is a guarantee, not an observation — but only on constrained rows

`sac_rank` is a max over the path, and untagged terrain is encoded as `-1`, which `max` ignores —
so historically an edge could contain kilometres of completely ungraded terrain and still report a
reassuring `sac_rank = 2`. That's a safety defect under a user-stated difficulty ceiling, not just
an accuracy gap (spec C4).

The fix is structural, not a client-side filter: **every constrained variant row
(`FAST_T2`/`FAST_T3`) is built by routing over a subgraph from which every ungraded-terrain edge
has been removed before the pathfinder ever runs.** That means `ungraded_m == 0` holds *by
construction* on every record with `variant != FAST_ANY` — it is not something the client needs to
check, and it is not merely "usually zero." This is what licenses the product-facing claim *"every
metre of this route is graded T3 or easier"* with no hedge. Filtering client-side on
`sac_rank <= 3` over `FAST_ANY` rows does **not** support that same claim — `sac_rank` alone hides
the ungraded terrain the way it always did; only routing on a pre-filtered subgraph does.

`FAST_T3_UNGRADED` is the fourth grid row (added because the strict ungraded-connectivity gate
measured 31.7%/36.9% of huts losing their last T2/T3 connection — far over the threshold that would
have kept the grid at three rows, see the findings doc): it permits ungraded terrain again but still
enforces the `sac_rank` ceiling. A client presenting this row must not imply the same "every metre
graded" guarantee `FAST_T2`/`FAST_T3` carry.

`inferred_m` is a related but separate fact: metres graded via the physical-implication table
(e.g. `highway=track` implies T1 by construction, even untagged) rather than an explicit
`sac_scale` tag. It does **not** count toward `ungraded_m`, because it supports a different claim —
"this terrain's difficulty is known with high confidence from what it physically is," not "someone
explicitly graded it."

**Difficulty resolution between routed thresholds is approximate.** The variant grid only routes at
whole thresholds (`<= T2`, `<= T3`); it is exact *at* T2 and T3 but does not support an arbitrary
client-chosen ceiling in between with the same guarantee (spec C9).

## 6. `approaches.bin` + `approaches.json`

Built by `pipeline/phases/postprocessing/build_approach_table.py` from `start_edges/records.npy`
(92,426 raw records over 27,261 parkings + 3,025 stations — not shippable as-is). Two things,
because a client needs both a small per-hut table and a way to answer "does this loop close":

**Approach table** (`approaches.bin`, columns per `approaches.json`'s `columns` manifest):
`hut_id` (u2), `start_id` (u8 — a raw OSM node id for `TYPE_PARKING`/`TYPE_STATION` rows, or the
Alpenverein ArcGIS layer's `OBJECTID` for `TYPE_PARTNER` rows — same field, two different id
spaces depending on `source_type`, exceeds u4 range either way), `source_type` (u1,
`binfmt.TYPE_PARKING`/`TYPE_STATION`/`TYPE_PARTNER` — the last added
`docs/superpowers/specs/2026-08-28-hut-classification-design.md`),
`access_unknown` (u1, boolean), `distance_m`/`ascent_m`/`descent_m` (f4). The k best approaches per
hut (k = `config.approach.k`, default 3), where "best" is **time-ranked** (DIN duration, §2), not
distance-ranked, and restricted-access candidates (`access`/`motor_vehicle ∈ {private, no}`, gated
forest roads) are hard-dropped before ranking — a missing access tag is kept but flagged via
`access_unknown` rather than dropped, since "unknown" and "known open" are different claims. At
least one parking-sourced and one station-sourced approach is kept where both exist, even if a
different source type would otherwise fill every slot, so a client's car/transit mode split always
has something to work with. Only `FAST_ANY` records are candidates — an approach is a fastest,
unconstrained leg to the hub, not a difficulty-graded one.

**There is no approach time cap** (`maxApproachTime` does not exist and must never be
reintroduced — see the root `CLAUDE.md`'s "Global Constraints" and spec E1). An approach is a full
leg, bounded by the same `maxEdgeKm` range cap as any hut-hut edge; any tighter time-based
filtering is a client-side UI decision (e.g. a `maxLegTime` the user sets), not a pipeline one.

`access_values` in the manifest (`approaches.json`) is a parallel array of raw OSM `access` tag
strings (one per approach row, `None` where absent) — interned as JSON rather than packed into the
binary, since the row count (~7k) makes that cheap and the value set is open-ended (any OSM
`access=` value: `"customers"`, `"permit"`, ...). A client wanting to surface "toll road" or
"permit required" reads this array by row index, not the binary payload.

**Loop-closure reverse index** (`approaches.json`'s `reverse_index`, JSON, not in the binary): the
client's car mode requires exit start-point == entry start-point, and the k≈3 approach tables of a
tour's first and last hut essentially never share a start id on their own — a naive intersection
would annihilate the result set. So every `start_edges` record whose start point appears in *any*
hut's retained approach ships here too (all variants — closure needs whatever the client already
has open, not just `FAST_ANY`), keyed both ways: `hut_to_starts[hut_id]` and
`start_to_huts[start_id]`, each a list of `{hut_id, start_id, source_type, variant, distance_m,
ascent_m, descent_m}`. Exit edges are these same records read backwards (§3) — nothing separate is
stored for "the return leg."

## 7. `unsnapped_huts.json`

Written directly by `build_hub_edges.py` (not a postprocessing reduction). A hub is "snapped" onto
the trail network by finding its nearest trail point; if no trail point exists within
`config.graph.maxSnapM` (default 100 m) horizontally, or the nearest candidate within that range
sits more than `config.graph.maxSnapAscentM` (default 25 m) above or below the hub's own DEM
elevation, the hub is dropped entirely rather than force-matched — no edges are computed for it.
This file is that drop list, made visible instead of silent: `{id, name, gap_m, dz_m, reason}` per
rejected hub, `reason ∈ {no_trail_data, gap_too_far, vertical_offset}`. Same honesty standard as
`ungraded_m` (§5) — a hub a client expects to route through and can't should be diagnosable, not a
silent gap in coverage.

## 8. Hut metadata

Already shipped as `huts.geojson` — this payload's `hut_ids` / `from_id`/`to_id` indices join back
onto it by array position, not by any new id scheme. `huts.geojson` itself gained `hutType`
(`"av"`/`"sonstige"`), `serviced` (bool), and `elevation` properties on 2026-08-28
(`docs/superpowers/specs/2026-08-28-hut-classification-design.md`) — a separate, unrelated change
from this backend, noted here only because a client reading this payload will likely also read
those fields off the huts it joins onto.
