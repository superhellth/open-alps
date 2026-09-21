// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, cleanup, waitFor, fireEvent } from '@testing-library/react'
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
