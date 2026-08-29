import { useEffect, useMemo, useRef, useState } from 'react'
import { MapContainer, TileLayer, CircleMarker, Polyline, Tooltip, useMap } from 'react-leaflet'
import L from 'leaflet'
import { leafletLayer, LineSymbolizer } from 'protomaps-leaflet'
import { Box, FormControlLabel, Switch } from '@mui/material'
import 'leaflet/dist/leaflet.css'
import './App.css'
import AppShell from './AppShell.js'
import { hutClassBadge, hutClassLabel, OPERATOR_COLOR, OPERATOR_LABEL, PARTNER_COLOR, PARTNER_LABEL, type HutClass, type HutOperator } from './hutClass.js'

const EDGE_STATS_URL = '/data/hut-edge-stats.json'
const HUTS_URL = '/data/huts.geojson'
const TRAILS_PMTILES_URL = '/data/trails.pmtiles'
const HUT_EDGES_PMTILES_URL = '/data/hut-edges.pmtiles'
const EDGE_GEOMETRY_MANIFEST_URL = '/data/hut-edge-geometry.json'
const EDGE_GEOMETRY_BIN_URL = '/data/hut-edge-geometry.bin'
const PARTNER_URL = '/data/partner_betriebe.geojson'

// How close the cursor has to be to a trail polyline to count as "hovering" it, in screen
// pixels - constant across zoom levels since it's a hit-test tolerance, not a map distance.
const HOVER_THRESHOLD_PX = 6

interface Edge {
  fromId: number
  toId: number
  distanceM: number
  roadM: number
  ascentM: number | null
  descentM: number | null
  elevationProfile: number[] | null
  sacScale: string | null
  viaFerrata: boolean
  positions: L.LatLngExpression[]
  bounds: L.LatLngBounds
}

interface Hut {
  id: number
  name: string
  lat: number
  lng: number
  hutClass: HutClass | null
}

interface PartnerPoint {
  id: number
  name: string
  lat: number
  lng: number
}

interface Hover {
  x: number
  y: number
  indices: number[]
}

interface EdgeStatsEntry {
  from_hut_id: number
  to_hut_id: number
  distance_m: number
  road_m: number
  ascent_m: number | null
  descent_m: number | null
  elevation_profile: number[] | null
  sac_scale: string | null
  via_ferrata: boolean
}

interface EdgeGeometryManifest {
  point_counts: number[]
}

/** Decodes hut-edge-geometry.bin's flat f4 [lon, lat] point stream (edge_id order, no framing)
 *  into one Leaflet-ready [lat, lng][] per edge, using point_counts as a prefix-sum offset table.
 *  Fetched whole rather than range-fetched (unlike ResultsMap's per-leg lookups) because
 *  HoverInspector below needs every edge's geometry at once. */
function decodeEdgeGeometry(manifest: EdgeGeometryManifest, buffer: ArrayBuffer): L.LatLngExpression[][] {
  const floats = new Float32Array(buffer)
  const perEdge: L.LatLngExpression[][] = new Array(manifest.point_counts.length)
  let pointOffset = 0
  for (let i = 0; i < manifest.point_counts.length; i++) {
    const count = manifest.point_counts[i]
    const positions: L.LatLngExpression[] = new Array(count)
    for (let p = 0; p < count; p++) {
      const base = (pointOffset + p) * 2
      positions[p] = [floats[base + 1], floats[base]]
    }
    perEdge[i] = positions
    pointOffset += count
  }
  return perEdge
}

function distToSegmentPx(p: L.Point, a: L.Point, b: L.Point): number {
  const dx = b.x - a.x
  const dy = b.y - a.y
  if (dx === 0 && dy === 0) return Math.hypot(p.x - a.x, p.y - a.y)
  let t = ((p.x - a.x) * dx + (p.y - a.y) * dy) / (dx * dx + dy * dy)
  t = Math.max(0, Math.min(1, t))
  return Math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy))
}

function distToPolylinePx(map: L.Map, cursorPt: L.Point, positions: L.LatLngExpression[]): number {
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
function degreesPerPixel(map: L.Map, cursorPt: L.Point): number {
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
function HoverInspector({ edges, onHover }: { edges: Edge[]; onHover: (hover: Hover | null) => void }) {
  const map = useMap()

  useEffect(() => {
    function handleMove(e: L.LeafletMouseEvent) {
      const cursorPt = map.latLngToContainerPoint(e.latlng)
      const bufferDeg = degreesPerPixel(map, cursorPt) * HOVER_THRESHOLD_PX
      const cursorLatLng = e.latlng

      const matches: { index: number; distPx: number }[] = []
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
          x: (e.originalEvent as MouseEvent).clientX,
          y: (e.originalEvent as MouseEvent).clientY,
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
function TrailTilesLayer({ visible }: { visible: boolean }) {
  const map = useMap()
  const layerRef = useRef<ReturnType<typeof leafletLayer> | null>(null)

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
      map.removeLayer(layerRef.current as unknown as L.Layer)
    }
  }, [map, visible])

  return null
}

/**
 * The derived hut-to-hut edges (data/osm/hut-edges.geojson, ~6,000 edges / ~7M vertices, ~184MB
 * as plain GeoJSON) render the same way the raw OSM network does - PMTiles + protomaps-leaflet,
 * not one React <Polyline> per edge - see data/scripts/11-build-hut-edge-tiles.py. Always on,
 * unlike TrailTilesLayer's toggle, since this is the graph view's primary layer.
 */
function HutEdgeTilesLayer() {
  const map = useMap()
  const layerRef = useRef<ReturnType<typeof leafletLayer> | null>(null)

  useEffect(() => {
    layerRef.current = leafletLayer({
      url: HUT_EDGES_PMTILES_URL,
      maxDataZoom: 14,
      paintRules: [
        {
          dataLayer: 'hut_edges',
          symbolizer: new LineSymbolizer({ color: '#e65100', width: 2, opacity: 0.7 }),
        },
      ],
    })
    layerRef.current.addTo(map)
    return () => {
      map.removeLayer(layerRef.current as unknown as L.Layer)
    }
  }, [map])

  return null
}

// Short display labels + color per OSM sac_scale value, easiest -> hardest (matches
// SAC_SCALE_RANK in data/scripts/06-build-hut-graph.py). Color scales green -> red with grade.
const SAC_SCALE_LABELS: Record<string, { label: string; color: string }> = {
  strolling: { label: 'Spazierweg', color: '#2e7d32' },
  hiking: { label: 'T1 Wandern', color: '#558b2f' },
  mountain_hiking: { label: 'T2 Bergwandern', color: '#9e9d24' },
  demanding_mountain_hiking: { label: 'T3 anspruchsvolles Bergwandern', color: '#f9a825' },
  alpine_hiking: { label: 'T4 Alpinwandern', color: '#ef6c00' },
  demanding_alpine_hiking: { label: 'T5 anspruchsvolles Alpinwandern', color: '#d84315' },
  difficult_alpine_hiking: { label: 'T6 schwieriges Alpinwandern', color: '#b71c1c' },
}

const SPARKLINE_WIDTH = 120
const SPARKLINE_HEIGHT = 32

/**
 * Small inline-SVG height profile for one edge, from its elevation_profile (script 08's
 * downsampled, evenly-distance-spaced elevation series) - no charting library needed at this
 * size. Flat/near-flat profiles get a fallback range so the line doesn't look broken.
 */
function ElevationSparkline({ values }: { values: number[] | null | undefined }) {
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
  const [edges, setEdges] = useState<Edge[]>([])
  const [huts, setHuts] = useState<Hut[]>([])
  const [error, setError] = useState<string | null>(null)
  const [hover, setHover] = useState<Hover | null>(null)
  const [showTrails, setShowTrails] = useState(false)
  const [allowedOperators, setAllowedOperators] = useState<Set<HutOperator>>(new Set(['av', 'sonstige']))
  const [showServiced, setShowServiced] = useState(true)
  const [showSelfService, setShowSelfService] = useState(true)
  const [showPartner, setShowPartner] = useState(true)
  const [partners, setPartners] = useState<PartnerPoint[]>([])

  useEffect(() => {
    Promise.all([
      fetch(EDGE_STATS_URL).then((r) => r.json()) as Promise<EdgeStatsEntry[]>,
      fetch(EDGE_GEOMETRY_MANIFEST_URL).then((r) => r.json()) as Promise<EdgeGeometryManifest>,
      fetch(EDGE_GEOMETRY_BIN_URL).then((r) => r.arrayBuffer()),
      fetch(HUTS_URL).then((r) => r.json()) as Promise<GeoJSON.FeatureCollection>,
      fetch(PARTNER_URL)
        .then((r) => r.json() as Promise<GeoJSON.FeatureCollection>)
        .catch(() => ({ type: 'FeatureCollection', features: [] }) as GeoJSON.FeatureCollection),
    ])
      .then(([edgeStats, geometryManifest, geometryBuffer, hutsFc, partnerFc]) => {
        // Geometry and stats are built from the same records.npy pass, in the same edge_id
        // order (build_edge_tiles.py's build_stats loop) - zip by index, no id lookup needed.
        const perEdgePositions = decodeEdgeGeometry(geometryManifest, geometryBuffer)
        setEdges(
          edgeStats.map((s, i) => {
            const positions = perEdgePositions[i]
            return {
              fromId: s.from_hut_id,
              toId: s.to_hut_id,
              distanceM: s.distance_m,
              roadM: s.road_m,
              ascentM: s.ascent_m,
              descentM: s.descent_m,
              elevationProfile: s.elevation_profile,
              sacScale: s.sac_scale,
              viaFerrata: s.via_ferrata,
              positions,
              bounds: L.latLngBounds(positions),
            }
          })
        )
        setHuts(
          hutsFc.features.map((f) => {
            const props = f.properties as { id: number; name: string; hutType?: string; serviced?: boolean }
            const hutClass: HutClass | null =
              props.hutType === 'av' || props.hutType === 'sonstige'
                ? { operator: props.hutType, serviced: props.serviced ?? true }
                : null
            return {
              id: props.id,
              name: props.name,
              lat: (f.geometry as GeoJSON.Point).coordinates[1],
              lng: (f.geometry as GeoJSON.Point).coordinates[0],
              hutClass,
            }
          })
        )
        setPartners(
          partnerFc.features.map((f) => {
            const props = f.properties as { id: number; name: string }
            const [lng, lat] = (f.geometry as GeoJSON.Point).coordinates
            return { id: props.id, name: props.name, lat, lng }
          })
        )
      })
      .catch((e: Error) => setError(e.message))
  }, [])

  const connectedIds = useMemo(() => new Set(edges.flatMap((e) => [e.fromId, e.toId])), [edges])
  const hutNameById = useMemo(() => new Map(huts.map((h) => [h.id, h.name])), [huts])

  function matchesFilter(hut: Hut): boolean {
    if (!hut.hutClass) return true // unclassified data (shouldn't happen post §Data-reality-check) is never dimmed away
    if (!allowedOperators.has(hut.hutClass.operator)) return false
    return hut.hutClass.serviced ? showServiced : showSelfService
  }

  return (
    <AppShell
      title="Hütten-Trail-Graph"
      status={
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <span>
            {error
              ? `Fehler: ${error}`
              : `${huts.length} Hütten, ${edges.length} Kanten (${connectedIds.size} verbunden)`}
          </span>
          <FormControlLabel
            control={<Switch size="small" checked={showTrails} onChange={(e) => setShowTrails(e.target.checked)} />}
            label="OSM-Wege (roh)"
            sx={{ color: 'inherit', m: 0 }}
          />
          {(Object.keys(OPERATOR_LABEL) as HutOperator[]).map((op) => (
            <FormControlLabel
              key={op}
              control={
                <Switch
                  size="small"
                  checked={allowedOperators.has(op)}
                  onChange={(e) =>
                    setAllowedOperators((prev) => {
                      const next = new Set(prev)
                      if (e.target.checked) next.add(op)
                      else next.delete(op)
                      return next
                    })
                  }
                />
              }
              label={OPERATOR_LABEL[op]}
              sx={{ color: 'inherit', m: 0 }}
            />
          ))}
          <FormControlLabel
            control={<Switch size="small" checked={showServiced} onChange={(e) => setShowServiced(e.target.checked)} />}
            label="Bewirtschaftet"
            sx={{ color: 'inherit', m: 0 }}
          />
          <FormControlLabel
            control={<Switch size="small" checked={showSelfService} onChange={(e) => setShowSelfService(e.target.checked)} />}
            label="Selbstversorger"
            sx={{ color: 'inherit', m: 0 }}
          />
          <FormControlLabel
            control={<Switch size="small" checked={showPartner} onChange={(e) => setShowPartner(e.target.checked)} />}
            label={PARTNER_LABEL}
            sx={{ color: 'inherit', m: 0 }}
          />
        </Box>
      }
    >
      <MapContainer center={[47.3, 12.0]} zoom={7} className="map" style={{ flex: 1 }}>
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> | Hüttendaten: Alpenverein / ArcGIS'
        />
        <TrailTilesLayer visible={showTrails} />
        <HutEdgeTilesLayer />
        <HoverInspector edges={edges} onHover={setHover} />
        {hover?.indices.map((i) => (
          <Polyline
            key={`hover-${i}`}
            positions={edges[i].positions}
            interactive={false}
            pathOptions={{ color: '#ff1744', weight: 5, opacity: 1 }}
          />
        ))}
        {huts.map((hut) => {
          const dim = !matchesFilter(hut)
          const connected = connectedIds.has(hut.id)
          const baseFill = hut.hutClass ? OPERATOR_COLOR[hut.hutClass.operator] : '#43a047'
          return (
            <CircleMarker
              key={hut.id}
              center={[hut.lat, hut.lng]}
              radius={connected ? 4 : 3}
              pathOptions={{
                color: connected ? '#1b5e20' : '#616161',
                fillColor: baseFill,
                fillOpacity: dim ? 0.15 : hut.hutClass?.serviced === false ? 0.4 : 0.9,
                weight: connected ? 1 : 1,
              }}
            >
              <Tooltip direction="top" offset={[0, -6]}>
                {hut.name}
                {hut.hutClass ? ` — ${hutClassLabel(hut.hutClass)} (${hutClassBadge(hut.hutClass)})` : ''}
              </Tooltip>
            </CircleMarker>
          )
        })}
        {showPartner &&
          partners.map((p) => (
            <CircleMarker
              key={`partner-${p.id}`}
              center={[p.lat, p.lng]}
              radius={4}
              pathOptions={{ color: PARTNER_COLOR, fillColor: PARTNER_COLOR, fillOpacity: 0.9, weight: 1 }}
            >
              <Tooltip direction="top" offset={[0, -6]}>
                {p.name} ({PARTNER_LABEL})
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
                {(edge.sacScale || edge.viaFerrata) && (
                  <span className="edge-difficulty-badges">
                    {edge.sacScale && SAC_SCALE_LABELS[edge.sacScale] && (
                      <span
                        className="difficulty-badge"
                        style={{ backgroundColor: SAC_SCALE_LABELS[edge.sacScale].color }}
                      >
                        {SAC_SCALE_LABELS[edge.sacScale].label}
                      </span>
                    )}
                    {edge.viaFerrata && (
                      <span className="difficulty-badge via-ferrata-badge">Klettersteig</span>
                    )}
                  </span>
                )}
                <ElevationSparkline values={edge.elevationProfile} />
              </div>
            )
          })}
        </div>
      )}
    </AppShell>
  )
}

export default GraphPage
