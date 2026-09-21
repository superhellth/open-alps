import { rankFit } from '../tourSearch/rankFit.js'
import type { NightState, RankTargets } from '../tourSearch/rankFit.js'
import { SOURCE_TYPE_PARKING, SOURCE_TYPE_PARTNER, SOURCE_TYPE_STATION } from '../tourSearch/types.js'
import type { FreeByOffset } from '../availability/types.js'
import type { FormState } from './formState.js'
import type { PlannerTour } from './tours.js'
import type { StartPoint } from './types.js'

export type SortKey = 'fit' | 'duration' | 'ascent' | 'distance'

export const SORT_LABEL: Record<SortKey, string> = {
  fit: 'Passend zu meinen Wünschen',
  duration: 'Gesamtdauer',
  ascent: 'Anstieg',
  distance: 'Distanz',
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

const MODE_SOURCE_TYPE = { transit: SOURCE_TYPE_STATION, car: SOURCE_TYPE_PARKING, village: SOURCE_TYPE_PARTNER } as const

/** Official tours join the search results under the same hard limits the engine applies. */
export function filterOfficial(tours: PlannerTour[], form: FormState, startById: Map<number, StartPoint>): PlannerTour[] {
  const [minLegs, maxLegs] = form.legCountRange
  return tours.filter((t) =>
    t.legs.length >= minLegs && t.legs.length <= maxLegs
    && t.legs.every((l) => l.durationH <= form.legTimeRange[1])
    && startById.get(t.startId)?.sourceType === MODE_SOURCE_TYPE[form.mode])
}

export function sortTours(
  tours: PlannerTour[], key: SortKey,
  { targets, ohrsIdByHutIndex, freeByOffset }: { targets: RankTargets; ohrsIdByHutIndex: Map<number, string | null>; freeByOffset: FreeByOffset | null },
): PlannerTour[] {
  if (key === 'fit') {
    return rankFit(tours, targets, freeByOffset ? (t, night) => nightStateOf(t, night, ohrsIdByHutIndex, freeByOffset) : undefined)
  }
  return [...tours].sort((a, b) => TOTAL[key](a) - TOTAL[key](b))
}
