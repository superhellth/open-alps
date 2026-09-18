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
  const views: OfficialTourView[] = []

  for (const tour of tours) {
    if (tour.legs.length !== tour.numDays) continue
    const legs: OfficialTourLeg[] = []
    let complete = true

    for (const leg of tour.legs) {
      if (
        !leg.from || !leg.to || leg.edgeId == null ||
        leg.distanceM == null || leg.ascentM == null || leg.descentM == null ||
        leg.durationS == null || leg.maxEleM == null
      ) {
        complete = false
        break
      }
      legs.push({
        legIndex: leg.legIndex, from: leg.from, to: leg.to, edgeId: leg.edgeId, reversed: false,
        distanceM: leg.distanceM, ascentM: leg.ascentM, descentM: leg.descentM,
        durationH: leg.durationS / 3600, maxEleM: leg.maxEleM,
      })
    }

    if (!complete) continue

    views.push({
      tourId: tour.tourId, name: tour.name, legs,
      totalDistanceM: legs.reduce((s, l) => s + l.distanceM, 0),
      totalAscentM: legs.reduce((s, l) => s + l.ascentM, 0),
      totalDescentM: legs.reduce((s, l) => s + l.descentM, 0),
      totalDurationH: legs.reduce((s, l) => s + l.durationH, 0),
    })
  }

  return views
}
