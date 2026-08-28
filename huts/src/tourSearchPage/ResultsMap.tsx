import { memo, useEffect, useMemo, useState } from 'react'
import { Box, Typography } from '@mui/material'
import { MapContainer, TileLayer, CircleMarker, Tooltip, Polyline, useMap } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { loadLegGeometry, type GeometryLayer } from '../tourSearch/loadLegGeometry.js'
import type { TourResult } from '../tourSearch/types.js'
import type { StartPoint } from './types.js'

const TILE_LAYER = (
  <TileLayer
    url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> | Hüttendaten: Alpenverein / ArcGIS'
  />
)

function chainPositions(
  chain: TourResult,
  hutCoordsById: Map<number, { lat: number; lng: number }>,
  startById: Map<number, StartPoint>,
): [number, number][] {
  const startPoint = startById.get(chain.startId)
  const endPoint = startById.get(chain.exitStartId)
  const hutPoints = chain.huts.map((h) => hutCoordsById.get(h)).filter((p): p is { lat: number; lng: number } => !!p)
  return [
    ...(startPoint ? [[startPoint.lat, startPoint.lng] as [number, number]] : []),
    ...hutPoints.map((p): [number, number] => [p.lat, p.lng]),
    ...(endPoint ? [[endPoint.lat, endPoint.lng] as [number, number]] : []),
  ]
}

// Recenters the map when a tour is selected (or a different one replaces it), but deliberately
// does nothing when selectedChain goes back to null - deselecting/minimizing a tour must leave
// the user's current pan/zoom untouched rather than snapping back to the overview view.
function RecenterOnSelect({
  selectedChain, hutCoordsById, startById,
}: {
  selectedChain: TourResult | null
  hutCoordsById: Map<number, { lat: number; lng: number }>
  startById: Map<number, StartPoint>
}) {
  const map = useMap()
  useEffect(() => {
    if (!selectedChain) return
    const positions = chainPositions(selectedChain, hutCoordsById, startById)
    if (positions.length < 2) return
    map.setView(positions[Math.floor(positions.length / 2)], 11)
    // Only re-run when the selected chain itself changes - hutCoordsById/startById are loaded
    // once and stable, and including them would refire this on unrelated parent re-renders.
  }, [map, selectedChain])
  return null
}

function legLayer(legIndex: number, legCount: number): GeometryLayer {
  return legIndex === 0 || legIndex === legCount - 1 ? 'start_edges' : 'hut_edges'
}

/** Resolves each leg's real trail geometry for the selected chain (spec F). While a leg's fetch
 *  is in flight, or if it rejects, its entry stays null so the caller falls back to a straight
 *  segment between that leg's own endpoints - the tour is never blank while loading. */
function useLegGeometries(
  selectedChain: TourResult | null,
  positions: [number, number][],
): ([number, number][] | null)[] {
  const [geometries, setGeometries] = useState<([number, number][] | null)[]>([])

  useEffect(() => {
    if (!selectedChain || positions.length !== selectedChain.legs.length + 1) {
      setGeometries([])
      return
    }
    const legs = selectedChain.legs
    setGeometries(new Array(legs.length).fill(null))
    let cancelled = false
    legs.forEach((leg, i) => {
      loadLegGeometry(legLayer(i, legs.length), leg.edgeId, leg.reversed).then(
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
  }, [selectedChain, positions])

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

// Persistent map pane next to the results list: shows every hut when no tour is selected, and
// the selected tour's route once a result card is expanded - real routed trail geometry per leg
// once it resolves, a straight dashed fallback for legs still loading or that failed to resolve
// - so the map is never replaced by the list. A single MapContainer stays mounted across
// selection changes so the current pan/zoom survives deselecting a tour.
const ResultsMap = memo(function ResultsMap({
  selectedChain, hutNameById, hutCoordsById, startById,
}: {
  selectedChain: TourResult | null
  hutNameById: Map<number, string>
  hutCoordsById: Map<number, { lat: number; lng: number }>
  startById: Map<number, StartPoint>
}) {
  const positions = useMemo(
    () => (selectedChain ? chainPositions(selectedChain, hutCoordsById, startById) : []),
    [selectedChain, hutCoordsById, startById],
  )
  const showChain = selectedChain !== null && positions.length >= 2
  const legGeometries = useLegGeometries(selectedChain, positions)
  const segments = showChain ? chainSegments(positions, legGeometries) : []
  const anyFallback = segments.some((s) => s.isFallback)

  return (
    <Box sx={{ position: 'relative', height: '100%', width: '100%' }}>
      <MapContainer center={[47.3, 12.0]} zoom={7} style={{ height: '100%', width: '100%' }}>
        {TILE_LAYER}
        <RecenterOnSelect selectedChain={selectedChain} hutCoordsById={hutCoordsById} startById={startById} />
        {!showChain &&
          [...hutCoordsById.entries()].map(([id, { lat, lng }]) => (
            <CircleMarker
              key={id}
              center={[lat, lng]}
              radius={4}
              pathOptions={{ color: '#1b5e20', fillColor: '#43a047', fillOpacity: 0.9, weight: 1 }}
            >
              <Tooltip direction="top" offset={[0, -6]}>
                {hutNameById.get(id) ?? id}
              </Tooltip>
            </CircleMarker>
          ))}
        {showChain && (
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
            {positions.map((pos, i) => (
              <CircleMarker
                key={i}
                center={pos}
                radius={i === 0 || i === positions.length - 1 ? 6 : 5}
                pathOptions={{ color: '#1b5e20', fillColor: '#43a047', fillOpacity: 1 }}
              />
            ))}
          </>
        )}
      </MapContainer>
      {showChain && anyFallback && (
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
