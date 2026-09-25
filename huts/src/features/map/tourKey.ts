import type { PlannerTour } from '@/tourSearch/plannerTour.js'

/** A tour's stable cross-component identity (hover sync between the map and the results list). */
export function tourKey(tour: PlannerTour): string {
  return `${tour.startId}-${tour.official?.tourId ?? ''}-${tour.huts.join('.')}`
}
