import type L from 'leaflet'

export interface View {
  bbox: [number, number, number, number]
  zoom: number
}

/** The bounds are padded by half a tile-width so markers just outside the viewport (and a
 *  zero-size map, as in jsdom) still resolve. */
export function currentView(map: L.Map): View {
  const b = map.getBounds()
  const zoom = Math.round(map.getZoom())
  const pad = (0.5 * 360) / 2 ** zoom
  return { bbox: [b.getWest() - pad, b.getSouth() - pad, b.getEast() + pad, b.getNorth() + pad], zoom }
}

export function inBbox(pt: { lat: number; lng: number }, bbox: [number, number, number, number]): boolean {
  const [w, s, e, n] = bbox
  return pt.lng >= w && pt.lng <= e && pt.lat >= s && pt.lat <= n
}

/** True when the bounding box of the waypoints overlaps the bbox — a route crossing the viewport
 *  between two off-screen waypoints still counts. */
export function routeTouchesBbox(waypoints: { lat: number; lng: number }[], bbox: [number, number, number, number]): boolean {
  const [w, s, e, n] = bbox
  let minLng = Infinity, maxLng = -Infinity, minLat = Infinity, maxLat = -Infinity
  for (const p of waypoints) {
    minLng = Math.min(minLng, p.lng); maxLng = Math.max(maxLng, p.lng)
    minLat = Math.min(minLat, p.lat); maxLat = Math.max(maxLat, p.lat)
  }
  return minLng <= e && maxLng >= w && minLat <= n && maxLat >= s
}
