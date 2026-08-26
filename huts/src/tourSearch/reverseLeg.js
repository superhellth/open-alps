import { dinDurationH } from './dinDuration.js'

function withDuration(leg) {
  return { ...leg, durationH: dinDurationH(leg.distanceM, leg.ascentM, leg.descentM) }
}

/** Reverse-traversal contract (docs/tour-suggestion-payload.md §3): distance/road/sacRank/
 *  viaFerrata/maxEle/ungraded/inferred unchanged; ascent<->descent swapped; duration recomputed. */
export function reverseHutLeg(record) {
  return withDuration({
    ...record,
    fromIndex: record.toIndex,
    toIndex: record.fromIndex,
    ascentM: record.descentM,
    descentM: record.ascentM,
  })
}

export function forwardHutLeg(record) {
  return withDuration(record)
}

export function reverseStartLeg(record) {
  return withDuration({ ...record, ascentM: record.descentM, descentM: record.ascentM })
}

export function forwardStartLeg(record) {
  return withDuration(record)
}
