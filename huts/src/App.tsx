import { useEffect, useState } from 'react'
import { MapContainer, TileLayer, CircleMarker, Tooltip } from 'react-leaflet'
import { Box, FormControlLabel, Switch } from '@mui/material'
import 'leaflet/dist/leaflet.css'
import AppShell from './AppShell.js'

const QUERY_URL =
  'https://services1.arcgis.com/PHS4LHADrqt5glC9/ArcGIS/rest/services/' +
  'AVT_GEO_CAA_HUETTEN_View_P/FeatureServer/0/query' +
  '?f=json&where=1%3D1&outFields=*&outSR=4326&returnGeometry=true' +
  '&resultRecordCount=8000&orderByFields=OBJECTID%20ASC'

const STATIONS_URL = '/data/stations.geojson'
const PARKING_URL = '/data/parking.geojson'

interface Hut {
  id: number
  name: string
  elevation: number | null
  category: string | null
  club: string | null
  lat: number
  lng: number
}

interface GeoPoint {
  id: number
  name: string | null
  lat: number
  lng: number
  [key: string]: unknown
}

interface ArcGisFeature {
  geometry?: { x: number; y: number }
  attributes: { OBJECTID: number; name: string; meereshoehe: number | null; kategorie: string | null; verein_name: string | null }
}

function pointsFromGeojson(fc: GeoJSON.FeatureCollection): GeoPoint[] {
  return fc.features.map((f, i) => ({
    id: i,
    name: (f.properties as Record<string, unknown> | null)?.name as string | null ?? null,
    ...(f.properties ?? {}),
    lat: (f.geometry as GeoJSON.Point).coordinates[1],
    lng: (f.geometry as GeoJSON.Point).coordinates[0],
  }))
}

function App() {
  const [huts, setHuts] = useState<Hut[]>([])
  const [stations, setStations] = useState<GeoPoint[]>([])
  const [parking, setParking] = useState<GeoPoint[]>([])
  const [showStations, setShowStations] = useState(false)
  const [showParking, setShowParking] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch(QUERY_URL)
      .then((r) => r.json())
      .then((data: { error?: { message: string }; features: ArcGisFeature[] }) => {
        if (data.error) throw new Error(data.error.message)
        setHuts(
          data.features
            .filter((f) => f.geometry)
            .map((f) => ({
              id: f.attributes.OBJECTID,
              name: f.attributes.name,
              elevation: f.attributes.meereshoehe,
              category: f.attributes.kategorie,
              club: f.attributes.verein_name,
              lat: f.geometry!.y,
              lng: f.geometry!.x,
            })),
        )
      })
      .catch((e: Error) => setError(e.message))

    fetch(STATIONS_URL)
      .then((r) => r.json())
      .then((fc: GeoJSON.FeatureCollection) => setStations(pointsFromGeojson(fc)))
      .catch((e: Error) => setError(e.message))

    fetch(PARKING_URL)
      .then((r) => r.json())
      .then((fc: GeoJSON.FeatureCollection) => setParking(pointsFromGeojson(fc)))
      .catch((e: Error) => setError(e.message))
  }, [])

  return (
    <AppShell
      title="Alpenvereinshütten"
      status={
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <span>{error ? `Fehler: ${error}` : `${huts.length} Hütten`}</span>
          <FormControlLabel
            control={<Switch size="small" checked={showStations} onChange={(e) => setShowStations(e.target.checked)} />}
            label="Bahnhöfe"
            sx={{ color: 'inherit', m: 0 }}
          />
          <FormControlLabel
            control={<Switch size="small" checked={showParking} onChange={(e) => setShowParking(e.target.checked)} />}
            label="Parkplätze"
            sx={{ color: 'inherit', m: 0 }}
          />
        </Box>
      }
    >
      <MapContainer center={[47.3, 12.0]} zoom={7} style={{ flex: 1 }}>
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> | Hüttendaten: Alpenverein / ArcGIS'
        />
        {huts.map((hut) => (
          <CircleMarker
            key={hut.id}
            center={[hut.lat, hut.lng]}
            radius={5}
            pathOptions={{ color: '#1b5e20', fillColor: '#43a047', fillOpacity: 0.9, weight: 1 }}
          >
            <Tooltip direction="top" offset={[0, -6]}>
              <strong>{hut.name}</strong>
              {hut.elevation ? <div>{hut.elevation} m</div> : null}
              {hut.category ? <div>{hut.category}</div> : null}
              {hut.club ? <div>{hut.club}</div> : null}
            </Tooltip>
          </CircleMarker>
        ))}
        {showParking &&
          parking.map((p) => (
            <CircleMarker
              key={`parking-${p.id}`}
              center={[p.lat, p.lng]}
              radius={3}
              pathOptions={{ color: '#0d47a1', fillColor: '#42a5f5', fillOpacity: 0.9, weight: 1 }}
            >
              <Tooltip direction="top" offset={[0, -6]}>
                <strong>{(p.name as string) || 'Parkplatz'}</strong>
                {p.capacity ? <div>{String(p.capacity)} Plätze</div> : null}
                {p.fee ? <div>Gebühr: {String(p.fee)}</div> : null}
              </Tooltip>
            </CircleMarker>
          ))}
        {showStations &&
          stations.map((s) => (
            <CircleMarker
              key={`station-${s.id}`}
              center={[s.lat, s.lng]}
              radius={4}
              pathOptions={{ color: '#e65100', fillColor: '#ff9800', fillOpacity: 0.9, weight: 1 }}
            >
              <Tooltip direction="top" offset={[0, -6]}>
                <strong>{(s.name as string) || 'Bahnhof'}</strong>
                {s.operator ? <div>{String(s.operator)}</div> : null}
              </Tooltip>
            </CircleMarker>
          ))}
      </MapContainer>
    </AppShell>
  )
}

export default App
