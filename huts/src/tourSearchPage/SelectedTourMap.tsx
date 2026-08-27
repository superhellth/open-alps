import { Box, Typography } from '@mui/material'
import { MapContainer, TileLayer, CircleMarker, Polyline } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import type { TourResult } from '../tourSearch/types.js'
import type { StartPoint } from './types.js'

function SelectedTourMap({
  chain, hutCoordsById, startById,
}: {
  chain: TourResult
  hutCoordsById: Map<number, { lat: number; lng: number }>
  startById: Map<number, StartPoint>
}) {
  const startPoint = startById.get(chain.startId)
  const endPoint = startById.get(chain.exitStartId)
  const hutPoints = chain.huts.map((h) => hutCoordsById.get(h)).filter((p): p is { lat: number; lng: number } => !!p)
  const positions: [number, number][] = [
    ...(startPoint ? [[startPoint.lat, startPoint.lng] as [number, number]] : []),
    ...hutPoints.map((p): [number, number] => [p.lat, p.lng]),
    ...(endPoint ? [[endPoint.lat, endPoint.lng] as [number, number]] : []),
  ]
  if (positions.length < 2) return null

  const center = positions[Math.floor(positions.length / 2)]

  return (
    <Box>
      <MapContainer center={center} zoom={11} style={{ height: 260, width: '100%' }}>
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        />
        <Polyline positions={positions} pathOptions={{ color: '#e65100', weight: 3, dashArray: '6 8' }} />
        {startPoint && (
          <CircleMarker center={[startPoint.lat, startPoint.lng]} radius={6} pathOptions={{ color: '#1b5e20', fillColor: '#43a047', fillOpacity: 1 }} />
        )}
        {endPoint && (
          <CircleMarker center={[endPoint.lat, endPoint.lng]} radius={6} pathOptions={{ color: '#1b5e20', fillColor: '#43a047', fillOpacity: 1 }} />
        )}
      </MapContainer>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
        Schematische Verbindung, nicht der reale Wegverlauf.
      </Typography>
    </Box>
  )
}

export default SelectedTourMap
