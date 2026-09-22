// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup, waitFor, fireEvent } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import PlannerMap from './PlannerMap.js'
import type { PlannerTour } from './tours.js'

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
  onSelectStarts: () => {}, route: null, fitRoute: false, highlightedLeg: null,
  tripHuts: [], tripEnds: [], candidates: [], candidateStartCoords: new Map(), onPickCandidate: () => {},
  activeLabel: null, onCancelEditing: undefined,
  allTours: [], sortKey: 'fit' as const,
  rankCtx: { targets: { legCountTarget: 2, legCountRange: [2, 4] as [number, number], legTimeRangeH: [1, 8] as [number, number] }, ohrsIdByHutIndex: new Map(), freeByOffset: null },
  routeCtx: null, hoveredTourKey: null, onHoverTour: () => {}, onPickRoute: () => {},
}

describe('PlannerMap discover mode', () => {
  it('shows one count marker per start point and reports the clicked start', async () => {
    const onSelectStarts = vi.fn()
    const groups = [{ startId: 1, tours: [tour(1), tour(1), tour(1)] }, { startId: 2, tours: [tour(2)] }]
    const { container } = render(<PlannerMap {...base} groups={groups} onSelectStarts={onSelectStarts} />)
    await waitFor(() => expect(container.querySelectorAll('.start-count-marker').length).toBeGreaterThan(0))
    const labels = [...container.querySelectorAll('.start-count-marker span')].map((n) => n.textContent)
    expect(labels).toContain('3')
    fireEvent.click(container.querySelector('.start-count-marker')!)
    expect(onSelectStarts).toHaveBeenCalled()
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

describe('PlannerMap candidate-mode status bar', () => {
  it('shows a status bar with Abbrechen while a candidate mode is active', () => {
    const onCancel = vi.fn()
    render(<PlannerMap {...base} mode="trip" activeLabel="Neue Hütte für Nacht 2 wählen" onCancelEditing={onCancel} />)
    expect(screen.getByText('Neue Hütte für Nacht 2 wählen')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Abbrechen'))
    expect(onCancel).toHaveBeenCalled()
  })
  it('shows no status bar when activeLabel is null', () => {
    render(<PlannerMap {...base} mode="trip" activeLabel={null} />)
    expect(screen.queryByText('Abbrechen')).not.toBeInTheDocument()
  })
})
