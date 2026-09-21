import { memo } from 'react'
import { Box } from '@mui/material'
import { MapContainer, TileLayer, useMapEvents } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import type { StartGroup } from '../tourSearch/groupByStart.js'
import DiscoverLayer from './map/DiscoverLayer.js'
import RouteLayer from './map/RouteLayer.js'
import TripLayer from './map/TripLayer.js'
import type { CandidateMapMarker, TripEndMarker, TripHutMarker } from './map/TripLayer.js'
import { ACTIVE_TILES } from './map/tiles.js'
import type { PlannerTour } from './tours.js'
import type { Route, StartPoint } from './types.js'
import './map/map.css'

export interface PlannerMapProps {
  mode: 'discover' | 'trip'
  groups: StartGroup<PlannerTour>[]
  /** Discover markers keep their previous counts, dimmed, while a new search runs. */
  dimmed: boolean
  startById: Map<number, StartPoint>
  hutCoordsById: Map<number, { lat: number; lng: number }>
  onSelectStarts: (startIds: number[]) => void
  onMapClick?: () => void
  route: Route | null
  fitRoute: boolean
  highlightedLeg: number | null
  tripHuts: TripHutMarker[]
  tripEnds: TripEndMarker[]
  /** Swap/extend candidates of the active edit, drawn as signposts. */
  candidates: CandidateMapMarker[]
  onPickCandidate: (hutIndex: number) => void
}

function MapClickWatcher({ onClick }: { onClick?: () => void }) {
  useMapEvents({ click: () => onClick?.() })
  return null
}

// One MapContainer stays mounted across discover <-> trip so pan/zoom survive switching.
const PlannerMap = memo(function PlannerMap(props: PlannerMapProps) {
  const {
    mode, groups, dimmed, startById, hutCoordsById, onSelectStarts, route, fitRoute, highlightedLeg,
    tripHuts, tripEnds, candidates, onPickCandidate, onMapClick,
  } = props
  return (
    <Box className={mode === 'discover' ? 'map-muted' : undefined} sx={{ height: '100%', width: '100%' }}>
      <MapContainer center={[47.3, 12.0]} zoom={7} style={{ height: '100%', width: '100%' }}>
        <TileLayer
          url={ACTIVE_TILES.url} attribution={ACTIVE_TILES.attribution}
          subdomains={ACTIVE_TILES.subdomains} maxZoom={ACTIVE_TILES.maxZoom}
        />
        <MapClickWatcher onClick={onMapClick} />
        {mode === 'discover' && (
          <DiscoverLayer groups={groups} startById={startById} dimmed={dimmed} onSelectStarts={onSelectStarts} />
        )}
        {route && <RouteLayer route={route} highlightedLeg={highlightedLeg} fit={fitRoute} />}
        {mode === 'trip' && (
          <TripLayer
            tripHuts={tripHuts} tripEnds={tripEnds} candidates={candidates}
            hutCoordsById={hutCoordsById} onPickCandidate={onPickCandidate}
          />
        )}
      </MapContainer>
    </Box>
  )
})

export default PlannerMap
