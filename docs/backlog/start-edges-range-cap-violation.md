# start_edges ignores the max-edge range cap (legs up to 268 km)

**Priority:** High

`graph.maxEdgeKm` (30) is the range cap every hub edge is supposed to obey — it is the
`--max-edge-km` param on `build_hub_edges.py` and `gather_route_subgraphs.py`, and
`build_approach_table.py`'s module docstring leans on it explicitly ("an approach is a full leg,
bounded by the same range cap as any hut-hut edge"). `start_edges/records.npy` does not obey it.

**Measured on the 2026-09-02 run** (`data/osm/start_edges/records.npy`, 471,196 rows):

| | over 30 km | worst row |
| --- | --- | --- |
| `start_edges` | **100,592 rows (21.3%)** | 267,637 m, 12,903 m ascent |
| `hut_edges` | 25 of 8,238 (0.3%) | 30,111 m |
| `tour_edges` | 0 of 5 | 15,268 m |

`hut_edges`' 25 rows overshoot by ~111 m, which is the folded endpoint snap gap on top of a 30 km
path — benign. `start_edges` is a different phenomenon entirely: the three worst rows are

```
7552770024(parking) -> 329(hut)   dist=267,637 m  ascent=12,903 m  FAST_T2   geom_count=11,797
14092290305(parking)-> 329(hut)   dist=262,276 m  ascent=12,867 m  FAST_T2   geom_count=11,609
984711989(station)  -> 590(hut)   dist=233,972 m  ascent=12,900 m  FAST_T3   geom_count=12,059
```

These carry real geometry (11k+ points), so they are routed paths, not artifacts — the router
simply was not stopped at the cap. 6,426 rows also exceed 5,000 m of ascent, which is the same
population seen from a different column.

## Why it matters

`start_edges` is not an internal array. `build_approach_table.py` selects the approach table out of
it and ships every retained start point's rows as the loop-closure reverse index, so a 268 km
"approach" can reach `approaches.bin`. It also inflates `start-edge-geometry.bin` (357 MB in
`data/osm` on this run) and `start-edges.pmtiles` (102 MB) with paths nothing should ever offer.

## Where to look

Suspicion is `phases/graph_building/build_access_edges.py` — the B5/B6 second routing pass added by
`docs/superpowers/specs/2026-09-02-hub-edge-scaling-design.md`. Unlike `task_build_hub_edges`, its
`pipeline_task` in `pipeline/dag/graph_building.py` declares **no `max_edge_km` param at all**, so
neither the action line nor the tracked cache key carries the cap. Two things to confirm:

1. whether `build_hub_edges.py`'s B3 distance pass already emits over-cap pairs into
   `access_distances.npy` (in which case `select_approach_pairs.py`'s top-k per
   `(hut_id, start_type)` faithfully selects them for remote huts with no nearby trailhead), or
2. whether the cap is applied in the distance pass and lost only in the geometry pass.

The fix is presumably one bounded Dijkstra parameter, but the *design* question underneath is
whether a hut whose nearest trailhead is 60 km away should get a truncated approach set or none —
`build_approach_table.py`'s "maxApproachTime is NOT reintroduced" note says the client filters by
`maxLegTime`, which argues for dropping over-cap rows at the pipeline layer rather than shipping
them for the client to hide.

Found while measuring baselines for the data-quality monitoring layer
(`docs/superpowers/specs/2026-09-02-data-quality-monitoring-design.md` §4.3.3, which turns this
into a standing check).
