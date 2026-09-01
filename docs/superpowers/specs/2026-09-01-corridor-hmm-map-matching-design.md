# Corridor HMM Map Matching — Design

**Problem:** `match_leg` (`pipeline/phases/graph_building/match_tour_edges.py:72`) routes each tour
leg as a single shortest-path Dijkstra call between its two endpoint hub vertices, inside a corridor
subgraph built from the leg's own GPX trace (`corridor_bounds`, buffered bbox). The corridor
constrains which *edges* are eligible but never forces the matched path through any of the trace's
own intermediate points — so a leg whose official route deliberately detours (over a summit, out to
a viewpoint and back) gets shortcut whenever a lower/flatter/more-direct path exists between the same
two hubs inside that bbox.

**Concrete case:** Kaisertour leg 1's GPX trace climbs from 682 m to a summit at 1589 m (80% of the
way through the trace), then only descends partway to 1386 m at the endpoint hub. The matched route
came back with a 0.63 length ratio (37% shorter than the trace) and a 1237 m max deviation, both
centered on the summit — measured by `pipeline/analysis/corridor_match_quality.py`.

**Root cause:** endpoint-only shortest-pathing has no way to represent "pass through this waypoint,"
only "start here, end there, stay near this bbox." This is a structural limit of the current matching
approach, not a corridor-buffer tuning issue, and it is general — any leg whose real route isn't the
locally-shortest path between its endpoints is at risk, not only summit-shortcut cases.

**Goal:** Replace `match_leg`'s single-Dijkstra core with HMM-style map matching (Newson & Krumm):
snap each (resampled) trace point to candidate graph edges and Viterbi-decode the maximum-likelihood
edge sequence, so the matched path is structurally pulled through the trace's own shape rather than
only anchored at its two ends. Scope is the whole matching core — every tour leg, not a
summit-specific special case — since the root cause applies uniformly.

## 0. Why not a lighter alternative

A "waypoint-forced" multi-stop shortest path (decimate the trace, snap each waypoint into the
corridor subgraph, shortest-path through the sequence) was considered and rejected: it still
shortest-paths between consecutive waypoints, so it only shrinks the shortcut gap rather than closing
it, and degrades exactly the same way on dense terrain (many candidate paths of similar length
between close waypoints) that this fix needs to handle correctly. Full HMM matching's Viterbi
decoding is what actually scores *sequences* of edges against the trace's shape (via transition
probabilities, §3) rather than re-deriving a fresh shortest path at every waypoint independently.

This is a real design change to `match_tour_edges.py`'s matching core, not a corridor-buffer or
threshold tweak.

## 1. Dependency — `leuvenmapmatching`

Added to the `alpen-osm` pixi env's `[pypi-dependencies]`. Pure Python, `numpy`/`scipy` at its core —
no new system dependency, unlike `fmm`'s C++/GDAL/Boost stack (rejected for that reason when this
same trade-off was scoped in `docs/superpowers/specs/2026-08-29-official-tours-integration-design.md`
§2.4, before the tour-folder-ingestion rewrite changed the input format out from under that draft).
`leuvenmapmatching.map.inmem.InMemMap` (plain-Python node/edge store, with a scipy KD-tree index when
constructed `index_edges=True`) and `leuvenmapmatching.matcher.distance.DistanceMatcher` (Viterbi
decoder over emission/transition probabilities) are the two pieces used here.

**Coordinate order is `(lat, lon)`, not `(lon, lat)`.** `InMemMap(use_latlon=True)` takes node
positions and observation points as `(lat, lon)`; every array column, GPX point, `vertex_coords`
entry and `PathResult` coordinate in this pipeline is `(lon, lat)`. The swap happens at exactly two
boundaries — nodes going into the map, and the resampled trace going into the matcher — and is
swapped back on the way out. A transposed pair raises nothing: it silently matches a plausible-
looking path somewhere else entirely, so §8 tests the round-trip explicitly instead of relying on
review to catch it.

## 2. Per-leg candidate graph

Matching must never touch the whole base graph — `base_graph/manifest.json` is 3,931,404 nodes /
4,730,712 edges, and `InMemMap` is Python dicts of tuples/sets, multiple GB before matching even
starts. One `InMemMap` is built **per leg**, sourced from exactly the corridor subgraph `match_leg`
already gathers today (`corridor_bounds` → `gather_subgraph_for_bounds` →
`clip_subgraph_to_bounds`, unchanged) plus the two endpoint hub snaps materialized into it
("Endpoint anchoring" below) — corridor sizing (`tourMatch.corridorBufferM`) stays the
candidate-edge prefilter, same role it plays today.

**Interior expansion is required, not optional.** Base-graph edges are contracted chains
(`build_base_graph.py`'s structural contraction) — the real curved shape of a trail lives in
`local_edges[i].interior_offset/interior_count` slices into `interior.npy`, not in the straight
u→v chord. Matching against the chord would discard exactly the curvature (switchbacks, a
summit-approach bend) the match is meant to discriminate on. Each corridor edge's interior polyline
is expanded into a chain of short `InMemMap` edges; each expanded sub-edge records its parent
base-graph edge id (and interior-segment index, for reconstructing a partial-edge cut point) so the
winning Viterbi state sequence maps back to real `EDGE_DTYPE` rows for accumulation (§5).

**The parent id is the disambiguated `base_edge_id`, not the raw `edge_id`.** `lib/cell_igraph.py`
(:129/:163/:178) encodes it as `edge_id * 3` for an original edge and `edge_id * 3 + 1` / `+ 2` for
the u-side/v-side half of a hub-split edge — spec §1 of
`docs/superpowers/specs/2026-08-29-avoid-overlapping-tracks-design.md`. Reconstruction here must emit
ids in that same namespace. Emitting a raw `edge_id` would put `tour_edges/edge_ids.npy` (and
`RECORD_DTYPE`'s `prefix_ids`/`suffix_ids`) in a different id space from `hut_edges/`, which the
overlap-suppression machinery compares against — with no error, just wrong answers. §8 asserts it.

### Bounding the map

`corridor_bounds` (`match_tour_edges.py:58`) is a **buffered bbox over the whole trace**, not a
buffered polyline. That is a fine candidate prefilter for a Dijkstra whose cost is dominated by the
two fixed endpoints, but here it sizes an `InMemMap` that also pays interior expansion and
bidirectional insertion on every edge inside it — and for a hook- or loop-shaped leg the bbox area is
a large multiple of the trace's own buffer. `_cached_gather_for_bounds` caches the *gather*, not the
map build, so this cost is paid once per leg.

Rough size, to keep this honest rather than assumed: ~4.7M edges over the AT+Bayern extract is order
30 edges/km²; a 10 × 6 km leg bbox is order 2–3k base edges; at ~132 m mean edge length with interior
points every 10–20 m that is order 20–30k sub-edges, doubled for direction. That is comfortably
in-memory — the point is that it is *bounded and estimated*, not that it is free.

**Expanded sub-edges are filtered to those within `hmmMaxDistM` of the trace polyline** before being
added to the map. No candidate further than the emission cutoff can ever win a state, so this drops
map size to the trace's actual buffer without changing a single matching outcome, and it keeps the
bbox/polyline distinction from silently becoming a scaling problem on long legs. `corridor_bounds`
itself is unchanged.

**Edges are added bidirectionally.** These are hiking trails, not one-way roads — `InMemMap.add_edge`
is called for both directions of every base-graph edge (and every expanded interior sub-edge), so a
trail segment is an equally valid candidate state whether the trace walks it outbound or return.

### Endpoint anchoring — the two hub snaps

A trace-driven Viterbi decode starts on whatever edge best explains the *first trace point*, which is
not the same place as the leg's endpoint hub snap. Today that question does not arise: routing runs
between `hub_vertex[src_key]` and `hub_vertex[tgt_key]`, so the routed path provably begins at
`src_snap`'s snap point and ends at `tgt_snap`'s. Everything in `build_tour_record` leans on that one
invariant:

> `path.coords[0]` **is** the src snap point and `path.coords[-1]` **is** the tgt snap point —
> so `gap_m` (a straight line from the hub to *that exact point*) and `fold_endpoint_snaps`' folding
> of `gap_dz_m` price exactly the piece the geometry `[from_coord, *path.coords, to_coord]` is
> missing, no more and no less.

Left unanchored, a matched leg would start tens to ~200 m from its own snap point, `snap_m` would
price a gap the geometry does not contain (breaking spec B3's "routing and display are the same
numbers"), a mid-chain-snapped hut would pull in a whole parent edge of phantom trail running past
it, and consecutive legs of one tour would no longer meet at the hut. The invariant is preserved
here, in two parts.

**1. The hub snaps are materialized into the `InMemMap`, exactly as `build_base_igraph_arrays` does
it** (`lib/cell_igraph.py:131-179`). `reconstruct_local_snaps` is unchanged and still runs before
matching, so `hub_unsnapped` keeps its current meaning and timing. Then:

- **Node snap** (`SnapResult.node_index`) — the snap point is already a base-graph node, hence
  already an `InMemMap` node after interior expansion (expansion keeps each edge's original two
  endpoints as real nodes). Nothing extra is needed; that node is the anchor.
- **Mid-chain snap** (`SnapResult.split`) — the parent edge is **not** added whole. It is cut at
  `split.split_coord`, which becomes an `InMemMap` node, and its two halves are added instead,
  carrying `split.interior_to_u`/`interior_to_v` as their interior polylines and the already-
  apportioned `dist_to_u`/`dist_to_v`, `road_m_*`, `ungraded_m_*`, `inferred_m_*`. Interior
  expansion then runs over the halves rather than the parent, and the halves are tagged
  `edge_id * 3 + 1` (u-side) and `+ 2` (v-side) — so §2's id encoding falls out naturally and the
  parent's plain `edge_id * 3` never appears for that edge in this leg.

**2. The decoded state sequence is reconciled to the anchors by trim-or-bridge.** The decoder is
never lied to about where the trace starts — it runs over the trace as-is. Afterwards, at the src
end (mirrored at the tgt end):

- **Anchor already first** — the common case, a GPX that starts at the hut door. Nothing to do.
- **Trim** — the anchor node appears *inside* the decoded sequence (the trace ran past the hut before
  turning up the leg's real direction). The states before it are dropped, and the sequence starts at
  the anchor.
- **Bridge** — the anchor is not on the decoded path at all. A Dijkstra **inside the corridor
  subgraph** connects the anchor to the decoded start, and that sub-path is prepended as ordinary
  directed states, accumulated like any other traversal (its edges appear in `base_edge_ids`).

The bridge is the one place a shortest path survives this design, and deliberately: between the hub
and where the recorded track begins, **the trace describes no shape at all**, so there is nothing for
an HMM to honor and shortest-path is the only defensible reconstruction. It also cannot reintroduce
the §0 shortcut problem — it is bounded by `tourMatch.endpointBridgeMaxM` (250 m, ≈ 2 ×
`graph.maxSnapM` plus slack for along-trail vs. straight-line distance: both the hub→snap-point and
the hub→trace-start gaps are already capped at `maxSnapM` = 100 m), which is orders of magnitude
below a leg length, and it applies only at the two ends. A bridge longer than the cap is not a match
to be patched but a sign the leg's endpoint hub is wrong: it becomes a gap (§4).

### Out-and-back detours (spur trails)

A leg whose official route detours off the direct line to a dead-end (a summit spur, a viewpoint) and
returns the same way is a distinct case from a through-detour like Kaisertour leg 1, and needs two
things to be representable:

1. **Bidirectional edges (above)** — the spur must be walkable both directions as separate candidate
   states.
2. **The final matched path is the concatenation of the shortest sub-path between each pair of
   consecutive Viterbi-selected states**, not one global src→tgt shortest path — that concatenation
   is the entire reason this design replaces the single-Dijkstra call. A trace that goes out along a
   spur and back naturally produces a state sequence that walks the same expanded sub-edges twice,
   once each direction, when reconstructed. Edge accumulation (§5) must **not** dedupe repeated
   edges — a real out-and-back really does double the distance/ascent/descent for that spur, and the
   record must reflect that, not silently collapse it to a single traversal.

**Direction has to survive reconstruction, not just map construction.** A Viterbi state is a
*directed* `(sub-edge, direction)` pair, and the concatenation walks that state sequence directly.
If the sub-path between consecutive states were instead resolved as an undirected node-to-node
shortest path, an out-and-back would collapse at the turnaround — the outbound state's far node and
the inbound state's near node are the same node, so the "shortest path" between them is empty, and
the spur silently disappears. Direction is also what `accumulate_path`'s ascent/descent swap keys off
(`lib/cell_igraph.py:290-291`): `ascent_m`/`descent_m` are stored per base edge in a fixed u→v
direction, so a v→u traversal must swap them or a descent gets reported as ascent.

Note that `write_edge_records` already reduces `base_edge_ids` to a sorted **set** for
`edge_ids.npy` (`lib/edge_output.py:53-58`); that is correct and stays. The no-dedupe rule applies to
the accumulated scalars and to the traversal-ordered `prefix_ids`/`suffix_ids`, not to that set — an
implementer must not "fix" `edge_output.py` to preserve duplicates.

A dead-end spur to a summit is structurally a single base-graph edge (a degree-1 node at the top,
from `build_base_graph.py`'s contraction — `lib/contraction.py:55` keeps every node whose degree
!= 2) already inside the corridor bbox, so no special-casing is needed beyond the points above.
A turnaround that is *not* a graph node — a viewpoint partway along an edge — is the partial-edge
case, handled by §5's apportionment rule.

## 3. Matching parameters

Trace point density spans two orders of magnitude across real tour GPX files (3–102 m/point,
measured against the AV's own published geometry in the predecessor spec's §0.1; tour-folder GPX
files vary similarly), so the trace is normalized before matching.

**Resampling is decimate-only** (`tourMatch.hmmResampleM`, ~25 m): a run of points closer together
than the spacing is thinned down to it, and a sparse stretch is **left alone** — no point is ever
interpolated into existence. Upsampling a 100 m/point trace to 25 m would fabricate three
observations per gap by linear interpolation, and on a switchback or a summit-approach bend those
fabricated points sit demonstrably off-trail — then act as real observations pulling the match away
from the trail the sparse trace actually describes. `DistanceMatcher`'s `non_emitting_states` is the
right tool for a sparse stretch: it lets the decode traverse intermediate edges between two distant
observations without demanding an observation for each. Endpoints are preserved exactly in both
directions.

- **Emission probability**: Gaussian in perpendicular distance from each trace point to a candidate
  edge. Two distinct roles, which must not share one number:
  - `max_dist` (`tourMatch.hmmMaxDistM`, 150 m) — the hard candidate cutoff, set to
    `corridorBufferM` so the candidate set matches the corridor prefilter.
  - `obs_noise` (`tourMatch.hmmObsNoiseM`, 25 m) — the Gaussian width, set to the *actual* accuracy
    of a hiking GPX track (Newson & Krumm use ~4 m for vehicle GPS; a hand-held under canopy or
    against a rock face is worse, order 10–25 m). Setting σ to the corridor buffer instead would
    make the emission term nearly flat across the whole corridor — a trail 140 m away would score
    almost as well as the one under the trace — which destroys exactly the discrimination this
    change exists to add. Distance must discriminate; `max_dist` is what stops it from over-
    excluding.
- **Transition probability**: ratio between consecutive matched states' graph path-length and their
  great-circle distance, with width `dist_noise` (`tourMatch.hmmDistNoiseM`, 25 m — `leuvenmapmatching`
  defaults this to `obs_noise`, so it is set explicitly rather than inherited). This is the mechanism
  that fixes the summit-shortcut case directly: a candidate sequence that skips the summit has a far
  worse path/great-circle ratio between the trace points bracketing it (a long low detour vs. a short
  direct climb) than the sequence that goes over, so the correct sequence wins even though it is not
  the shortest path between the leg's two endpoints.
- **`max_lattice_width`**: left at the library default initially, but named here as a deliberate
  choice — it is the beam width, and a too-narrow beam prunes the correct-but-currently-behind
  summit branch before the trace reaches the evidence that vindicates it. It is the first knob to
  raise if a summit case still loses after §3's other params are tuned.

All four new params re-tuned against real data (Kaisertour, Welser Höhenweg, and any other folders on
disk) once the phase runs, same "start with a reasoned default, retune with evidence" discipline
`corridorBufferM`/`lengthDivergenceRatio` already followed in the tour-folder-ingestion spec.

## 4. Break handling — never faked

If the Viterbi decode cannot maintain edge continuity for some stretch of the trace (a via ferrata
missing from OSM, GPS noise that leaves the trail, a trace point with no candidate edge inside the
corridor at all), **the whole leg is dropped as a gap** — never a partial or stitched-together match.
This is the same discipline `match_leg` already applies elsewhere
(`docs/superpowers/specs/2026-08-30-tour-folder-ingestion-design.md` §5): a leg either matches
end-to-end or it produces no `records.npy` row.

Two new gap reasons, added to `tour-match-gaps.json`'s existing vocabulary:

| reason | when |
|---|---|
| `hmm_match_broken` | the Viterbi decode found no viable state sequence covering the whole trace |
| `endpoint_bridge_too_long` | the decode covered the trace, but §2's bridge from an endpoint hub's snap point to the matched path exceeds `endpointBridgeMaxM` |

`tour-match-gaps.json` is the actionable record of what the pipeline could not do (per the
tour-folder-ingestion spec), so the detail must be enough to diagnose without rerunning.
`hmm_match_broken` carries the **resampled-trace index range** the decode failed to cover, the
**lon/lat** at the start of that range, and the **nearest candidate distance** found there (which
distinguishes "no trail in OSM at all" from "trail exists but sits just outside `hmmMaxDistM`" — two
very different fixes). `endpoint_bridge_too_long` carries which endpoint (`from`/`to`), the bridge
length and the cap — a leg failing this way almost always means `nearest_hub_to_point` picked the
wrong hub, not that the match is bad.

This **supersedes** today's `no_corridor_path` (the old "no path at all between the two endpoint
vertices" case is now just one way the decode can fail to cover the trace) — `no_corridor_path` is
removed as a distinct reason. `outside_extract` and `hub_unsnapped` are unchanged (they're rejected
before matching starts, same as today). `length_divergent` stays as a final sanity check on the
winning path's total length vs. the trace length (`lengthDivergenceRatio`) — matching can in
principle produce a path that covers every trace point but is still implausibly long or short, and
that check catches it independent of *how* the path was built.

**This is strictly stricter than today's rule**, and that has a cost worth measuring rather than
assuming: a leg that currently matches *via a shortcut* can become a gap under a decode that refuses
to cover its trace. §8's real-data check therefore records the matched-leg count before and after,
not only the deviation metric. A drop is a result to explain leg-by-leg (each newly-gapped leg
traced to a real OSM coverage gap), not a regression to absorb silently — and if it turns out to be
broad, that is evidence for retuning §3 rather than for loosening §4.

## 5. Output — unchanged shape, different internals

No `RECORD_DTYPE` or `tour_meta.npy` schema change. The winning Viterbi state sequence is walked to
produce the same fields `accumulate_path` produces today (`dist`, `road_m`, `ungraded_m`,
`inferred_m`, `ascent_m`/`descent_m` — summed per direction-adjusted traversal, not deduped per
§2's out-and-back requirement —, `max_ele_m`, `sac_rank`, `via_ferrata`, `base_edge_ids`), so
`build_tour_record` (`match_tour_edges.py:119`) needs no changes: it already just consumes a
`PathResult`-shaped object plus the two endpoint `SnapResult`s, and §2's endpoint anchoring keeps the
one invariant it relies on — `coords[0]`/`coords[-1]` *are* the two snap points, so `snap_m`,
`fold_endpoint_snaps` and the geometry prefix/suffix stay exactly as correct as they are today. The
concatenation/accumulation logic that walks the
Viterbi output into that shape is new code inside `match_tour_edges.py` (or a small new `lib/`
helper if it turns out reusable), replacing today's `graph.get_shortest_paths` + `accumulate_path`
call in `match_leg`.

**Partial-edge traversal must be apportioned, not rounded.** A base edge is only partly walked
whenever the decode's cut point falls between two of its interior vertices — at any turnaround that
is not itself a graph node. (At the two leg *ends* this is already handled: §2 materializes each
mid-chain hub snap as a pre-apportioned pair of halves, so the endpoint cut is a real `InMemMap`
node, not a partial traversal.) `dist`, `road_m`, `ungraded_m` and `inferred_m` are apportioned by
distance ratio along the interior polyline, exactly as `lib/edge_split.py`'s `split_edge_at_point`
already does for hub snaps (reuse it rather than re-deriving the arithmetic);
`max_ele_m` is taken over the interior points actually traversed. `ascent_m`/`descent_m` have no
per-interior-point elevation to apportion from — the known limitation documented at
`lib/cell_igraph.py:110-113`, where a split edge's halves inherit rather than divide — so a partial
traversal contributes them at the same distance ratio, and this approximation is stated here rather
than discovered later.

**`match_leg`'s signature changes.** It needs the leg's trace points, not just `trace_length_m`.
This is not a purely internal change: `tests/test_match_tour_edges.py:48-95` calls `match_leg`
directly in four tests, all of which need updating alongside.

**`_check_routable` must be called explicitly.** `lib/cell_igraph.py:60` is documented as the one
chokepoint every routing caller passes through — it catches a subgraph whose `time_s` is still UNSET
(`compute_edge_profiles` never ran against this base graph), which igraph otherwise turns into hours
of silent 100%-CPU Bellman-Ford per call. Dropping the igraph build from `match_leg` drops that
guard for this script unless it is invoked directly on the corridor subgraph. Keep it.

`corridor_match_quality.py` needs no changes — its deviation metric (mean/max trace-point-to-routed-
polyline distance) is exactly the yardstick this fix is measured against.

**Expected outcome, stated so it can't fail spuriously:** Kaisertour leg 1's matched
`base_edge_ids`/geometry include the summit, and its max deviation drops from 1237 m to the order of
the *geometric disagreement between the OSM way and the GPX track* — tens of metres. Deviation is
trace-point-to-routed-polyline distance, so its floor is how far the mapped trail sits from the
recorded track, **not** the observation spacing; "shrinks to ~`hmmResampleM`" would be the wrong
acceptance bar and could fail a match that is entirely correct.

## 6. Config changes

`pipeline/pipeline.config.json`'s `tourMatch` block gains five keys, keeps the two it has:

```jsonc
"tourMatch": {
  "corridorBufferM": 150.0,       // unchanged — still the candidate-edge prefilter
  "lengthDivergenceRatio": 2.0,   // unchanged — still the final length sanity check
  "hmmResampleM": 25.0,           // new — minimum trace point spacing (decimate-only, §3)
  "hmmObsNoiseM": 25.0,           // new — emission Gaussian width ≈ real GPX accuracy
  "hmmMaxDistM": 150.0,           // new — hard candidate cutoff, = corridorBufferM
  "hmmDistNoiseM": 25.0,          // new — transition width (leuven would default it to obs_noise)
  "endpointBridgeMaxM": 250.0     // new — cap on §2's hub-snap-to-matched-path bridge
}
```

`tests/test_config.py:16` asserts the exact key set
(`set(tm.keys()) == {"corridorBufferM", "lengthDivergenceRatio"}`) and must be extended in the same
change, or it fails the moment the config is edited.

No `record_schema_version` bump — `RECORD_DTYPE` itself is untouched (§5).

## 7. DAG wiring

No task-graph shape change: `match_tour_edges.py` keeps the same `task_dep`/`file_dep`/`targets`
`docs/superpowers/specs/2026-08-30-tour-folder-ingestion-design.md` §6 describes.

It does need new **params**, though — `dag/graph_building.py:125-129` currently tracks only
`corridor_buffer_m` and `length_divergence_ratio` via `cli_param`. Each of §6's five new keys needs
its own `cli_param` there and a matching `argparse` flag in `main()`. Without that, §3's "retune with
evidence" loop silently does nothing: changing `hmmObsNoiseM` would not invalidate the task, so doit
would consider the existing `tour_edges/` outputs up to date and skip the rerun — the exact failure
`TaskOptionsChanged` exists to prevent.

## 8. Testing

- **Resampling**: unit test that a dense 3 m/point fixture is decimated to ~25 m spacing, that a
  sparse 100 m/point fixture passes through **unchanged** (no interpolated points), and that
  endpoints are preserved exactly in both cases.
- **Coordinate order**: unit test that a known `(lon, lat)` polyline fed through map construction and
  matching comes back as the same `(lon, lat)` polyline — the (lat, lon) boundary of §1 is silent
  when wrong, so it needs an explicit round-trip assertion.
- **Interior expansion**: unit test that a synthetic base-graph edge with a curved interior polyline
  expands into the expected chain of `InMemMap` sub-edges, each tagged with its parent base edge id.
- **`base_edge_id` namespace**: unit test that a matched leg's `base_edge_ids` are `edge_id * 3`
  encoded (§2), i.e. in the same id space `build_hub_edges.py` emits — not raw `edge_id`s.
- **Endpoint anchoring — the invariant**: for every leg matched in the golden-tour fixture, assert
  `path.coords[0]` equals the src `SnapResult`'s snap point and `path.coords[-1]` the tgt's, exactly
  (§2). This is the assertion `build_tour_record`'s correctness rests on, so it is checked directly
  rather than inferred from a distance total.
- **Mid-chain snap materialization**: fixture where an endpoint hub snaps mid-edge; assert the
  matched path starts at `split.split_coord`, that its first id is the `edge_id * 3 + 1` / `+ 2`
  half, that the parent's plain `edge_id * 3` never appears for that edge, and that no phantom trail
  beyond the hut is accumulated.
- **Trim**: fixture whose trace runs past the anchor before heading up the leg; assert the states
  before the anchor are dropped and the geometry starts at the anchor.
- **Bridge**: fixture whose trace starts short of the anchor; assert the bridge's edges appear in
  `base_edge_ids` and its length is included in `distance_m`.
- **Bridge cap**: same fixture with the anchor moved beyond `endpointBridgeMaxM`; assert
  `endpoint_bridge_too_long` in `tour-match-gaps.json` with endpoint/length/cap detail, and **no**
  `records.npy` row.
- **Summit-detour (through case)**: synthetic fixture shaped like Kaisertour leg 1 — a corridor
  containing both a short low path and a longer path over a "summit" node, with a trace that
  follows the summit path. Assert the matched output includes the summit node/edges, not the
  shortcut.
- **Out-and-back (spur case)**: synthetic fixture with a dead-end spur edge off the direct route,
  trace that walks out to the spur's end and back. Assert the matched `base_edge_ids` includes the
  spur edge **twice** (both directions) and that accumulated distance/ascent for that leg reflects
  walking it twice, not once.
- **Partial-edge apportionment**: fixture whose decode turns around partway along an edge; assert
  `dist`/`road_m`/`ungraded_m`/`inferred_m` are apportioned at the cut point rather than counting
  the whole edge (§5).
- **Break handling**: synthetic fixture where the trace crosses a genuine gap in the corridor
  subgraph (no candidate edge within `hmmMaxDistM` for some stretch). Assert `hmm_match_broken` in
  `tour-match-gaps.json`, detail carrying the trace index range, lon/lat and nearest-candidate
  distance (§4), and **no** `records.npy` row for that leg.
- **`length_divergent` still reachable**: a fixture where the Viterbi decode succeeds end-to-end but
  the winning path's total length still exceeds `lengthDivergenceRatio` — confirms the check still
  fires independent of how the path was built.
- **Existing `match_leg` tests**: the four direct callers at `tests/test_match_tour_edges.py:48-95`
  are updated for the new signature (§5), and `test_config.py`'s key-set assertion for §6.
- **Real-data check**: rerun `corridor_match_quality.py` against the tour folders on disk (Kaisertour,
  Welser Höhenweg) once implemented. Record **both** the deviation metric and the matched-leg /
  gap counts before and after (§4), and confirm Kaisertour leg 1's matched path includes the summit
  with deviation down to tens of metres (§5). Subject to `CLAUDE.md`'s "ask before running any
  pipeline task" rule.

## Out of scope

- **Retuning `corridorBufferM`/`lengthDivergenceRatio` beyond what §3/§6 already states as
  defaults.** Real retuning happens against measured results once this lands, same as the
  tour-folder-ingestion spec deferred its own corridor/divergence retuning.
- **Replacing `corridor_bounds`' bbox with a true buffered-polyline corridor.** §2 bounds the
  `InMemMap` by filtering expanded sub-edges against the trace polyline, which gets the size benefit
  without changing the gather/clip path every other caller shares.
- **Populating more tour folders, fixing hub-layer coverage gaps, or any other tour-folder-ingestion
  non-goal** — unrelated to this change, unaffected by it.
- **Client-side consumption** — `tour_edges/` output shape doesn't change, so nothing downstream of
  the pipeline needs to change.
