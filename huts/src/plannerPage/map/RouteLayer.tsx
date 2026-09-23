import { Fragment, useEffect, useMemo, useRef } from 'react'
import type L from 'leaflet'
import { CircleMarker, FeatureGroup, Polyline, useMap } from 'react-leaflet'
import { tokens } from '../../theme.js'
import type { Route } from '../types.js'
import { useLegGeometries } from './useLegGeometries.js'

interface Segment {
  positions: [number, number][]
  isFallback: boolean
}

/** Above every route line (overlayPane is 400), below the marker pane, so hut dots are never
 *  covered by another route's line. */
const HUT_DOT_PANE = 'route-hut-dots'

function segmentsOf(positions: [number, number][], geometries: ([number, number][] | null)[]): Segment[] {
  return positions.slice(0, -1).map((from, i) => {
    const real = geometries[i]
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
export default function RouteLayer({ route, highlightedLeg = null, fit = false, muted = false, dimmedOut = false, onHover, onClick }: {
  route: Route
  highlightedLeg?: number | null
  fit?: boolean
  muted?: boolean
  dimmedOut?: boolean
  onHover?: (hovering: boolean) => void
  onClick?: () => void
}) {
  const positions = useMemo(() => route.waypoints.map((w): [number, number] => [w.lat, w.lng]), [route])
  const geometries = useLegGeometries(route)
  const segments = segmentsOf(positions, geometries)
  const baseWidth = muted ? 2 : 4
  const opacity = dimmedOut ? 0.35 : 1
  const map = useMap()
  if (!map.getPane(HUT_DOT_PANE)) map.createPane(HUT_DOT_PANE).style.zIndex = '450'
  const linesRef = useRef<L.FeatureGroup>(null)
  // A full-opacity route drawn beneath dimmed ones would be darkened by their translucent casings.
  useEffect(() => {
    if (!dimmedOut) linesRef.current?.bringToFront()
  }, [dimmedOut, segments.length, geometries])

  return (
    <>
      {fit && <FitRoute positions={positions} />}
      <FeatureGroup ref={linesRef}>
      {segments.map((seg, i) => {
        const width = highlightedLeg === i ? baseWidth + 2 : baseWidth
        const dash = seg.isFallback ? '6 8' : undefined
        return (
          <Fragment key={i}>
            <Polyline positions={seg.positions} pathOptions={{ color: tokens.ink, weight: width + (muted ? 2 : 4), dashArray: dash, opacity }} />
            <Polyline
              positions={seg.positions} pathOptions={{ color: tokens.signpost, weight: width, dashArray: dash, opacity }}
              eventHandlers={{ mouseover: () => onHover?.(true), mouseout: () => onHover?.(false), click: () => onClick?.() }}
            />
          </Fragment>
        )
      })}
      </FeatureGroup>
      {positions.map((pos, i) => (
        <CircleMarker
          key={i} center={pos} pane={HUT_DOT_PANE} radius={i === 0 || i === positions.length - 1 ? 6 : 4}
          pathOptions={{ color: tokens.ink, fillColor: tokens.signpost, fillOpacity: opacity, opacity, weight: 2 }}
        />
      ))}
    </>
  )
}
