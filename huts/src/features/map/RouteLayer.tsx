import { Fragment, useEffect, useMemo } from 'react'
import type L from 'leaflet'
import { CircleMarker, Polyline, useMap } from 'react-leaflet'
import { tokens } from '@/ui/theme.js'
import { ensureRoutePanes, paneName } from './routePanes.js'
import type { EmphasisTier, Route } from './types.js'
import { useLegGeometries } from './useLegGeometries.js'

interface Segment {
  positions: [number, number][]
  isFallback: boolean
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
 *  without geometry) are dashed straight lines between their huts. Discover passes `emphasis`
 *  (rest and focused are thin candidates, hovered is the bold single-tour style); without it,
 *  `muted` draws the thin candidate style and `dimmedOut` fades the route into the rest tier. */
export default function RouteLayer({ route, highlightedLeg = null, fit = false, muted = false, dimmedOut = false, emphasis, dots = true, interactive = true, onHover, onClick }: {
  route: Route
  highlightedLeg?: number | null
  fit?: boolean
  /** Thin candidate style instead of the bold selected-route style. Ignored when `emphasis` is set. */
  muted?: boolean
  /** Fades the route into the rest tier. Ignored when `emphasis` is set. */
  dimmedOut?: boolean
  emphasis?: EmphasisTier
  /** false draws lines only (Discover draws waypoint symbols in a separate layer). */
  dots?: boolean
  /** false draws a display-only copy that never receives pointer events. */
  interactive?: boolean
  onHover?: (hovering: boolean, legIndex: number, at: L.LatLng) => void
  onClick?: (legIndex: number) => void
}) {
  const positions = useMemo(() => route.waypoints.map((w): [number, number] => [w.lat, w.lng]), [route])
  const geometries = useLegGeometries(route)
  const segments = segmentsOf(positions, geometries)
  const tier: EmphasisTier = emphasis ?? (dimmedOut ? 'rest' : 'hovered')
  const thin = emphasis ? emphasis !== 'hovered' : muted
  const baseWidth = thin ? 2 : 4
  const map = useMap()
  ensureRoutePanes(map)
  const casingPane = paneName(tier, 'casing')
  const linePane = paneName(tier, 'line')
  const dotPane = paneName(tier, 'symbol')

  return (
    <>
      {fit && <FitRoute positions={positions} />}
      {segments.map((seg, i) => {
        if (!seg) return null
        const width = highlightedLeg === i ? baseWidth + 2 : baseWidth
        const dash = seg.isFallback ? '6 8' : undefined
        return (
          <Fragment key={i}>
            <Polyline positions={seg.positions} pane={casingPane} pathOptions={{ color: tokens.ink, weight: width + (thin ? 2 : 4), dashArray: dash, interactive: false }} />
            <Polyline
              positions={seg.positions} pane={linePane} pathOptions={{ color: tokens.signpost, weight: width, dashArray: dash, interactive, bubblingMouseEvents: false }}
              eventHandlers={{ mouseover: (e) => onHover?.(true, i, e.latlng), mouseout: (e) => onHover?.(false, i, e.latlng), click: () => onClick?.(i) }}
            />
          </Fragment>
        )
      })}
      {dots && positions.map((pos, i) => (
        <CircleMarker
          key={i} center={pos} pane={dotPane} radius={i === 0 || i === positions.length - 1 ? 6 : 4}
          pathOptions={{ color: tokens.ink, fillColor: tokens.signpost, fillOpacity: 1, weight: 2, interactive: false }}
        />
      ))}
    </>
  )
}
