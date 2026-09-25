import { memo, useEffect } from 'react'
import { Box } from '@mui/material'
import { MapContainer, TileLayer, useMap, useMapEvents } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { DiscoverMapLayers } from './DiscoverMapLayers.js'
import type { DiscoverMapMode } from './DiscoverMapLayers.js'
import RouteLayer from './RouteLayer.js'
import { SavedMapLayers } from './SavedMapLayers.js'
import type { SavedMapMode } from './SavedMapLayers.js'
import { TripMapLayers, TripMapProfile, TripMapStatusBar } from './TripMapLayers.js'
import type { TripMapMode } from './TripMapLayers.js'
import { ACTIVE_TILES } from './tiles.js'
import type { Bounds, ViewTarget } from './useMapView.js'
import type { Route } from './types.js'
import './map.css'
import { styles } from './PlannerMap.styles.js'

export interface MapCommands {
  route: Route | null
  fitRoute: boolean
  highlightedLeg: number | null
  /** Set once to jump the map back to Discover's viewport from before a tour was picked. */
  restoreView: ViewTarget | null
  /** Set to a fresh value to fly the map to these bounds. */
  fitBounds: Bounds | null
  onMapClick: () => void
}

export type MapMode = DiscoverMapMode | TripMapMode | SavedMapMode

export interface PlannerMapProps {
  mode: MapMode
  commands: MapCommands
}

function MapClickWatcher({ onClick }: { onClick: () => void }) {
  useMapEvents({ click: onClick })
  return null
}

/** Commands the map back to a remembered view (e.g. Discover's viewport from before a tour was
 *  picked) — an immediate jump, not an animated flight, so it's deterministic and instant. */
function RestoreView({ view }: { view: ViewTarget | null }) {
  const map = useMap()
  useEffect(() => { if (view) map.setView([view.lat, view.lng], view.zoom) }, [map, view])
  return null
}

/** Flies the map to the given bounds each time a new bounds value arrives. */
function FitBoundsCommand({ bounds }: { bounds: Bounds | null }) {
  const map = useMap()
  useEffect(() => { if (bounds) map.flyToBounds(bounds, { padding: [40, 40], duration: 0.6 }) }, [map, bounds])
  return null
}

// One MapContainer stays mounted across modes so pan/zoom survive switching.
const PlannerMap = memo(function PlannerMap({ mode, commands }: PlannerMapProps) {
  const { route, fitRoute, highlightedLeg, restoreView, fitBounds, onMapClick } = commands
  return (
    <Box className={mode.kind === 'discover' ? 'map-muted' : undefined} sx={styles.root}>
      <Box sx={{ flex: 1, minHeight: 0, position: 'relative' }}>
        {mode.kind === 'trip' && <TripMapStatusBar mode={mode} />}
        <MapContainer center={[47.3, 12.0]} zoom={7} style={{ height: '100%', width: '100%' }}>
          <TileLayer
            url={ACTIVE_TILES.url} attribution={ACTIVE_TILES.attribution}
            subdomains={ACTIVE_TILES.subdomains} maxZoom={ACTIVE_TILES.maxZoom}
          />
          <MapClickWatcher onClick={onMapClick} />
          {mode.kind === 'discover' && <DiscoverMapLayers mode={mode} />}
          {/* Rendered after the discover layers so their own moveend/zoomend listeners are already
              subscribed once this fires the map back to the pre-pick view. */}
          <RestoreView view={restoreView} />
          <FitBoundsCommand bounds={fitBounds} />
          {route && <RouteLayer route={route} highlightedLeg={highlightedLeg} fit={fitRoute} />}
          {mode.kind === 'trip' && <TripMapLayers mode={mode} />}
          {mode.kind === 'saved' && <SavedMapLayers mode={mode} />}
        </MapContainer>
      </Box>
      {mode.kind === 'trip' && <TripMapProfile mode={mode} highlightedLeg={highlightedLeg} />}
    </Box>
  )
})

export default PlannerMap
