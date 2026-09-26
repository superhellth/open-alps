import { Fragment, useEffect, useMemo } from 'react'
import type L from 'leaflet'
import { CircleMarker, Polyline, useMap } from 'react-leaflet'
import { tokens } from '@/ui/theme.js'
import { opacity } from '@/ui/tokens.js'
import { pointAlong } from './pointAlong.js'
import { LEG_HIT_PANE, ensureRoutePanes, paneName } from './routePanes.js'
import type { ProfilePosition } from '@/trip/tripLegs.js'
import type { EmphasisTier, Route } from './types.js'
import { useLegGeometries } from './useLegGeometries.js'

/** Line widths in px. */
const HIT_WIDTH = 16
const HIGHLIGHT_EXTRA = 4

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
 *  without geometry) are dashed straight lines between their huts. `tier` picks the panes, `thin`
 *  the candidate line widths. Hover and click come from a wide invisible hit line per leg. */
export default function RouteLayer({ route, highlightedLeg = null, fit = false, tier = 'hovered', thin = false, dots = true, interactive = true, cursor = null, onHover, onClick }: {
  route: Route
  highlightedLeg?: number | null
  fit?: boolean
  /** Emphasis tier: picks the route's panes (opacity and stacking). */
  tier?: EmphasisTier
  /** Thin candidate style instead of the bold selected-route style. */
  thin?: boolean
  /** false draws lines only (Discover draws waypoint symbols in a separate layer). */
  dots?: boolean
  /** false draws a display-only copy that never receives pointer events. */
  interactive?: boolean
  /** Position hovered on the height profile, drawn as a dot on its leg. */
  cursor?: ProfilePosition | null
  onHover?: (hovering: boolean, legIndex: number, at: L.LatLng) => void
  onClick?: (legIndex: number) => void
}) {
  const positions = useMemo(() => route.waypoints.map((w): [number, number] => [w.lat, w.lng]), [route])
  const geometries = useLegGeometries(route)
  const segments = segmentsOf(positions, geometries)
  const cursorSegment = cursor ? segments[cursor.legIndex] ?? null : null
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
        const highlighted = highlightedLeg === i
        const width = highlighted ? baseWidth + HIGHLIGHT_EXTRA : baseWidth
        const strokeOpacity = highlightedLeg !== null && !highlighted ? opacity.dimmed : 1
        const dash = seg.isFallback ? '6 8' : undefined
        return (
          <Fragment key={i}>
            <Polyline positions={seg.positions} pane={casingPane} pathOptions={{ color: tokens.ink, weight: width + (thin ? 2 : 4), dashArray: dash, opacity: strokeOpacity }} interactive={false} />
            <Polyline positions={seg.positions} pane={linePane} pathOptions={{ color: tokens.signpost, weight: width, dashArray: dash, opacity: strokeOpacity }} interactive={false} />
            {interactive && (
              <Polyline
                positions={seg.positions} pane={LEG_HIT_PANE} interactive bubblingMouseEvents={false}
                pathOptions={{ weight: HIT_WIDTH, opacity: 0 }}
                eventHandlers={{ mouseover: (e) => onHover?.(true, i, e.latlng), mouseout: (e) => onHover?.(false, i, e.latlng), click: () => onClick?.(i) }}
              />
            )}
          </Fragment>
        )
      })}
      {dots && positions.map((pos, i) => (
        <CircleMarker
          key={i} center={pos} pane={dotPane} radius={i === 0 || i === positions.length - 1 ? 6 : 4}
          pathOptions={{ color: tokens.ink, fillColor: tokens.signpost, fillOpacity: 1, weight: 2, interactive: false }}
        />
      ))}
      {cursorSegment && (
        <CircleMarker
          center={pointAlong(cursorSegment.positions, cursor!.fraction)} pane={dotPane} radius={5} interactive={false}
          pathOptions={{ color: tokens.ink, fillColor: tokens.white, fillOpacity: 1, weight: 2 }}
        />
      )}
    </>
  )
}
