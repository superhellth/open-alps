import type L from 'leaflet'
import type { EdgeGeometryManifest } from './types.js'

/** Decodes hut-edge-geometry.bin's flat f4 [lon, lat] point stream (edge_id order, no framing)
 *  into one Leaflet-ready [lat, lng][] per edge, using point_counts as a prefix-sum offset table.
 *  Fetched whole rather than range-fetched (unlike ResultsMap's per-leg lookups) because
 *  HoverInspector needs every edge's geometry at once. */
export function decodeEdgeGeometry(manifest: EdgeGeometryManifest, buffer: ArrayBuffer): L.LatLngExpression[][] {
  const floats = new Float32Array(buffer)
  const perEdge: L.LatLngExpression[][] = new Array(manifest.point_counts.length)
  let pointOffset = 0
  for (let i = 0; i < manifest.point_counts.length; i++) {
    const count = manifest.point_counts[i]
    const positions: L.LatLngExpression[] = new Array(count)
    for (let p = 0; p < count; p++) {
      const base = (pointOffset + p) * 2
      positions[p] = [floats[base + 1], floats[base]]
    }
    perEdge[i] = positions
    pointOffset += count
  }
  return perEdge
}
