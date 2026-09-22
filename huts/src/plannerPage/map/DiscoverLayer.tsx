import { useMemo, useState } from 'react'
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
import './map.css'

const ROUTE_ZOOM_MIN = 11
const MAX_ROUTES = 50

interface View {
  bbox: [number, number, number, number]
  zoom: number
}

// The bounds are padded by half a tile-width so markers just outside the viewport (and a
// zero-size map, as in jsdom) still resolve.
function currentView(map: L.Map): View {
  const b = map.getBounds()
  const zoom = Math.round(map.getZoom())
  const pad = (0.5 * 360) / 2 ** zoom
  return { bbox: [b.getWest() - pad, b.getSouth() - pad, b.getEast() + pad, b.getNorth() + pad], zoom }
}

const iconCache = new Map<string, L.DivIcon>()
function countIcon(count: number, dimmed: boolean): L.DivIcon {
  const key = `${count}|${dimmed}`
  let icon = iconCache.get(key)
  if (!icon) {
    const size = Math.round(markerRadius(count) * 2)
    icon = L.divIcon({
      className: `start-count-marker${dimmed ? ' dimmed' : ''}`,
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

function inViewport(startId: number, startById: Map<number, StartPoint>, bbox: View['bbox']): boolean {
  const p = startById.get(startId)
  if (!p) return false
  const [w, s, e, n] = bbox
  return p.lng >= w && p.lng <= e && p.lat >= s && p.lat <= n
}

/** One marker per start point with matching tours, clustered by zoom; a cluster shows the sum of
 *  its members' match counts. Panning and zooming only re-cluster, they never re-search. From
 *  zoom 11, also draws thin route lines for the best-sorted, viewport-visible, capped-at-50 tours,
 *  so results are reachable without hunting for the right marker. */
export default function DiscoverLayer({
  groups, startById, dimmed, onSelectStarts, allTours, sortKey, rankCtx, routeCtx, hoveredTourKey, onHoverTour, onPickRoute,
}: {
  groups: StartGroup<PlannerTour>[]
  startById: Map<number, StartPoint>
  dimmed: boolean
  onSelectStarts: (startIds: number[]) => void
  allTours: PlannerTour[]
  sortKey: SortKey
  rankCtx: { targets: RankTargets; ohrsIdByHutIndex: Map<number, string | null>; freeByOffset: FreeByOffset | null }
  routeCtx: RouteContext | null
  hoveredTourKey: string | null
  onHoverTour: (key: string | null) => void
  onPickRoute: (tour: PlannerTour) => void
}) {
  const map = useMap()
  const [view, setView] = useState(() => currentView(map))
  useMapEvents({ moveend: () => setView(currentView(map)), zoomend: () => setView(currentView(map)) })

  const clusterer = useMemo(() => createStartClusterer(groups.flatMap((g) => {
    const s = startById.get(g.startId)
    return s ? [{ startId: g.startId, count: g.tours.length, lat: s.lat, lng: s.lng }] : []
  })), [groups, startById])

  const routedTours = useMemo(() => {
    if (view.zoom < ROUTE_ZOOM_MIN || !routeCtx) return []
    const inView = allTours.filter((t) => inViewport(t.startId, startById, view.bbox))
    const sorted = sortKey === 'fit'
      ? rankFit(inView, rankCtx.targets, rankCtx.freeByOffset ? (t, night) => nightStateOf(t, night, rankCtx.ohrsIdByHutIndex, rankCtx.freeByOffset) : undefined)
      : [...inView].sort((a, b) => {
          const total = { duration: (t: PlannerTour) => t.totalDurationH, ascent: (t: PlannerTour) => t.totalAscentM, distance: (t: PlannerTour) => t.totalDistanceM }
          return (total[sortKey as 'duration' | 'ascent' | 'distance']?.(a) ?? 0) - (total[sortKey as 'duration' | 'ascent' | 'distance']?.(b) ?? 0)
        })
    return sorted.slice(0, MAX_ROUTES)
  }, [allTours, view, routeCtx, sortKey, rankCtx, startById])

  return (
    <>
      {clusterer.clustersFor(view.bbox, view.zoom).map((m) => (
        <Marker
          key={m.kind === 'start' ? `s${m.startId}` : `c${m.clusterId}`}
          position={[m.lat, m.lng]}
          icon={countIcon(m.count, dimmed)}
          eventHandlers={{
            click: () => {
              if (m.kind === 'start') { onSelectStarts([m.startId]); return }
              map.flyTo([m.lat, m.lng], Math.min(clusterer.expansionZoom(m.clusterId), map.getMaxZoom()))
              onSelectStarts(clusterer.startIdsOf(m.clusterId))
            },
          }}
        />
      ))}
      {routeCtx && routedTours.map((tour) => {
        const route = tourToRoute(tour, routeCtx)
        if (!route) return null
        const key = tourKey(tour)
        const isHovered = hoveredTourKey === key
        const isDimmed = hoveredTourKey !== null && !isHovered
        return (
          <RouteLayer
            key={key} route={route} muted={!isHovered} dimmedOut={isDimmed}
            onHover={(hovering) => onHoverTour(hovering ? key : null)}
            onClick={() => onPickRoute(tour)}
          />
        )
      })}
    </>
  )
}
