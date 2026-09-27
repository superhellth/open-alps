import { rankFit } from '@/tourSearch/rankFit.js'
import type { NightState, RankTargets } from '@/tourSearch/rankFit.js'
import type { FreeByOffset } from '@/availability/types.js'
import type { PlannerTour } from '@/tourSearch/plannerTour.js'

export type SortKey = 'fit' | 'duration' | 'ascent' | 'distance'

export const SORT_LABEL: Record<SortKey, string> = {
  fit: 'Empfehlung',
  duration: 'Gesamtdauer',
  distance: 'Distanz',
  ascent: 'Anstieg',
}

const TOTAL: Record<Exclude<SortKey, 'fit'>, (t: PlannerTour) => number> = {
  duration: (t) => t.totalDurationH,
  ascent: (t) => t.totalAscentM,
  distance: (t) => t.totalDistanceM,
}

/** Night n of a tour is read at offset n+1 of the availability fetch (the fetch's base date is one
 *  day before the first night). Missing OHRS id, failed night and no availability are all 'unknown'. */
export function nightStateOf(
  tour: PlannerTour, night: number, ohrsIdByHutIndex: Map<number, string | null>, freeByOffset: FreeByOffset | null,
): NightState {
  const ohrsId = ohrsIdByHutIndex.get(tour.huts[night])
  if (ohrsId == null || !freeByOffset) return 'unknown'
  const free = freeByOffset.get(night + 1)
  if (free === undefined || free === 'unknown') return 'unknown'
  return free.has(ohrsId) ? 'free' : 'full'
}

export type SortDir = 'asc' | 'desc'

export function sortTours(
  tours: PlannerTour[], key: SortKey, dir: SortDir,
  { targets, ohrsIdByHutIndex, freeByOffset }: { targets: RankTargets; ohrsIdByHutIndex: Map<number, string | null>; freeByOffset: FreeByOffset | null },
): PlannerTour[] {
  if (key === 'fit') {
    return rankFit(tours, targets, freeByOffset ? (t, night) => nightStateOf(t, night, ohrsIdByHutIndex, freeByOffset) : undefined)
  }
  const sorted = [...tours].sort((a, b) => TOTAL[key](a) - TOTAL[key](b))
  return dir === 'desc' ? sorted.reverse() : sorted
}
