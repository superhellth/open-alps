import { useCallback, useEffect, useRef } from 'react'
import * as L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { chooseHandles } from './decimate.js'
import { LONG_SEGMENT_M, nearestSegment, segmentLengthsM } from './segments.js'
import { snapPoint, type SnapContext } from './snap.js'
import type { Hub, HubType, LonLat } from './types.js'

export interface EditorMapProps {
  legKey: string
  points: LonLat[]
  hubs: Hub[]
  snapCtx: SnapContext | null
  maxSnapM: number | null
  requireHut: { start: boolean; end: boolean }
  onMove(index: number, lon: number, lat: number): void
  onInsert(afterIndex: number, lon: number, lat: number): void
  onDelete(index: number): void
  onSelectPoint?(index: number | null): void
}

const TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
const TILE_ATTR =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>-Mitwirkende'
const HANDLE_MIN_PX = 12
const HUB_COLORS: Record<HubType, string> = {
  hut: '#e0562f', station: '#3b82f6', parking: '#8b8b8b', partner_betrieb: '#a855f7',
}
const OK_COLOR = '#2e7d32'
const BAD_COLOR = '#d32f2f'
const MAX_HUB_DOTS = 5000
const OTHER_HUB_MIN_ZOOM = 11

const HANDLE_CSS = `
.gpx-handle{width:12px;height:12px;border-radius:50%;background:#fff;border:2px solid #e0562f;box-sizing:border-box}
.gpx-handle.endpoint{border-color:#111;background:#ffd54f}
.gpx-handle.selected{background:#e0562f}
.gpx-dist{background:#fff;border:1px solid #999;padding:0 4px;font-size:11px}
`

const ll = (p: LonLat): L.LatLngExpression => [p.lat, p.lon]
const inTextField = (t: EventTarget | null) =>
  t instanceof HTMLElement && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)

export default function EditorMap(props: EditorMapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const canvasRef = useRef<L.Canvas | null>(null)
  const groups = useRef<Record<'hubs' | 'line' | 'overlay' | 'handles', L.LayerGroup> | null>(null)
  const polyRef = useRef<L.Polyline | null>(null)
  const selectedRef = useRef<number | null>(null)
  const lastFitKey = useRef<string | null>(null)
  const latest = useRef(props)
  latest.current = props

  const redrawHubs = useCallback(() => {
    const map = mapRef.current
    const g = groups.current
    if (!map || !g) return
    g.hubs.clearLayers()
    const bounds = map.getBounds().pad(0.1)
    const zoom = map.getZoom()
    let drawn = 0
    for (const h of latest.current.hubs) {
      if (h.type !== 'hut' && zoom < OTHER_HUB_MIN_ZOOM) continue
      if (!bounds.contains([h.lat, h.lon])) continue
      L.circleMarker([h.lat, h.lon], {
        renderer: canvasRef.current ?? undefined, radius: h.type === 'hut' ? 5 : 3, weight: 1,
        color: HUB_COLORS[h.type], fillColor: HUB_COLORS[h.type], fillOpacity: 0.8, interactive: false,
      }).addTo(g.hubs)
      if (++drawn >= MAX_HUB_DOTS) break
    }
  }, [])

  const redrawOverlay = useCallback((pts: LonLat[]) => {
    const g = groups.current
    if (!g) return
    g.overlay.clearLayers()
    const { snapCtx, maxSnapM, requireHut } = latest.current
    if (!snapCtx || maxSnapM === null || pts.length < 2) return
    const ends = [
      { p: pts[0]!, req: requireHut.start },
      { p: pts[pts.length - 1]!, req: requireHut.end },
    ]
    for (const { p, req } of ends) {
      const r = snapPoint(snapCtx, p, maxSnapM, req)
      const color = r.chosen ? OK_COLOR : BAD_COLOR
      L.circleMarker(ll(p), { radius: 14, color, weight: 3, fill: false, interactive: false }).addTo(g.overlay)
      if (r.nearest) {
        L.polyline([ll(p), ll(r.nearest)], { color, weight: 2, dashArray: '6 6', interactive: false })
          .bindTooltip(`${Math.round(r.nearestDistM)} m`, { permanent: true, direction: 'center', className: 'gpx-dist' })
          .addTo(g.overlay)
        L.circleMarker(ll(r.nearest), { radius: 10, color, weight: 2, fill: false, interactive: false }).addTo(g.overlay)
      }
    }
  }, [])

  const redrawLine = useCallback(() => {
    const map = mapRef.current
    const g = groups.current
    if (!map || !g) return
    g.line.clearLayers()
    polyRef.current = null
    const { points, onInsert } = latest.current
    if (points.length < 2) return
    const lls = points.map((p) => L.latLng(p.lat, p.lon))
    const poly = L.polyline(lls, { renderer: canvasRef.current ?? undefined, color: '#e0562f', weight: 4 }).addTo(g.line)
    poly.on('click', (e: L.LeafletMouseEvent) => {
      L.DomEvent.stopPropagation(e)
      const px = latest.current.points.map((p) => map.latLngToLayerPoint([p.lat, p.lon]))
      const seg = nearestSegment(px, map.latLngToLayerPoint(e.latlng))
      onInsert(seg.index, e.latlng.lng, e.latlng.lat)
    })
    polyRef.current = poly
    segmentLengthsM(points).forEach((len, i) => {
      if (len > LONG_SEGMENT_M) {
        L.polyline([lls[i]!, lls[i + 1]!], { color: '#ffb300', weight: 7, opacity: 0.8, interactive: false }).addTo(g.line)
      }
    })
  }, [])

  const redrawHandles = useCallback(() => {
    const map = mapRef.current
    const g = groups.current
    if (!map || !g) return
    g.handles.clearLayers()
    const { points } = latest.current
    if (points.length === 0) return
    const size = map.getSize()
    const pad = 50
    const px = points.map((p) => map.latLngToContainerPoint([p.lat, p.lon]))
    const idx = chooseHandles(
      px, { minX: -pad, minY: -pad, maxX: size.x + pad, maxY: size.y + pad }, HANDLE_MIN_PX,
    )
    const last = points.length - 1
    for (const i of idx) {
      const p = points[i]!
      const endpoint = i === 0 || i === last
      const marker = L.marker(ll(p), {
        draggable: true, keyboard: false,
        icon: L.divIcon({ className: `gpx-handle${endpoint ? ' endpoint' : ''}`, iconSize: [12, 12] }),
      }).addTo(g.handles)
      let draft: LonLat[] | null = null
      marker.on('dragstart', () => {
        draft = latest.current.points.slice()
      })
      marker.on('drag', () => {
        if (!draft) return
        const at = marker.getLatLng()
        draft[i] = { lon: at.lng, lat: at.lat }
        const lls = polyRef.current?.getLatLngs() as L.LatLng[] | undefined
        if (lls) {
          lls[i] = at
          polyRef.current?.redraw()
        }
        if (endpoint) redrawOverlay(draft)
      })
      marker.on('dragend', () => {
        const at = marker.getLatLng()
        draft = null
        latest.current.onMove(i, at.lng, at.lat)
      })
      marker.on('click', () => {
        selectedRef.current = i
        latest.current.onSelectPoint?.(i)
        g.handles.eachLayer((layer) => (layer as L.Marker).getElement()?.classList.remove('selected'))
        marker.getElement()?.classList.add('selected')
      })
      marker.on('contextmenu', (e: L.LeafletMouseEvent) => {
        L.DomEvent.preventDefault(e.originalEvent)
        if (!endpoint) latest.current.onDelete(i)
      })
    }
  }, [redrawOverlay])

  // Map lifecycle.
  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const map = L.map(container, { center: [47.2, 11.4], zoom: 8 })
    L.tileLayer(TILE_URL, { attribution: TILE_ATTR, maxZoom: 19 }).addTo(map)
    canvasRef.current = L.canvas({ tolerance: 6 })
    groups.current = {
      hubs: L.layerGroup().addTo(map), line: L.layerGroup().addTo(map),
      overlay: L.layerGroup().addTo(map), handles: L.layerGroup().addTo(map),
    }
    mapRef.current = map
    const onView = () => {
      redrawHubs()
      redrawHandles()
    }
    map.on('moveend zoomend', onView)
    const onKey = (e: KeyboardEvent) => {
      const i = selectedRef.current
      if (e.key !== 'Delete' || i === null || inTextField(e.target)) return
      const last = latest.current.points.length - 1
      if (i > 0 && i < last) latest.current.onDelete(i)
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      map.remove()
      mapRef.current = null
      groups.current = null
    }
  }, [redrawHandles, redrawHubs])

  useEffect(redrawHubs, [props.hubs, redrawHubs])

  // Points / snap state changed: redraw everything derived from them.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    selectedRef.current = null
    latest.current.onSelectPoint?.(null)
    redrawLine()
    redrawOverlay(props.points)
    redrawHandles()
    if (props.points.length > 1 && lastFitKey.current !== props.legKey) {
      lastFitKey.current = props.legKey
      map.fitBounds(L.latLngBounds(props.points.map(ll)), { padding: [30, 30] })
    }
  }, [props.points, props.snapCtx, props.maxSnapM, props.requireHut, props.legKey, redrawLine, redrawOverlay, redrawHandles])

  return (
    <>
      <style>{HANDLE_CSS}</style>
      <div ref={containerRef} style={{ height: '100%', width: '100%' }} />
    </>
  )
}
