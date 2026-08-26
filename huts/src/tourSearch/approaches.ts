import { forwardStartLeg, reverseStartLeg } from './reverseLeg.js'
import type { ApproachesData, StartLeg } from './types.js'

/** The curated k-best-per-hut table, FAST_ANY only (docs/tour-suggestion-payload.md §6):
 *  "an approach is a fastest, unconstrained leg to the hub, not a difficulty-graded one." */
export function getApproachLegs(hutIndex: number, approachesData: ApproachesData): StartLeg[] {
  return approachesData.records
    .filter((r) => r.hutIndex === hutIndex)
    .map((r) => forwardStartLeg(r))
}

/** Exits are the (all-variant) loop-closure reverse index, read backwards — a separate
 *  structure from the approach table on purpose (spec Part 4: "nothing extra is stored"). */
export function getExitLegs(hutIndex: number, variant: number, approachesData: ApproachesData): StartLeg[] {
  const entries = approachesData.reverseIndex.hut_to_starts[String(hutIndex)] || []
  return entries
    .filter((r) => r.variant === variant)
    .map((r) =>
      reverseStartLeg({
        hutIndex,
        startId: r.start_id,
        sourceType: r.source_type,
        accessUnknown: false,
        distanceM: r.distance_m,
        ascentM: r.ascent_m,
        descentM: r.descent_m,
        access: null,
      }),
    )
}
