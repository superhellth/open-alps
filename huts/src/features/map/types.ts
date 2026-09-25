import type { GeometryLayer } from '@/tourSearch/loadLegGeometry.js'

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

export type EmphasisTier = 'rest' | 'focused' | 'hovered'
