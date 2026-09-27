import { anchorCandidates, tourAnchor } from '@/tourSearch/tourAnchor.js'
import type { Bbox, TourAnchor } from '@/tourSearch/tourAnchor.js'
import type { LegAnchorLookup } from '@/tourSearch/legAnchors.js'
import { legLayer } from '@/tourSearch/loadLegGeometry.js'
import type { TripLegs } from '@/trip/tripLegs.js'
import type { Trip } from '@/trip/trip.js'
import type { PlannerTour } from '@/tourSearch/plannerTour.js'
import type { Route, RouteWaypoint } from './types.js'
import type { StartPoint } from '@/data/types.js'
import type { HutClass } from '@/data/hutClass.js'

export interface RouteContext {
  hutCoordsById: Map<number, { lat: number; lng: number }>
  startById: Map<number, StartPoint>
  hutClassByIndex: Map<number, HutClass>
  /** Anchor points of a leg's edge, for placing a tour's signpost on its route. */
  legAnchors: LegAnchorLookup
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
  return {
    waypoints,
    legs: tour.legs.map((leg, i) => ({
      edgeId: leg.edgeId, reversed: leg.reversed, layer: legLayer(i, tour.legs.length),
    })),
  }
}

function anchorRouteOf(tour: PlannerTour, route: Route) {
  return {
    waypoints: route.waypoints,
    legs: route.legs.map((l, i) => ({ layer: l.layer, edgeId: l.edgeId, reversed: l.reversed, distanceM: tour.legs[i].distanceM })),
  }
}

/** Where the tour's signpost stands on its route, or null when no anchor of the tour is in `bbox`. */
export function tourAnchorOf(tour: PlannerTour, route: Route, ctx: RouteContext, bbox: Bbox): TourAnchor | null {
  return tourAnchor(anchorRouteOf(tour, route), ctx.legAnchors, bbox)
}

const WORLD: Bbox = [-180, -90, 180, 90]

/** Where the tour stands on the map before any viewport clipping: its default signpost anchor, or its start point when
 *  the route does not resolve. Count bubbles cluster tours at this point and the results list tests it against the view. */
export function tourMapPoint(tour: PlannerTour, ctx: RouteContext): { lat: number; lng: number } | null {
  const route = tourToRoute(tour, ctx)
  return (route && tourAnchorOf(tour, route, ctx, WORLD)) ?? ctx.startById.get(tour.startId) ?? null
}

/** Every anchor of the tour's route in `bbox`, nearest half the tour's distance first: the places its signpost may stand. */
export function tourAnchorCandidatesOf(tour: PlannerTour, route: Route, ctx: RouteContext, bbox: Bbox): TourAnchor[] {
  return anchorCandidates(anchorRouteOf(tour, route), ctx.legAnchors, bbox)
}

/** Every waypoint (start, huts, exit) of the given tours; tours that fail to resolve are skipped. */
export function tourWaypoints(tours: PlannerTour[], ctx: RouteContext): RouteWaypoint[] {
  return tours.flatMap((tour) => tourToRoute(tour, ctx)?.waypoints ?? [])
}

/** The active trip's route, drawn along the legs re-derived from the hut graph. */
export function tripToRoute(trip: Trip, tripLegs: TripLegs, ctx: RouteContext): Route | null {
  const startCoords = place(trip.start.startId, 'start', ctx)
  const exitCoords = place(trip.exit.startId, 'start', ctx)
  const hutCoords = tripLegs.hutIndices.map((i) => (i === null ? null : place(i, 'hut', ctx)))
  const points = [startCoords, ...hutCoords, exitCoords]
  if (!points.every((p): p is RouteWaypoint => p !== null)) return null

  return {
    waypoints: points,
    legs: tripLegs.legs.map((leg, i) => ({
      edgeId: leg ? leg.edgeId : -1, reversed: leg ? leg.reversed : false, layer: legLayer(i, tripLegs.legs.length),
    })),
  }
}
