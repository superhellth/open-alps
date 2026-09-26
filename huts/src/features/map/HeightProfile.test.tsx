// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import HeightProfile from './HeightProfile.js'
import { PROFILE_MARGINS } from './profileScale.js'
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
const stops = ['Bahnhof X', 'Hütte A', 'Bahnhof X']
const noop = () => {}
const draw = (over: Partial<Parameters<typeof HeightProfile>[0]> = {}) =>
  render(<HeightProfile elevation={elevation} stops={stops} highlightedLeg={null} onHoverLeg={noop} onHoverPosition={noop} {...over} />)

// The jsdom svg is laid out at the fallback width of 600 px with a zero-based bounding rect.
const plotPx = (fractionOfTrip: number) => PROFILE_MARGINS.left + fractionOfTrip * (600 - PROFILE_MARGINS.left - PROFILE_MARGINS.right)

describe('HeightProfile', () => {
  it('draws a vertical separator at each interior night boundary only', () => {
    draw()
    expect(screen.getAllByTestId('night-separator')).toHaveLength(1)
  })

  it('shows a loading state instead of a chart while elevation.loading is true', () => {
    draw({ elevation: { ...elevation, loading: true } })
    expect(screen.getByText('Höhenprofil lädt …')).toBeInTheDocument()
    expect(screen.queryByTestId('profile-svg')).not.toBeInTheDocument()
  })

  it('shows nothing when there are no points and not loading', () => {
    draw({ elevation: { points: [], nightBoundariesKm: [], loading: false } })
    expect(screen.queryByTestId('profile-svg')).not.toBeInTheDocument()
    expect(screen.queryByText('Höhenprofil lädt …')).not.toBeInTheDocument()
  })

  it('names the start, each hut and the exit at the night boundaries', () => {
    draw()
    const labels = screen.getAllByTestId('stop-label').map((n) => n.textContent)
    expect(labels).toEqual(['Bahnhof X', 'Hütte A', 'Bahnhof X'])
  })

  it('draws a grid line and label per round elevation step', () => {
    draw()
    expect(screen.getAllByTestId('grid-line')).toHaveLength(3) // 1000, 1250, 1500
    expect(screen.getByText((1250).toLocaleString('de-DE'))).toBeInTheDocument()
  })

  it('labels km at the night boundaries', () => {
    draw()
    expect(screen.getAllByTestId('km-label').map((n) => n.textContent)).toEqual(['0,0', '1,0', '1,5'])
  })

  it('highlights the area and line of highlightedLeg', () => {
    draw({ highlightedLeg: 1 })
    for (const id of ['leg-segment-1', 'leg-area-1']) expect(screen.getByTestId(id)).toHaveAttribute('data-highlighted', 'true')
    for (const id of ['leg-segment-0', 'leg-area-0']) expect(screen.getByTestId(id)).toHaveAttribute('data-highlighted', 'false')
  })

  it('hovering reports the leg and the fraction along it, leaving clears both', () => {
    const onHoverLeg = vi.fn()
    const onHoverPosition = vi.fn()
    draw({ onHoverLeg, onHoverPosition })
    const svg = screen.getByTestId('profile-svg')
    fireEvent.mouseMove(svg, { clientX: plotPx(1.125 / 1.5) })
    expect(onHoverLeg).toHaveBeenLastCalledWith(1)
    const position = onHoverPosition.mock.calls.at(-1)![0]
    expect(position.legIndex).toBe(1)
    expect(position.fraction).toBeCloseTo(0.25)
    fireEvent.mouseLeave(svg)
    expect(onHoverLeg).toHaveBeenLastCalledWith(null)
    expect(onHoverPosition).toHaveBeenLastCalledWith(null)
  })

  it('shows a readout with km, elevation and stage while hovering, "Abstieg" on the exit leg', () => {
    draw()
    const svg = screen.getByTestId('profile-svg')
    fireEvent.mouseMove(svg, { clientX: plotPx(0.163 / 1.5) })
    expect(screen.getByText(`km 0,2 · ${(1000).toLocaleString('de-DE')} m · Etappe 1`)).toBeInTheDocument()
    expect(screen.getByTestId('profile-cursor')).toBeInTheDocument()
    fireEvent.mouseMove(svg, { clientX: plotPx(1.2 / 1.5) })
    expect(screen.getByText(`km 1,2 · ${(1400).toLocaleString('de-DE')} m · Abstieg`)).toBeInTheDocument()
    fireEvent.mouseLeave(svg)
    expect(screen.queryByTestId('profile-cursor')).not.toBeInTheDocument()
  })

  it('copes with a leg that has no elevation data', () => {
    const onHoverLeg = vi.fn()
    draw({
      elevation: {
        points: [{ distanceKm: 0, elevationM: 900, legIndex: 1 }, { distanceKm: 1, elevationM: 1100, legIndex: 1 }],
        nightBoundariesKm: [0, 0, 1],
        loading: false,
      },
      highlightedLeg: 0, onHoverLeg,
    })
    fireEvent.mouseMove(screen.getByTestId('profile-svg'), { clientX: plotPx(0) })
    expect(onHoverLeg).toHaveBeenLastCalledWith(1)
    expect(screen.queryByTestId('leg-area-0')).not.toBeInTheDocument()
  })
})
