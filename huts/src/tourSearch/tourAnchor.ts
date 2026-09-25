import { anchorFractions } from './anchors.js'
import type { LatLng } from './anchors.js'
import type { LegAnchorLookup } from './legAnchors.js'
import type { GeometryLayer } from './loadLegGeometry.js'

export type Heading = 'east' | 'west'
export type Bbox = [west: number, south: number, east: number, north: number]

export interface AnchorLeg { layer: GeometryLayer; edgeId: number; reversed: boolean; distanceM: number }
/** A tour's route as the anchor choice sees it: `waypoints.length === legs.length + 1`. */
export interface AnchorRoute { waypoints: LatLng[]; legs: AnchorLeg[] }
export interface TourAnchor extends LatLng { heading: Heading }

interface Candidate extends TourAnchor { at: number }

const CHORD_FRACTIONS = anchorFractions(3)

const inBbox = (p: LatLng, [w, s, e, n]: Bbox) => p.lng >= w && p.lng <= e && p.lat >= s && p.lat <= n

const lerp = (a: LatLng, b: LatLng, t: number): LatLng => ({ lat: a.lat + (b.lat - a.lat) * t, lng: a.lng + (b.lng - a.lng) * t })

/** Every anchor of the route in walking order with its arc-length position along the tour and the travel
 *  direction there (from the previous point of the route to the next, waypoints included). A leg without
 *  shipped anchors contributes the chord points at the same fractions. */
function candidates(route: AnchorRoute, lookup: LegAnchorLookup): Candidate[] {
  const seq: { p: LatLng; at: number | null }[] = [{ p: route.waypoints[0], at: null }]
  let walked = 0
  route.legs.forEach((leg, i) => {
    const shipped = lookup(leg.layer, leg.edgeId)
    const points = shipped
      ? (leg.reversed ? [...shipped].reverse() : shipped)
      : CHORD_FRACTIONS.map((t) => lerp(route.waypoints[i], route.waypoints[i + 1], t))
    const fractions = anchorFractions(points.length)
    points.forEach((p, k) => seq.push({ p, at: walked + fractions[k] * leg.distanceM }))
    walked += leg.distanceM
    seq.push({ p: route.waypoints[i + 1], at: null })
  })
  return seq.flatMap(({ p, at }, j) => {
    if (at === null) return []
    const heading: Heading = seq[j + 1].p.lng < seq[j - 1].p.lng ? 'west' : 'east'
    return [{ lat: p.lat, lng: p.lng, at, heading }]
  })
}

/** Where a tour's signpost stands: the anchor nearest half the tour's distance, or, when that is outside `bbox`,
 *  the in-view anchor nearest it; null when the tour has no anchor in view. */
export function tourAnchor(route: AnchorRoute, lookup: LegAnchorLookup, bbox: Bbox): TourAnchor | null {
  const half = route.legs.reduce((sum, l) => sum + l.distanceM, 0) / 2
  let best: Candidate | null = null
  let bestInView: Candidate | null = null
  for (const c of candidates(route, lookup)) {
    const d = Math.abs(c.at - half)
    if (!best || d < Math.abs(best.at - half)) best = c
    if (inBbox(c, bbox) && (!bestInView || d < Math.abs(bestInView.at - half))) bestInView = c
  }
  const chosen = best && inBbox(best, bbox) ? best : bestInView
  return chosen ? { lat: chosen.lat, lng: chosen.lng, heading: chosen.heading } : null
}
