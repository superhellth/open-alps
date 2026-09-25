import { useEffect, useMemo, useRef, useState } from 'react'
import L from 'leaflet'
import { Marker, useMap, useMapEvents } from 'react-leaflet'
import type { StartGroup } from '@/tourSearch/groupByStart.js'
import { NO_TOURS, tourKey } from '@/tourSearch/tourKey.js'
import type { PlannerTour } from '@/tourSearch/plannerTour.js'
import type { StartPoint } from '@/data/types.js'
import { currentView, routeTouchesBbox } from '@/lib/viewport.js'
import type { View } from '@/lib/viewport.js'
import { tourToRoute, tourWaypoints } from './routes.js'
import type { RouteContext } from './routes.js'
import RouteLayer from './RouteLayer.js'
import WaypointLayer, { collectSymbols } from './WaypointLayer.js'
import HoverTooltip from './HoverTooltip.js'
import SignpostMarker from './SignpostMarker.js'
import type { Activation } from './SignpostMarker.js'
import { createStartClusterer, markerKind, markerRadius } from './clusterStarts.js'
import type { MapMarker } from './clusterStarts.js'
import { escapeHtml, singleHtml, stackHtml } from './signpostHtml.js'
import type { Heading } from './signpostHtml.js'
import { tourBoardLabel } from './tourBoard.js'
import { indexToursByHut, indexToursByLeg, legKey, tierOf } from './tourMatch.js'
import './map.css'

/** Below this zoom, routes stay hidden and only markers show — tuned lower than the
 *  clusterer's own maxZoom (14) so routes appear before markers finish separating one-per-start. */
export const ROUTE_REVEAL_ZOOM = 11

const iconCache = new Map<string, L.DivIcon>()
function bubbleIcon(count: number, dimmed: boolean, highlighted: boolean): L.DivIcon {
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

/** The side of its start the tour's first leg leaves to, judged by the first waypoint after the start. */
function headingOf(tour: PlannerTour, ctx: RouteContext | null): Heading {
  const w = ctx ? tourToRoute(tour, ctx)?.waypoints : undefined
  return w && w.length > 1 && w[1].lng < w[0].lng ? 'west' : 'east'
}

const toursText = (n: number) => `In ${n} Touren`

/** One marker per start point with matching tours or per cluster of start points, clustered by zoom. Below
 *  `ROUTE_REVEAL_ZOOM` every marker is a round yellow bubble with the summed count, and a click always focuses and zooms in; from there
 *  on a start point becomes a signpost (a single tour board, or a stack of boards with the tour count) and a cluster stays a bubble.
 *  Panning and zooming only re-cluster, they never re-search. A single board and every board of a spread stack
 *  pick their tour on click; a stack or cluster click flies the map to the bounds of its tours, focuses the results list on them
 *  and draws them at the focused tier until the focus is dropped (show all tours, a map click, or zooming out
 *  past the zoom the click flew to); markers outside the focus fade like the search-running state.
 *  Past `ROUTE_REVEAL_ZOOM`, routes draw for every tour whose waypoints' bounding box overlaps the viewport,
 *  in three tiers (rest, focused, hovered); the focused and hovered tiers are display-only copies above the
 *  interactive rest lines, so mouseout always fires. Hovering a leg or hut hovers every visible tour containing
 *  it; clicking one focuses the list on those tours (a leg or hut in a single tour picks it). */
export default function DiscoverLayer({
  groups, startById, dimmed, allTours, routeCtx, hutNameById, hoveredTourKeys, onHoverTours, onPickRoute, onNavigate,
  focusTours, onFocusTours, onHoverStarts, onViewChange,
}: {
  groups: StartGroup<PlannerTour>[]
  startById: Map<number, StartPoint>
  dimmed: boolean
  allTours: PlannerTour[]
  routeCtx: RouteContext | null
  hutNameById: Map<number, string>
  /** Tours hovered anywhere (map or results list); drawn at the hovered tier. */
  hoveredTourKeys: ReadonlySet<string>
  onHoverTours: (keys: ReadonlySet<string>) => void
  onPickRoute: (tour: PlannerTour) => void
  onNavigate?: () => void
  /** Tour keys the results list is limited to and the map highlights; null when unfocused. */
  focusTours?: ReadonlySet<string> | null
  /** Sets the focus; null lifts it. */
  onFocusTours?: (keys: string[] | null) => void
  /** Start points of the marker under the pointer; null when none. */
  onHoverStarts?: (startIds: Set<number> | null) => void
  onViewChange?: (view: View) => void
}) {
  const map = useMap()
  /** Zoom the map settled on when the focus was set; zooming out below it drops the focus. */
  const focusZoom = useRef(0)
  const [view, setView] = useState<View>(() => currentView(map))
  useMapEvents({
    moveend: () => setView(currentView(map)),
    zoomend: () => {
      setView(currentView(map))
      if (focusTours && map.getZoom() < focusZoom.current) onFocusTours?.(null)
    },
  })
  useEffect(() => { onViewChange?.(view) }, [view, onViewChange])

  const clusterer = useMemo(() => createStartClusterer(groups.flatMap((g) => {
    const s = startById.get(g.startId)
    return s ? [{ startId: g.startId, count: g.tours.length, lat: s.lat, lng: s.lng }] : []
  })), [groups, startById])
  const groupOfStart = useMemo(() => new Map(groups.map((g) => [g.startId, g])), [groups])
  const tourByKey = useMemo(() => new Map(allTours.map((t) => [tourKey(t), t])), [allTours])
  const keysOfStarts = (startIds: number[]) => startIds.flatMap((id) => groupOfStart.get(id)?.tours.map(tourKey) ?? [])

  const routeReveal = view.zoom >= ROUTE_REVEAL_ZOOM
  const routedTours = useMemo(() => {
    if (!routeCtx || !routeReveal) return []
    return allTours.flatMap((tour) => {
      const route = tourToRoute(tour, routeCtx)
      return route && routeTouchesBbox(route.waypoints, view.bbox) ? [{ key: tourKey(tour), tour, route }] : []
    })
  }, [allTours, routeCtx, routeReveal, view.bbox])
  const toursByLeg = useMemo(() => indexToursByLeg(routedTours), [routedTours])
  const toursByHut = useMemo(() => indexToursByHut(routedTours), [routedTours])

  const [hoveredStartIds, setHoveredStartIds] = useState<ReadonlySet<number> | null>(null)
  const hoverStarts = (ids: Set<number> | null) => { setHoveredStartIds(ids); onHoverStarts?.(ids) }
  const tiered = useMemo(() => routedTours.map((r) => ({
    ...r, tier: tierOf({ key: r.key, startId: r.tour.startId }, { hoveredKeys: hoveredTourKeys, hoveredStarts: hoveredStartIds, focus: focusTours ?? null }),
  })), [routedTours, hoveredTourKeys, hoveredStartIds, focusTours])
  const drawn = useMemo(() => tiered.filter((t) => t.tier !== 'rest'), [tiered])
  const symbols = useMemo(() => collectSymbols(tiered), [tiered])

  const [tip, setTip] = useState<{ at: L.LatLng; html: string } | null>(null)
  const hoverKeys = (keys: string[] | null, at: L.LatLng, title?: string) => {
    if (!keys) { onHoverTours(NO_TOURS); setTip(null); return }
    onHoverTours(new Set(keys))
    setTip({ at, html: `${title ? `<strong>${escapeHtml(title)}</strong><br>` : ''}${toursText(keys.length)}` })
  }
  /** A shared leg or hut: one tour is picked, several focus the list on them. */
  const clickKeys = (keys: string[]) => {
    if (keys.length === 0) return
    onNavigate?.()
    if (keys.length === 1) {
      const tour = tourByKey.get(keys[0])
      if (tour) onPickRoute(tour)
      return
    }
    onFocusTours?.(keys)
    const bounds = boundsOfTours(keys.flatMap((k) => tourByKey.get(k) ?? []))
    if (bounds) zoomToBounds(bounds)
    else focusZoom.current = map.getZoom()
  }

  /** Bounds of every waypoint of the given tours. */
  const boundsOfTours = (tours: PlannerTour[]): L.LatLngBounds | null => {
    if (!routeCtx) return null
    const bounds = L.latLngBounds([])
    for (const p of tourWaypoints(tours, routeCtx)) bounds.extend([p.lat, p.lng])
    return bounds.isValid() ? bounds : null
  }
  /** Bounds of every tour starting at one of the given start points. */
  const tourBounds = (startIds: number[]) => {
    const ids = new Set(startIds)
    return boundsOfTours(groups.filter((g) => ids.has(g.startId)).flatMap((g) => g.tours))
  }
  const zoomToBounds = (bounds: L.LatLngBounds) => {
    focusZoom.current = Math.min(map.getBoundsZoom(bounds, false, L.point(80, 80)), map.getMaxZoom())
    map.flyToBounds(bounds, { padding: [40, 40], duration: 0.6 })
  }

  const startIdsOf = (m: MapMarker) => (m.kind === 'cluster' ? clusterer.startIdsOf(m.clusterId) : [m.startId])
  const markerKey = (m: MapMarker) => (m.kind === 'start' ? `s${m.startId}` : `c${m.clusterId}`)

  const markers = useMemo(() => clusterer.clustersFor(view.bbox, view.zoom), [clusterer, view])
  const htmlByMarker = useMemo(() => new Map(markers.flatMap((m) => {
    if (m.kind === 'cluster' || !routeReveal) return []
    const boards = (groupOfStart.get(m.startId)?.tours ?? [])
      .map((t) => ({ key: tourKey(t), label: tourBoardLabel(t, startById) }))
    const tour = groupOfStart.get(m.startId)?.tours[0]
    const single = markerKind(m) === 'single' && boards[0] && tour
    return [[markerKey(m), single ? singleHtml(boards[0], headingOf(tour, routeCtx)) : stackHtml(boards)] as const]
  })), [markers, groupOfStart, startById, routeReveal, routeCtx])

  const highlightedStarts = useMemo(() => {
    const ids = new Set<number>()
    for (const key of hoveredTourKeys) { const t = tourByKey.get(key); if (t) ids.add(t.startId) }
    return ids
  }, [hoveredTourKeys, tourByKey])

  const hoverActive = hoveredTourKeys.size > 0 || (hoveredStartIds?.size ?? 0) > 0

  const activate = (m: MapMarker, a: Activation) => {
    onNavigate?.()
    if (a.kind === 'tour') {
      const tour = tourByKey.get(a.tourKey)
      if (tour) onPickRoute(tour)
      return
    }
    const startIds = startIdsOf(m)
    const only = routeReveal && m.kind === 'start' && m.count === 1 ? groupOfStart.get(m.startId)?.tours[0] : undefined
    if (only) { onPickRoute(only); return }
    onFocusTours?.(keysOfStarts(startIds))
    const bounds = tourBounds(startIds)
    if (bounds) {
      zoomToBounds(bounds)
    } else if (m.kind === 'cluster') {
      focusZoom.current = Math.min(clusterer.expansionZoom(m.clusterId), map.getMaxZoom())
      map.setView([m.lat, m.lng], focusZoom.current)
    }
  }

  return (
    <>
      {markers.map((m) => {
        const ids = startIdsOf(m)
        const outsideFocus = focusTours != null && !keysOfStarts(ids).some((k) => focusTours.has(k))
        const highlighted = ids.some((id) => highlightedStarts.has(id))
        const hovered = highlighted || ids.some((id) => hoveredStartIds?.has(id))
        const dimmedMarker = dimmed || outsideFocus || (hoverActive && !hovered)
        if (m.kind === 'cluster' || !routeReveal) {
          return (
            <Marker
              key={markerKey(m)} position={[m.lat, m.lng]} icon={bubbleIcon(m.count, dimmedMarker, highlighted)}
              eventHandlers={{
                mouseover: () => hoverStarts(new Set(ids)),
                mouseout: () => hoverStarts(null),
                click: () => activate(m, { kind: 'body' }),
              }}
            />
          )
        }
        return (
          <SignpostMarker
            key={markerKey(m)} position={[m.lat, m.lng]} kind={markerKind(m)} html={htmlByMarker.get(markerKey(m)) ?? ''}
            dimmed={dimmedMarker} highlighted={highlighted}
            onHoverMarker={(hovering) => hoverStarts(hovering ? new Set(ids) : null)}
            onHoverTour={(key) => onHoverTours(key ? new Set([key]) : NO_TOURS)}
            onActivate={(a) => activate(m, a)}
          />
        )
      })}
      {drawn.map(({ key, route }) => (
        <RouteLayer
          key={key} route={route} emphasis="rest" dots={false}
          onHover={(hovering, i, at) => {
            const lk = legKey(route.legs[i])
            hoverKeys(hovering ? (lk ? toursByLeg.get(lk) ?? [key] : [key]) : null, at)
          }}
          onClick={(i) => { const lk = legKey(route.legs[i]); clickKeys(lk ? toursByLeg.get(lk) ?? [key] : [key]) }}
        />
      ))}
      {/* The focused and hovered tiers are display-only copies above the rest tier; the interactive
          layers underneath never change, so their mouseout always fires. */}
      {tiered.filter((t) => t.tier === 'focused').map(({ key, route }) => <RouteLayer key={`f-${key}`} route={route} emphasis="focused" dots={false} interactive={false} />)}
      {tiered.filter((t) => t.tier === 'hovered').map(({ key, route }) => <RouteLayer key={`h-${key}`} route={route} emphasis="hovered" dots={false} interactive={false} />)}
      <WaypointLayer
        symbols={symbols}
        onHoverHut={(hutId, at) => hoverKeys(hutId === null ? null : toursByHut.get(hutId) ?? [], at, hutId === null ? undefined : hutNameById.get(hutId) ?? String(hutId))}
        onClickHut={(hutId) => clickKeys(toursByHut.get(hutId) ?? [])}
      />
      <HoverTooltip tip={tip} />
    </>
  )
}
