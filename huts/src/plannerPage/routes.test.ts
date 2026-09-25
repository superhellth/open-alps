import { describe, it, expect } from 'vitest'
import { legLayer, straightRoute, tourToRoute, tripToRoute } from './routes.js'
import type { RouteContext } from './routes.js'
import type { PlannerTour } from './tours.js'
import { legsFromTrip } from '../tourSearch/tripLegs.js'
import { makeTripGraph } from '@/testing/tripTestGraph.js'
import { newTrip } from '../trip/trip.js'

const ctx: RouteContext = {
  hutCoordsById: new Map([[0, { lat: 47.1, lng: 11.1 }], [1, { lat: 47.2, lng: 11.2 }]]),
  startById: new Map([[100, { name: 'S', sourceType: 1, lat: 47.0, lng: 11.0 }]]),
  officialById: new Map(),
}
const chain = (over: Partial<PlannerTour> = {}): PlannerTour => ({
  huts: [0, 1], startId: 100, exitStartId: 100, totalDurationH: 1, totalAscentM: 0, totalDescentM: 0, totalDistanceM: 0,
  legs: [0, 1, 2].map((edgeId) => ({ durationH: 1, ascentM: 0, descentM: 0, distanceM: 0, edgeId, reversed: false })), ...over,
})

describe('legLayer', () => {
  it('uses start_edges for approach and exit, hut_edges between', () => {
    expect([0, 1, 2].map((i) => legLayer(i, 3))).toEqual(['start_edges', 'hut_edges', 'start_edges'])
  })
})

describe('tourToRoute', () => {
  it('builds start, huts, exit waypoints and per-leg layers for a search chain', () => {
    const r = tourToRoute(chain(), ctx)!
    expect(r.waypoints).toHaveLength(4)
    expect(r.legs.map((l) => l.layer)).toEqual(['start_edges', 'hut_edges', 'start_edges'])
  })
  it('uses the tour-edge layer for an official tour', () => {
    const view = { tourId: 9, legs: [] } as never
    const r = tourToRoute(chain({ official: { tourId: 9, name: 'x' } }), { ...ctx, officialById: new Map([[9, view]]) })!
    expect(r.legs.every((l) => l.layer === 'tour_edges')).toBe(true)
  })
  it('is null when a waypoint cannot be placed', () => {
    expect(tourToRoute(chain({ huts: [0, 99] }), ctx)).toBeNull()
  })
})

describe('straightRoute', () => {
  it('marks every leg as having no geometry so only straight lines draw', () => {
    const r = straightRoute([{ lat: 1, lng: 1 }, { lat: 2, lng: 2 }, { lat: 3, lng: 3 }])
    expect(r.legs.map((l) => l.edgeId)).toEqual([-1, -1])
  })
})

describe('tripToRoute', () => {
  const graph = makeTripGraph()
  const trip = newTrip({
    name: 't', startDate: null, partySize: 1, start: { startId: 100, sourceType: 1 }, huts: ['{A}', '{B}'],
    exit: { startId: 100, sourceType: 1 }, variant: { sacCeiling: null, allowUngraded: false },
  }, new Date(), 'id')
  it('derives leg geometry references from the resolved trip legs; a missing leg gets edgeId -1', () => {
    const legs = legsFromTrip(graph, trip) // B has no exit -> exit leg is missing
    const r = tripToRoute(trip, legs, ctx)!
    expect(r.waypoints).toHaveLength(4)
    expect(r.legs.map((l) => l.edgeId >= 0)).toEqual([true, true, false])
  })
})
