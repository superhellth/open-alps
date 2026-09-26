import Supercluster from 'supercluster'

/** One tour on the bubble map, at the point its signpost stands on from the reveal zoom on. */
export interface TourPoint {
  key: string
  lat: number
  lng: number
}

export type MapMarker =
  | { kind: 'tour'; key: string; count: 1; lat: number; lng: number }
  | { kind: 'cluster'; clusterId: number; count: number; lat: number; lng: number }

export interface TourClusterer {
  clustersFor(bbox: [number, number, number, number], zoom: number): MapMarker[]
  keysOf(clusterId: number): string[]
}

type PointProps = { key: string }

export function createTourClusterer(points: TourPoint[]): TourClusterer {
  const index = new Supercluster<PointProps>({ radius: 60, maxZoom: 14 })
  index.load(points.map((p) => ({
    type: 'Feature' as const,
    properties: { key: p.key },
    geometry: { type: 'Point' as const, coordinates: [p.lng, p.lat] },
  })))

  return {
    clustersFor(bbox, zoom) {
      return index.getClusters(bbox, Math.round(zoom)).map((f): MapMarker => {
        const [lng, lat] = f.geometry.coordinates
        const props = f.properties as Record<string, unknown>
        if (props.cluster) {
          return { kind: 'cluster', clusterId: props.cluster_id as number, count: props.point_count as number, lat, lng }
        }
        return { kind: 'tour', key: props.key as string, count: 1, lat, lng }
      })
    },
    keysOf: (clusterId) => index.getLeaves(clusterId, Infinity).map((f) => (f.properties as PointProps).key),
  }
}

const MIN_RADIUS = 12
const MAX_RADIUS = 34

/** Cluster bubble radius in px: sqrt of the match count with fixed bounds, so large clusters do not cover the map. */
export function markerRadius(count: number): number {
  return Math.min(MAX_RADIUS, Math.max(MIN_RADIUS, 9 + 3.5 * Math.sqrt(count)))
}
