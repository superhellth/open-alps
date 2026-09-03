import { useEffect } from 'react'
import { useMap } from 'react-leaflet'
import L from 'leaflet'
import type { Edge, Hover } from './types.js'

// How close the cursor has to be to a trail polyline to count as "hovering" it, in screen
// pixels - constant across zoom levels since it's a hit-test tolerance, not a map distance.
const HOVER_THRESHOLD_PX = 6

function distToSegmentPx(p: L.Point, a: L.Point, b: L.Point): number {
  const dx = b.x - a.x
  const dy = b.y - a.y
  if (dx === 0 && dy === 0) return Math.hypot(p.x - a.x, p.y - a.y)
  let t = ((p.x - a.x) * dx + (p.y - a.y) * dy) / (dx * dx + dy * dy)
  t = Math.max(0, Math.min(1, t))
  return Math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy))
}

function distToPolylinePx(map: L.Map, cursorPt: L.Point, positions: L.LatLngExpression[]): number {
  let min = Infinity
  for (let i = 0; i < positions.length - 1; i++) {
    const a = map.latLngToContainerPoint(positions[i])
    const b = map.latLngToContainerPoint(positions[i + 1])
    const d = distToSegmentPx(cursorPt, a, b)
    if (d < min) min = d
  }
  return min
}

// Degrees-per-pixel at the cursor's location, used to cheaply pre-filter which edges are even
// worth a precise (per-vertex) pixel-distance check - avoids walking every polyline's full
// vertex list on every mousemove.
function degreesPerPixel(map: L.Map, cursorPt: L.Point): number {
  const a = map.containerPointToLatLng(cursorPt)
  const b = map.containerPointToLatLng(L.point(cursorPt.x + HOVER_THRESHOLD_PX, cursorPt.y))
  return Math.abs(b.lng - a.lng)
}

/**
 * Renders no visible layer itself - just listens for mousemove on the underlying Leaflet map
 * and reports every edge whose trail polyline passes within HOVER_THRESHOLD_PX of the cursor,
 * not just whichever one Leaflet's native per-shape hit-testing would pick (the topmost path).
 * That's the only way to surface every edge in a stack of overlapping/contained trails.
 */
export default function HoverInspector({ edges, onHover }: { edges: Edge[]; onHover: (hover: Hover | null) => void }) {
  const map = useMap()

  useEffect(() => {
    function handleMove(e: L.LeafletMouseEvent) {
      const cursorPt = map.latLngToContainerPoint(e.latlng)
      const bufferDeg = degreesPerPixel(map, cursorPt) * HOVER_THRESHOLD_PX
      const cursorLatLng = e.latlng

      const matches: { index: number; distPx: number }[] = []
      for (let i = 0; i < edges.length; i++) {
        const edge = edges[i]
        if (!edge.bounds.pad(0).contains(cursorLatLng)) {
          // cheap reject unless within a buffered bbox first
          const padded = L.latLngBounds(
            [edge.bounds.getSouth() - bufferDeg, edge.bounds.getWest() - bufferDeg],
            [edge.bounds.getNorth() + bufferDeg, edge.bounds.getEast() + bufferDeg]
          )
          if (!padded.contains(cursorLatLng)) continue
        }
        const distPx = distToPolylinePx(map, cursorPt, edge.positions)
        if (distPx <= HOVER_THRESHOLD_PX) matches.push({ index: i, distPx })
      }
      matches.sort((a, b) => a.distPx - b.distPx)

      if (matches.length === 0) {
        onHover(null)
      } else {
        onHover({
          x: (e.originalEvent as MouseEvent).clientX,
          y: (e.originalEvent as MouseEvent).clientY,
          indices: matches.map((m) => m.index),
        })
      }
    }

    function handleLeave() {
      onHover(null)
    }

    map.on('mousemove', handleMove)
    map.on('mouseout', handleLeave)
    return () => {
      map.off('mousemove', handleMove)
      map.off('mouseout', handleLeave)
    }
  }, [map, edges, onHover])

  return null
}
