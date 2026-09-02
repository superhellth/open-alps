# Routed edge geometry drops trail detail (straight hops up to 3.9 km)

**Priority:** High

Stored edge geometry contains long straight hops that no trail follows. On the 2026-09-02 run,
`hut_edges/geometry.npy` holds **1,438 consecutive-vertex segments longer than 500 m, spread over
700 of 8,238 records** — the worst is **3,929 m**, inside a record with 1,766 geometry points.

Nothing should be able to insert a straight hop of that length: `graph.maxSnapM` is 100 m and
`tourMatch.endpointBridgeMaxM` is 250 m. And the hops are not endpoint artifacts — **0 of the 700
occur on a record's first or last segment**, so the folded hub snap is not the source. They sit
mid-path, and the same hop recurs across many records and all four variants (the 3,929 m one shows
up in at least 11 records routed by different hut pairs), which is the signature of a shared
underlying connection, not a per-record accident.

## What has been ruled out

| layer | finding |
| --- | --- |
| Base graph | Not the source. Its own per-edge max vertex gap is p50 28 m, p99.9 460 m. |
| Subgraph cache | Not the source. `route_subgraphs/*/local_edges.npy` carries `interior_offset=1265336, interior_count=196` for the edge under the worst hop — identical to `base_graph/edges.npy`. |
| Mid-chain snaps | Not the source. Across all 1,251 edge-kind snaps, parent interior points = 24,404, points kept by the split halves = 24,404. Zero loss. |
| `inferred_m` | Not an explanation. That field is about SAC grading, not geometry: its median is 8.3 km per record and its correlation with hop length is −0.26; 6,214 records have `inferred_m > 500` and no hop at all. |

## What the evidence points at

Sampling 200 of the >500 m hops: 119 have both ends land within 30 m of real base-graph nodes, and
**117 of those 119 node pairs are joined by a base-graph edge that carries a non-empty interior
polyline** — geometry that exists upstream and is absent from the emitted record. So the loss
happens between `subgraph.local_edges` and `write_edge_records`, i.e. in
`lib/cell_igraph.py`'s `interiors` construction (~line 101) / `build_igraph_base`'s `_filter` /
`accumulate_path`'s `trail_coords.extend(interior)` (~line 293).

**One thing that does not fit and needs explaining first:** the record holding the worst hop
(`hut_edges` row 2734, `138→124`, FAST_ANY, 58 base edges traversed) does **not** list that
candidate edge (`edge_id=449644`) in its `edge_ids.npy` slice. Either the nearest-node attribution
above picked the wrong edge, or the path traversed a synthetic/parallel edge whose interior is
genuinely empty. Resolving that is the first step of the debugging pass — reconstruct one affected
record's traversal edge by edge and find the first point where the emitted polyline diverges from
the concatenated base-graph interiors.

When decoding `edge_ids.npy`, note that `base_edge_ids` are encoded `3n` / `3n+1` / `3n+2`
(`lib/cell_igraph.py:129,163,178` — original edge and the two halves of a mid-chain split), so raw
ids do not index `base_graph/edges.npy` directly.

## Why it matters

This is the "straight line ignoring the trail network" the map has been showing. It is display-only
— `distance_m`/`time_s`/`ascent_m` come from edge attributes and are unaffected — but the drawn
route is what a user judges the tour by, and a 3.9 km straight line across a valley reads as a
broken product.

(For the record: the screenshot in `docs/backlog.md` that first prompted this was *not* this bug.
Its route is dashed end to end, which in `ResultsMap.tsx:186-193` means `isFallback`, and its
straight leg lies exactly on the line between two hut markers. That one is `loadLegGeometry`
rejecting or still in flight — a separate, frontend-side issue. This bug was found by measurement
afterwards and is real independently of it.)

Found while measuring baselines for the data-quality monitoring layer
(`docs/superpowers/specs/2026-09-02-data-quality-monitoring-design.md` §4.3.4, which turns the
vertex-gap metric into a standing check).
