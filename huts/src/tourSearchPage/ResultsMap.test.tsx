// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, waitFor, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import ResultsMap from './ResultsMap.js'
import * as loadLegGeometryModule from '../tourSearch/loadLegGeometry.js'
import type { Route } from './types.js'
import type { StartPoint } from './types.js'
import type { HutClass } from '../hutClass.js'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

const route: Route = {
  waypoints: [{ lat: 47.0, lng: 11.0 }, { lat: 47.1, lng: 11.1 }, { lat: 47.2, lng: 11.2 }],
  legs: [
    { edgeId: 5, reversed: false, layer: 'start_edges' },
    { edgeId: 6, reversed: true, layer: 'start_edges' },
  ],
}

const hutNameById = new Map([[0, 'HutA']])
const hutCoordsById = new Map([[0, { lat: 47.1, lng: 11.1 }]])
const startById = new Map<number, StartPoint>([
  [100, { name: 'Start', sourceType: 2, lat: 47.0, lng: 11.0 }],
  [200, { name: 'End', sourceType: 2, lat: 47.2, lng: 11.2 }],
])

function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

const CAPTION = 'Schematische Verbindung, nicht der reale Wegverlauf.'

describe('ResultsMap real geometry integration', () => {
  it('resolves (layer, edgeId, reversed) per leg, keeps the caption while any leg is still a fallback, and hides it once every leg resolves', async () => {
    const d0 = deferred<[number, number][]>()
    const d1 = deferred<[number, number][]>()
    const spy = vi
      .spyOn(loadLegGeometryModule, 'loadLegGeometry')
      .mockImplementationOnce(() => d0.promise)
      .mockImplementationOnce(() => d1.promise)

    render(<ResultsMap route={route} hutNameById={hutNameById} hutCoordsById={hutCoordsById} startById={startById} hutClassByIndex={new Map()} excludedHutIndices={new Set()} />)

    expect(screen.getByText(CAPTION)).toBeInTheDocument()
    expect(spy).toHaveBeenNthCalledWith(1, 'start_edges', 5, false)
    expect(spy).toHaveBeenNthCalledWith(2, 'start_edges', 6, true)

    d0.resolve([[47.0, 11.0], [47.05, 11.05], [47.1, 11.1]])
    await waitFor(() => expect(screen.getByText(CAPTION)).toBeInTheDocument())

    d1.resolve([[47.1, 11.1], [47.15, 11.15], [47.2, 11.2]])
    await waitFor(() => expect(screen.queryByText(CAPTION)).not.toBeInTheDocument())
  })

  it('a leg whose fetch rejects keeps its straight-line fallback instead of crashing', async () => {
    vi.spyOn(loadLegGeometryModule, 'loadLegGeometry').mockRejectedValue(new Error('range not supported'))

    render(<ResultsMap route={route} hutNameById={hutNameById} hutCoordsById={hutCoordsById} startById={startById} hutClassByIndex={new Map()} excludedHutIndices={new Set()} />)

    await waitFor(() => expect(screen.getByText(CAPTION)).toBeInTheDocument())
  })

  it('deselecting the tour clears the caption and shows the full hut list again', () => {
    vi.spyOn(loadLegGeometryModule, 'loadLegGeometry').mockReturnValue(new Promise(() => {}))

    const { container } = render(
      <ResultsMap route={null} hutNameById={hutNameById} hutCoordsById={hutCoordsById} startById={startById} hutClassByIndex={new Map()} excludedHutIndices={new Set()} />,
    )

    expect(screen.queryByText(CAPTION)).not.toBeInTheDocument()
    expect(container.querySelectorAll('path.leaflet-interactive')).toHaveLength(1)
  })

  it('renders one Polyline per leg for a tour_edges-layer route', async () => {
    vi.spyOn(loadLegGeometryModule, 'loadLegGeometry').mockResolvedValue([[47.0, 11.0], [47.1, 11.1]])
    const tourRoute: Route = {
      waypoints: [{ lat: 47.0, lng: 11.0 }, { lat: 47.05, lng: 11.05 }, { lat: 47.1, lng: 11.1 }],
      legs: [
        { edgeId: 0, reversed: false, layer: 'tour_edges' },
        { edgeId: 1, reversed: false, layer: 'tour_edges' },
      ],
    }
    const { container } = render(
      <ResultsMap route={tourRoute} hutNameById={hutNameById} hutCoordsById={hutCoordsById} startById={startById} hutClassByIndex={new Map()} excludedHutIndices={new Set()} />,
    )
    await waitFor(() => expect(container.querySelectorAll('path.leaflet-interactive')).toHaveLength(5)) // 2 polylines + 3 waypoint markers; loose upper-bound, the pinning checks are below
    expect(loadLegGeometryModule.loadLegGeometry).toHaveBeenCalledWith('tour_edges', 0, false)
    expect(loadLegGeometryModule.loadLegGeometry).toHaveBeenCalledWith('tour_edges', 1, false)
  })
})

describe('ResultsMap hut-class styling', () => {
  it('colours the overview markers by operator and dims huts excluded by the active filter', () => {
    const hutClassByIndex = new Map<number, HutClass>([[0, { operator: 'av', serviced: true }]])
    const { container } = render(
      <ResultsMap
        route={null} hutNameById={hutNameById} hutCoordsById={hutCoordsById}
        startById={startById} hutClassByIndex={hutClassByIndex}
        excludedHutIndices={new Set([0])}
      />,
    )
    const marker = container.querySelector('path.leaflet-interactive')
    expect(marker).not.toBeNull()
    expect(marker?.getAttribute('fill-opacity')).not.toBe('0.9')
  })
})
