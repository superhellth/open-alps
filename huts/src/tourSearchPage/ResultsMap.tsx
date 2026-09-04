import { memo, useEffect, useMemo, useState } from 'react'
import { Box, Typography } from '@mui/material'
import { MapContainer, TileLayer, CircleMarker, Tooltip, Polyline, useMap } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { loadLegGeometry } from '../tourSearch/loadLegGeometry.js'
import { SOURCE_TYPE_PARTNER } from '../tourSearch/types.js'
import type { Route } from './types.js'
import type { StartPoint } from './types.js'
import { OPERATOR_COLOR, OPERATOR_LABEL, PARTNER_COLOR, PARTNER_LABEL, hutClassLabel, type HutClass } from '../hutClass.js'

const TILE_LAYER = (
  <TileLayer
    url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> | Hüttendaten: Alpenverein / ArcGIS'
  />
)

function routePositions(route: Route): [number, number][] {
  return route.waypoints.map((w): [number, number] => [w.lat, w.lng])
}

// Recenters/refits the map when a route is selected (or a different one replaces it), but
// deliberately does nothing when route goes back to null - deselecting/minimizing a route must
// leave the user's current pan/zoom untouched. fitBounds (not a fixed zoom) because official
// tours run 4-8 legs over much longer distances than the 2-4-leg search chains this was originally
// tuned for - a fixed zoom tuned for the latter runs an official tour off both edges of the view.
function RecenterOnSelect({ route }: { route: Route | null }) {
  const map = useMap()
  useEffect(() => {
    if (!route) return
    const positions = routePositions(route)
    if (positions.length < 2) return
    map.fitBounds(positions, { padding: [24, 24] })
  }, [map, route])
  return null
}

/** Resolves each leg's real trail geometry for the selected route (spec F, generalized). While a
 *  leg's fetch is in flight, or if it rejects, its entry stays null so the caller falls back to a
 *  straight segment between that leg's own endpoints - the route is never blank while loading. */
function useLegGeometries(route: Route | null): ([number, number][] | null)[] {
  const [geometries, setGeometries] = useState<([number, number][] | null)[]>([])

  useEffect(() => {
    if (!route || route.waypoints.length !== route.legs.length + 1) {
      setGeometries([])
      return
    }
    const legs = route.legs
    setGeometries(new Array(legs.length).fill(null))
    let cancelled = false
    legs.forEach((leg, i) => {
      loadLegGeometry(leg.layer, leg.edgeId, leg.reversed).then(
        (points) => {
          if (cancelled) return
          setGeometries((prev) => {
            const next = [...prev]
            next[i] = points
            return next
          })
        },
        () => {
          // Leave this leg's entry null - its straight-line fallback segment stays in place.
        },
      )
    })
    return () => {
      cancelled = true
    }
  }, [route])

  return geometries
}

interface ChainSegment {
  positions: [number, number][]
  isFallback: boolean
}

function chainSegments(
  positions: [number, number][],
  legGeometries: ([number, number][] | null)[],
): ChainSegment[] {
  return positions.slice(0, -1).map((from, i) => {
    const real = legGeometries[i]
    if (real && real.length >= 2) return { positions: real, isFallback: false }
    return { positions: [from, positions[i + 1]], isFallback: true }
  })
}

// Persistent map pane next to the results list: shows every hut when no route is selected, and
// the selected route (a search chain or an official tour, generalized to Route) once one is
// picked - real routed trail geometry per leg once it resolves, a straight dashed fallback for
// legs still loading or that failed to resolve - so the map is never replaced by the list. A
// single MapContainer stays mounted across selection changes so the current pan/zoom survives
// deselecting a route.
const ResultsMap = memo(function ResultsMap({
  route, hutNameById, hutCoordsById, startById, hutClassByIndex, excludedHutIndices,
}: {
  route: Route | null
  hutNameById: Map<number, string>
  hutCoordsById: Map<number, { lat: number; lng: number }>
  startById: Map<number, StartPoint>
  hutClassByIndex: Map<number, HutClass>
  excludedHutIndices: Set<number>
}) {
  const positions = useMemo(() => (route ? routePositions(route) : []), [route])
  const showRoute = route !== null && positions.length >= 2
  const legGeometries = useLegGeometries(route)
  const segments = showRoute ? chainSegments(positions, legGeometries) : []
  const anyFallback = segments.some((s) => s.isFallback)

  return (
    <Box sx={{ position: 'relative', height: '100%', width: '100%' }}>
      <MapContainer center={[47.3, 12.0]} zoom={7} style={{ height: '100%', width: '100%' }}>
        {TILE_LAYER}
        <RecenterOnSelect route={route} />
        {!showRoute &&
          [...hutCoordsById.entries()].map(([id, { lat, lng }]) => {
            const cls = hutClassByIndex.get(id)
            const excluded = excludedHutIndices.has(id)
            const color = cls ? OPERATOR_COLOR[cls.operator] : '#1b5e20'
            return (
              <CircleMarker
                key={id}
                center={[lat, lng]}
                radius={4}
                pathOptions={{
                  color,
                  fillColor: color,
                  fillOpacity: excluded ? 0.25 : cls?.serviced === false ? 0.15 : 0.9,
                  weight: excluded ? 1 : cls?.serviced === false ? 2 : 1,
                }}
              >
                <Tooltip direction="top" offset={[0, -6]}>
                  {hutNameById.get(id) ?? id}
                  {cls ? ` — ${hutClassLabel(cls)}` : ''}
                </Tooltip>
              </CircleMarker>
            )
          })}
        {!showRoute &&
          [...startById.entries()]
            .filter(([, s]) => s.sourceType === SOURCE_TYPE_PARTNER)
            .map(([id, s]) => (
              <CircleMarker
                key={`partner-${id}`}
                center={[s.lat, s.lng]}
                radius={5}
                pathOptions={{ color: PARTNER_COLOR, fillColor: PARTNER_COLOR, fillOpacity: 0.9, weight: 1 }}
              >
                <Tooltip direction="top" offset={[0, -6]}>
                  {s.name ?? PARTNER_LABEL} ({PARTNER_LABEL})
                </Tooltip>
              </CircleMarker>
            ))}
        {showRoute && (
          <>
            {segments.map((seg, i) => (
              <Polyline
                key={i}
                positions={seg.positions}
                pathOptions={
                  seg.isFallback
                    ? { color: '#e65100', weight: 3, dashArray: '6 8' }
                    : { color: '#e65100', weight: 3 }
                }
              />
            ))}
            {/* Route waypoints don't carry hut identity (Route is generic over search chains and
                official tours alike), so unlike the overview markers above these render in one
                fixed style rather than colored by operator - the endpoints are just drawn larger. */}
            {positions.map((pos, i) => {
              const isEndpoint = i === 0 || i === positions.length - 1
              return (
                <CircleMarker
                  key={i}
                  center={pos}
                  radius={isEndpoint ? 6 : 5}
                  pathOptions={{ color: '#1b5e20', fillColor: '#1b5e20', fillOpacity: 1 }}
                />
              )
            })}
          </>
        )}
      </MapContainer>
      <Box
        sx={{
          position: 'absolute', top: 8, right: 8, zIndex: 1000, bgcolor: 'background.paper',
          p: 1, borderRadius: 1, fontSize: '0.75rem', display: 'flex', flexDirection: 'column', gap: 0.5,
        }}
      >
        {(Object.keys(OPERATOR_LABEL) as (keyof typeof OPERATOR_LABEL)[]).map((op) => (
          <Box key={op} sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <Box sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: OPERATOR_COLOR[op] }} />
            {OPERATOR_LABEL[op]}
          </Box>
        ))}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          <Box sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: PARTNER_COLOR }} />
          {PARTNER_LABEL}
        </Box>
      </Box>
      {showRoute && anyFallback && (
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ position: 'absolute', bottom: 4, left: 4, bgcolor: 'background.paper', px: 0.5, borderRadius: 0.5, zIndex: 1000 }}
        >
          Schematische Verbindung, nicht der reale Wegverlauf.
        </Typography>
      )}
    </Box>
  )
})

export default ResultsMap
