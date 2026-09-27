import type { PlannerTour } from './plannerTour.js'

/** A tour's stable cross-component identity (hover and focus sync between the map and the results list). */
export function tourKey(tour: PlannerTour): string {
  return `${tour.startId}-${tour.exitStartId}-${tour.huts.join('.')}`
}

/** Shared empty set, so "nothing hovered" is one stable value and never triggers a re-render. */
export const NO_TOURS: ReadonlySet<string> = new Set()
