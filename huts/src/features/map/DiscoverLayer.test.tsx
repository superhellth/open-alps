// @vitest-environment jsdom
import { useState } from 'react'
import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import L from 'leaflet'
import { render, cleanup, fireEvent, act, waitFor } from '@testing-library/react'
import { MapContainer, useMap, useMapEvents } from 'react-leaflet'
import DiscoverLayer from './DiscoverLayer.js'
import { OPEN_DELAY_MS } from './SignpostMarker.js'
import type { PlannerTour } from '@/tourSearch/plannerTour.js'
import { NO_TOURS, tourKey } from '@/tourSearch/tourKey.js'
import * as geometry from '@/tourSearch/loadLegGeometry.js'

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
  startById, officialById: new Map(), hutClassByIndex,
}

let map: L.Map
function CaptureMap() { map = useMap(); return null }
function MapClick({ onClick }: { onClick: () => void }) { useMapEvents({ click: onClick }); return null }

const layerProps = {
  hutNameById: new Map<number, string>(), hoveredTourKeys: NO_TOURS, onHoverTours: () => {}, onPickRoute: () => {},
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
  return <DiscoverLayer {...props} focusTours={focus} onFocusTours={(keys) => setFocus(keys && new Set(keys))} />
}

describe('DiscoverLayer route lines', () => {
  it('draws no route lines below the reveal zoom', () => {
    const { container } = renderLayer({}, 9)
    expect(container.querySelectorAll('path.leaflet-interactive')).toHaveLength(0)
  })

  it('draws a route line for a tour whose start is in view, past the reveal zoom', async () => {
    const { container } = renderLayer({}, 13)
    await waitFor(() => expect(container.querySelectorAll('path.leaflet-interactive').length).toBeGreaterThan(0))
  })

  it('draws no route lines for tours whose start is far outside the viewport', () => {
    const { container } = renderLayer({ allTours: [tour(2, [10, 11])], startById: new Map([...startById, [2, { name: null, sourceType: 1, lat: 10, lng: 10 }]]) }, 13)
    expect(container.querySelectorAll('path.leaflet-interactive')).toHaveLength(0)
  })

  it('draws every in-view tour, with no cap', async () => {
    const many = Array.from({ length: 80 }, (_, i) => tour(1, [i]))
    const routeCtxMany = {
      hutCoordsById: new Map(many.map((t, i) => [i, { lat: 47.3, lng: 12 + i * 0.0001 }])),
      startById, officialById: new Map(), hutClassByIndex: new Map(),
    }
    const { container: all } = renderLayer({ allTours: many, routeCtx: routeCtxMany }, 13)
    const { container: few } = renderLayer({ allTours: many.slice(0, 10), routeCtx: routeCtxMany }, 13)
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
    const { container } = renderLayer({ allTours: [a, b], onHoverTours })
    fireEvent.mouseOver(await firstRestPath(container))
    expect([...onHoverTours.mock.calls.at(-1)![0]].sort()).toEqual([tourKey(a), tourKey(b)].sort())
    expect(document.querySelector('.leaflet-tooltip')!.textContent).toBe('In 2 Touren')
  })

  it('a leg click focuses the matched tours and is not read as the map click that drops the focus', async () => {
    const onFocusTours = vi.fn()
    const onMapClick = vi.fn()
    const { container } = renderLayer({ allTours: [a, b], onFocusTours }, 13, <MapClick onClick={onMapClick} />)
    fireEvent.click(await firstRestPath(container))
    expect(onFocusTours).toHaveBeenCalledWith(expect.arrayContaining([tourKey(a), tourKey(b)]))
    expect(onMapClick).not.toHaveBeenCalled()
  })

  it('a leg in a single tour picks it on click', async () => {
    const onPickRoute = vi.fn()
    const onFocusTours = vi.fn()
    const { container } = renderLayer({ allTours: [c], onPickRoute, onFocusTours })
    fireEvent.click(await firstRestPath(container))
    expect(onPickRoute).toHaveBeenCalledWith(c)
    expect(onFocusTours).not.toHaveBeenCalled()
  })

  it('hovering a hut hit target hovers every tour stopping there; the tooltip names the hut', async () => {
    const onHoverTours = vi.fn()
    const { container } = renderLayer({ allTours: [a, b], onHoverTours, hutNameById: new Map([[10, 'Hütte Eins']]) })
    const hits = container.querySelectorAll('.leaflet-route-hit-pane .leaflet-marker-icon')
    expect(hits.length).toBeGreaterThan(0)
    fireEvent.mouseOver(hits[0])
    expect(onHoverTours.mock.calls.at(-1)![0].size).toBe(2)
    expect(document.querySelector('.leaflet-tooltip')!.textContent).toBe('Hütte EinsIn 2 Touren')
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

describe('DiscoverLayer marker focus', () => {
  const two = new Map([...startById, [2, { name: null, sourceType: 1, lat: 47.3, lng: 12.015 }]])
  const tours = [tour(1, [10, 11]), tour(2, [10, 11])]
  const groups = [{ startId: 1, tours: [tours[0], tours[0]] }, { startId: 2, tours: [tours[1], tours[1]] }] as never
  const routeCtx2 = { ...routeCtx, startById: two }

  beforeEach(() => {
    vi.spyOn(L.Map.prototype, 'flyToBounds').mockReturnThis()
    vi.spyOn(L.Map.prototype, 'getSize').mockReturnValue(L.point(400, 400))
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
    fireEvent.click(container.querySelector('.signpost-marker .sign') as HTMLElement)
    await waitFor(() => expect(focused()).toBeGreaterThan(0))
    expect(container.querySelectorAll('.leaflet-route-rest-line-pane path').length).toBeGreaterThan(0)
    const markers = container.querySelectorAll('.signpost-marker')
    expect(markers[0].classList.contains('dimmed')).toBe(false)
    expect(markers[1].classList.contains('dimmed')).toBe(true)
  })

  it('keeps the focus through a drag and through zooming that stays at or above the click zoom, drops it below', async () => {
    vi.spyOn(L.Map.prototype, 'getBoundsZoom').mockReturnValue(13)
    const { container } = renderFocused()
    const focused = () => container.querySelectorAll('.leaflet-route-focused-line-pane path').length > 0
    fireEvent.click(container.querySelector('.signpost-marker .sign') as HTMLElement)
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
    vi.useFakeTimers()
    vi.spyOn(L.Map.prototype, 'getSize').mockReturnValue(L.point(400, 400))
  })
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })

  const withExit = new Map([
    [1, { name: 'Kaprun', sourceType: 1, lat: 47.3, lng: 12 }],
    [2, { name: 'Kaunertal', sourceType: 2, lat: 47.301, lng: 12 }],
  ])
  const exiting = (i: number) => tour(1, [i], { exitStartId: 2, totalDistanceM: 42_300 } as never)
  const stackTours = (n: number) => Array.from({ length: n }, (_, i) => exiting(i))
  const group = (tours: PlannerTour[]) => [{ startId: 1, tours }] as never
  const render1 = (tours: PlannerTour[], props: Partial<Parameters<typeof DiscoverLayer>[0]> = {}, zoom = 13) =>
    renderLayer({ groups: group(tours), allTours: tours, startById: withExit, routeCtx: { ...routeCtx, startById: withExit }, ...props }, zoom)
  const advance = (ms: number) => act(() => { vi.advanceTimersByTime(ms) })

  it('renders a single tour as one board labelled end point and distance; click picks the tour', () => {
    const t = exiting(0)
    const onPickRoute = vi.fn()
    const { container } = render1([t], { onPickRoute })
    const sign = container.querySelector('.signpost-marker.single .sign') as HTMLElement
    expect(sign.textContent).toContain('Kaunertal')
    expect(sign.textContent).toContain('42.3 km')
    fireEvent.click(sign)
    expect(onPickRoute).toHaveBeenCalledWith(t)
  })

  it('renders several tours from one start as a stack with the count', () => {
    const { container } = render1(stackTours(3))
    expect(container.querySelector('.signpost-marker.stack .stack-sign')!.textContent).toBe('3')
  })

  it('spreads a stack on hover into one board per tour and picks a board\'s tour on click', () => {
    const tours = stackTours(3)
    const onPickRoute = vi.fn()
    const { container } = render1(tours, { onPickRoute })
    fireEvent.mouseOver(container.querySelector('.signpost-marker .sign')!)
    advance(OPEN_DELAY_MS)
    expect(container.querySelector('.signpost-marker')!.classList.contains('spread')).toBe(true)
    const boards = container.querySelectorAll('.board[data-tour-key]')
    expect(boards).toHaveLength(3)
    fireEvent.click(boards[1])
    expect(onPickRoute).toHaveBeenCalledWith(tours[1])
  })

  it('hovering a spread board hovers just that tour', () => {
    const tours = stackTours(3)
    const onHoverTours = vi.fn()
    const { container } = render1(tours, { onHoverTours })
    fireEvent.mouseOver(container.querySelector('.signpost-marker .sign')!)
    advance(OPEN_DELAY_MS)
    fireEvent.mouseOver(container.querySelectorAll('.board[data-tour-key]')[2])
    expect([...onHoverTours.mock.calls.at(-1)![0]]).toEqual([tourKey(tours[2])])
  })

  it('caps a spread at 8 boards plus an overflow board whose click focuses that start\'s tours', () => {
    const tours = stackTours(11)
    const onPickRoute = vi.fn()
    const onFocusTours = vi.fn()
    const { container } = render1(tours, { onPickRoute, onFocusTours })
    expect(container.querySelectorAll('.board[data-tour-key]')).toHaveLength(8)
    const overflow = container.querySelector('.board.overflow')!
    expect(overflow.textContent).toBe('+3')
    fireEvent.click(overflow)
    expect(onFocusTours).toHaveBeenCalledWith(tours.map(tourKey))
    expect(onPickRoute).not.toHaveBeenCalled()
  })

  it('renders a cluster as a two-arm sign with the summed count and never spreads it', () => {
    const close = new Map([
      [1, { name: null, sourceType: 1, lat: 47.3, lng: 12 }],
      [2, { name: null, sourceType: 1, lat: 47.31, lng: 12.01 }],
    ])
    const groups = [{ startId: 1, tours: [tour(1, [10]), tour(1, [11])] }, { startId: 2, tours: [tour(2, [10]), tour(2, [11]), tour(2, [12])] }] as never
    const { container } = renderLayer({ groups, startById: close }, 9)
    const cluster = container.querySelector('.signpost-marker.cluster') as HTMLElement
    expect(cluster.textContent).toBe('5')
    expect(cluster.querySelectorAll('.arm')).toHaveLength(2)
    fireEvent.mouseOver(cluster.querySelector('.sign')!)
    advance(300)
    expect(cluster.classList.contains('spread')).toBe(false)
  })

  it('highlights the marker of a start whose tour is hovered from the list', () => {
    const tours = stackTours(2)
    const { container } = render1(tours, { hoveredTourKeys: new Set([tourKey(tours[0])]) })
    expect(container.querySelector('.signpost-marker')!.classList.contains('highlighted')).toBe(true)
  })
})
