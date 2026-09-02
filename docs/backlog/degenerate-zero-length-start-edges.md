# 82,017 degenerate near-zero-length start_edges rows (surfaced as max_ele_m == 0)

**Priority:** Medium

`RECORD_DTYPE`'s `max_ele_m` is `0.0` on 82,017 of 471,196 `start_edges` rows (17.4%) and 24 of
8,238 `hut_edges` rows on the 2026-09-02 run. Zero is not a possible maximum elevation in this bbox
— the lowest node in the sampled DEM is 120.0 m (`base_graph/node_ele.npy`: 120.0–3793.5;
`interior_ele.npy`: 119.7–3759.0).

**It is not corruption of real legs.** Every affected row is degenerate:

| | `start_edges` (82,017 rows) | `hut_edges` (24 rows) |
| --- | --- | --- |
| `distance_m` | min 0.6, median **30**, max 166 | min 26, median 39, max 76 |
| `geom_count` | 2–3 points | 2 points |
| `ascent_m` | median 1 m, max 32 m | median 3 m, max 6 m |

These are hub pairs that snap onto the same (or an adjacent) base-graph node, so
`lib/cell_igraph.py`'s `accumulate_path` takes its `src_v == tgt_v` branch and returns
`PathResult([], 0.0, …)` — `max_ele_m` included. `build_access_edges.py:128` and
`build_hub_edges.py:273` then write `float(path.max_ele_m) if np.isfinite(...) else 0.0`, so the
unset value lands in the column as sea level.

## The two separable problems

1. **The sentinel.** `0.0` is indistinguishable from a real measurement in a column whose stated
   purpose is "the client never scans a profile to apply an altitude cap" (`binfmt.py`'s
   `RECORD_DTYPE` comment). A row carrying `0` passes every "stays below N metres" filter — it
   fails open. If a zero-length path genuinely has no maximum elevation, the sentinel should be
   something the client cannot mistake for a measurement (`NaN`, or the endpoint node's elevation,
   which is both finite and correct for a zero-length path).
2. **The rows themselves.** A 0.6 m "approach leg" from a station to a hut is not a leg; it means
   the access point and the hut resolved to the same snap. 82,017 of them ship inside
   `start_edges` → `build_approach_table.py`'s loop-closure reverse index, and they inflate
   `start-edge-geometry.bin` and `start-edges.pmtiles`. Whether they should be emitted at all (a
   minimum-length floor in `build_access_edges.py`) or just carry an honest `max_ele_m` is the
   design call.

Note the variant split on the `start_edges` rows — FAST_T2 39,095 / FAST_T3 30,710 /
FAST_T3_UNGRADED 12,197 but FAST_ANY only 15 — so this is overwhelmingly the constrained variants,
where the masked subgraph leaves the pair with no usable path and the snap-coincident fallback is
all that remains.

Found while measuring baselines for the data-quality monitoring layer
(`docs/superpowers/specs/2026-09-02-data-quality-monitoring-design.md` §4.3.6, which turns
`max_ele_m == 0` into a standing check).
