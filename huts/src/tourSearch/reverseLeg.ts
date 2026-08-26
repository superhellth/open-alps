import { dinDurationH } from './dinDuration.js'
import type { ApproachRecord, HutEdgeRecord, HutLeg, StartLeg } from './types.js'

function withDuration<T extends { distanceM: number; ascentM: number; descentM: number }>(
  leg: T,
): T & { durationH: number } {
  return { ...leg, durationH: dinDurationH(leg.distanceM, leg.ascentM, leg.descentM) }
}

/** Reverse-traversal contract (docs/tour-suggestion-payload.md §3): distance/road/sacRank/
 *  viaFerrata/maxEle/ungraded/inferred unchanged; ascent<->descent swapped; duration recomputed. */
export function reverseHutLeg(record: HutEdgeRecord): HutLeg {
  return withDuration({
    ...record,
    fromIndex: record.toIndex,
    toIndex: record.fromIndex,
    ascentM: record.descentM,
    descentM: record.ascentM,
  })
}

export function forwardHutLeg(record: HutEdgeRecord): HutLeg {
  return withDuration(record)
}

export function reverseStartLeg(record: ApproachRecord): StartLeg {
  return withDuration({ ...record, ascentM: record.descentM, descentM: record.ascentM })
}

export function forwardStartLeg(record: ApproachRecord): StartLeg {
  return withDuration(record)
}
