import { describe, it, expect } from 'vitest'
import { tourAnchorOf, tourToRoute, tripToRoute } from './routes.js'
import type { RouteContext } from './routes.js'
import type { PlannerTour } from '@/tourSearch/plannerTour.js'
import { legsFromTrip } from '@/trip/tripLegs.js'
import { makeTripGraph } from '@/testing/tripTestGraph.js'
import { newTrip } from '@/trip/trip.js'

const ctx: RouteContext = {
  hutCoordsById: new Map([[0, { lat: 47.1, lng: 11.1 }], [1, { lat: 47.2, lng: 11.2 }]]),
  startById: new Map([[100, { name: 'S', sourceType: 1, lat: 47.0, lng: 11.0 }]]),
  hutClassByIndex: new Map([[0, { operator: 'av', serviced: true }]]),
  legAnchors: () => null,
}
const chain = (over: Partial<PlannerTour> = {}): PlannerTour => ({
  huts: [0, 1], startId: 100, exitStartId: 100, totalDurationH: 1, totalAscentM: 0, totalDescentM: 0, totalDistanceM: 0,
  legs: [0, 1, 2].map((edgeId) => ({ durationH: 1, ascentM: 0, descentM: 0, distanceM: 0, edgeId, reversed: false })), ...over,
})

describe('tourToRoute', () => {
  it('builds start, huts, exit waypoints and per-leg layers for a search chain', () => {
    const r = tourToRoute(chain(), ctx)!
    expect(r.waypoints).toHaveLength(4)
    expect(r.legs.map((l) => l.layer)).toEqual(['start_edges', 'hut_edges', 'start_edges'])
  })
  it('tourAnchorOf runs the anchor choice over the route with the tour leg distances', () => {
    const tour = chain()
    const route = tourToRoute({ ...tour, legs: tour.legs.map((l) => ({ ...l, distanceM: 1000 })) }, ctx)!
    const a = tourAnchorOf({ ...tour, legs: tour.legs.map((l) => ({ ...l, distanceM: 1000 })) }, route, ctx, [-180, -90, 180, 90])
    expect(a).not.toBeNull()
  })
  it('is null when a waypoint cannot be placed', () => {
    expect(tourToRoute(chain({ huts: [0, 99] }), ctx)).toBeNull()
  })
})

describe('waypoint stops', () => {
  it('marks huts with their class and end points with their kind', () => {
    const r = tourToRoute(chain(), ctx)!
    expect(r.waypoints[0].stop).toEqual({ type: 'end', startId: 100, sourceType: 1 })
    expect(r.waypoints[1].stop).toEqual({ type: 'hut', hutId: 0, operator: 'av', serviced: true })
    expect(r.waypoints[3].stop).toEqual({ type: 'end', startId: 100, sourceType: 1 })
  })
  it('gives an unclassified hut no stop instead of a guessed one', () => {
    const r = tourToRoute(chain(), ctx)!
    expect(r.waypoints[2]).toEqual({ lat: 47.2, lng: 11.2 })
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
