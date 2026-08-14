import { useEffect, useState } from 'react'
import { MapContainer, TileLayer, CircleMarker, Tooltip } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import './App.css'

const QUERY_URL =
  'https://services1.arcgis.com/PHS4LHADrqt5glC9/ArcGIS/rest/services/' +
  'AVT_GEO_CAA_HUETTEN_View_P/FeatureServer/0/query' +
  '?f=json&where=1%3D1&outFields=*&outSR=4326&returnGeometry=true' +
  '&resultRecordCount=8000&orderByFields=OBJECTID%20ASC'

function App() {
  const [huts, setHuts] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch(QUERY_URL)
      .then((r) => r.json())
      .then((data) => {
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
              lat: f.geometry.y,
              lng: f.geometry.x,
            }))
        )
      })
      .catch((e) => setError(e.message))
  }, [])

  return (
    <div className="app">
      <header>
        <h1>Alpenvereinshütten</h1>
        <a href="#graph" className="nav-link">
          Trail-Graph
        </a>
        <span>{error ? `Fehler: ${error}` : `${huts.length} Hütten`}</span>
      </header>
      <MapContainer center={[47.3, 12.0]} zoom={7} className="map">
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
      </MapContainer>
    </div>
  )
}

export default App
