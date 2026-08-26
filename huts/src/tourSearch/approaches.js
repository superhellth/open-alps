import { forwardStartLeg, reverseStartLeg } from './reverseLeg.js'

/** The curated k-best-per-hut table, FAST_ANY only (docs/tour-suggestion-payload.md §6):
 *  "an approach is a fastest, unconstrained leg to the hub, not a difficulty-graded one." */
export function getApproachLegs(hutIndex, approachesData) {
  return approachesData.records
    .filter((r) => r.hutIndex === hutIndex)
    .map((r) => forwardStartLeg(r))
}

/** Exits are the (all-variant) loop-closure reverse index, read backwards — a separate
 *  structure from the approach table on purpose (spec Part 4: "nothing extra is stored"). */
export function getExitLegs(hutIndex, variant, approachesData) {
  const entries = approachesData.reverseIndex.hut_to_starts[String(hutIndex)] || []
  return entries
    .filter((r) => r.variant === variant)
    .map((r) => reverseStartLeg({
      startId: r.start_id,
      sourceType: r.source_type,
      distanceM: r.distance_m,
      ascentM: r.ascent_m,
      descentM: r.descent_m,
    }))
}
