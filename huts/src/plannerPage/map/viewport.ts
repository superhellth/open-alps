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
