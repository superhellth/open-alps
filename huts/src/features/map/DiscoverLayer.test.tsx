// @vitest-environment jsdom
import { useState } from 'react'
import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import L from 'leaflet'
import { render, cleanup, fireEvent, act, waitFor } from '@testing-library/react'
import { MapContainer, useMap, useMapEvents } from 'react-leaflet'
import DiscoverLayer from './DiscoverLayer.js'
import type { PlannerTour } from '@/tourSearch/plannerTour.js'
import { NO_TOURS, tourKey } from '@/tourSearch/tourKey.js'
import * as geometry from '@/tourSearch/loadLegGeometry.js'
import * as routes from './routes.js'

afterEach(cleanup)
beforeEach(() => {
  vi.spyOn(geometry, 'loadLegGeometry').mockResolvedValue([[47.3, 12], [47.31, 12.01]])
})

function tour(startId: number, huts: number[], over: Partial<PlannerTour> = {}): PlannerTour {
  return {
    startId, exitStartId: startId, huts,
    legs: [...huts, 0].map(() => ({ durationH: 4, ascentM: 0, descentM: 0, distanceM: 0, edgeId: 1, reversed: false })),
    totalDurationH: huts.length * 4, totalAscentM: 0, totalDescentM: 0, totalDistanceM: 0,
    ...over,
  } as PlannerTour
}

const startById = new Map([[1, { name: null, sourceType: 1, lat: 47.3, lng: 12 }]])
const hutClassByIndex = new Map([[10, { operator: 'av' as const, serviced: true }], [11, { operator: 'sonstige' as const, serviced: false }], [12, { operator: 'av' as const, serviced: true }]])
const routeCtx = {
  hutCoordsById: new Map([[10, { lat: 47.3, lng: 12 }], [11, { lat: 47.31, lng: 12.01 }], [12, { lat: 47.32, lng: 12.02 }]]),
  startById, officialById: new Map(), hutClassByIndex, legAnchors: () => null,
}

let map: L.Map
function CaptureMap() { map = useMap(); return null }
function MapClick({ onClick }: { onClick: () => void }) { useMapEvents({ click: onClick }); return null }

const focusOn = (...tours: PlannerTour[]) => ({ allTours: tours, focusTours: new Set(tours.map(tourKey)) })

const layerProps = {
  hutNameById: new Map<number, string>(), hoveredTourKeys: NO_TOURS, onHoverTours: () => {}, onPickRoute: () => {},
  onNavigate: () => {}, focusTours: null, onFocusTours: () => {}, onViewChange: () => {},
}

function renderLayer(props: Partial<Parameters<typeof DiscoverLayer>[0]> = {}, zoom = 13, extra?: React.ReactNode) {
  return render(
    <MapContainer center={[47.3, 12]} zoom={zoom} style={{ height: 400, width: 400 }}>
      <CaptureMap />
      {extra}
      <DiscoverLayer
        groups={[]} startById={startById}
        dimmed={false} allTours={[tour(1, [10, 11])]}
        routeCtx={routeCtx}
        {...layerProps}
        {...props}
      />
    </MapContainer>,
  )
}

/** Owns the focus the way the planner does, so the layer's own focus changes feed back into its props. */
function FocusedLayer(props: Parameters<typeof DiscoverLayer>[0]) {
  const [focus, setFocus] = useState<Set<string> | null>(null)
  const [hovered, setHovered] = useState<ReadonlySet<string>>(NO_TOURS)
  return <DiscoverLayer {...props} focusTours={focus} onFocusTours={(keys) => setFocus(keys && new Set(keys))} hoveredTourKeys={hovered} onHoverTours={setHovered} />
}

describe('DiscoverLayer route lines', () => {
  it('draws no route lines below the reveal zoom', () => {
    const { container } = renderLayer({}, 9)
    expect(container.querySelectorAll('path.leaflet-interactive')).toHaveLength(0)
  })

  it('draws a route line for a tour whose start is in view, past the reveal zoom', async () => {
    const { container } = renderLayer(focusOn(tour(1, [10, 11])), 13)
    await waitFor(() => expect(container.querySelectorAll('path.leaflet-interactive').length).toBeGreaterThan(0))
  })

  it('draws no route lines for tours whose start is far outside the viewport', () => {
    const { container } = renderLayer({ allTours: [tour(2, [10, 11])], startById: new Map([...startById, [2, { name: null, sourceType: 1, lat: 10, lng: 10 }]]) }, 13)
    expect(container.querySelectorAll('path.leaflet-interactive')).toHaveLength(0)
  })

  it('draws every in-view tour, with no cap', async () => {
    const many = Array.from({ length: 80 }, (_, i) => tour(1, [i]))
    const routeCtxMany = {
      hutCoordsById: new Map(many.map((_, i) => [i, { lat: 47.3, lng: 12 + i * 0.0001 }])),
      startById, officialById: new Map(), hutClassByIndex: new Map(), legAnchors: () => null,
    }
    const { container: all } = renderLayer({ ...focusOn(...many), routeCtx: routeCtxMany }, 13)
    const { container: few } = renderLayer({ ...focusOn(...many.slice(0, 10)), routeCtx: routeCtxMany }, 13)
    const count = (c: HTMLElement) => c.querySelectorAll('path.leaflet-interactive').length
    await waitFor(() => expect(count(few)).toBeGreaterThan(0))
    const pathsPerTour = count(few) / 10
    await waitFor(() => expect(count(all)).toBe(80 * pathsPerTour))
  })
})

describe('DiscoverLayer shared legs and huts', () => {
  const a = tour(1, [10, 11])
  const b = tour(1, [10, 11, 12])
  const c = tour(1, [12], { legs: [2, 2].map((edgeId) => ({ durationH: 1, ascentM: 0, descentM: 0, distanceM: 0, edgeId, reversed: false })) } as never)
  const restPaths = (container: HTMLElement) => container.querySelectorAll('.leaflet-route-rest-line-pane path.leaflet-interactive')
  const firstRestPath = async (container: HTMLElement) => {
    await waitFor(() => expect(restPaths(container).length).toBeGreaterThan(0))
    return restPaths(container)[0]
  }

  it('hovering a shared leg hovers every tour containing it, with a count tooltip', async () => {
    const onHoverTours = vi.fn()
    const { container } = renderLayer({ ...focusOn(a, b), onHoverTours })
    fireEvent.mouseOver(await firstRestPath(container))
    expect([...onHoverTours.mock.calls.at(-1)![0]].sort()).toEqual([tourKey(a), tourKey(b)].sort())
    expect(document.querySelector('.leaflet-tooltip')!.textContent).toBe('In 2 Touren')
  })

  it('a leg click focuses the matched tours and is not read as the map click that drops the focus', async () => {
    const fly = vi.spyOn(L.Map.prototype, 'flyToBounds').mockReturnThis()
    vi.spyOn(L.Map.prototype, 'getBoundsZoom').mockReturnValue(13)
    const onFocusTours = vi.fn()
    const onMapClick = vi.fn()
    const { container } = renderLayer({ ...focusOn(a, b), onFocusTours }, 13, <MapClick onClick={onMapClick} />)
    fireEvent.click(await firstRestPath(container))
    expect(onFocusTours).toHaveBeenCalledWith(expect.arrayContaining([tourKey(a), tourKey(b)]))
    expect(fly).toHaveBeenCalledTimes(1)
    expect(onMapClick).not.toHaveBeenCalled()
  })

  it('a leg in a single tour picks it on click', async () => {
    const onPickRoute = vi.fn()
    const onFocusTours = vi.fn()
    const { container } = renderLayer({ ...focusOn(c), onPickRoute, onFocusTours })
    fireEvent.click(await firstRestPath(container))
    expect(onPickRoute).toHaveBeenCalledWith(c)
    expect(onFocusTours).not.toHaveBeenCalled()
  })

  it('hovering a hut hit target hovers every tour stopping there; the tooltip names the hut', async () => {
    const onHoverTours = vi.fn()
    const { container } = renderLayer({ ...focusOn(a, b), onHoverTours, hutNameById: new Map([[10, 'Hütte Eins']]) })
    const hits = container.querySelectorAll('.leaflet-route-hit-pane .leaflet-marker-icon')
    expect(hits.length).toBeGreaterThan(0)
    fireEvent.mouseOver(hits[1])
    expect(onHoverTours.mock.calls.at(-1)![0].size).toBe(2)
    expect(document.querySelector('.leaflet-tooltip')!.textContent).toBe('Hütte EinsIn 2 Touren')
  })

  it('hovering an end point hit target hovers every tour starting or ending there; the tooltip names it', async () => {
    const onHoverTours = vi.fn()
    const { container } = renderLayer({ ...focusOn(a, b), onHoverTours })
    fireEvent.mouseOver(container.querySelectorAll('.leaflet-route-hit-pane .leaflet-marker-icon')[0])
    expect(onHoverTours.mock.calls.at(-1)![0].size).toBe(2)
    expect(document.querySelector('.leaflet-tooltip')!.textContent).toBe('BahnhofIn 2 Touren')
  })

  it('draws hovered tours at the hovered tier and leaves the rest layer interactive', async () => {
    const { container } = renderLayer({ hoveredTourKeys: new Set([tourKey(a)]) })
    await waitFor(() => expect(container.querySelectorAll('.leaflet-route-hovered-line-pane path').length).toBeGreaterThan(0))
    expect(container.querySelectorAll('.leaflet-route-rest-line-pane path.leaflet-interactive').length).toBeGreaterThan(0)
  })

  it('draws focused tours thin at the focused tier and no dots on route lines', async () => {
    const { container } = renderLayer({ focusTours: new Set([tourKey(a)]) })
    await waitFor(() => expect(container.querySelectorAll('.leaflet-route-focused-line-pane path').length).toBeGreaterThan(0))
    expect(container.querySelectorAll('.leaflet-route-rest-symbol-pane path.leaflet-interactive, .leaflet-route-focused-symbol-pane path.leaflet-interactive, .leaflet-route-hovered-symbol-pane path.leaflet-interactive')).toHaveLength(0)
  })
})

describe('DiscoverLayer rest tier', () => {
  it('draws no route line but still the hut symbols of a tour that is neither focused nor hovered', async () => {
    const { container } = renderLayer({ allTours: [tour(1, [10, 11])] })
    await waitFor(() => expect(container.querySelectorAll('.leaflet-route-hit-pane .leaflet-marker-icon').length).toBeGreaterThan(0))
    expect(container.querySelectorAll('[class*="leaflet-route-"] path.leaflet-interactive')).toHaveLength(0)
  })
})

describe('DiscoverLayer marker focus', () => {
  const two = new Map([...startById, [2, { name: null, sourceType: 1, lat: 47.3, lng: 12.015 }]])
  /** Legs are shared only within a start, so a leg click focuses one start's tours. */
  const ownLegs = (startId: number, huts: number[]) => tour(startId, huts, {
    legs: [...huts, 0].map(() => ({ durationH: 4, ascentM: 0, descentM: 0, distanceM: 0, edgeId: startId, reversed: false })),
  } as never)
  const tours = [ownLegs(1, [10, 11]), ownLegs(1, [10, 11, 12]), ownLegs(2, [10, 11]), ownLegs(2, [10, 11, 12])]
  /** Hovering a board draws its tour's interactive line; a click on that line focuses the start's tours. */
  const focusViaBoard = async (c: HTMLElement) => {
    const board = c.querySelector('.signpost-marker.board .sign')!
    fireEvent.mouseOver(board)
    await waitFor(() => expect(c.querySelector('.leaflet-route-rest-line-pane path.leaflet-interactive')).not.toBeNull())
    fireEvent.click(c.querySelector('.leaflet-route-rest-line-pane path.leaflet-interactive')!)
    fireEvent.mouseOut(board, { relatedTarget: document.body })
  }
  const groups = [{ startId: 1, tours: tours.slice(0, 2) }, { startId: 2, tours: tours.slice(2) }] as never
  const routeCtx2 = { ...routeCtx, startById: two }

  beforeEach(() => {
    vi.spyOn(L.Map.prototype, 'flyToBounds').mockReturnThis()
    vi.spyOn(L.Map.prototype, 'getSize').mockImplementation(() => L.point(400, 400))
    vi.spyOn(routes, 'tourAnchorCandidatesOf').mockImplementation((t) => [{ lat: 47.3, lng: t.startId === 1 ? 12 : 12.015, heading: 'east' }])
  })
  afterEach(() => { vi.restoreAllMocks() })

  function renderFocused() {
    return render(
      <MapContainer center={[47.3, 12]} zoom={13} style={{ height: 400, width: 400 }}>
        <CaptureMap />
        <FocusedLayer groups={groups} startById={two} dimmed={false} allTours={tours} routeCtx={routeCtx2} {...layerProps} />
      </MapContainer>,
    )
  }

  it('draws the clicked marker\'s tours at the focused tier and dims other markers', async () => {
    const { container } = renderFocused()
    const focused = () => container.querySelectorAll('.leaflet-route-focused-line-pane path').length
    expect(focused()).toBe(0)
    await focusViaBoard(container)
    await waitFor(() => expect(focused()).toBeGreaterThan(0))
    expect(container.querySelectorAll('.leaflet-route-rest-line-pane path').length).toBeGreaterThan(0)
    const markers = container.querySelectorAll('.signpost-marker')
    expect(markers[0].classList.contains('dimmed')).toBe(false)
    expect(container.querySelector('.signpost-marker.dimmed')).not.toBeNull()
  })

  it('a hovered tour outside the focus shows its signpost undimmed', async () => {
    const { container } = renderFocused()
    await focusViaBoard(container)
    await waitFor(() => expect(container.querySelector('.signpost-marker.dimmed')).not.toBeNull())
    const outside = container.querySelector('.signpost-marker.dimmed')!
    fireEvent.mouseOver(outside.querySelector('.sign')!)
    await waitFor(() => expect(outside.classList.contains('dimmed')).toBe(false))
  })

  it('keeps the focus through a drag and through zooming that stays at or above the click zoom, drops it below', async () => {
    vi.spyOn(L.Map.prototype, 'getBoundsZoom').mockReturnValue(13)
    const { container } = renderFocused()
    const focused = () => container.querySelectorAll('.leaflet-route-focused-line-pane path').length > 0
    await focusViaBoard(container)
    await waitFor(() => expect(focused()).toBe(true))
    act(() => { map.fire('dragstart') })
    await waitFor(() => expect(focused()).toBe(true))
    act(() => { map.setZoom(14, { animate: false }) })
    await waitFor(() => expect(focused()).toBe(true))
    act(() => { map.setZoom(13, { animate: false }) })
    await waitFor(() => expect(focused()).toBe(true))
    act(() => { map.setZoom(12, { animate: false }) })
    await waitFor(() => expect(focused()).toBe(false))
  })
})

describe('DiscoverLayer signposts', () => {
  beforeEach(() => {
    vi.spyOn(L.Map.prototype, 'getSize').mockImplementation(() => L.point(400, 400))
  })
  afterEach(() => { vi.restoreAllMocks() })

  const withExit = new Map([
    [1, { name: 'Kaprun', sourceType: 1, lat: 47.3, lng: 12 }],
    [2, { name: 'Kaunertal', sourceType: 2, lat: 47.301, lng: 12 }],
  ])
  const exiting = (i: number) => tour(1, [100 + i], { exitStartId: 2, totalDistanceM: 42_300 } as never)
  const signpostHuts = new Map(Array.from({ length: 12 }, (_, i) => [100 + i, { lat: 47.31, lng: 12.01 }] as const))
  const stackTours = (n: number) => Array.from({ length: n }, (_, i) => exiting(i))
  const group = (tours: PlannerTour[]) => [{ startId: 1, tours }] as never
  const c1 = { lat: 47.31, lng: 11.98, heading: 'east' as const }
  const c2 = { lat: 47.29, lng: 12.02, heading: 'east' as const }
  /** Deterministic projection: 1° lng = 5000 px, 1° lat = 8000 px, viewport centre (47.3, 12) at (200, 200). */
  const linearProjection = () => vi.spyOn(L.Map.prototype, 'latLngToContainerPoint').mockImplementation(((p: L.LatLngExpression) => {
    const ll = L.latLng(p)
    return L.point(200 + (ll.lng - 12) * 5000, 200 - (ll.lat - 47.3) * 8000)
  }) as never)
  const twoCandidates = () => { vi.spyOn(routes, 'tourAnchorCandidatesOf').mockReturnValue([c1, c2]); linearProjection() }
  const render1 = (tours: PlannerTour[], props: Partial<Parameters<typeof DiscoverLayer>[0]> = {}, zoom = 13) =>
    renderLayer({ groups: group(tours), allTours: tours, startById: withExit, routeCtx: { ...routeCtx, startById: withExit, hutCoordsById: signpostHuts }, ...props }, zoom)

  it('renders a single tour as one board labelled end point and distance; click picks the tour', () => {
    const t = exiting(0)
    const onPickRoute = vi.fn()
    const { container } = render1([t], { onPickRoute })
    const sign = container.querySelector('.signpost-marker.board .sign') as HTMLElement
    expect(sign.textContent).toContain('Kaunertal')
    expect(sign.textContent).toContain('42.3 km')
    fireEvent.click(sign)
    expect(onPickRoute).toHaveBeenCalledWith(t)
  })

  it('gives tours with the same route their own boards on distinct anchors and drops the rest to dots', () => {
    twoCandidates()
    const tours = stackTours(3)
    const { container } = render1(tours)
    const markers = [...container.querySelectorAll('.signpost-marker')]
    expect(markers.map((m) => m.classList.contains('board') ? 'board' : 'dot')).toEqual(['board', 'board', 'dot'])
    expect(container.querySelector('.stack-sign')).toBeNull()
  })

  it('hovering a board hovers just its tour; clicking a board picks it', () => {
    twoCandidates()
    const tours = stackTours(3)
    const onHoverTours = vi.fn()
    const onPickRoute = vi.fn()
    const { container } = render1(tours, { onHoverTours, onPickRoute })
    const second = container.querySelectorAll('.signpost-marker.board .sign')[1]
    fireEvent.mouseOver(second)
    expect([...onHoverTours.mock.calls.at(-1)![0]]).toEqual([tourKey(tours[1])])
    fireEvent.click(second)
    expect(onPickRoute).toHaveBeenCalledWith(tours[1])
  })

  it('a click on a dot picks its tour and hovering it hovers just that tour', () => {
    twoCandidates()
    const tours = stackTours(3)
    const onHoverTours = vi.fn()
    const onPickRoute = vi.fn()
    const { container } = render1(tours, { onHoverTours, onPickRoute })
    const dot = container.querySelector('.signpost-marker.dot .dot')!
    fireEvent.mouseOver(dot)
    expect([...onHoverTours.mock.calls.at(-1)![0]]).toEqual([tourKey(tours[2])])
    fireEvent.click(dot)
    expect(onPickRoute).toHaveBeenCalledWith(tours[2])
  })

  it('shows a dot\'s board as a preview while its tour is hovered from the results list', () => {
    twoCandidates()
    const tours = stackTours(3)
    const { container } = render1(tours, { hoveredTourKeys: new Set([tourKey(tours[2])]) })
    const dot = container.querySelector('.signpost-marker.dot')!
    expect(dot.classList.contains('previewing')).toBe(true)
    expect(dot.querySelector('.preview .sign')!.textContent).toContain('Kaunertal')
  })

  it('draws no signpost for a tour without any anchor candidate in view', () => {
    vi.spyOn(routes, 'tourAnchorCandidatesOf').mockReturnValue([])
    const { container } = render1(stackTours(2))
    expect(container.querySelector('.signpost-marker')).toBeNull()
  })

  it('renders a cluster as a round count bubble, not a signpost, and highlights it like the old bubbles', () => {
    const close = new Map([
      [1, { name: null, sourceType: 1, lat: 47.3, lng: 12 }],
      [2, { name: null, sourceType: 1, lat: 47.31, lng: 12.01 }],
    ])
    const hovered = tour(1, [10])
    const groups = [{ startId: 1, tours: [hovered, tour(1, [11])] }, { startId: 2, tours: [tour(2, [10]), tour(2, [11]), tour(2, [12])] }] as never
    const { container } = renderLayer({ groups, startById: close, routeCtx: { ...routeCtx, startById: close }, allTours: [hovered], hoveredTourKeys: new Set([tourKey(hovered)]) }, 9)
    expect(container.querySelector('.signpost-marker')).toBeNull()
    const bubble = container.querySelector('.start-count-marker') as HTMLElement
    expect(bubble.textContent).toBe('5')
    expect(bubble.classList.contains('highlighted')).toBe(true)
  })

  it('shows a start point as a bubble below the reveal zoom and as a signpost from it', () => {
    const tours = stackTours(2)
    const { container: far } = render1(tours, {}, 9)
    expect(far.querySelector('.signpost-marker')).toBeNull()
    expect(far.querySelector('.start-count-marker')!.textContent).toBe('2')
    const { container: near } = render1(tours, {}, 13)
    expect(near.querySelector('.signpost-marker')).not.toBeNull()
    expect(near.querySelector('.start-count-marker')).toBeNull()
  })

  it('stands a bubble on its tour\'s anchor, not on its start point', () => {
    const t = tour(1, [10, 11])
    const ctx = { ...routeCtx, legAnchors: () => [{ lat: 47.35, lng: 12.05 }] }
    const { container } = renderLayer({ groups: [{ startId: 1, tours: [t] }] as never, allTours: [t], routeCtx: ctx }, 9)
    const el = container.querySelector<HTMLElement>('.start-count-marker')!
    const expected = map.latLngToLayerPoint(L.latLng(47.35, 12.05))
    expect(L.DomUtil.getPosition(el).x).toBeCloseTo(expected.x, 0)
    expect(L.DomUtil.getPosition(el).y).toBeCloseTo(expected.y, 0)
  })

  it('a bubble click flies to its tours\' anchors at the reveal zoom, without focusing or picking', () => {
    const fly = vi.spyOn(L.Map.prototype, 'flyTo').mockReturnThis()
    const t = tour(1, [10, 11])
    const onPickRoute = vi.fn()
    const onFocusTours = vi.fn()
    const ctx = { ...routeCtx, legAnchors: () => [{ lat: 47.35, lng: 12.05 }] }
    const { container } = renderLayer({ groups: [{ startId: 1, tours: [t] }] as never, allTours: [t], routeCtx: ctx, onPickRoute, onFocusTours }, 9)
    fireEvent.click(container.querySelector('.start-count-marker')!)
    expect(fly).toHaveBeenCalledTimes(1)
    const [center, zoom] = fly.mock.calls[0]
    expect(L.latLng(center as L.LatLngExpression).equals(L.latLng(47.35, 12.05))).toBe(true)
    expect(zoom).toBeGreaterThanOrEqual(11)
    expect(onFocusTours).not.toHaveBeenCalled()
    expect(onPickRoute).not.toHaveBeenCalled()
  })

  it('a bubble hovered from the list dims the other bubbles, one hovered on the map does not', async () => {
    const far = new Map([
      [1, { name: null, sourceType: 1, lat: 47.3, lng: 12 }],
      [2, { name: null, sourceType: 1, lat: 47.3, lng: 12.3 }],
    ])
    const a = tour(1, [10])
    const b = tour(2, [11])
    const props = { groups: [{ startId: 1, tours: [a] }, { startId: 2, tours: [b] }] as never, startById: far, routeCtx: { ...routeCtx, startById: far }, allTours: [a, b] }
    const bubbles = (c: HTMLElement) => [...c.querySelectorAll('.start-count-marker')]
    const dimmedCount = (c: HTMLElement) => bubbles(c).filter((el) => el.classList.contains('dimmed')).length

    const { container: listHover } = renderLayer({ ...props, hoveredTourKeys: new Set([tourKey(a)]) }, 9)
    expect(bubbles(listHover)).toHaveLength(2)
    expect(dimmedCount(listHover)).toBe(1)
    cleanup()

    const { container: mapHover } = render(
      <MapContainer center={[47.3, 12]} zoom={9} style={{ height: 400, width: 400 }}>
        <FocusedLayer {...layerProps} {...props} dimmed={false} />
      </MapContainer>,
    )
    fireEvent.mouseOver(bubbles(mapHover)[0])
    await waitFor(() => expect(bubbles(mapHover).some((el) => el.classList.contains('highlighted'))).toBe(true))
    expect(dimmedCount(mapHover)).toBe(0)
  })

  it('highlights the marker of a start whose tour is hovered from the list', () => {
    const tours = stackTours(2)
    const { container } = render1(tours, { hoveredTourKeys: new Set([tourKey(tours[0])]) })
    expect(container.querySelector('.signpost-marker')!.classList.contains('highlighted')).toBe(true)
  })
})

describe('DiscoverLayer signposts on the route', () => {
  beforeEach(() => {
    vi.spyOn(L.Map.prototype, 'getSize').mockImplementation(() => L.point(400, 400))
  })
  afterEach(() => { vi.restoreAllMocks() })

  const signposts = (c: HTMLElement) => c.querySelectorAll('.signpost-marker')
  const anchor = { lat: 47.305, lng: 12.005, heading: 'east' as const }

  it('draws no signposts below the reveal zoom, only count bubbles', () => {
    const t = tour(1, [10, 11])
    const { container } = renderLayer({ ...focusOn(t), groups: [{ startId: 1, tours: [t] }] as never }, 9)
    expect(signposts(container)).toHaveLength(0)
    expect(container.querySelectorAll('.start-count-marker')).toHaveLength(1)
  })

  it('stands a tour\'s board on its anchor, not on its start point', async () => {
    vi.spyOn(routes, 'tourAnchorCandidatesOf').mockReturnValue([anchor])
    const t = tour(1, [10, 11])
    const { container } = renderLayer({ ...focusOn(t), groups: [{ startId: 1, tours: [t] }] as never }, 13)
    await waitFor(() => expect(signposts(container)).toHaveLength(1))
    const el = container.querySelector<HTMLElement>('.signpost-marker')!
    const expected = map.latLngToLayerPoint(L.latLng(anchor.lat, anchor.lng))
    expect(L.DomUtil.getPosition(el).x).toBeCloseTo(expected.x, 0)
    expect(L.DomUtil.getPosition(el).y).toBeCloseTo(expected.y, 0)
    expect(container.querySelector('.start-count-marker')).toBeNull()
  })

  it('draws no signpost for a tour with no anchor in view', () => {
    vi.spyOn(routes, 'tourAnchorCandidatesOf').mockReturnValue([])
    const t = tour(1, [10, 11])
    const { container } = renderLayer({ ...focusOn(t), groups: [{ startId: 1, tours: [t] }] as never }, 13)
    expect(signposts(container)).toHaveLength(0)
  })

  it('gives tours whose anchors coincide one board and one dot instead of a stack', async () => {
    vi.spyOn(routes, 'tourAnchorCandidatesOf').mockReturnValue([anchor])
    const a = tour(1, [10, 11])
    const b = tour(1, [10, 11, 12])
    const { container } = renderLayer({ ...focusOn(a, b), groups: [{ startId: 1, tours: [a, b] }] as never }, 13)
    await waitFor(() => expect(signposts(container)).toHaveLength(2))
    expect(container.querySelectorAll('.signpost-marker.board')).toHaveLength(1)
    expect(container.querySelectorAll('.signpost-marker.dot')).toHaveLength(1)
  })

  it('fades a board while its tour is hovered from elsewhere, not while the board itself is hovered', async () => {
    vi.spyOn(routes, 'tourAnchorCandidatesOf').mockReturnValue([anchor])
    const t = tour(1, [10, 11])
    const { container } = renderLayer({ ...focusOn(t), groups: [{ startId: 1, tours: [t] }] as never, hoveredTourKeys: new Set([tourKey(t)]) }, 13)
    await waitFor(() => expect(container.querySelector('.sign.faded')).not.toBeNull())
    fireEvent.mouseOver(container.querySelector('.sign')!)
    await waitFor(() => expect(container.querySelector('.sign.faded')).toBeNull())
  })
})
