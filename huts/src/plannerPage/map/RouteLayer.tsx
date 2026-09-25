import { Fragment, useEffect, useMemo } from 'react'
import type L from 'leaflet'
import { CircleMarker, Polyline, useMap } from 'react-leaflet'
import { tokens } from '@/ui/theme.js'
import type { Route } from '../types.js'
import { useLegGeometries } from './useLegGeometries.js'

interface Segment {
  positions: [number, number][]
  isFallback: boolean
}

/** Route panes, bottom to top (overlayPane is 400, markerPane 600): every dimmed casing, every
 *  dimmed line, the dimmed hut dots, then the same three at full strength. Dimming is the pane's
 *  own CSS opacity rather than per-path alpha, so overlapping dimmed routes stay one flat colour
 *  instead of compounding, and no route's casing ever covers another route's line or dots. */
const PANES = {
  dimCasing: { name: 'route-dim-casing', z: 410, opacity: 0.35 },
  dimLine: { name: 'route-dim-line', z: 420, opacity: 0.35 },
  dimDot: { name: 'route-dim-dot', z: 430, opacity: 0.35 },
  casing: { name: 'route-casing', z: 440, opacity: 1 },
  line: { name: 'route-line', z: 450, opacity: 1 },
  dot: { name: 'route-dot', z: 460, opacity: 1 },
}

function ensurePanes(map: L.Map) {
  for (const { name, z, opacity } of Object.values(PANES)) {
    if (map.getPane(name)) continue
    const pane = map.createPane(name)
    pane.style.zIndex = String(z)
    pane.style.opacity = String(opacity)
  }
}

/** One segment per leg; a leg whose geometry is still loading yields null and is not drawn. */
function segmentsOf(positions: [number, number][], geometries: ([number, number][] | null | undefined)[]): (Segment | null)[] {
  return positions.slice(0, -1).map((from, i) => {
    const real = geometries[i]
    if (real === undefined) return null
    return real && real.length >= 2
      ? { positions: real, isFallback: false }
      : { positions: [from, positions[i + 1]], isFallback: true }
  })
}

function FitRoute({ positions }: { positions: [number, number][] }) {
  const map = useMap()
  useEffect(() => {
    if (positions.length >= 2) map.flyToBounds(positions, { padding: [40, 40], duration: 1 })
  }, [map, positions])
  return null
}

/** A route as selected-route styling: signpost yellow over an ink casing. Legs still loading (or
 *  without geometry) are dashed straight lines between their huts. `muted` draws the thin
 *  Discover-mode candidate style instead of the bold selected-route style; `dimmedOut` fades it
 *  further while a different route is hovered. */
export default function RouteLayer({ route, highlightedLeg = null, fit = false, muted = false, dimmedOut = false, interactive = true, onHover, onClick }: {
  route: Route
  highlightedLeg?: number | null
  fit?: boolean
  muted?: boolean
  dimmedOut?: boolean
  /** false draws a display-only copy that never receives pointer events. */
  interactive?: boolean
  onHover?: (hovering: boolean) => void
  onClick?: () => void
}) {
  const positions = useMemo(() => route.waypoints.map((w): [number, number] => [w.lat, w.lng]), [route])
  const geometries = useLegGeometries(route)
  const segments = segmentsOf(positions, geometries)
  const baseWidth = muted ? 2 : 4
  const map = useMap()
  ensurePanes(map)
  const casingPane = (dimmedOut ? PANES.dimCasing : PANES.casing).name
  const linePane = (dimmedOut ? PANES.dimLine : PANES.line).name
  const dotPane = (dimmedOut ? PANES.dimDot : PANES.dot).name

  return (
    <>
      {fit && <FitRoute positions={positions} />}
      {segments.map((seg, i) => {
        if (!seg) return null
        const width = highlightedLeg === i ? baseWidth + 2 : baseWidth
        const dash = seg.isFallback ? '6 8' : undefined
        return (
          <Fragment key={i}>
            <Polyline positions={seg.positions} pane={casingPane} pathOptions={{ color: tokens.ink, weight: width + (muted ? 2 : 4), dashArray: dash, interactive: false }} />
            <Polyline
              positions={seg.positions} pane={linePane} pathOptions={{ color: tokens.signpost, weight: width, dashArray: dash, interactive }}
              eventHandlers={{ mouseover: () => onHover?.(true), mouseout: () => onHover?.(false), click: () => onClick?.() }}
            />
          </Fragment>
        )
      })}
      {positions.map((pos, i) => (
        <CircleMarker
          key={i} center={pos} pane={dotPane} radius={i === 0 || i === positions.length - 1 ? 6 : 4}
          pathOptions={{ color: tokens.ink, fillColor: tokens.signpost, fillOpacity: 1, weight: 2, interactive: false }}
        />
      ))}
    </>
  )
}
