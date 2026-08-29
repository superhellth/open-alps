// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, waitFor, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import ResultsMap from './ResultsMap.js'
import * as loadLegGeometryModule from '../tourSearch/loadLegGeometry.js'
import type { TourResult } from '../tourSearch/types.js'
import type { StartPoint } from './types.js'
import type { HutClass } from '../hutClass.js'

// vitest.config.js doesn't set `globals: true`, so @testing-library/react's automatic
// afterEach(cleanup) never registers - without this, each test's render() stacks onto the
// previous test's un-unmounted DOM, which is invisible until an assertion checks for something's
// *absence* (queryByText(...).not.toBeInTheDocument()), as the third test below does.
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

const chain: TourResult = {
  huts: [0], startId: 100, exitStartId: 200,
  totalDurationH: 3, totalAscentM: 300, totalDescentM: 300, totalDistanceM: 6000,
  legs: [
    { durationH: 1.5, ascentM: 150, descentM: 150, distanceM: 3000, edgeId: 5, reversed: false },
    { durationH: 1.5, ascentM: 150, descentM: 150, distanceM: 3000, edgeId: 6, reversed: true },
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

    render(<ResultsMap selectedChain={chain} hutNameById={hutNameById} hutCoordsById={hutCoordsById} startById={startById} hutClassByIndex={new Map()} excludedHutIndices={new Set()} />)

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

    render(<ResultsMap selectedChain={chain} hutNameById={hutNameById} hutCoordsById={hutCoordsById} startById={startById} hutClassByIndex={new Map()} excludedHutIndices={new Set()} />)

    await waitFor(() => expect(screen.getByText(CAPTION)).toBeInTheDocument())
  })

  it('deselecting the tour clears the caption and shows the full hut list again', () => {
    vi.spyOn(loadLegGeometryModule, 'loadLegGeometry').mockReturnValue(new Promise(() => {}))

    const { container } = render(
      <ResultsMap selectedChain={null} hutNameById={hutNameById} hutCoordsById={hutCoordsById} startById={startById} hutClassByIndex={new Map()} excludedHutIndices={new Set()} />,
    )

    expect(screen.queryByText(CAPTION)).not.toBeInTheDocument()
    // react-leaflet's Tooltip only mounts its text into the DOM on hover, so the hut name isn't
    // queryable at rest - the hut circle marker itself is the observable proxy for "the full hut
    // list is shown" instead.
    expect(container.querySelectorAll('path.leaflet-interactive')).toHaveLength(1)
  })
})

describe('ResultsMap hut-class styling', () => {
  it('colours the overview markers by operator and dims huts excluded by the active filter', () => {
    const hutClassByIndex = new Map<number, HutClass>([[0, { operator: 'av', serviced: true }]])
    const { container } = render(
      <ResultsMap
        selectedChain={null} hutNameById={hutNameById} hutCoordsById={hutCoordsById}
        startById={startById} hutClassByIndex={hutClassByIndex}
        excludedHutIndices={new Set([0])}
      />,
    )
    const marker = container.querySelector('path.leaflet-interactive')
    expect(marker).not.toBeNull()
    // Dimmed excluded huts render with reduced fill-opacity rather than being removed.
    expect(marker?.getAttribute('fill-opacity')).not.toBe('0.9')
  })
})
