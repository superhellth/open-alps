import Supercluster from 'supercluster'

export interface StartMarker {
  startId: number
  count: number
  lat: number
  lng: number
}

export type MapMarker =
  | { kind: 'start'; startId: number; count: number; lat: number; lng: number }
  | { kind: 'cluster'; clusterId: number; count: number; lat: number; lng: number }

export interface StartClusterer {
  clustersFor(bbox: [number, number, number, number], zoom: number): MapMarker[]
  expansionZoom(clusterId: number): number
  startIdsOf(clusterId: number): number[]
}

type PointProps = { startId: number; count: number }
type ClusterProps = { count: number }

export function createStartClusterer(markers: StartMarker[]): StartClusterer {
  const index = new Supercluster<PointProps, ClusterProps>({
    radius: 60,
    maxZoom: 14,
    map: (props) => ({ count: props.count }),
    reduce: (accumulated, props) => { accumulated.count += props.count },
  })
  index.load(markers.map((m) => ({
    type: 'Feature' as const,
    properties: { startId: m.startId, count: m.count },
    geometry: { type: 'Point' as const, coordinates: [m.lng, m.lat] },
  })))

  return {
    clustersFor(bbox, zoom) {
      return index.getClusters(bbox, Math.round(zoom)).map((f): MapMarker => {
        const [lng, lat] = f.geometry.coordinates
        const props = f.properties as Record<string, unknown>
        if (props.cluster) {
          return { kind: 'cluster', clusterId: props.cluster_id as number, count: props.count as number, lat, lng }
        }
        return { kind: 'start', startId: props.startId as number, count: props.count as number, lat, lng }
      })
    },
    expansionZoom: (clusterId) => index.getClusterExpansionZoom(clusterId),
    startIdsOf: (clusterId) => index.getLeaves(clusterId, Infinity).map((f) => (f.properties as PointProps).startId),
  }
}

const MIN_RADIUS = 12
const MAX_RADIUS = 34

/** Marker radius in px: sqrt of the match count with fixed bounds, so single start points stay
 *  clickable and large clusters do not cover the map. */
export function markerRadius(count: number): number {
  return Math.min(MAX_RADIUS, Math.max(MIN_RADIUS, 9 + 3.5 * Math.sqrt(count)))
}
