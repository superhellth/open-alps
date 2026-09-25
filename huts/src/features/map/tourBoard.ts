import { formatDistanceKm } from '@/format/distance.js'
import { SOURCE_TYPE_LABEL, makeStartLabel } from '@/data/labels.js'
import { SOURCE_TYPE_STATION } from '@/tourSearch/types.js'
import type { PlannerTour } from '@/tourSearch/plannerTour.js'
import type { StartPoint } from '@/data/types.js'

export const ROUND_TRIP_LABEL = 'Rundtour'

export interface TourBoardLabel {
  /** End point name (bare, without a "(Parkplatz)" suffix), the kind label when unnamed, or "Rundtour". */
  text: string
  distance: string
  /** Full end point label plus distance, for the board's `title` attribute. */
  title: string
  /** Kind of the end point, for the board's small symbol. */
  sourceType: number
}

export function tourBoardLabel(tour: PlannerTour, startById: Map<number, StartPoint>): TourBoardLabel {
  const exit = startById.get(tour.exitStartId)
  const sourceType = exit?.sourceType ?? SOURCE_TYPE_STATION
  const kind = SOURCE_TYPE_LABEL[sourceType] ?? 'Startpunkt'
  const roundTrip = tour.exitStartId === tour.startId
  const text = roundTrip ? ROUND_TRIP_LABEL : exit ? exit.name || kind : 'Startpunkt'
  const distance = formatDistanceKm(tour.totalDistanceM)
  return { text, distance, title: `${makeStartLabel(startById)(tour.exitStartId)}, ${distance}`, sourceType }
}
