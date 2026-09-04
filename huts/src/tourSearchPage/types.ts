import type { GeometryLayer } from '../tourSearch/loadLegGeometry.js'

export interface StartPoint {
  name: string | null
  sourceType: number
  lat: number
  lng: number
}

export interface RouteWaypoint {
  lat: number
  lng: number
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
