// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import HeightProfile from './HeightProfile.js'
import type { TripElevation } from './useTripElevation.js'

afterEach(cleanup)

const elevation: TripElevation = {
  points: [
    { distanceKm: 0, elevationM: 1000, legIndex: 0 }, { distanceKm: 0.5, elevationM: 1200, legIndex: 0 },
    { distanceKm: 1, elevationM: 1400, legIndex: 1 }, { distanceKm: 1.5, elevationM: 1300, legIndex: 1 },
  ],
  nightBoundariesKm: [0, 1, 1.5],
  loading: false,
}

describe('HeightProfile', () => {
  it('draws a vertical separator at each night boundary except the very start', () => {
    render(<HeightProfile elevation={elevation} highlightedLeg={null} onHoverLeg={() => {}} onHoverPosition={() => {}} />)
    // one separator per interior boundary (nightBoundariesKm.length - 2, excluding start and exit ends)
    expect(screen.getAllByTestId('night-separator')).toHaveLength(1)
  })

  it('shows a loading state instead of a chart while elevation.loading is true', () => {
    render(<HeightProfile elevation={{ ...elevation, loading: true }} highlightedLeg={null} onHoverLeg={() => {}} onHoverPosition={() => {}} />)
    expect(screen.getByText('Höhenprofil lädt …')).toBeInTheDocument()
  })

  it('shows nothing (not even the loading text) when there are no points and not loading', () => {
    render(<HeightProfile elevation={{ points: [], nightBoundariesKm: [], loading: false }} highlightedLeg={null} onHoverLeg={() => {}} onHoverPosition={() => {}} />)
    expect(screen.queryByTestId('profile-svg')).not.toBeInTheDocument()
  })

  it('hovering the strip reports the nearest leg index and distance', () => {
    const onHoverLeg = vi.fn()
    const onHoverPosition = vi.fn()
    render(<HeightProfile elevation={elevation} highlightedLeg={null} onHoverLeg={onHoverLeg} onHoverPosition={onHoverPosition} />)
    const svg = screen.getByTestId('profile-svg')
    fireEvent.mouseMove(svg, { clientX: 10 })
    expect(onHoverLeg).toHaveBeenCalled()
    expect(onHoverPosition).toHaveBeenCalledWith(expect.objectContaining({ distanceKm: expect.any(Number) }))
    fireEvent.mouseLeave(svg)
    expect(onHoverLeg).toHaveBeenLastCalledWith(null)
    expect(onHoverPosition).toHaveBeenLastCalledWith(null)
  })

  it('highlights the segment matching highlightedLeg', () => {
    render(<HeightProfile elevation={elevation} highlightedLeg={1} onHoverLeg={() => {}} onHoverPosition={() => {}} />)
    expect(screen.getByTestId('leg-segment-1')).toHaveAttribute('data-highlighted', 'true')
    expect(screen.getByTestId('leg-segment-0')).toHaveAttribute('data-highlighted', 'false')
  })
})
