import { useEffect, useMemo, useState } from 'react'
import { MapContainer, TileLayer, CircleMarker, Polyline, Tooltip } from 'react-leaflet'
import L from 'leaflet'
import { Box, FormControlLabel, Switch } from '@mui/material'
import 'leaflet/dist/leaflet.css'
import './App.css'
import AppShell from '../AppShell.js'
import { hutClassBadge, hutClassLabel, OPERATOR_COLOR, OPERATOR_LABEL, PARTNER_COLOR, PARTNER_LABEL, type HutClass, type HutOperator } from '../hutClass.js'
import { decodeEdgeGeometry } from './decodeEdgeGeometry.js'
import { decodeEdgeElevation } from './decodeEdgeElevation.js'
import { TrailTilesLayer, HutEdgeTilesLayer } from './TrailLayers.js'
import HoverInspector from './HoverInspector.js'
import EdgeHoverPanel from './EdgeHoverPanel.js'
import type { Edge, EdgeGeometryManifest, EdgeStatsEntry, ElevationManifest, Hover, Hut, PartnerPoint } from './types.js'

const EDGE_STATS_URL = '/data/hut-edge-stats.json'
const HUTS_URL = '/data/huts.geojson'
const EDGE_GEOMETRY_MANIFEST_URL = '/data/hut-edge-geometry.json'
const EDGE_GEOMETRY_BIN_URL = '/data/hut-edge-geometry.bin'
const EDGE_ELEVATION_MANIFEST_URL = '/data/hut-edge-elevation.json'
const EDGE_ELEVATION_BIN_URL = '/data/hut-edge-elevation.bin'
const PARTNER_URL = '/data/partner_betriebe.geojson'

/**
 * Internal-only debugging/sanity-check view of the raw hut-to-hut routing graph - not linked
 * from anything user-facing. Renders every trail/hut-edge and lets you hover an edge to inspect
 * its stats (distance, ascent/descent, difficulty, elevation profile).
 */
function AdminPage() {
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
      fetch(EDGE_ELEVATION_MANIFEST_URL).then((r) => r.json()) as Promise<ElevationManifest>,
      fetch(EDGE_ELEVATION_BIN_URL).then((r) => r.arrayBuffer()),
      fetch(HUTS_URL).then((r) => r.json()) as Promise<GeoJSON.FeatureCollection>,
      fetch(PARTNER_URL)
        .then((r) => r.json() as Promise<GeoJSON.FeatureCollection>)
        .catch(() => ({ type: 'FeatureCollection', features: [] }) as GeoJSON.FeatureCollection),
    ])
      .then(([edgeStats, geometryManifest, geometryBuffer, elevationManifest, elevationBuffer, hutsFc, partnerFc]) => {
        // Geometry, elevation and stats are built from the same records.npy pass, in the same
        // edge_id order (build_edge_tiles.py's build_stats loop) - zip by index, no id lookup needed.
        const perEdgePositions = decodeEdgeGeometry(geometryManifest, geometryBuffer)
        const perEdgeElevation = decodeEdgeElevation(elevationManifest, elevationBuffer)
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
              elevationProfile: perEdgeElevation[i],
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
      title="Hütten-Trail-Graph (Admin)"
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
        <EdgeHoverPanel hover={hover} edges={edges} hutNameById={hutNameById} />
      )}
    </AppShell>
  )
}

export default AdminPage
