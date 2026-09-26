import type { HutOperator } from '@/data/hutClass.js'
import type { GeometryLayer } from '@/tourSearch/loadLegGeometry.js'

/** What a waypoint is, so the map can draw its symbol; absent when nothing reliable is known (no guessing). */
export type WaypointStop =
  | { type: 'hut'; hutId: number; operator: HutOperator; serviced: boolean }
  | { type: 'end'; startId: number; sourceType: number }

export interface RouteWaypoint {
  lat: number
  lng: number
  stop?: WaypointStop
}

export interface RouteLeg {
  edgeId: number
  reversed: boolean
  layer: GeometryLayer
}

export interface Route {
  waypoints: RouteWaypoint[]
  legs: RouteLeg[]
}

export type EmphasisTier = 'rest' | 'focused' | 'hovered'

/** A point on the height profile: which leg and how far along it (0…1), in travel direction. */
export interface ProfilePosition {
  legIndex: number
  fraction: number
}
