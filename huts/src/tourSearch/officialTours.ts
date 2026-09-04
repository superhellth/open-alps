import { dinDurationH } from './dinDuration.js'
import type { RawTour, TourEndpointType } from './loadOfficialTours.js'
import type { TourEdgeRecord } from './loadTourEdges.js'

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
  sacRank: number
  viaFerrata: boolean
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

export function buildOfficialTourViews(
  tours: RawTour[],
  tourEdgeRecords: Map<string, TourEdgeRecord>,
): OfficialTourView[] {
  const views: OfficialTourView[] = []

  for (const tour of tours) {
    const legs: OfficialTourLeg[] = []
    let complete = true

    for (const leg of tour.legs) {
      const record = tourEdgeRecords.get(`${tour.tourId}:${leg.legIndex}`)
      if (!leg.from || !leg.to || !record) {
        complete = false
        break
      }
      legs.push({
        legIndex: leg.legIndex, from: leg.from, to: leg.to, edgeId: record.edgeId, reversed: false,
        distanceM: record.distanceM, ascentM: record.ascentM, descentM: record.descentM,
        durationH: dinDurationH(record.distanceM, record.ascentM, record.descentM),
        maxEleM: record.maxEleM, sacRank: record.sacRank, viaFerrata: record.viaFerrata,
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
