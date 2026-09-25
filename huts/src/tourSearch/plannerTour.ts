import type { OfficialTourView } from './officialTours.js'
import type { TourResult } from './types.js'

/** A search chain or an official tour, in the one shape lists, ranking and the map consume. For an
 *  official tour every leg's edgeId indexes the tour-edge layer instead of hut/start edges. */
export type PlannerTour = TourResult & { official?: { tourId: number; name: string } }

export function officialToTour(view: OfficialTourView): PlannerTour | null {
  const first = view.legs[0]
  const last = view.legs[view.legs.length - 1]
  if (!first || first.from.type === 'hut' || last.to.type === 'hut') return null
  return {
    huts: view.legs.slice(0, -1).map((l) => l.to.id),
    startId: first.from.id,
    exitStartId: last.to.id,
    totalDurationH: view.totalDurationH,
    totalAscentM: view.totalAscentM,
    totalDescentM: view.totalDescentM,
    totalDistanceM: view.totalDistanceM,
    legs: view.legs.map((l) => ({
      durationH: l.durationH, ascentM: l.ascentM, descentM: l.descentM, distanceM: l.distanceM,
      edgeId: l.edgeId, reversed: l.reversed,
    })),
    official: { tourId: view.tourId, name: view.name },
  }
}
