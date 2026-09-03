# Steep-Terrain Time Model — Design

**Problem:** `quality.elevation.implied_speed` (`docs/superpowers/specs/
2026-09-02-data-quality-monitoring-design.md` §4.2.3) flags 1,011 of 4,730,712 base-graph edges
where `dist_m / time_s` implies a walking speed under 0.05 m/s — some as low as 1e-10 m/s, i.e.
`time_s` in the billions/trillions of seconds for a few hundred metres of trail. This is not bad
elevation data (investigated live against `data/quality/elevation.json` — see the session this
spec came out of): every sample is finite and in-range, `unresolved_sentinels` and
`profile_integrity_*` are clean. The defect is in how `phases/elevation/compute_edge_profiles.py`
turns a real elevation profile into a time cost when a segment is short and steep.

**Evidence, not guesswork** — every number below came from re-deriving each flagged edge's own
point sequence (`node_ele.npy`/`interior_ele.npy`/`edges.npy`) and rerunning
`compute_edge_profiles.py`'s own functions against it, read-only, no pipeline task rerun:

- **It's concentrated on genuinely technical terrain, not random noise.** Flag rate by
  `sac_rank` (excluding `via_ferrata`): T1 0.0023%, T2 0.12%, T3 0.75%, T4 2.50%, T5 4.84%, T6
  14.9% — a ~6,500x gradient tracking difficulty. `via_ferrata` edges flag at 30.2% (389/1,287)
  vs. 0.013% for everything else — a ~1,400x enrichment. Random DEM noise unrelated to terrain
  would flag a roughly constant fraction regardless of grade; it doesn't.
- **The non-via_ferrata flagged edges (622) are mostly real short steep features, not sensor
  noise.** Checked whether the anomalous segment's elevation reverses right after (the signature
  of one bad DEM pixel — spike up, then back down) vs. continues in the same direction (a real
  short pitch): 462/480 sampled (96%) continue in the same direction. Example: edge 105338 (T1,
  "easy" trail) is 3 points over 24.4 m, dropping 33 m in the last 22 m segment — a real staircase
  or rock step, not noise.
- **This isn't confined to the unrestricted routing variant.** `lib/variants.py`'s `FAST_T2`/
  `FAST_T3` require `constrained_ok` and cap `sac_rank`, but that doesn't exclude a short steep
  pitch on an otherwise-easy trail: 163 flagged edges pass into `FAST_T2` (max sac_rank 2), 213
  into `FAST_T3`. A user who explicitly asks for "easy terrain only" can still get a leg whose
  time estimate is nonsense. (`via_ferrata` edges, by contrast, are unconditionally excluded from
  every variant except `FAST_ANY` — `variants.py:54` — so that failure mode is already confined to
  the one variant that promises no restrictions.)
- **A wider smoothing/aggregation window helps but doesn't close the gap.** Simulated merging
  consecutive profile segments up to a minimum horizontal run before computing slope, at several
  window sizes, re-running the exact `edge_time_s` computation:

  | window | non-via_ferrata still flagged | via_ferrata still flagged |
  | --- | --- | --- |
  | 30 m (current kernel width) | 280 / 622 | 250 / 389 |
  | 50 m | 209 / 622 | 201 / 389 |
  | 100 m | 174 / 622 | 148 / 389 |

  Real sustained steep terrain (a genuine 50-100m+ climb, not a digitization artifact) remains
  under any window — this needs a different time model, not just a wider one.
- **A terrain-tier pace model, applied on top of aggregation, closes the via_ferrata gap
  completely.** Replacing the Tobler walking formula with a constant pace over 3D distance
  (`hypot(horizontal_m, |dz_m|)`) for `via_ferrata` segments: even at a conservative 0.15 m/s,
  **0/389 via_ferrata edges remain flagged** (tested up to 0.5 m/s, same result). This confirms
  the fix is choosing the right model for climbing terrain, not merely widening the window.

**Goal:** No base-graph edge should ever imply a walking speed a human could not plausibly
sustain, whether that's from a digitization artifact on an easy trail or from applying a walking
formula to climbing terrain. Every edge stays in the graph — via_ferrata and T4-T6 routes remain
real, plannable connections users can select via `FAST_ANY`; this spec fixes what their cost
*means*, not whether they exist.

**Non-goals:**
- **Frontend disclaimer** for legs touching via_ferrata/high-SAC terrain — filed as a low-priority
  backlog item (`backlog/steep-terrain-time-disclaimer.md`), not part of this spec. `sac_rank`/
  `via_ferrata` already flow through the edge payload (`docs/tour-suggestion-payload.md`), so no
  data-contract change is needed for that follow-up.
- **Precise calibration of the technical-terrain pace constant.** No DIN-33466-equivalent ground
  truth exists for via ferrata the way `analysis/routing_probe.py` calibrated the walking model.
  §2's constant is a literature-informed starting point, explicitly not final.
- **Dropping any edge.** Investigated and rejected — see Evidence above; both the T1-T3 and
  via_ferrata populations are predominantly real terrain, not corrupt data.

## 1. Segment aggregation (compute_edge_profiles.py)

`_fill_edge_time_and_elevation` currently computes `time_s` from `speed.edge_time_s(seg_len,
np.diff(smoothed), ...)` at the raw per-point segment granularity — `smooth_profile` averages
*elevation values* over a distance-weighted kernel, but the *segment lengths* used to derive slope
stay at whatever spacing the OSM way happened to be digitized at (p25 19.7 m per
`pipeline/CLAUDE.md`). A real staircase digitized as two points 20 m apart produces one segment
whose slope is computed as if the whole 20 m were that steep.

Fix: before computing `edge_time_s`, merge consecutive `(seg_len, dz)` pairs from the smoothed
profile until each merged segment's horizontal run is at least a new config value,
`dem.minSlopeSegmentM` (default 30, matching `dem.smoothingKernelM` — same underlying concern,
kept as a separate knob because they act on different things: one smooths elevation *values*, the
other bounds the horizontal *run* slope is computed over). `ascent_m`/`descent_m` keep using the
existing fine-grained `edge_ascent_descent` — merging would understate real elevation gain/loss on
a genuine staircase, which is a different, correct number from the time cost of walking it.

`edge_time_s` is still called once per merged segment and summed, so the additive property noted
in `lib/speed.py`'s module docstring is preserved — this is a change to segment *granularity*
going in, not a change to the summation.

## 2. Terrain-tier pace for via_ferrata / T5-T6

`lib.speed.edge_time_s`'s Tobler model is calibrated for walking (`analysis/routing_probe.py`
against DIN 33466) and is the wrong model once a segment is `via_ferrata` or `sac_rank >= 5` —
that's climbing/scrambling, not walking, and the pace isn't primarily a function of horizontal
slope the way Tobler assumes.

Fix: a new function alongside `edge_time_s` in `lib/speed.py`, used for any *aggregated* segment
(post-§1) whose source edge is `via_ferrata` or has `sac_rank >= 5`:

```python
def technical_time_s(dist_m, dz_m, *, pace_ms: float):
    """Constant pace over 3D distance - via ferrata / T5-T6 terrain isn't walking, and its pace
    isn't primarily a function of horizontal slope the way Tobler assumes."""
    return np.hypot(dist_m, dz_m) / pace_ms
```

`pace_ms` is a new `graph.speedModel.technicalPaceMs` config value. Starting point: 0.2 m/s
(≈720 vertical m/h if fully vertical, inside the range guidebooks give for average-party via
ferrata ascent) — explicitly a first estimate (see Non-goals), exposed as config so it can be
retuned without a code change once real data exists.

`compute_edge_profiles.py`'s per-edge loop picks `technical_time_s` vs. `edge_time_s` per edge
based on that edge's own `via_ferrata`/`sac_rank` columns (already read from `edges.npy` — no new
input needed).

## 3. Hard floor (backstop)

Even after §1 and §2, a residual remains — real sustained steep terrain on ordinary (non-via
ferrata, `sac_rank < 5`) trails that doesn't get the technical pace model and can still exceed any
reasonable aggregation window (measured: 93 T1-T3 and 70 ungraded edges still flagged at a 50 m
window). Rather than chase this with an ever-wider window or an ever-more-specific tag rule, clamp
the final per-edge `time_s` so implied speed can never drop below a configurable
`graph.speedModel.minSpeedMs` (default 0.15 m/s — chosen below the technical pace constant so it
never binds ahead of §2's model on terrain that already has a dedicated pace, and above the quality
check's own 0.05 m/s threshold with margin). This is a safety net: after §1/§2, most edges should
never reach it. It also protects against terrain this spec's evidence didn't anticipate (mistagged
`sac_rank`, future OSM edits, additional regions).

Implementation: applied once, after `time_s` is computed by whichever of §1/§2's paths ran, as
`time_s = min(time_s, dist_m / min_speed_ms)` — guards against `time_s == 0` the same way
`edge_time_s` already does (`dist_m > 0` guard in `lib/speed.py`).

## Config additions (`pipeline.config.json`)

```jsonc
"dem": {
  // ... existing keys ...
  "minSlopeSegmentM": 30
},
"graph": {
  "speedModel": {
    // ... existing v0/k/s0 ...
    "technicalPaceMs": 0.2,
    "minSpeedMs": 0.15
  }
}
```

All three are `cli_param`s on `task_compute_edge_profiles` (same pattern as the existing
`--speed-v0`/`--speed-k`/`--speed-s0` args — declared as CLI args, not read from config directly,
so `dodo.py`'s `TaskOptionsChanged` tracks them and a config-only edit invalidates the task's
cache).

## Testing

- Unit tests for `merge_segments` (§1): segments below the window merge, a final under-window
  remainder is kept (not dropped), zero-length input handled.
- Unit tests for `technical_time_s` (§2): matches `hypot(dist, dz) / pace` exactly; symmetric in
  the sign of `dz` (climbing and descending a via ferrata pitch take the same time — walking's
  Tobler model is deliberately asymmetric, this model is not, since 3D distance is unsigned).
- Unit test for the floor (§3): an edge whose computed `time_s` implies < `minSpeedMs` gets
  clamped to exactly `dist_m / minSpeedMs`; an edge already above the floor is untouched.
- **Acceptance test is `data/quality/elevation.json`'s existing `implied_speed` check** — no new
  check needed. After this lands, rerun `check_elevation` and confirm `summary.flagged` collapses
  from 1,011 toward the small residual §3 is expected to still catch (formerly-flagged edges
  landing exactly on `minSpeedMs` are the correctly-clamped case, not a regression) — update
  `summary.baseline` for `implied_speed` to the new measured count once the rerun is done (spec
  2026-09-02's §2: baseline is "the count measured last time," meant to be updated when a check's
  count moves for an intentional reason, not silently drift).

## Backlog items filed

- `backlog/steep-terrain-time-disclaimer.md` (low priority) — frontend "technical terrain, time
  estimate approximate" warning on legs where `via_ferrata` or `sac_rank >= 5`, once this spec's
  data is trustworthy. No pipeline/data-contract change needed; `sac_rank`/`via_ferrata` are
  already in the edge payload.
