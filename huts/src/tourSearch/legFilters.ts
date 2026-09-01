import type { KillCounters, LegBase } from './types.js'

export interface LegConstraints {
  maxLegTimeH: number
  minLegTimeH: number
  legAscentCapM: number
  maxEleM: number | null
  allowViaFerrata: boolean
}

export function createKillCounters(): KillCounters {
  return {
    maxLegTime: 0, minLegTime: 0, legAscentCap: 0, maxEleM: 0, viaFerrata: 0, revisit: 0,
    hutFiltered: 0, trackOverlap: 0, availability: 0,
  }
}

/** No maxApproachTime: this predicate is applied identically to hut-hut, approach, and exit
 *  legs (root CLAUDE.md Global Constraints; spec Part 4). */
export function legPasses(leg: LegBase, constraints: LegConstraints, killCounters: KillCounters): boolean {
  const { maxLegTimeH, minLegTimeH, legAscentCapM, maxEleM, allowViaFerrata } = constraints

  if (leg.durationH > maxLegTimeH) { killCounters.maxLegTime++; return false }
  if (leg.durationH < minLegTimeH) { killCounters.minLegTime++; return false }
  if (leg.ascentM > legAscentCapM) { killCounters.legAscentCap++; return false }
  if (maxEleM != null && leg.maxEleM != null && leg.maxEleM > maxEleM) { killCounters.maxEleM++; return false }
  if (!allowViaFerrata && leg.viaFerrata) { killCounters.viaFerrata++; return false }
  return true
}
