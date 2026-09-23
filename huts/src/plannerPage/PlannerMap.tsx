import { memo, useEffect, useState } from 'react'
import { Box, Button, Collapse, Typography } from '@mui/material'
import { MapContainer, TileLayer, useMap, useMapEvents } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import type { FreeByOffset } from '../availability/types.js'
import type { TripLegs } from '../tourSearch/tripLegs.js'
import type { RankTargets } from '../tourSearch/rankFit.js'
import type { StartGroup } from '../tourSearch/groupByStart.js'
import DiscoverLayer from './map/DiscoverLayer.js'
import HeightProfile from './map/HeightProfile.js'
import RouteLayer from './map/RouteLayer.js'
import SavedTripsLayer from './map/SavedTripsLayer.js'
import TripLayer from './map/TripLayer.js'
import type { CandidateMapMarker, TripEndMarker, TripHutMarker } from './map/TripLayer.js'
import { ACTIVE_TILES } from './map/tiles.js'
import type { View } from './map/viewport.js'
import { useTripElevation } from './map/useTripElevation.js'
import type { SortKey } from './rankTours.js'
import type { RouteContext } from './routes.js'
import type { TripGraph } from '../tourSearch/tripLegs.js'
import type { Trip } from '../trip/trip.js'
import type { PlannerTour } from './tours.js'
import type { Route, StartPoint } from './types.js'
import './map/map.css'

const EMPTY_TRIP_LEGS: TripLegs = { variantId: -1, hutIndices: [], legs: [], changed: [] }

export interface PlannerMapProps {
  mode: 'discover' | 'trip' | 'saved'
  groups: StartGroup<PlannerTour>[]
  /** Discover markers keep their previous counts, dimmed, while a new search runs. */
  dimmed: boolean
  startById: Map<number, StartPoint>
  hutCoordsById: Map<number, { lat: number; lng: number }>
  /** Called when a Discover marker is clicked — navigation only, no filtering. */
  onNavigate?: () => void
  /** Called whenever the map's bbox/zoom changes in Discover mode, so the list can mirror it. */
  onViewChange?: (view: View) => void
  onMapClick?: () => void
  route: Route | null
  fitRoute: boolean
  highlightedLeg: number | null
  tripHuts: TripHutMarker[]
  tripEnds: TripEndMarker[]
  /** Swap/extend/start/exit candidates of the active edit, drawn as signposts. */
  candidates: CandidateMapMarker[]
  candidateStartCoords: Map<number, { lat: number; lng: number }>
  onPickCandidate: (arg: { hutIndex?: number; startId?: number }) => void
  activeLabel: string | null
  onCancelEditing?: () => void
  allTours: PlannerTour[]
  sortKey: SortKey
  rankCtx: { targets: RankTargets; ohrsIdByHutIndex: Map<number, string | null>; freeByOffset: FreeByOffset | null }
  routeCtx: RouteContext | null
  hoveredTourKey: string | null
  onHoverTour: (key: string | null) => void
  previewStartId?: number | null
  onPickRoute: (tour: PlannerTour) => void
  /** A point to fly to once (e.g. after "N Touren anzeigen" picks an off-screen start). */
  /** Set once to jump the map back to Discover's viewport from before a tour was picked. */
  restoreView?: { lat: number; lng: number; zoom: number } | null
  /** null when no trip is open — the height profile then renders nothing. */
  tripLegs: TripLegs | null
  onHoverLeg: (index: number | null) => void
  savedTrips?: Trip[]
  savedGraph?: TripGraph
  savedRouteCtx?: RouteContext
  hoveredTripId?: string | null
  onHoverTrip?: (id: string | null) => void
  onOpenSavedTrip?: (id: string) => void
}

function MapClickWatcher({ onClick }: { onClick?: () => void }) {
  useMapEvents({ click: () => onClick?.() })
  return null
}

/** Commands the map back to a remembered view (e.g. Discover's viewport from before a tour was
 *  picked) — an immediate jump, not an animated flight, so it's deterministic and instant. */
function RestoreView({ view }: { view: { lat: number; lng: number; zoom: number } | null | undefined }) {
  const map = useMap()
  useEffect(() => { if (view) map.setView([view.lat, view.lng], view.zoom) }, [map, view])
  return null
}

// One MapContainer stays mounted across discover <-> trip so pan/zoom survive switching.
const PlannerMap = memo(function PlannerMap(props: PlannerMapProps) {
  const {
    mode, groups, dimmed, startById, hutCoordsById, onNavigate, onViewChange, route, fitRoute, highlightedLeg,
    tripHuts, tripEnds, candidates, candidateStartCoords, onPickCandidate, onMapClick,
    activeLabel, onCancelEditing, allTours, sortKey, rankCtx, routeCtx, hoveredTourKey, onHoverTour, previewStartId, onPickRoute, restoreView,
    tripLegs, onHoverLeg, savedTrips, savedGraph, savedRouteCtx, hoveredTripId, onHoverTrip, onOpenSavedTrip,
  } = props
  const elevation = useTripElevation(tripLegs ?? EMPTY_TRIP_LEGS)
  const [profileOpen, setProfileOpen] = useState(true)
  return (
    <Box className={mode === 'discover' ? 'map-muted' : undefined} sx={{ height: '100%', width: '100%', display: 'flex', flexDirection: 'column' }}>
      <Box sx={{ flex: 1, minHeight: 0, position: 'relative' }}>
        {activeLabel && (
          <Box sx={{ position: 'absolute', top: 8, left: '50%', transform: 'translateX(-50%)', zIndex: 1000, bgcolor: 'background.paper', border: '1px solid', borderColor: 'divider', borderRadius: 1, px: 1.5, py: 0.5, display: 'flex', gap: 1, alignItems: 'center' }}>
            <Typography variant="body2">{activeLabel}</Typography>
            {onCancelEditing && <Button size="small" onClick={onCancelEditing}>Abbrechen</Button>}
          </Box>
        )}
        <MapContainer center={[47.3, 12.0]} zoom={7} style={{ height: '100%', width: '100%' }}>
          <TileLayer
            url={ACTIVE_TILES.url} attribution={ACTIVE_TILES.attribution}
            subdomains={ACTIVE_TILES.subdomains} maxZoom={ACTIVE_TILES.maxZoom}
          />
          <MapClickWatcher onClick={onMapClick} />
          {mode === 'discover' && (
            <DiscoverLayer
              groups={groups} startById={startById} dimmed={dimmed} onNavigate={onNavigate} onViewChange={onViewChange}
              allTours={allTours} sortKey={sortKey} rankCtx={rankCtx} routeCtx={routeCtx}
              hoveredTourKey={hoveredTourKey} onHoverTour={onHoverTour} previewStartId={previewStartId} onPickRoute={onPickRoute}
            />
          )}
          {/* Rendered after DiscoverLayer so its own moveend/zoomend listeners are already
              subscribed once this fires the map back to the pre-pick view. */}
          <RestoreView view={restoreView} />
          {route && <RouteLayer route={route} highlightedLeg={highlightedLeg} fit={fitRoute} />}
          {mode === 'trip' && (
            <TripLayer
              tripHuts={tripHuts} tripEnds={tripEnds} candidates={candidates}
              hutCoordsById={hutCoordsById} candidateStartCoords={candidateStartCoords} onPickCandidate={onPickCandidate}
            />
          )}
          {mode === 'saved' && savedTrips && savedGraph && savedRouteCtx && (
            <SavedTripsLayer
              active={mode === 'saved'} trips={savedTrips} graph={savedGraph} routeCtx={savedRouteCtx}
              hoveredTripId={hoveredTripId ?? null} onHoverTrip={onHoverTrip ?? (() => {})}
              onOpen={onOpenSavedTrip ?? (() => {})}
            />
          )}
        </MapContainer>
      </Box>
      {mode === 'trip' && tripLegs && (
        <Box sx={{ borderTop: '1px solid', borderColor: 'divider' }}>
          <Button size="small" onClick={() => setProfileOpen((o) => !o)} sx={{ width: '100%', justifyContent: 'space-between' }}>
            Höhenprofil {profileOpen ? '▾' : '▸'}
          </Button>
          <Collapse in={profileOpen}>
            <HeightProfile elevation={elevation} highlightedLeg={highlightedLeg} onHoverLeg={onHoverLeg} onHoverPosition={() => {}} />
          </Collapse>
        </Box>
      )}
    </Box>
  )
})

export default PlannerMap
