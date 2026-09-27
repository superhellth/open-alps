import type { TripGraph } from '@/tourSearch/types.js'
import type { Trip } from '@/trip/trip.js'
import SavedTripsLayer from './SavedTripsLayer.js'
import type { RouteContext } from './routes.js'

export interface SavedMapMode {
  kind: 'saved'
  trips: Trip[]
  graph: TripGraph
  routeCtx: RouteContext
  hoveredTripId: string | null
  onHoverTrip: (id: string | null) => void
  onOpen: (id: string) => void
}

export function SavedMapLayers({ mode }: { mode: SavedMapMode }) {
  return (
    <SavedTripsLayer
      active trips={mode.trips} graph={mode.graph} routeCtx={mode.routeCtx}
      hoveredTripId={mode.hoveredTripId} onHoverTrip={mode.onHoverTrip} onOpen={mode.onOpen}
    />
  )
}
