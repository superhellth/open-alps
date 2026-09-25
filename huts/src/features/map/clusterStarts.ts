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

export type MarkerKind = 'single' | 'stack'

/** single = one start point with one tour; stack = one start point with several. */
export function markerKind(m: Extract<MapMarker, { kind: 'start' }>): MarkerKind {
  return m.count === 1 ? 'single' : 'stack'
}

export interface AnchorPoint { tourKey: string; lat: number; lng: number }

/** One signpost: the tours whose anchors cluster together, best-ranked first. The foot stands on the
 *  best-ranked tour's own anchor, never on a cluster centroid. */
export interface AnchorMarker { id: string; lat: number; lng: number; tourKeys: string[] }

export interface AnchorClusterer {
  markersFor(bbox: [number, number, number, number], zoom: number): AnchorMarker[]
}

/** Screen radius (px) within which anchors share one signpost; boards are wider than count bubbles. */
const ANCHOR_CLUSTER_RADIUS = 70
const ANCHOR_CLUSTER_MAX_ZOOM = 16

/** `points` are in rank order, best first; that order decides each marker's foot and board order. */
export function createAnchorClusterer(points: AnchorPoint[]): AnchorClusterer {
  const index = new Supercluster<{ rank: number }>({ radius: ANCHOR_CLUSTER_RADIUS, maxZoom: ANCHOR_CLUSTER_MAX_ZOOM })
  index.load(points.map((p, rank) => ({
    type: 'Feature' as const,
    properties: { rank },
    geometry: { type: 'Point' as const, coordinates: [p.lng, p.lat] },
  })))
  return {
    markersFor(bbox, zoom) {
      return index.getClusters(bbox, Math.round(zoom)).map((f): AnchorMarker => {
        const props = f.properties as { cluster?: boolean; cluster_id?: number; rank?: number }
        const ranks = props.cluster
          ? index.getLeaves(props.cluster_id!, Infinity).map((leaf) => (leaf.properties as { rank: number }).rank).sort((a, b) => a - b)
          : [props.rank!]
        const foot = points[ranks[0]]
        return { id: foot.tourKey, lat: foot.lat, lng: foot.lng, tourKeys: ranks.map((r) => points[r].tourKey) }
      })
    },
  }
}

export function anchorMarkerKind(m: AnchorMarker): MarkerKind {
  return m.tourKeys.length === 1 ? 'single' : 'stack'
}

const MIN_RADIUS = 12
const MAX_RADIUS = 34

/** Cluster bubble radius in px: sqrt of the match count with fixed bounds, so large clusters do not cover the map. */
export function markerRadius(count: number): number {
  return Math.min(MAX_RADIUS, Math.max(MIN_RADIUS, 9 + 3.5 * Math.sqrt(count)))
}
