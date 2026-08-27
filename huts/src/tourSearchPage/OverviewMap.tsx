import { memo } from 'react'
import { MapContainer, TileLayer, CircleMarker, Tooltip } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'

// Memoized because the ~1200 hut CircleMarker/Tooltip elements are otherwise reconciled on
// every keystroke/slider-drag in the sibling form (hutNameById/hutCoordsById never change after
// the initial load, so this never actually needs to re-render).
const OverviewMap = memo(function OverviewMap({
  hutNameById, hutCoordsById,
}: {
  hutNameById: Map<number, string>
  hutCoordsById: Map<number, { lat: number; lng: number }>
}) {
  return (
    <MapContainer center={[47.3, 12.0]} zoom={7} style={{ flex: 1, height: '100%', width: '100%' }}>
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> | Hüttendaten: Alpenverein / ArcGIS'
      />
      {[...hutCoordsById.entries()].map(([id, { lat, lng }]) => (
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
    </MapContainer>
  )
})

export default OverviewMap
