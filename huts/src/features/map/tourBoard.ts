import { formatDistanceKm } from '@/format/distance.js'
import { formatSignpostTime } from '@/format/signpostTime.js'
import { makeStartLabel } from '@/data/labels.js'
import type { PlannerTour } from '@/tourSearch/plannerTour.js'
import type { StartPoint } from '@/data/types.js'

export const ROUND_TRIP_LABEL = 'Rundtour'

export interface TourBoardLabel {
  /** Total distance. */
  text: string
  /** Total ascent. */
  detail: string
  /** The tour ends where it starts; its board shows a loop icon. */
  roundTrip: boolean
  /** Route (start and exit, or "Rundtour ab" start) plus all stats, for the board's `title` attribute. */
  title: string
}

export function tourBoardLabel(tour: PlannerTour, startById: Map<number, StartPoint>): TourBoardLabel {
  const startLabel = makeStartLabel(startById)
  const roundTrip = tour.exitStartId === tour.startId
  const time = formatSignpostTime(tour.totalDurationH)
  const distance = formatDistanceKm(tour.totalDistanceM)
  const detail = `↑ ${Math.round(tour.totalAscentM).toLocaleString('de-DE')} m`
  const route = roundTrip
    ? `${ROUND_TRIP_LABEL} ab ${startLabel(tour.startId)}`
    : `${startLabel(tour.startId)} → ${startLabel(tour.exitStartId)}`
  return {
    text: distance,
    detail,
    roundTrip,
    title: `${route} · ${distance} · ${detail} · ${time}`,
  }
}
