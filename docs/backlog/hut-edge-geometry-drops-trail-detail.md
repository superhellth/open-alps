# Routed edge geometry drops trail detail (straight hops up to 3.9 km)

**Status: root cause found, fix applied in code — pending a hub-edge rebuild to confirm in data.**

Stored edge geometry contains long straight hops that no trail follows. On the 2026-09-02 run,
`hut_edges/geometry.npy` holds **1,438 consecutive-vertex segments longer than 500 m, spread over
700 of 8,238 records** — the worst is **3,929 m**, inside a record with 1,766 geometry points.

## Root cause

`lib/cell_igraph.py`'s `accumulate_path` decides whether to walk an edge's `interior` polyline
forward or reversed with `forward = e.source == cur` (`e` an igraph edge). That's wrong:
`ig.Graph(edges=[(u, v), ...], directed=False)` **canonicalizes every undirected edge's
`source`/`target` to ascending vertex-id order**, discarding which side of the pair was actually
inserted as `u`. Confirmed directly:

```python
>>> ig.Graph(n=5, edges=[(3, 1)], directed=False).es[0].tuple
(1, 3)
```

Whenever an edge's local `u` index happens to be greater than its local `v` index, `e.source` is
igraph's `v`, not the caller's `u` — but `interior` (and `ascent_m`/`descent_m`, spec-neutral in
the u→v direction) are stored in the *original* u→v order from `build_base_igraph_arrays`. Walking
such an edge starting from `cur == u` now reads `forward = False` (since `e.source` is `v`, not
`u`), so `accumulate_path` uses the un-reversed interior anyway — i.e. it enters the edge at `u`,
immediately emits the interior in u→v order starting from a point *near v* (the far end), walks
back down to end up near `u` again, then the next edge's entry point (near the *true* `v`) creates
the second half of the round trip. Two roughly edge-length jumps result — reproduced exactly for
`hut_edges` row `138→124` FAST_ANY: `edge_id=449644`, walked at `epath` index 43, worst gap
3,939.4766 m — the same value logged for this record's flagged row in `data/quality/graph_building.json`.

The bug also mis-swaps `ascent_m`/`descent_m` for the same edges (not just display geometry) —
`accumulate_path` uses the same wrong `forward` flag to decide whether to add `ascent_m` or
`descent_m` in the direction of travel — so a fraction of edges in every routed record (hut_edges,
start_edges, tour_edges — anything through `lib/cell_igraph.py`) may have been reporting a climb as
a descent and vice versa, independent of the geometry defect.

## Fix

`build_igraph_from_base` now also stores an `orig_u` edge attribute (the value actually inserted as
`u`, immune to igraph's canonicalization), and `accumulate_path` computes `forward =
e["orig_u"] == cur` instead of `e.source == cur`. `nxt` (the other endpoint) is now derived as
"whichever of `e.source`/`e.target` isn't `cur`", independent of canonicalization.

Regression test: `pipeline/tests/test_cell_igraph.py` (new file — `lib/cell_igraph.py` had no
dedicated tests before this) constructs a two-node, one-edge subgraph with `u` deliberately given
the *larger* local index (forcing igraph to canonicalize), asserts both directions' `coords` and
`ascent_m`/`descent_m` come out right, and includes a control case where `u < v` (never broken) for
contrast. Verified to fail (`ascent_m`/`descent_m` swapped) against the pre-fix code.

Reproduced live against the current `data/osm/route_subgraphs/cell_14` cache for hut pair
`138→124`: worst gap dropped from 3,939.5 m to 182.5 m (normal trail vertex spacing) with the fix,
total `distance_m` unchanged (28,587.6 m, from `dist` attributes, which were never affected).

## Remaining step

The fix is in `lib/cell_igraph.py` only — `data/osm/hut_edges/`, `start_edges/`, `tour_edges/`
still hold geometry/ascent/descent computed by the old code and need `build_hub_edges.py` (+
`build_access_edges.py`, `match_tour_edges.py`) rerun to pick it up. That's a multi-hour class of
task (see root `CLAUDE.md`'s pipeline-run rule) — not run as part of this fix; ask before
triggering it.

Found while measuring baselines for the data-quality monitoring layer
(`docs/superpowers/specs/2026-09-02-data-quality-monitoring-design.md` §4.3.4, which turns the
vertex-gap metric into a standing check).
