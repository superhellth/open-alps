# Base-graph time_s has a nonsense tail (up to 94,000 years for one edge)

**Priority:** Medium

`compute_edge_profiles.py` fills `base_graph/edges.npy`'s `time_s` from `lib/speed.py`'s pointwise
Tobler model. The bulk is healthy — implied speed (`dist / time_s`) over 4,730,712 edges is
p0.1 = 0.17, p50 = 0.92, p99 = 1.09, p99.9 = 1.11 m/s, exactly the walking band the model is
calibrated for. The tail is not:

| | count |
| --- | --- |
| edges below 0.05 m/s (~180 m/h) | 1,011 |
| edges below 0.01 m/s | 346 |
| `time_s` over 24 h | 184 |
| `time_s` over one year | 20 |

Worst rows:

```
edge_id=4505826  dist=1,411.8 m  time_s=2.954e+12  ascent=344.7 m  sac_rank=4
edge_id=1729957  dist=1,308.3 m  time_s=3.474e+10  ascent=659.1 m  sac_rank=6  via_ferrata
edge_id=2570179  dist=  118.0 m  time_s=3.143e+10  ascent=  0.0 m  sac_rank=1
```

2.954 × 10¹² s is roughly 94,000 years for a 1.4 km edge with 345 m of ascent. There are no zero or
negative `time_s` values and no NaN, so this is not an unset-sentinel problem — the model is
returning these numbers.

The third row is the informative one: **118 m, zero ascent, `sac_rank` 1** — an easy, flat, short
edge. Whatever produces the blow-up is therefore not "steep terrain makes Tobler slow"; it is more
likely a degenerate slope from a bad elevation delta over a very short horizontal distance
(`lib/speed.py`'s pointwise integration dividing by a near-zero segment length), which the two
long/steep rows would also hit at their steepest sample.

## Why it matters

Low priority on routing correctness — the router minimises time, so these edges are effectively
barriers and never get chosen, which is why they have gone unnoticed. It matters for three other
reasons:

1. `time_s` is the ranking key `select_approach_pairs.py` uses (spec B4 chose it precisely because
   it is "free from the Dijkstra"), so a poisoned value silently reorders selection.
2. These edges are *silently* impassable. An edge that should be a normal 20-minute walk becoming a
   barrier can disconnect huts, and §4.3.2 of the monitoring spec already measures large
   disconnected pockets per variant (FAST_T2: 46 components, 429 isolated huts) with no explanation
   attached to them yet. Worth checking whether these overlap.
3. `time_s` is unusable as a diagnostic while the tail exists.

Fix is presumably a floor on the per-sample slope or a clamp on the resulting pointwise speed in
`lib/speed.py`, plus a guard against near-zero segment lengths. Both `analysis/routing_probe.py`
(the DIN-33466 calibration harness) and `test_speed.py` exist to check that a clamp does not move
the calibrated band.

Found while measuring baselines for the data-quality monitoring layer
(`docs/superpowers/specs/2026-09-02-data-quality-monitoring-design.md` §4.2.3, which turns implied
speed into a standing check).
