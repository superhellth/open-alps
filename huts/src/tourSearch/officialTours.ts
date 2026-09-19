import type { RawTour, TourEndpointType } from './loadOfficialTours.js'

export interface OfficialTourLeg {
  legIndex: number
  from: { type: TourEndpointType; id: number }
  to: { type: TourEndpointType; id: number }
  edgeId: number
  reversed: false
  distanceM: number
  ascentM: number
  descentM: number
  durationH: number
  maxEleM: number
}

export interface OfficialTourView {
  tourId: number
  name: string
  legs: OfficialTourLeg[]
  totalDistanceM: number
  totalAscentM: number
  totalDescentM: number
  totalDurationH: number
}

export function buildOfficialTourViews(tours: RawTour[]): OfficialTourView[] {
  return tours.map((tour) => {
    const legs: OfficialTourLeg[] = tour.legs.map((leg) => ({
      legIndex: leg.legIndex, from: leg.from, to: leg.to, edgeId: leg.edgeId, reversed: false,
      distanceM: leg.distanceM, ascentM: leg.ascentM, descentM: leg.descentM,
      durationH: leg.durationS / 3600, maxEleM: leg.maxEleM,
    }))
    return {
      tourId: tour.tourId, name: tour.name, legs,
      totalDistanceM: legs.reduce((s, l) => s + l.distanceM, 0),
      totalAscentM: legs.reduce((s, l) => s + l.ascentM, 0),
      totalDescentM: legs.reduce((s, l) => s + l.descentM, 0),
      totalDurationH: legs.reduce((s, l) => s + l.durationH, 0),
    }
  })
}
