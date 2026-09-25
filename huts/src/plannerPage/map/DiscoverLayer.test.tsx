// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { render, cleanup } from '@testing-library/react'
import { MapContainer } from 'react-leaflet'
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

function renderLayer(props: Partial<Parameters<typeof DiscoverLayer>[0]> = {}, zoom = 13) {
  return render(
    <MapContainer center={[47.3, 12]} zoom={zoom} style={{ height: 400, width: 400 }}>
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
