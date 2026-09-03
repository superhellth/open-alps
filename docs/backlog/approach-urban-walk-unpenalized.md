# Approach selection doesn't penalize long walks through urban/street terrain

**Priority:** Medium

Approach-candidate selection (`select_approaches`,
`pipeline/phases/postprocessing/build_approach_table.py:84-106`) ranks purely by DIN duration —
there is no signal anywhere that distinguishes "2h on a real trail from a valley trailhead" from
"2h of which 1.5h is walking through town streets from a bus station before the trail even
starts." Both get ranked and shipped identically if their total duration matches.

This isn't an oversight that's partially handled elsewhere — it's unhandled at every layer:

- `pipeline.config.json`'s `trailTagFilter` deliberately includes `residential,service,
  unclassified,tertiary` highway tags across the whole Austria+Bavaria extract, so trail-snap
  distance alone can't exclude urban parking/stations. The comment in
  `filter_start_points.py:5-8` acknowledges this directly.
- `is_usable()` (`filter_start_points.py:37-50`) only hard-drops `access=private/no`,
  `motor_vehicle` restrictions, gate barriers, and disused/abandoned tags — nothing keyed on
  surface or highway classification.
- The binary approach/start-edge records carry only `distance_m`/`ascent_m`/`descent_m`/
  `source_type`/`access` — no per-segment tag breakdown survives into the shipped data, so even a
  post-hoc client-side penalty has nothing to work with today.
- No mention in `docs/alpenverein-api.md` or `docs/tour-suggestion-payload.md`.

Fixing this needs a pipeline-side signal (e.g. per-edge fraction of distance/time spent on
`residential`/`service`/`unclassified`/`tertiary`/`footway`-in-town tags vs. genuine trail tags,
computed during hub/start-edge building and either used to re-rank candidates or shipped so the
client can penalize/flag it) — a client-side workaround isn't possible since the tag detail
doesn't exist past the pipeline stage that already discarded it.

Raised while discussing the [approach table reserved-slot bug](approach-reserved-type-slot-overwrite.md):
not the same root cause (that bug is about slot-selection mechanics; this is about candidate
*quality*), so filed separately per the "fix problems at their root layer" rule.
