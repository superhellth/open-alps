import { useEffect, useMemo, useRef } from 'react'
import { useMap } from 'react-leaflet'
import { legsFromTrip } from '../../tourSearch/tripLegs.js'
import type { TripGraph } from '../../tourSearch/tripLegs.js'
import type { Trip } from '../../trip/trip.js'
import { tripToRoute } from '../routes.js'
import type { RouteContext } from '../routes.js'
import type { Route } from '../types.js'
import RouteLayer from './RouteLayer.js'

export interface SavedTripsLayerProps {
  /** True while the `saved` sidebar view is showing — controls the one-time fit-to-all-trips. */
  active: boolean
  trips: Trip[]
  graph: TripGraph
  routeCtx: RouteContext
  hoveredTripId: string | null
  onHoverTrip: (id: string | null) => void
  onOpen: (id: string) => void
}

function FitAllOnEntry({ active, routes }: { active: boolean; routes: Route[] }) {
  const map = useMap()
  const wasActive = useRef(false)
  useEffect(() => {
    if (active && !wasActive.current && routes.length > 0) {
      const positions = routes.flatMap((r) => r.waypoints.map((w): [number, number] => [w.lat, w.lng]))
      map.fitBounds(positions, { padding: [40, 40] })
    }
    wasActive.current = active
  }, [active, routes, map])
  return null
}

// Every resolvable saved trip drawn as a thin muted route (RouteLayer's own dashed-segment
// fallback covers geometry still loading or failed to fetch); an unresolvable trip has no route
// to draw at all (tripToRoute returns null) and is skipped, matching the list's "geändert" row.
export default function SavedTripsLayer({ active, trips, graph, routeCtx, hoveredTripId, onHoverTrip, onOpen }: SavedTripsLayerProps) {
  const entries = useMemo(
    () => trips.flatMap((trip) => {
      const tripLegs = legsFromTrip(graph, trip)
      const route = tripToRoute(trip, tripLegs, routeCtx)
      return route ? [{ trip, route }] : []
    }),
    [trips, graph, routeCtx],
  )

  return (
    <>
      <FitAllOnEntry active={active} routes={entries.map((e) => e.route)} />
      {entries.map(({ trip, route }) => (
        <RouteLayer
          key={trip.id} route={route} muted
          dimmedOut={hoveredTripId !== null && hoveredTripId !== trip.id}
          onHover={(hovering) => onHoverTrip(hovering ? trip.id : null)}
          onClick={() => onOpen(trip.id)}
        />
      ))}
    </>
  )
}
