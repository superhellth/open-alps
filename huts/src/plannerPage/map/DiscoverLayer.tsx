import { useEffect, useMemo, useState } from 'react'
import L from 'leaflet'
import { Marker, useMap, useMapEvents } from 'react-leaflet'
import type { StartGroup } from '../../tourSearch/groupByStart.js'
import { tourToRoute } from '../routes.js'
import type { RouteContext } from '../routes.js'
import type { PlannerTour } from '@/tourSearch/plannerTour.js'
import type { StartPoint } from '@/data/types.js'
import RouteLayer from './RouteLayer.js'
import { createStartClusterer, markerRadius } from './clusterStarts.js'
import type { MapMarker } from './clusterStarts.js'
import { currentView, routeTouchesBbox } from './viewport.js'
import type { View } from './viewport.js'
import './map.css'

/** Below this zoom, routes stay hidden and only count-markers show — tuned lower than the
 *  clusterer's own maxZoom (14) so routes appear before markers finish separating one-per-start. */
export const ROUTE_REVEAL_ZOOM = 10

const iconCache = new Map<string, L.DivIcon>()
function countIcon(count: number, cluster: boolean, dimmed: boolean, highlighted: boolean): L.DivIcon {
  const key = `${count}|${cluster}|${dimmed}|${highlighted}`
  let icon = iconCache.get(key)
  if (!icon) {
    const size = Math.round(markerRadius(count) * 2)
    icon = L.divIcon({
      className: `start-count-marker${cluster ? ' cluster' : ''}${dimmed ? ' dimmed' : ''}${highlighted ? ' highlighted' : ''}`,
      html: `<span>${count}</span>`,
      iconSize: [size, size],
    })
    iconCache.set(key, icon)
  }
  return icon
}

/** A tour's stable cross-component identity (hover sync between the map and the results list). */
export function tourKey(tour: PlannerTour): string {
  return `${tour.startId}-${tour.official?.tourId ?? ''}-${tour.huts.join('.')}`
}

/** One marker per start point with matching tours, clustered by zoom; a cluster shows the sum of
 *  its members' match counts. Panning and zooming only re-cluster, they never re-search. Past
 *  `ROUTE_REVEAL_ZOOM`, faint route lines draw for every tour whose waypoints' bounding box
 *  overlaps the current viewport, so a tour stays drawn while any part of it is on screen. Markers no longer "select":
 *  clicking one that stands for a single tour picks it; otherwise it flies the map to the bounds of the tours it stands for and focuses the results
 *  list on them. Cluster bubbles (several start points) carry a ring; single start points do not. */
export default function DiscoverLayer({
  groups, startById, dimmed, allTours, routeCtx, hoveredTourKey, onHoverTour, previewStartId, onPickRoute, onNavigate, onFocusStarts, onHoverStarts, onViewChange,
}: {
  groups: StartGroup<PlannerTour>[]
  startById: Map<number, StartPoint>
  dimmed: boolean
  allTours: PlannerTour[]
  routeCtx: RouteContext | null
  hoveredTourKey: string | null
  onHoverTour: (key: string | null) => void
  /** Start point of the tour hovered in the results list; the marker covering it is highlighted. */
  previewStartId?: number | null
  onPickRoute: (tour: PlannerTour) => void
  onNavigate?: () => void
  /** Start points whose tours the results list should be limited to; null lifts the limit. */
  onFocusStarts?: (startIds: number[] | null) => void
  /** Start points of the bubble under the pointer; null when none. */
  onHoverStarts?: (startIds: Set<number> | null) => void
  onViewChange?: (view: View) => void
}) {
  const map = useMap()
  const [view, setView] = useState<View>(() => currentView(map))
  useMapEvents({
    moveend: () => setView(currentView(map)),
    zoomend: () => setView(currentView(map)),
    dragstart: () => onFocusStarts?.(null),
  })
  useEffect(() => { onViewChange?.(view) }, [view, onViewChange])

  const clusterer = useMemo(() => createStartClusterer(groups.flatMap((g) => {
    const s = startById.get(g.startId)
    return s ? [{ startId: g.startId, count: g.tours.length, lat: s.lat, lng: s.lng }] : []
  })), [groups, startById])

  const routeReveal = view.zoom >= ROUTE_REVEAL_ZOOM
  const routedTours = useMemo(() => {
    if (!routeCtx || !routeReveal) return []
    return allTours.flatMap((tour) => {
      const route = tourToRoute(tour, routeCtx)
      return route && routeTouchesBbox(route.waypoints, view.bbox) ? [{ tour, route }] : []
    })
  }, [allTours, routeCtx, routeReveal, view.bbox])

  const [hoveredStartIds, setHoveredStartIds] = useState<Set<number> | null>(null)
  const hoverStarts = (ids: Set<number> | null) => { setHoveredStartIds(ids); onHoverStarts?.(ids) }
  const highlightedRoutes = useMemo(() => routedTours.flatMap(({ tour, route }) =>
    tourKey(tour) === hoveredTourKey || hoveredStartIds?.has(tour.startId) ? [{ key: tourKey(tour), route }] : []),
  [routedTours, hoveredTourKey, hoveredStartIds])

  /** Bounds of every waypoint of every tour starting at one of the given start points. */
  const tourBounds = (startIds: number[]): L.LatLngBounds | null => {
    if (!routeCtx) return null
    const ids = new Set(startIds)
    const bounds = L.latLngBounds([])
    for (const g of groups) {
      if (!ids.has(g.startId)) continue
      for (const tour of g.tours) {
        const route = tourToRoute(tour, routeCtx)
        route?.waypoints.forEach((p) => bounds.extend([p.lat, p.lng]))
      }
    }
    return bounds.isValid() ? bounds : null
  }

  const startIdsOf = (m: MapMarker) => (m.kind === 'cluster' ? clusterer.startIdsOf(m.clusterId) : [m.startId])

  const markers = clusterer.clustersFor(view.bbox, view.zoom)
  const highlightedMarker = useMemo(() => {
    if (previewStartId == null) return null
    return markers.find((m) => m.kind === 'start' ? m.startId === previewStartId : clusterer.startIdsOf(m.clusterId).includes(previewStartId)) ?? null
  }, [markers, clusterer, previewStartId])

  return (
    <>
      {markers.map((m) => (
        <Marker
          key={m.kind === 'start' ? `s${m.startId}` : `c${m.clusterId}`}
          position={[m.lat, m.lng]}
          icon={countIcon(m.count, m.kind === 'cluster', dimmed, m === highlightedMarker)}
          eventHandlers={{
            mouseover: () => hoverStarts(new Set(startIdsOf(m))),
            mouseout: () => hoverStarts(null),
            click: () => {
              const only = m.kind === 'start' && m.count === 1 ? groups.find((g) => g.startId === m.startId)?.tours[0] : undefined
              onNavigate?.()
              if (only) { onPickRoute(only); return }
              const startIds = startIdsOf(m)
              onFocusStarts?.(startIds)
              const bounds = tourBounds(startIds)
              if (bounds) map.flyToBounds(bounds, { padding: [40, 40], duration: 0.6 })
              else if (m.kind === 'cluster') map.setView([m.lat, m.lng], Math.min(clusterer.expansionZoom(m.clusterId), map.getMaxZoom()))
            },
          }}
        />
      ))}
      {routedTours.map(({ tour, route }) => {
        const key = tourKey(tour)
        return (
          <RouteLayer
            key={key} route={route} muted dimmedOut
            onHover={(hovering) => onHoverTour(hovering ? key : null)}
            onClick={() => onPickRoute(tour)}
          />
        )
      })}
      {/* The hover highlight is a display-only copy above the dimmed routes; the interactive
          layers underneath never change, so their mouseout always fires. */}
      {highlightedRoutes.map(({ key, route }) => <RouteLayer key={key} route={route} muted interactive={false} />)}
    </>
  )
}
