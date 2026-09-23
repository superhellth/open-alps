import { useEffect, useMemo, useState } from 'react'
import L from 'leaflet'
import { Marker, useMap, useMapEvents } from 'react-leaflet'
import type { FreeByOffset } from '../../availability/types.js'
import { rankFit } from '../../tourSearch/rankFit.js'
import type { RankTargets } from '../../tourSearch/rankFit.js'
import type { StartGroup } from '../../tourSearch/groupByStart.js'
import { nightStateOf } from '../rankTours.js'
import type { SortKey } from '../rankTours.js'
import { tourToRoute } from '../routes.js'
import type { RouteContext } from '../routes.js'
import type { PlannerTour } from '../tours.js'
import type { StartPoint } from '../types.js'
import RouteLayer from './RouteLayer.js'
import { createStartClusterer, markerRadius } from './clusterStarts.js'
import { currentView, inBbox } from './viewport.js'
import type { View } from './viewport.js'
import './map.css'

const MAX_ROUTES = 50

/** Below this zoom, routes stay hidden and only count-markers show — tuned lower than the
 *  clusterer's own maxZoom (14) so routes appear before markers finish separating one-per-start. */
export const ROUTE_REVEAL_ZOOM = 10

const iconCache = new Map<string, L.DivIcon>()
function countIcon(count: number, dimmed: boolean, highlighted: boolean): L.DivIcon {
  const key = `${count}|${dimmed}|${highlighted}`
  let icon = iconCache.get(key)
  if (!icon) {
    const size = Math.round(markerRadius(count) * 2)
    icon = L.divIcon({
      className: `start-count-marker${dimmed ? ' dimmed' : ''}${highlighted ? ' highlighted' : ''}`,
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
 *  `ROUTE_REVEAL_ZOOM`, faint route lines draw for every tour whose start point is in the current
 *  viewport (capped at 50, ranked by the active sort) — the same set the results list shows, so
 *  the map never shows more than what's on screen and already listed. Markers no longer "select":
 *  clicking one only flies/zooms the map there. */
export default function DiscoverLayer({
  groups, startById, dimmed, allTours, sortKey, rankCtx, routeCtx, hoveredTourKey, onHoverTour, previewStartId, onPickRoute, onNavigate, onViewChange,
}: {
  groups: StartGroup<PlannerTour>[]
  startById: Map<number, StartPoint>
  dimmed: boolean
  allTours: PlannerTour[]
  sortKey: SortKey
  rankCtx: { targets: RankTargets; ohrsIdByHutIndex: Map<number, string | null>; freeByOffset: FreeByOffset | null }
  routeCtx: RouteContext | null
  hoveredTourKey: string | null
  onHoverTour: (key: string | null) => void
  /** Start point of the tour hovered in the results list; the marker covering it is highlighted. */
  previewStartId?: number | null
  onPickRoute: (tour: PlannerTour) => void
  onNavigate?: () => void
  onViewChange?: (view: View) => void
}) {
  const map = useMap()
  const [view, setView] = useState<View>(() => currentView(map))
  useMapEvents({ moveend: () => setView(currentView(map)), zoomend: () => setView(currentView(map)) })
  useEffect(() => { onViewChange?.(view) }, [view, onViewChange])

  const clusterer = useMemo(() => createStartClusterer(groups.flatMap((g) => {
    const s = startById.get(g.startId)
    return s ? [{ startId: g.startId, count: g.tours.length, lat: s.lat, lng: s.lng }] : []
  })), [groups, startById])

  const routeReveal = view.zoom >= ROUTE_REVEAL_ZOOM
  const routedTours = useMemo(() => {
    if (!routeCtx || !routeReveal) return []
    const inView = allTours.filter((t) => {
      const s = startById.get(t.startId)
      return s !== undefined && inBbox(s, view.bbox)
    })
    const sorted = sortKey === 'fit'
      ? rankFit(inView, rankCtx.targets, rankCtx.freeByOffset ? (t, night) => nightStateOf(t, night, rankCtx.ohrsIdByHutIndex, rankCtx.freeByOffset) : undefined)
      : [...inView].sort((a, b) => {
          const total = { duration: (t: PlannerTour) => t.totalDurationH, ascent: (t: PlannerTour) => t.totalAscentM, distance: (t: PlannerTour) => t.totalDistanceM }
          return (total[sortKey as 'duration' | 'ascent' | 'distance']?.(a) ?? 0) - (total[sortKey as 'duration' | 'ascent' | 'distance']?.(b) ?? 0)
        })
    return sorted.slice(0, MAX_ROUTES)
  }, [allTours, routeCtx, routeReveal, view.bbox, startById, sortKey, rankCtx])

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
          icon={countIcon(m.count, dimmed, m === highlightedMarker)}
          eventHandlers={{
            click: () => {
              onNavigate?.()
              if (m.kind === 'cluster') map.setView([m.lat, m.lng], Math.min(clusterer.expansionZoom(m.clusterId), map.getMaxZoom()))
            },
          }}
        />
      ))}
      {routeCtx && routedTours.map((tour) => {
        const route = tourToRoute(tour, routeCtx)
        if (!route) return null
        const key = tourKey(tour)
        const isHovered = hoveredTourKey === key
        return (
          <RouteLayer
            key={key} route={route} muted dimmedOut={!isHovered}
            onHover={(hovering) => onHoverTour(hovering ? key : null)}
            onClick={() => onPickRoute(tour)}
          />
        )
      })}
    </>
  )
}
