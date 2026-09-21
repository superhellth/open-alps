import { Fragment, useEffect, useMemo } from 'react'
import { CircleMarker, Polyline, useMap } from 'react-leaflet'
import { tokens } from '../../theme.js'
import type { Route } from '../types.js'
import { useLegGeometries } from './useLegGeometries.js'

interface Segment {
  positions: [number, number][]
  isFallback: boolean
}

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
    if (positions.length >= 2) map.fitBounds(positions, { padding: [40, 40] })
  }, [map, positions])
  return null
}

/** A route as selected-route styling: signpost yellow over an ink casing. Legs still loading (or
 *  without geometry) are dashed straight lines between their huts. */
export default function RouteLayer({ route, highlightedLeg = null, fit = false }:
  { route: Route; highlightedLeg?: number | null; fit?: boolean }) {
  const positions = useMemo(() => route.waypoints.map((w): [number, number] => [w.lat, w.lng]), [route])
  const geometries = useLegGeometries(route)
  const segments = segmentsOf(positions, geometries)

  return (
    <>
      {fit && <FitRoute positions={positions} />}
      {segments.map((seg, i) => {
        const width = highlightedLeg === i ? 6 : 4
        const dash = seg.isFallback ? '6 8' : undefined
        return (
          <Fragment key={i}>
            <Polyline positions={seg.positions} pathOptions={{ color: tokens.ink, weight: width + 4, dashArray: dash }} />
            <Polyline positions={seg.positions} pathOptions={{ color: tokens.signpost, weight: width, dashArray: dash }} />
          </Fragment>
        )
      })}
      {positions.map((pos, i) => (
        <CircleMarker
          key={i} center={pos} radius={i === 0 || i === positions.length - 1 ? 6 : 4}
          pathOptions={{ color: tokens.ink, fillColor: tokens.signpost, fillOpacity: 1, weight: 2 }}
        />
      ))}
    </>
  )
}
