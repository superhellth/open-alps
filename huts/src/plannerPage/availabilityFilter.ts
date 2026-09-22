import type { FreeByOffset } from '../availability/types.js'
import type { PlannerTour } from './tours.js'

/** Direct-booking huts (no OHRS id) and a failed/unfetched offset both count as available — only a
 *  confirmed "no free beds" makes a night full. */
export function tourHasFullNight(
  tour: PlannerTour, ohrsIdByHutIndex: Map<number, string | null>, freeByOffset: FreeByOffset,
): boolean {
  for (let night = 0; night < tour.huts.length; night++) {
    const ohrsId = ohrsIdByHutIndex.get(tour.huts[night])
    if (ohrsId == null) continue
    const free = freeByOffset.get(night + 1)
    if (free === undefined || free === 'unknown') continue
    if (!free.has(ohrsId)) return true
  }
  return false
}

/** The "Verfügbarkeit prüfen" filter: applied client-side to an already-searched tour list, so
 *  toggling "auch volle Touren zeigen" never re-runs the whole-graph search. */
export function filterByAvailability(
  tours: PlannerTour[], enabled: boolean, showFullToo: boolean,
  ohrsIdByHutIndex: Map<number, string | null>, freeByOffset: FreeByOffset | null,
): PlannerTour[] {
  if (!enabled || !freeByOffset || showFullToo) return tours
  return tours.filter((t) => !tourHasFullNight(t, ohrsIdByHutIndex, freeByOffset))
}
