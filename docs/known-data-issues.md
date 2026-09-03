# Known data issues out of our reach

Confirmed defects that originate in a source dataset (OpenStreetMap, the DEM, the Alpenverein API)
rather than in this pipeline's code. Nothing here is actionable inside `pipeline/` — no code change
fixes it, because the pipeline is already faithfully representing what the upstream source
contains. Logged here so the data-quality layer's flags aren't repeatedly re-investigated as
pipeline bugs, and so a future look at the same symptom finds the answer instead of re-deriving it.

An entry graduates out of this file only if the upstream data changes (e.g. someone improves the
OSM way in question) and a rebuild picks that up.

## Sparse OSM way geometry — long straight-line hops in routed edges

**Symptom:** the `vertex_gap_base_graph`/`vertex_gap_hut_edges`/`vertex_gap_start_edges`
data-quality checks (`pipeline/phases/quality/check_graph_building.py`) flag consecutive-vertex
gaps of hundreds to thousands of metres in some edges' stored polylines — on the map, these render
as an unnaturally straight line cutting across terrain instead of following the trail's real curve.
`vertex_gap_base_graph` flags the same sparse ways one layer earlier, directly on `base_graph`
edges, before contraction/routing ever threads them into a `hut_edges`/`start_edges` record — same
root cause, same verdict, not a separate defect.

**Root cause:** some OSM ways are mapped with GPS detail only at their two ends and a single
straight-line guess across the stretch in between — common for remote alpine terrain (scree,
glacier, ridge) that's hard to survey continuously. The pipeline stores every point a way actually
has; when a way only has points at its ends, that's all there is to store.

**Confirmed example:** hut pair 110→452 (Braunschweiger Hütte) routes over base-graph
`edge_id 3023176`, a single continuous OSM way spanning ~1.8 km. It has exactly 9 recorded points:
5 clustered near one end, 2 clustered near the other, and one 1,707 m jump between the two clusters
with nothing traced in between.

**Why we keep the edge anyway:** it's a real, walkable trail, not a fabricated connection — dropping
it would strand real routes to "fix" what is a display fidelity problem, not a routing-correctness
one. `dist`/`time_s` for the edge come from OSM's own recorded endpoints, so they're not made any
more accurate by removing the edge, only less complete. The only actual downside is the drawn
line's shape between the two clusters; nothing about whether the route is valid or how long it
takes is affected by this defect.

**Actionable fix, if it's ever worth it:** improving the source way in OpenStreetMap itself. There
is no pipeline-side fix — inventing intermediate shape points would mean fabricating trail detail
we don't have, not recovering it.

**Status:** confirmed on the 2026-09-03 rebuild, 120 `vertex_gap_hut_edges` flags total (of 8,314
records checked) and 3,389 `vertex_gap_base_graph` flags (of 4,730,712 edges checked), most sharing
this same pattern (identical `max_gap_m` values repeating across records that funnel through the
same sparse way — e.g. `edge_id 3023176` above is the same base-graph edge flagged directly by
`vertex_gap_base_graph`). Investigated closing out the former
`docs/backlog/hut-edge-geometry-drops-trail-detail.md` backlog item (removed once resolved — see
git history for the full investigation). That item's other residual, `self_retrace_hut_edges`, was
a *different*, actually-fixable defect (hub-snap preferring a far node over a much closer trail
edge) — that one was fixed in `lib/hub_snap.py`, not logged here.
