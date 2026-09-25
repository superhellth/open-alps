import { useEffect, useMemo, useRef, useState } from 'react'
import L from 'leaflet'
import { Marker, useMap, useMapEvents } from 'react-leaflet'
import type { TourAnchor } from '@/tourSearch/tourAnchor.js'
import type { StartGroup } from '@/tourSearch/groupByStart.js'
import { NO_TOURS, tourKey } from '@/tourSearch/tourKey.js'
import type { PlannerTour } from '@/tourSearch/plannerTour.js'
import type { StartPoint } from '@/data/types.js'
import { currentView, routeTouchesBbox } from '@/lib/viewport.js'
import type { View } from '@/lib/viewport.js'
import { tourAnchorOf, tourToRoute, tourWaypoints } from './routes.js'
import type { RouteContext } from './routes.js'
import RouteLayer from './RouteLayer.js'
import WaypointLayer, { collectSymbols } from './WaypointLayer.js'
import HoverTooltip from './HoverTooltip.js'
import { HOVER_Z_OFFSET } from './routePanes.js'
import SignpostMarker from './SignpostMarker.js'
import type { Activation } from './SignpostMarker.js'
import { anchorMarkerKind, createAnchorClusterer, createStartClusterer, markerRadius } from './clusterStarts.js'
import type { AnchorMarker, MapMarker } from './clusterStarts.js'
import { escapeHtml, singleHtml, stackHtml } from './signpostHtml.js'
import { tourBoardLabel } from './tourBoard.js'
import { indexToursByEnd, indexToursByHut, indexToursByLeg, legKey, tierOf } from './tourMatch.js'
import { makeStartLabel } from '@/data/labels.js'
import type { WaypointStop } from './types.js'
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

const toursText = (n: number) => `In ${n} Touren`

/** Below `ROUTE_REVEAL_ZOOM` one round yellow bubble per start point or cluster of start points carries the summed count; a click
 *  focuses the results list on those tours and zooms in. From `ROUTE_REVEAL_ZOOM` on each tour's board stands on a mast planted
 *  on its route's mid-route anchor (`tourAnchorOf`), and tours whose anchors cluster share one stack signpost with the tour count.
 *  Panning and zooming only re-cluster, they never re-search. A single board and every board of a spread stack
 *  pick their tour on click; a stack click flies the map to the bounds of its tours, focuses the results list on them
 *  and draws them at the focused tier until the focus is dropped (show all tours, a map click, or zooming out
 *  past the zoom the click flew to); markers outside the focus fade like the search-running state.
 *  Past `ROUTE_REVEAL_ZOOM`, routes draw for every tour whose waypoints' bounding box overlaps the viewport,
 *  in three tiers (rest, focused, hovered); the focused and hovered tiers are display-only copies above the
 *  interactive rest lines, so mouseout always fires. Hovering a leg or hut hovers every visible tour containing
 *  it; clicking one focuses the list on those tours (a leg or hut in a single tour picks it). A board fades while its tour is
 *  hovered from anywhere but the signpost itself. */
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
  const anchoredTours = useMemo(() => routedTours.flatMap(({ key, tour, route }) => {
    const anchor = routeCtx ? tourAnchorOf(tour, route, routeCtx, view.bbox) : null
    return anchor ? [{ key, tour, anchor }] : []
  }), [routedTours, routeCtx, view.bbox])
  const anchorByKey = useMemo(() => new Map<string, TourAnchor>(anchoredTours.map((t) => [t.key, t.anchor])), [anchoredTours])
  const anchorClusterer = useMemo(
    () => createAnchorClusterer(anchoredTours.map(({ key, anchor }) => ({ tourKey: key, lat: anchor.lat, lng: anchor.lng }))),
    [anchoredTours],
  )
  const signposts = useMemo(() => (routeReveal ? anchorClusterer.markersFor(view.bbox, view.zoom) : []), [anchorClusterer, routeReveal, view])
  const htmlOfSignpost = (m: AnchorMarker) => {
    const boards = m.tourKeys.flatMap((k) => {
      const t = tourByKey.get(k)
      return t ? [{ key: k, label: tourBoardLabel(t, startById) }] : []
    })
    return anchorMarkerKind(m) === 'single' && boards[0]
      ? singleHtml(boards[0], anchorByKey.get(m.tourKeys[0])?.heading ?? 'east')
      : stackHtml(boards)
  }
  /** The pointer is on a signpost: its own board keeps full opacity. */
  const [pointerOnSignpost, setPointerOnSignpost] = useState(false)
  const toursByLeg = useMemo(() => indexToursByLeg(routedTours), [routedTours])
  const toursByHut = useMemo(() => indexToursByHut(routedTours), [routedTours])
  const toursByEnd = useMemo(() => indexToursByEnd(routedTours), [routedTours])
  const startLabel = useMemo(() => makeStartLabel(startById), [startById])
  const toursOfStop = (stop: WaypointStop) => (stop.type === 'hut' ? toursByHut.get(stop.hutId) : toursByEnd.get(stop.startId)) ?? []
  const titleOfStop = (stop: WaypointStop) => (stop.type === 'hut' ? hutNameById.get(stop.hutId) ?? String(stop.hutId) : startLabel(stop.startId))

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

  const highlightedStarts = useMemo(() => {
    const ids = new Set<number>()
    for (const key of hoveredTourKeys) { const t = tourByKey.get(key); if (t) ids.add(t.startId) }
    return ids
  }, [hoveredTourKeys, tourByKey])

  const hoverActive = hoveredTourKeys.size > 0 || (hoveredStartIds?.size ?? 0) > 0

  const activateSignpost = (m: AnchorMarker, a: Activation) => {
    onNavigate?.()
    const only = a.kind === 'tour' ? tourByKey.get(a.tourKey) : m.tourKeys.length === 1 ? tourByKey.get(m.tourKeys[0]) : undefined
    if (only) { onPickRoute(only); return }
    onFocusTours?.(m.tourKeys)
    const bounds = boundsOfTours(m.tourKeys.flatMap((k) => tourByKey.get(k) ?? []))
    if (bounds) zoomToBounds(bounds)
  }

  const activate = (m: MapMarker) => {
    onNavigate?.()
    const startIds = startIdsOf(m)
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
      {!routeReveal && markers.map((m) => {
        const ids = startIdsOf(m)
        const outsideFocus = focusTours != null && !keysOfStarts(ids).some((k) => focusTours.has(k))
        const highlighted = ids.some((id) => highlightedStarts.has(id))
        const hovered = highlighted || ids.some((id) => hoveredStartIds?.has(id))
        const dimmedMarker = dimmed || outsideFocus || (hoverActive && !hovered)
        return (
          <Marker
            key={markerKey(m)} position={[m.lat, m.lng]} icon={bubbleIcon(m.count, dimmedMarker, highlighted)}
            zIndexOffset={hovered ? HOVER_Z_OFFSET : 0}
            eventHandlers={{
              mouseover: () => hoverStarts(new Set(ids)),
              mouseout: () => hoverStarts(null),
              click: () => activate(m),
            }}
          />
        )
      })}
      {signposts.map((m) => {
        const outsideFocus = focusTours != null && !m.tourKeys.some((k) => focusTours.has(k))
        const highlighted = m.tourKeys.some((k) => hoveredTourKeys.has(k))
        const startHovered = m.tourKeys.some((k) => hoveredStartIds?.has(tourByKey.get(k)?.startId ?? -1))
        const dimmedMarker = dimmed || outsideFocus || (hoverActive && !(highlighted || startHovered))
        return (
          <SignpostMarker
            key={m.id} position={[m.lat, m.lng]} kind={anchorMarkerKind(m)} html={htmlOfSignpost(m)}
            heading={anchorByKey.get(m.tourKeys[0])?.heading ?? 'east'}
            dimmed={dimmedMarker} highlighted={highlighted || startHovered}
            fadedKeys={pointerOnSignpost ? NO_TOURS : hoveredTourKeys}
            onHoverMarker={(hovering) => { setPointerOnSignpost(hovering); onHoverTours(hovering ? new Set(m.tourKeys) : NO_TOURS) }}
            onHoverTour={(key) => onHoverTours(key ? new Set([key]) : NO_TOURS)}
            onActivate={(a) => activateSignpost(m, a)}
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
        onHoverStop={(stop, at) => hoverKeys(stop === null ? null : toursOfStop(stop), at, stop === null ? undefined : titleOfStop(stop))}
        onClickStop={(stop) => clickKeys(toursOfStop(stop))}
      />
      <HoverTooltip tip={tip} />
    </>
  )
}
