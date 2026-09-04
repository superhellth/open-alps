import type L from 'leaflet'
import type { HutClass } from '../hutClass.js'

export interface Edge {
  fromId: number
  toId: number
  distanceM: number
  roadM: number
  ascentM: number | null
  descentM: number | null
  elevationProfile: number[] | null
  sacScale: string | null
  viaFerrata: boolean
  positions: L.LatLngExpression[]
  bounds: L.LatLngBounds
}

export interface Hut {
  id: number
  name: string
  lat: number
  lng: number
  hutClass: HutClass | null
}

export interface PartnerPoint {
  id: number
  name: string
  lat: number
  lng: number
}

export interface Hover {
  x: number
  y: number
  indices: number[]
}

export interface EdgeStatsEntry {
  from_hut_id: number
  to_hut_id: number
  distance_m: number
  road_m: number
  ascent_m: number | null
  descent_m: number | null
  sac_scale: string | null
  via_ferrata: boolean
}

export interface EdgeGeometryManifest {
  point_counts: number[]
}

export interface ElevationManifest {
  profile_counts: number[]
}
