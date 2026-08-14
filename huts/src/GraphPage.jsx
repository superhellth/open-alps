import { useEffect, useMemo, useRef, useState } from 'react'
import { MapContainer, TileLayer, CircleMarker, Polyline, Tooltip, useMap } from 'react-leaflet'
import L from 'leaflet'
import { leafletLayer, LineSymbolizer } from 'protomaps-leaflet'
import 'leaflet/dist/leaflet.css'
import './App.css'

const EDGES_URL = '/data/hut-edges.geojson'
const HUTS_URL = '/data/huts.geojson'
const TRAILS_PMTILES_URL = '/data/trails.pmtiles'

// How close the cursor has to be to a trail polyline to count as "hovering" it, in screen
// pixels - constant across zoom levels since it's a hit-test tolerance, not a map distance.
const HOVER_THRESHOLD_PX = 6

function distToSegmentPx(p, a, b) {
  const dx = b.x - a.x
  const dy = b.y - a.y
  if (dx === 0 && dy === 0) return Math.hypot(p.x - a.x, p.y - a.y)
  let t = ((p.x - a.x) * dx + (p.y - a.y) * dy) / (dx * dx + dy * dy)
  t = Math.max(0, Math.min(1, t))
  return Math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy))
}

function distToPolylinePx(map, cursorPt, positions) {
  let min = Infinity
  for (let i = 0; i < positions.length - 1; i++) {
    const a = map.latLngToContainerPoint(positions[i])
    const b = map.latLngToContainerPoint(positions[i + 1])
    const d = distToSegmentPx(cursorPt, a, b)
    if (d < min) min = d
  }
  return min
}

// Degrees-per-pixel at the cursor's location, used to cheaply pre-filter which edges are even
// worth a precise (per-vertex) pixel-distance check - avoids walking every polyline's full
// vertex list on every mousemove.
function degreesPerPixel(map, cursorPt) {
  const a = map.containerPointToLatLng(cursorPt)
  const b = map.containerPointToLatLng(L.point(cursorPt.x + HOVER_THRESHOLD_PX, cursorPt.y))
  return Math.abs(b.lng - a.lng)
}

/**
 * Renders no visible layer itself - just listens for mousemove on the underlying Leaflet map
 * and reports every edge whose trail polyline passes within HOVER_THRESHOLD_PX of the cursor,
 * not just whichever one Leaflet's native per-shape hit-testing would pick (the topmost path).
 * That's the only way to surface every edge in a stack of overlapping/contained trails.
 */
function HoverInspector({ edges, onHover }) {
  const map = useMap()

  useEffect(() => {
    function handleMove(e) {
      const cursorPt = map.latLngToContainerPoint(e.latlng)
      const bufferDeg = degreesPerPixel(map, cursorPt) * HOVER_THRESHOLD_PX
      const cursorLatLng = e.latlng

      const matches = []
      for (let i = 0; i < edges.length; i++) {
        const edge = edges[i]
        if (!edge.bounds.pad(0).contains(cursorLatLng)) {
          // cheap reject unless within a buffered bbox first
          const padded = L.latLngBounds(
            [edge.bounds.getSouth() - bufferDeg, edge.bounds.getWest() - bufferDeg],
            [edge.bounds.getNorth() + bufferDeg, edge.bounds.getEast() + bufferDeg]
          )
          if (!padded.contains(cursorLatLng)) continue
        }
        const distPx = distToPolylinePx(map, cursorPt, edge.positions)
        if (distPx <= HOVER_THRESHOLD_PX) matches.push({ index: i, distPx })
      }
      matches.sort((a, b) => a.distPx - b.distPx)

      if (matches.length === 0) {
        onHover(null)
      } else {
        onHover({
          x: e.originalEvent.clientX,
          y: e.originalEvent.clientY,
          indices: matches.map((m) => m.index),
        })
      }
    }

    function handleLeave() {
      onHover(null)
    }

    map.on('mousemove', handleMove)
    map.on('mouseout', handleLeave)
    return () => {
      map.off('mousemove', handleMove)
      map.off('mouseout', handleLeave)
    }
  }, [map, edges, onHover])

  return null
}

/**
 * The raw OSM trail network (data/osm/trails.osm.pbf, ~26.5M nodes) is too large to ship as
 * GeoJSON, so it's pre-built (data/scripts/09-build-trail-tiles.py) into a single static
 * PMTiles vector-tile archive and rendered client-side via protomaps-leaflet - no tile server,
 * just an HTTP range-request-able file, same "no backend" shape as every other asset here.
 */
function TrailTilesLayer({ visible }) {
  const map = useMap()
  const layerRef = useRef(null)

  useEffect(() => {
    if (!layerRef.current) {
      layerRef.current = leafletLayer({
        url: TRAILS_PMTILES_URL,
        maxDataZoom: 14,
        paintRules: [
          {
            dataLayer: 'trails',
            symbolizer: new LineSymbolizer({ color: '#7b1fa2', width: 1, opacity: 0.5 }),
          },
        ],
      })
    }
    if (visible) layerRef.current.addTo(map)
    return () => {
      map.removeLayer(layerRef.current)
    }
  }, [map, visible])

  return null
}

const SPARKLINE_WIDTH = 120
const SPARKLINE_HEIGHT = 32

/**
 * Small inline-SVG height profile for one edge, from its elevation_profile (script 08's
 * downsampled, evenly-distance-spaced elevation series) - no charting library needed at this
 * size. Flat/near-flat profiles get a fallback range so the line doesn't look broken.
 */
function ElevationSparkline({ values }) {
  if (!values || values.length < 2) return null

  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1

  const points = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * SPARKLINE_WIDTH
      const y = SPARKLINE_HEIGHT - ((v - min) / range) * SPARKLINE_HEIGHT
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')

  return (
    <svg
      className="elevation-sparkline"
      width={SPARKLINE_WIDTH}
      height={SPARKLINE_HEIGHT}
      viewBox={`0 0 ${SPARKLINE_WIDTH} ${SPARKLINE_HEIGHT}`}
    >
      <polyline points={points} fill="none" stroke="#e65100" strokeWidth="1.5" />
    </svg>
  )
}

function GraphPage() {
  const [edges, setEdges] = useState([])
  const [huts, setHuts] = useState([])
  const [error, setError] = useState(null)
  const [hover, setHover] = useState(null) // { x, y, indices: number[] } | null
  const [showTrails, setShowTrails] = useState(false)

  useEffect(() => {
    Promise.all([fetch(EDGES_URL).then((r) => r.json()), fetch(HUTS_URL).then((r) => r.json())])
      .then(([edgesFc, hutsFc]) => {
        setEdges(
          edgesFc.features.map((f) => {
            const positions = f.geometry.coordinates.map(([lng, lat]) => [lat, lng])
            return {
              fromId: f.properties.from_hut_id,
              toId: f.properties.to_hut_id,
              distanceM: f.properties.distance_m,
              ascentM: f.properties.ascent_m,
              descentM: f.properties.descent_m,
              elevationProfile: f.properties.elevation_profile,
              positions,
              bounds: L.latLngBounds(positions),
            }
          })
        )
        setHuts(
          hutsFc.features.map((f) => ({
            id: f.properties.id,
            name: f.properties.name,
            lat: f.geometry.coordinates[1],
            lng: f.geometry.coordinates[0],
          }))
        )
      })
      .catch((e) => setError(e.message))
  }, [])

  const connectedIds = useMemo(() => new Set(edges.flatMap((e) => [e.fromId, e.toId])), [edges])
  const hutNameById = useMemo(() => new Map(huts.map((h) => [h.id, h.name])), [huts])
  const hoveredSet = useMemo(() => new Set(hover?.indices ?? []), [hover])

  return (
    <div className="app">
      <header>
        <h1>Hütten-Trail-Graph</h1>
        <a href="#" className="nav-link">
          Karte
        </a>
        <span>
          {error
            ? `Fehler: ${error}`
            : `${huts.length} Hütten, ${edges.length} Kanten (${connectedIds.size} verbunden)`}
        </span>
        <label className="layer-toggle">
          <input
            type="checkbox"
            checked={showTrails}
            onChange={(e) => setShowTrails(e.target.checked)}
          />
          OSM-Wege (roh)
        </label>
      </header>
      <MapContainer center={[47.3, 12.0]} zoom={7} className="map">
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> | Hüttendaten: Alpenverein / ArcGIS'
        />
        <TrailTilesLayer visible={showTrails} />
        <HoverInspector edges={edges} onHover={setHover} />
        {edges.map((edge, i) => (
          <Polyline
            key={`${edge.fromId}-${edge.toId}-${i}`}
            positions={edge.positions}
            interactive={false}
            pathOptions={
              hoveredSet.has(i)
                ? { color: '#ff1744', weight: 5, opacity: 1 }
                : { color: '#e65100', weight: 2, opacity: 0.7 }
            }
          />
        ))}
        {huts.map((hut) => (
          <CircleMarker
            key={hut.id}
            center={[hut.lat, hut.lng]}
            radius={connectedIds.has(hut.id) ? 4 : 3}
            pathOptions={
              connectedIds.has(hut.id)
                ? { color: '#1b5e20', fillColor: '#43a047', fillOpacity: 0.9, weight: 1 }
                : { color: '#616161', fillColor: '#bdbdbd', fillOpacity: 0.6, weight: 1 }
            }
          >
            <Tooltip direction="top" offset={[0, -6]}>
              {hut.name}
            </Tooltip>
          </CircleMarker>
        ))}
      </MapContainer>
      {hover && hover.indices.length > 0 && (
        <div
          className="edge-hover-panel"
          style={{ left: hover.x + 14, top: hover.y + 14 }}
        >
          {hover.indices.map((i) => {
            const edge = edges[i]
            return (
              <div key={i} className="edge-hover-row">
                <strong>
                  {hutNameById.get(edge.fromId) ?? edge.fromId} → {hutNameById.get(edge.toId) ?? edge.toId}
                </strong>
                <span>
                  {(edge.distanceM / 1000).toFixed(1)} km
                  {edge.ascentM != null && edge.descentM != null
                    ? ` · ↑${Math.round(edge.ascentM)}m ↓${Math.round(edge.descentM)}m`
                    : ''}
                </span>
                <ElevationSparkline values={edge.elevationProfile} />
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default GraphPage
