import { useEffect, useMemo, useRef, useState } from 'react'
import L from 'leaflet'
import { Marker, useMap, useMapEvents } from 'react-leaflet'
import type { StartGroup } from '@/tourSearch/groupByStart.js'
import { NO_TOURS, tourKey } from '@/tourSearch/tourKey.js'
import type { PlannerTour } from '@/tourSearch/plannerTour.js'
import type { StartPoint } from '@/data/types.js'
import { currentView, routeTouchesBbox } from '@/lib/viewport.js'
import type { View } from '@/lib/viewport.js'
import { tourAnchorCandidatesOf, tourToRoute, tourWaypoints } from './routes.js'
import type { RouteContext } from './routes.js'
import RouteLayer from './RouteLayer.js'
import WaypointLayer, { collectSymbols } from './WaypointLayer.js'
import HoverTooltip from './HoverTooltip.js'
import { HOVER_Z_OFFSET } from './routePanes.js'
import SignpostMarker from './SignpostMarker.js'
import { createStartClusterer, markerRadius } from './clusterStarts.js'
import type { MapMarker } from './clusterStarts.js'
import { dotHtml, escapeHtml, singleHtml } from './signpostHtml.js'
import { measureBoard, placeSignposts } from './placeSignposts.js'
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
 *  focuses the results list on those tours and zooms in. From `ROUTE_REVEAL_ZOOM` on each tour's board stands on a mast planted on
 *  one of its route's anchors (`placeSignposts`: rank order, a colliding tour moves to its next anchor candidate); a tour that fits
 *  nowhere shows as a foot dot whose hover, focus or list hover shows its board. Panning and zooming only re-place, they never
 *  re-search. Boards and dots pick their tour on click. A shared leg or hut click focuses the results list on its tours and flies
 *  to their bounds; the focused tours draw at the focused tier until the focus is dropped (show all tours, a map click, or
 *  zooming out past the zoom the click flew to); markers outside the focus fade like the search-running state.
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
  /** Tours with at least one anchor candidate in view, in rank order (`allTours` order); recomputed with every view change. */
  const placeableTours = useMemo(() => routedTours.flatMap(({ key, tour, route }) => {
    const candidates = routeCtx ? tourAnchorCandidatesOf(tour, route, routeCtx, view.bbox) : []
    return candidates.length > 0 ? [{ key, label: tourBoardLabel(tour, startById), candidates }] : []
  }), [routedTours, routeCtx, view.bbox, startById])
  const labelByKey = useMemo(() => new Map(placeableTours.map((t) => [t.key, t.label])), [placeableTours])
  const placements = useMemo(() => {
    const size = map.getSize()
    return placeSignposts(placeableTours, (p) => map.latLngToContainerPoint([p.lat, p.lng]), measureBoard, { width: size.x, height: size.y })
  }, [placeableTours, map])
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
      {placements.map((p) => {
        const tour = tourByKey.get(p.key)
        const label = labelByKey.get(p.key)
        if (!tour || !label) return null
        const outsideFocus = focusTours != null && !focusTours.has(p.key)
        const highlighted = hoveredTourKeys.has(p.key)
        const startHovered = hoveredStartIds?.has(tour.startId) ?? false
        const dimmedMarker = dimmed || outsideFocus || (hoverActive && !(highlighted || startHovered))
        const boardTour = { key: p.key, label }
        return (
          <SignpostMarker
            key={p.key} position={[p.lat, p.lng]} kind={p.kind}
            html={p.kind === 'board' ? singleHtml(boardTour, p.side) : dotHtml(boardTour, p.side)}
            dimmed={dimmedMarker} highlighted={highlighted || startHovered}
            fadedKeys={pointerOnSignpost ? NO_TOURS : hoveredTourKeys}
            onHoverMarker={(hovering) => { setPointerOnSignpost(hovering); onHoverTours(hovering ? new Set([p.key]) : NO_TOURS) }}
            onActivate={() => { onNavigate?.(); onPickRoute(tour) }}
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
