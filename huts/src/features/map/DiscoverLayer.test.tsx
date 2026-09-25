// @vitest-environment jsdom
import { useState } from 'react'
import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import L from 'leaflet'
import { render, cleanup, fireEvent, act } from '@testing-library/react'
import { MapContainer, useMap } from 'react-leaflet'
import DiscoverLayer from './DiscoverLayer.js'
import type { PlannerTour } from '@/tourSearch/plannerTour.js'

afterEach(cleanup)

function tour(startId: number, huts: number[]): PlannerTour {
  return {
    startId, exitStartId: startId, huts,
    legs: huts.map(() => ({ durationH: 4, ascentM: 0, descentM: 0, distanceM: 0, edgeId: 1, reversed: false })),
    totalDurationH: huts.length * 4, totalAscentM: 0, totalDescentM: 0, totalDistanceM: 0,
  } as PlannerTour
}

const startById = new Map([[1, { name: null, sourceType: 1, lat: 47.3, lng: 12 }]])
const routeCtx = {
  hutCoordsById: new Map([[10, { lat: 47.3, lng: 12 }], [11, { lat: 47.31, lng: 12.01 }]]),
  startById, officialById: new Map(),
}

let map: L.Map
function CaptureMap() { map = useMap(); return null }

function renderLayer(props: Partial<Parameters<typeof DiscoverLayer>[0]> = {}, zoom = 13) {
  return render(
    <MapContainer center={[47.3, 12]} zoom={zoom} style={{ height: 400, width: 400 }}>
      <CaptureMap />
      <DiscoverLayer
        groups={[]} startById={startById}
        dimmed={false} allTours={[tour(1, [10, 11])]}
        routeCtx={routeCtx}
        hoveredTourKey={null} onHoverTour={() => {}} onPickRoute={() => {}}
        {...props}
      />
    </MapContainer>,
  )
}

/** Owns the focus the way the planner does, so the layer's own focus changes feed back into its props. */
function FocusedLayer(props: Parameters<typeof DiscoverLayer>[0]) {
  const [focus, setFocus] = useState<Set<number> | null>(null)
  return <DiscoverLayer {...props} focusStarts={focus} onFocusStarts={(ids) => setFocus(ids && new Set(ids))} />
}

describe('DiscoverLayer route lines', () => {
  it('draws no route lines below the reveal zoom', () => {
    const { container } = renderLayer({}, 9)
    expect(container.querySelectorAll('path.leaflet-interactive')).toHaveLength(0)
  })

  it('draws a route line for a tour whose start is in view, past the reveal zoom', () => {
    const { container } = renderLayer({}, 13)
    expect(container.querySelectorAll('path.leaflet-interactive').length).toBeGreaterThan(0)
  })

  it('draws no route lines for tours whose start is far outside the viewport', () => {
    const { container } = renderLayer({ allTours: [tour(2, [10, 11])], startById: new Map([...startById, [2, { name: null, sourceType: 1, lat: 10, lng: 10 }]]) }, 13)
    expect(container.querySelectorAll('path.leaflet-interactive')).toHaveLength(0)
  })

  it('draws every in-view tour, with no cap', () => {
    const many = Array.from({ length: 80 }, (_, i) => tour(1, [i]))
    const routeCtxMany = {
      hutCoordsById: new Map(many.map((t, i) => [i, { lat: 47.3, lng: 12 + i * 0.0001 }])),
      startById, officialById: new Map(),
    }
    const { container: all } = renderLayer({ allTours: many, routeCtx: routeCtxMany }, 13)
    const { container: few } = renderLayer({ allTours: many.slice(0, 10), routeCtx: routeCtxMany }, 13)
    const pathsPerTour = few.querySelectorAll('path.leaflet-interactive').length / 10
    expect(all.querySelectorAll('path.leaflet-interactive').length).toBe(80 * pathsPerTour)
  })
})

describe('DiscoverLayer bubble focus', () => {
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
        <FocusedLayer
          groups={groups} startById={two} dimmed={false} allTours={tours} routeCtx={routeCtx2}
          hoveredTourKey={null} onHoverTour={() => {}} onPickRoute={() => {}}
        />
      </MapContainer>,
    )
  }

  it('highlights the clicked bubble\'s tours above the faded rest and dims other bubbles', () => {
    const { container } = renderFocused()
    const highlighted = () => container.querySelectorAll('.leaflet-route-dot-pane path').length
    const faded = () => container.querySelectorAll('.leaflet-route-dim-dot-pane path').length
    expect(highlighted()).toBe(0)
    fireEvent.click(container.querySelector('.start-count-marker') as HTMLElement)
    expect(highlighted()).toBeGreaterThan(0)
    expect(highlighted()).toBe(faded() / 2)
    const bubbles = container.querySelectorAll('.start-count-marker')
    expect(bubbles[0].classList.contains('dimmed')).toBe(false)
    expect(bubbles[1].classList.contains('dimmed')).toBe(true)
  })

  it('keeps the focus through a drag and through zooming that stays at or above the click zoom, drops it below', () => {
    vi.spyOn(L.Map.prototype, 'getBoundsZoom').mockReturnValue(13)
    const { container } = renderFocused()
    const focused = () => container.querySelectorAll('.leaflet-route-dot-pane path').length > 0
    fireEvent.click(container.querySelector('.start-count-marker') as HTMLElement)
    expect(focused()).toBe(true)
    act(() => { map.fire('dragstart') })
    expect(focused()).toBe(true)
    act(() => { map.setZoom(14, { animate: false }) })
    expect(focused()).toBe(true)
    act(() => { map.setZoom(13, { animate: false }) })
    expect(focused()).toBe(true)
    act(() => { map.setZoom(12, { animate: false }) })
    expect(focused()).toBe(false)
  })
})
