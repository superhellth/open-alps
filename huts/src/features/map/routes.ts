import { tourAnchor } from '@/tourSearch/tourAnchor.js'
import type { Bbox, TourAnchor } from '@/tourSearch/tourAnchor.js'
import type { LegAnchorLookup } from '@/tourSearch/legAnchors.js'
import type { GeometryLayer } from '@/tourSearch/loadLegGeometry.js'
import type { OfficialTourView } from '@/tourSearch/officialTours.js'
import type { TripLegs } from '@/trip/tripLegs.js'
import type { Trip } from '@/trip/trip.js'
import type { PlannerTour } from '@/tourSearch/plannerTour.js'
import type { Route, RouteWaypoint } from './types.js'
import type { StartPoint } from '@/data/types.js'
import type { HutClass } from '@/data/hutClass.js'

export interface RouteContext {
  hutCoordsById: Map<number, { lat: number; lng: number }>
  startById: Map<number, StartPoint>
  officialById: Map<number, OfficialTourView>
  hutClassByIndex: Map<number, HutClass>
  /** Anchor points of a leg's edge, for placing a tour's signpost on its route. */
  legAnchors: LegAnchorLookup
}

export function legLayer(legIndex: number, legCount: number): GeometryLayer {
  return legIndex === 0 || legIndex === legCount - 1 ? 'start_edges' : 'hut_edges'
}

/** Leg geometry with edgeId -1 is never fetched; the map draws a dashed straight line instead. */
export function straightRoute(waypoints: RouteWaypoint[]): Route {
  return {
    waypoints,
    legs: waypoints.slice(1).map(() => ({ edgeId: -1, reversed: false, layer: 'hut_edges' as const })),
  }
}

function place(id: number, kind: 'hut' | 'start', ctx: RouteContext): RouteWaypoint | null {
  if (kind === 'hut') {
    const p = ctx.hutCoordsById.get(id)
    if (!p) return null
    const cls = ctx.hutClassByIndex.get(id)
    return cls
      ? { lat: p.lat, lng: p.lng, stop: { type: 'hut', hutId: id, operator: cls.operator, serviced: cls.serviced } }
      : { lat: p.lat, lng: p.lng }
  }
  const s = ctx.startById.get(id)
  return s ? { lat: s.lat, lng: s.lng, stop: { type: 'end', startId: id, sourceType: s.sourceType } } : null
}

function waypointsOf(startId: number, huts: number[], exitStartId: number, ctx: RouteContext): RouteWaypoint[] | null {
  const points = [place(startId, 'start', ctx), ...huts.map((h) => place(h, 'hut', ctx)), place(exitStartId, 'start', ctx)]
  return points.every((p): p is RouteWaypoint => p !== null) ? points : null
}

export function tourToRoute(tour: PlannerTour, ctx: RouteContext): Route | null {
  const waypoints = waypointsOf(tour.startId, tour.huts, tour.exitStartId, ctx)
  if (!waypoints) return null
  const official = tour.official !== undefined
  return {
    waypoints,
    legs: tour.legs.map((leg, i) => ({
      edgeId: leg.edgeId, reversed: leg.reversed,
      layer: official ? ('tour_edges' as const) : legLayer(i, tour.legs.length),
    })),
  }
}

/** Where the tour's signpost stands on its route, or null when no anchor of the tour is in `bbox`. */
export function tourAnchorOf(tour: PlannerTour, route: Route, ctx: RouteContext, bbox: Bbox): TourAnchor | null {
  return tourAnchor({
    waypoints: route.waypoints,
    legs: route.legs.map((l, i) => ({ layer: l.layer, edgeId: l.edgeId, reversed: l.reversed, distanceM: tour.legs[i].distanceM })),
  }, ctx.legAnchors, bbox)
}

/** Every waypoint (start, huts, exit) of the given tours; tours that fail to resolve are skipped. */
export function tourWaypoints(tours: PlannerTour[], ctx: RouteContext): RouteWaypoint[] {
  return tours.flatMap((tour) => tourToRoute(tour, ctx)?.waypoints ?? [])
}

/** The active trip's route. An unedited official trip is drawn along the official GPX (tour-edge
 *  layer); any other trip along the legs re-derived from the hut graph. */
export function tripToRoute(trip: Trip, tripLegs: TripLegs, ctx: RouteContext): Route | null {
  const startCoords = place(trip.start.startId, 'start', ctx)
  const exitCoords = place(trip.exit.startId, 'start', ctx)
  const hutCoords = tripLegs.hutIndices.map((i) => (i === null ? null : place(i, 'hut', ctx)))
  const points = [startCoords, ...hutCoords, exitCoords]
  if (!points.every((p): p is RouteWaypoint => p !== null)) return null

  const view = trip.source ? ctx.officialById.get(trip.source.tourId) : undefined
  if (view && view.legs.length === trip.huts.length + 1) {
    return { waypoints: points, legs: view.legs.map((l) => ({ edgeId: l.edgeId, reversed: l.reversed, layer: 'tour_edges' as const })) }
  }
  return {
    waypoints: points,
    legs: tripLegs.legs.map((leg, i) => ({
      edgeId: leg ? leg.edgeId : -1, reversed: leg ? leg.reversed : false, layer: legLayer(i, tripLegs.legs.length),
    })),
  }
}
