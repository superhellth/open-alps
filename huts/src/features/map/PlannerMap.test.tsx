// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup, waitFor, fireEvent } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import PlannerMap from './PlannerMap.js'
import type { PlannerTour } from '@/tourSearch/plannerTour.js'
import { newTrip } from '@/trip/trip.js'
import type { TripGraph } from '@/tourSearch/types.js'

afterEach(cleanup)

const tour = (startId: number): PlannerTour => ({
  huts: [0], startId, exitStartId: startId, totalDurationH: 1, totalAscentM: 0, totalDescentM: 0, totalDistanceM: 0, legs: [],
})
const startById = new Map([
  [1, { name: 'A', sourceType: 1, lat: 47.3, lng: 12.0 }],
  [2, { name: 'B', sourceType: 1, lat: 47.9, lng: 14.0 }],
])
const base = {
  mode: 'discover' as const, dimmed: false, startById, hutCoordsById: new Map(),
  route: null, fitRoute: false, highlightedLeg: null,
  tripHuts: [], tripEnds: [], candidates: [], candidateStartCoords: new Map(), onPickCandidate: () => {},
  activeLabel: null, onCancelEditing: undefined,
  allTours: [], sortKey: 'fit' as const,
  rankCtx: { targets: { legCountTarget: 2, legCountRange: [2, 4] as [number, number], legTimeRangeH: [1, 8] as [number, number] }, ohrsIdByHutIndex: new Map(), freeByOffset: null },
  routeCtx: null, hoveredTourKey: null, onHoverTour: () => {}, onPickRoute: () => {},
  tripLegs: null, onHoverLeg: () => {},
}

describe('PlannerMap discover mode', () => {
  it('shows one count marker per start point and reports a click as navigation', async () => {
    const onNavigate = vi.fn()
    const groups = [{ startId: 1, tours: [tour(1), tour(1), tour(1)] }, { startId: 2, tours: [tour(2)] }]
    const { container } = render(<PlannerMap {...base} groups={groups} onNavigate={onNavigate} />)
    await waitFor(() => expect(container.querySelectorAll('.start-count-marker').length).toBeGreaterThan(0))
    const labels = [...container.querySelectorAll('.start-count-marker span')].map((n) => n.textContent)
    expect(labels).toContain('3')
    fireEvent.click(container.querySelector('.start-count-marker')!)
    expect(onNavigate).toHaveBeenCalled()
  })
  it('reports the current bbox/zoom as the map settles', async () => {
    const onViewChange = vi.fn()
    render(<PlannerMap {...base} groups={[]} onViewChange={onViewChange} />)
    await waitFor(() => expect(onViewChange).toHaveBeenCalled())
    const view = onViewChange.mock.calls[0][0]
    expect(view.bbox).toHaveLength(4)
    expect(typeof view.zoom).toBe('number')
  })
  it('renders no markers without matches', () => {
    const { container } = render(<PlannerMap {...base} groups={[]} />)
    expect(container.querySelectorAll('.start-count-marker')).toHaveLength(0)
  })
  it('mutes the tiles in discover mode only', () => {
    const { container, rerender } = render(<PlannerMap {...base} groups={[]} />)
    expect(container.querySelector('.map-muted')).not.toBeNull()
    rerender(<PlannerMap {...base} mode="trip" groups={[]} />)
    expect(container.querySelector('.map-muted')).toBeNull()
  })
})

describe('PlannerMap trip mode', () => {
  const tripBase = {
    ...base, mode: 'trip' as const, groups: [], hutCoordsById: new Map([[0, { lat: 47.3, lng: 12.0 }]]),
    tripHuts: [{ hutIndex: 0, name: 'Hütte A', operator: 'av' as const, serviced: true }],
    tripEnds: [{ lat: 47.29, lng: 12.0, sourceType: 1 }],
    candidates: [{ hutIndex: 5, name: 'Hütte X', legInH: 2.5, legOutH: 3 }],
    hutCoordsByIdWithCandidate: new Map([[0, { lat: 47.3, lng: 12.0 }], [5, { lat: 47.35, lng: 12.05 }]]),
    onPickCandidate: () => {},
  }
  it('draws trip huts as yellow-filled symbols and start/exit symbols', async () => {
    const { container } = render(<PlannerMap {...tripBase} />)
    await waitFor(() => expect(container.querySelectorAll('.hut-marker').length).toBe(1))
    expect(container.querySelector('.hut-marker svg')?.innerHTML).toContain('#F5B700')
    expect(container.querySelectorAll('.start-symbol')).toHaveLength(1)
  })
  it('shows swap candidates as signposts with both leg times and reports a pick', async () => {
    const onPickCandidate = vi.fn()
    const { container } = render(
      <PlannerMap {...tripBase} hutCoordsById={tripBase.hutCoordsByIdWithCandidate} onPickCandidate={onPickCandidate} />,
    )
    await waitFor(() => expect(container.querySelector('.swap-marker')).not.toBeNull())
    expect(container.querySelector('.swap-marker')?.textContent).toContain('Hütte X')
    expect(container.querySelector('.swap-marker')?.textContent).toContain('2½ Std')
    expect(container.querySelector('.swap-marker')?.textContent).toContain('3 Std')
    fireEvent.click(container.querySelector('.swap-marker')!)
    expect(onPickCandidate).toHaveBeenCalledWith({ hutIndex: 5 })
  })
  it('shows no discover markers in trip mode', () => {
    const { container } = render(<PlannerMap {...tripBase} groups={[{ startId: 1, tours: [] }]} />)
    expect(container.querySelectorAll('.start-count-marker')).toHaveLength(0)
  })
})

describe('PlannerMap saved mode', () => {
  it('renders SavedTripsLayer in saved mode', () => {
    const savedGraph: TripGraph = { hutEdges: { hutIds: ['{A}'], variantNames: {}, records: [] }, approaches: { records: [], reverseIndex: { hut_to_starts: {}, start_to_huts: {} } } }
    const savedRouteCtx = { hutCoordsById: new Map([[0, { lat: 47.3, lng: 12 }]]), startById: new Map([[100, { name: 'Start', sourceType: 1 as const, lat: 47.2, lng: 12.1 }]]), officialById: new Map() }
    const savedTrip = newTrip({ name: 'T', startDate: null, partySize: 1, start: { startId: 100, sourceType: 1 }, huts: ['{A}'], exit: { startId: 100, sourceType: 1 }, variant: { sacCeiling: null, allowUngraded: false } })
    const { container: baselineContainer } = render(<PlannerMap {...base} groups={[]} mode="discover" />)
    const baseline = baselineContainer.querySelectorAll('path').length
    const { container } = render(
      <PlannerMap
        {...base} groups={[]} mode="saved"
        savedTrips={[savedTrip]} savedGraph={savedGraph} savedRouteCtx={savedRouteCtx}
        hoveredTripId={null} onHoverTrip={vi.fn()} onOpenSavedTrip={vi.fn()}
      />,
    )
    expect(container.querySelectorAll('path').length).toBeGreaterThan(baseline)
  })
})

describe('PlannerMap height profile', () => {
  const someTripLegs = {
    variantId: 0, hutIndices: [0],
    legs: [
      { startId: 1, sourceType: 1, distanceM: 1000, ascentM: 50, descentM: 0, durationH: 1, edgeId: -1, reversed: false },
      { startId: 2, sourceType: 1, distanceM: 500, ascentM: 0, descentM: 20, durationH: 0.5, edgeId: -1, reversed: false },
    ],
    changed: [false],
  } as never

  it('renders a collapsible height profile docked at the bottom when a trip is open', () => {
    render(<PlannerMap {...base} groups={[]} mode="trip" tripLegs={someTripLegs} />)
    expect(screen.getByRole('button', { name: /Höhenprofil/ })).toBeInTheDocument()
  })

  it('renders no profile toggle when no trip is open', () => {
    render(<PlannerMap {...base} groups={[]} mode="discover" tripLegs={null} />)
    expect(screen.queryByRole('button', { name: /Höhenprofil/ })).not.toBeInTheDocument()
  })
})

describe('PlannerMap candidate-mode status bar', () => {
  it('shows a status bar with Abbrechen while a candidate mode is active', () => {
    const onCancel = vi.fn()
    render(<PlannerMap {...base} mode="trip" groups={[]} activeLabel="Neue Hütte für Nacht 2 wählen" onCancelEditing={onCancel} />)
    expect(screen.getByText('Neue Hütte für Nacht 2 wählen')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Abbrechen'))
    expect(onCancel).toHaveBeenCalled()
  })
  it('shows no status bar when activeLabel is null', () => {
    render(<PlannerMap {...base} mode="trip" groups={[]} activeLabel={null} />)
    expect(screen.queryByText('Abbrechen')).not.toBeInTheDocument()
  })
})
