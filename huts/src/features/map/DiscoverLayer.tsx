import { useEffect, useMemo, useRef, useState } from 'react'
import L from 'leaflet'
import { Marker, useMap, useMapEvents } from 'react-leaflet'
import type { StartGroup } from '@/tourSearch/groupByStart.js'
import { NO_TOURS, tourKey } from '@/tourSearch/tourKey.js'
import type { PlannerTour } from '@/tourSearch/plannerTour.js'
import type { StartPoint } from '@/data/types.js'
import { currentView, routeTouchesBbox } from '@/lib/viewport.js'
import type { View } from '@/lib/viewport.js'
import { tourAnchorCandidatesOf, tourMapPoint, tourToRoute, tourWaypoints } from './routes.js'
import type { RouteContext } from './routes.js'
import RouteLayer from './RouteLayer.js'
import WaypointLayer from './WaypointLayer.js'
import { collectSymbols } from './waypointSymbols.js'
import HoverTooltip from './HoverTooltip.js'
import { HOVER_Z_OFFSET } from './routePanes.js'
import SignpostMarker from './SignpostMarker.js'
import { createTourClusterer, markerRadius } from './clusterTours.js'
import type { MapMarker } from './clusterTours.js'
import { dotHtml, escapeHtml, singleHtml } from './signpostHtml.js'
import { measureBoard, placeSignposts } from './placeSignposts.js'
import type { Placement } from './placeSignposts.js'
import { tourBoardLabel } from './tourBoard.js'
import { indexToursByEnd, indexToursByHut, indexToursByLeg, legKey, tierOf } from './tourMatch.js'
import { makeStartLabel } from '@/data/labels.js'
import type { WaypointStop } from './types.js'
import './map.css'

/** Below this zoom only count bubbles show; from it on tour boards, route hover and waypoint symbols do. Lower than the
 *  clusterer's own maxZoom (14), so boards appear before bubbles finish separating one-per-start. */
const ROUTE_REVEAL_ZOOM = 11

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

/** A count bubble. A bubble that re-clusters away while hovered never gets a `mouseout`, so its hover is released on unmount. */
function BubbleMarker({ position, icon, highlighted, onHover, onActivate }: {
  position: [number, number]
  icon: L.DivIcon
  highlighted: boolean
  onHover: (hovering: boolean) => void
  onActivate: () => void
}) {
  const callbacks = useRef({ onHover, onActivate })
  useEffect(() => { callbacks.current = { onHover, onActivate } })
  const hovering = useRef(false)
  useEffect(() => () => {
    if (hovering.current) callbacks.current.onHover(false)
  }, [])
  return (
    <Marker
      position={position} icon={icon} zIndexOffset={highlighted ? HOVER_Z_OFFSET : 0}
      eventHandlers={{
        mouseover: () => { hovering.current = true; callbacks.current.onHover(true) },
        mouseout: () => { hovering.current = false; callbacks.current.onHover(false) },
        click: () => callbacks.current.onActivate(),
      }}
    />
  )
}

/** A bubble click zooms to its tours' anchors at no less than `ROUTE_REVEAL_ZOOM`, so it splits into boards, and at no more than this. */
const BUBBLE_ZOOM_MAX = 13

const toursText = (n: number) => (n === 1 ? 'In 1 Tour' : `In ${n} Touren`)

/** Below `ROUTE_REVEAL_ZOOM` round yellow bubbles cluster the tours at their default signpost anchors (`tourAnchor` unclipped),
 *  so crossing the reveal zoom splits a bubble into the boards standing where it stood; a click flies to its tours' anchors
 *  at the reveal zoom or closer, without focusing them. A tour hovered from the list dims the bubbles not holding it; a bubble
 *  hovered on the map only highlights itself. From `ROUTE_REVEAL_ZOOM` on each tour's board stands on a mast planted on
 *  one of its route's anchors (`placeSignposts`: rank order, a colliding tour moves to its next anchor candidate, a board whose
 *  foot stays in view is pinned and turns into a dot on its spot when it collides); a tour that fits nowhere shows as a foot
 *  dot whose hover, focus or list hover shows its board. Panning and zooming only re-place, they never re-search. Boards and
 *  dots pick their tour on click. A board fades while its tour is hovered from anywhere but the signpost itself.
 *
 *  Route lines draw only for hovered or focused tours; hut and end symbols draw for every tour whose waypoints' bounding box
 *  overlaps the viewport, at that tour's tier (rest, focused, hovered). A drawn tour's lines are an interactive rest-tier copy
 *  with display-only focused or hovered copies above it, so mouseout always fires. Hovering a leg or hut hovers every visible
 *  tour containing it; clicking one picks the tour when it is the only one there, otherwise focuses the results list on those
 *  tours and flies to their bounds. The focus lasts until it is dropped (show all tours, a map click, or zooming out past the
 *  zoom the click flew to); markers outside the focus fade like the search-running state unless their tour is hovered. */
export default function DiscoverLayer({
  groups, startById, dimmed, allTours, routeCtx, hutNameById, hoveredTourKeys, onHoverTours, onPickRoute, onNavigate,
  focusTours, onFocusTours, onViewChange,
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
  onNavigate: () => void
  /** Tour keys the results list is limited to and the map highlights; null when unfocused. */
  focusTours: ReadonlySet<string> | null
  /** Sets the focus; null lifts it. */
  onFocusTours: (keys: string[] | null) => void
  onViewChange: (view: View) => void
}) {
  const map = useMap()
  /** Zoom the map settled on when the focus was set; zooming out below it drops the focus. */
  const focusZoom = useRef(0)
  const [view, setView] = useState<View>(() => currentView(map))
  useMapEvents({
    moveend: () => setView(currentView(map)),
    zoomend: () => {
      setView(currentView(map))
      if (focusTours && map.getZoom() < focusZoom.current) onFocusTours(null)
    },
  })
  useEffect(() => { onViewChange(view) }, [view, onViewChange])

  const bubbleTourByKey = useMemo(() => new Map(groups.flatMap((g) => g.tours).map((t) => [tourKey(t), t])), [groups])
  /** A tour whose route does not resolve stands on its start point. */
  const pointByKey = useMemo(() => new Map([...bubbleTourByKey].flatMap(([key, tour]) => {
    const p = routeCtx ? tourMapPoint(tour, routeCtx) : startById.get(tour.startId)
    return p ? [[key, { lat: p.lat, lng: p.lng }] as const] : []
  })), [bubbleTourByKey, routeCtx, startById])
  const clusterer = useMemo(() => createTourClusterer([...pointByKey].map(([key, p]) => ({ key, ...p }))), [pointByKey])
  const tourByKey = useMemo(() => new Map(allTours.map((t) => [tourKey(t), t])), [allTours])

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
  /** The last committed placement; the next one pins its boards that are still in view. */
  const previousPlacements = useRef<Placement[]>([])
  const placements = useMemo(() => {
    const size = map.getSize()
    const project = (p: { lat: number; lng: number }) => map.latLngToContainerPoint([p.lat, p.lng])
    return placeSignposts(placeableTours, project, measureBoard, { width: size.x, height: size.y }, previousPlacements.current)
  }, [placeableTours, map])
  useEffect(() => { previousPlacements.current = placements }, [placements])
  /** Zoom at which the pointer entered a count bubble. A zoom change re-clusters the bubbles without a mouseout, so the
   *  pointer counts as on a bubble only at that zoom; there the other bubbles keep full opacity. */
  const [bubbleHoverZoom, setBubbleHoverZoom] = useState<number | null>(null)
  const pointerOnBubble = bubbleHoverZoom === view.zoom
  const toursByLeg = useMemo(() => indexToursByLeg(routedTours), [routedTours])
  const toursByHut = useMemo(() => indexToursByHut(routedTours), [routedTours])
  const toursByEnd = useMemo(() => indexToursByEnd(routedTours), [routedTours])
  const startLabel = useMemo(() => makeStartLabel(startById), [startById])
  const toursOfStop = (stop: WaypointStop) => (stop.type === 'hut' ? toursByHut.get(stop.hutId) : toursByEnd.get(stop.startId)) ?? []
  const titleOfStop = (stop: WaypointStop) => (stop.type === 'hut' ? hutNameById.get(stop.hutId) ?? String(stop.hutId) : startLabel(stop.startId))

  const tiered = useMemo(() => routedTours.map((r) => ({
    ...r, tier: tierOf(r.key, { hoveredKeys: hoveredTourKeys, focus: focusTours }),
  })), [routedTours, hoveredTourKeys, focusTours])
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
    onNavigate()
    if (keys.length === 1) {
      const tour = tourByKey.get(keys[0])
      if (tour) onPickRoute(tour)
      return
    }
    onFocusTours(keys)
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
  const zoomToBounds = (bounds: L.LatLngBounds) => {
    focusZoom.current = Math.min(map.getBoundsZoom(bounds, false, L.point(80, 80)), map.getMaxZoom())
    map.flyToBounds(bounds, { padding: [40, 40], duration: 0.6 })
  }

  const keysOf = (m: MapMarker) => (m.kind === 'cluster' ? clusterer.keysOf(m.clusterId) : [m.key])
  const markerKey = (m: MapMarker) => (m.kind === 'tour' ? `t${m.key}` : `c${m.clusterId}`)

  const markers = useMemo(() => clusterer.clustersFor(view.bbox, view.zoom), [clusterer, view])

  const hoverActive = hoveredTourKeys.size > 0

  /** Flies to the bubble's tour anchors, where it splits into their boards. */
  const activate = (m: MapMarker) => {
    onNavigate()
    const bounds = L.latLngBounds(keysOf(m).flatMap((k) => pointByKey.get(k) ?? []))
    if (!bounds.isValid()) return
    const fit = map.getBoundsZoom(bounds, false, L.point(80, 80))
    const zoom = Math.min(Math.max(fit, ROUTE_REVEAL_ZOOM), BUBBLE_ZOOM_MAX, map.getMaxZoom())
    map.flyTo(bounds.getCenter(), zoom, { duration: 0.6 })
  }

  return (
    <>
      {!routeReveal && markers.map((m) => {
        const keys = keysOf(m)
        const outsideFocus = focusTours != null && !keys.some((k) => focusTours.has(k))
        const highlighted = keys.some((k) => hoveredTourKeys.has(k))
        const dimmedMarker = dimmed || (!highlighted && (outsideFocus || (hoverActive && !pointerOnBubble)))
        return (
          <BubbleMarker
            key={markerKey(m)} position={[m.lat, m.lng]} icon={bubbleIcon(m.count, dimmedMarker, highlighted)} highlighted={highlighted}
            onHover={(hovering) => {
              setBubbleHoverZoom(hovering ? view.zoom : null)
              onHoverTours(hovering ? new Set(keys) : NO_TOURS)
            }}
            onActivate={() => activate(m)}
          />
        )
      })}
      {placements.map((p) => {
        const tour = tourByKey.get(p.key)
        const label = labelByKey.get(p.key)
        if (!tour || !label) return null
        const outsideFocus = focusTours != null && !focusTours.has(p.key)
        const highlighted = hoveredTourKeys.has(p.key)
        const dimmedMarker = dimmed || (!highlighted && (outsideFocus || hoverActive))
        const boardTour = { key: p.key, label }
        return (
          <SignpostMarker
            key={p.key} position={[p.lat, p.lng]} kind={p.kind}
            html={p.kind === 'board' ? singleHtml(boardTour, p.side) : dotHtml(boardTour, p.side)}
            dimmed={dimmedMarker} highlighted={highlighted}
            onHoverMarker={(hovering) => onHoverTours(hovering ? new Set([p.key]) : NO_TOURS)}
            onActivate={() => { onNavigate(); onPickRoute(tour) }}
          />
        )
      })}
      {drawn.map(({ key, route }) => (
        <RouteLayer
          key={key} route={route} tier="rest" thin dots={false}
          onHover={(hovering, i, at) => {
            const lk = legKey(route.legs[i])
            hoverKeys(hovering ? (lk ? toursByLeg.get(lk) ?? [key] : [key]) : null, at)
          }}
          onClick={(i) => { const lk = legKey(route.legs[i]); clickKeys(lk ? toursByLeg.get(lk) ?? [key] : [key]) }}
        />
      ))}
      {/* The focused and hovered tiers are display-only copies above the rest tier; the interactive
          layers underneath never change, so their mouseout always fires. */}
      {tiered.filter((t) => t.tier === 'focused').map(({ key, route }) => <RouteLayer key={`f-${key}`} route={route} tier="focused" thin dots={false} interactive={false} />)}
      {tiered.filter((t) => t.tier === 'hovered').map(({ key, route }) => <RouteLayer key={`h-${key}`} route={route} tier="hovered" dots={false} interactive={false} />)}
      <WaypointLayer
        symbols={symbols}
        onHoverStop={(stop, at) => { hoverKeys(stop === null ? null : toursOfStop(stop), at, stop === null ? undefined : titleOfStop(stop)) }}
        onClickStop={(stop) => clickKeys(toursOfStop(stop))}
      />
      <HoverTooltip tip={tip} />
    </>
  )
}
