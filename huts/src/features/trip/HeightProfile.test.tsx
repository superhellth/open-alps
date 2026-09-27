// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import HeightProfile from './HeightProfile.js'
import { PROFILE_MARGINS } from './profileScale.js'
import type { TripElevation } from './useTripElevation.js'
import { STOP_SYMBOL_SIZE } from '@/ui/StopSymbol.js'
import type { StopMark } from '@/ui/StopSymbol.js'

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
const marks: StopMark[] = [{ type: 'end', sourceType: 1 }, { type: 'hut', changed: false }, { type: 'end', sourceType: 2 }]
const noop = () => {}
const draw = (over: Partial<Parameters<typeof HeightProfile>[0]> = {}) =>
  render(<HeightProfile elevation={elevation} stops={stops} marks={marks} highlightedLeg={null} onHoverLeg={noop} onHoverPosition={noop} {...over} />)

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

  it('marks the start, each hut and the exit with its map symbol centred on the line', () => {
    draw()
    const symbols = screen.getAllByTestId('stop-symbol')
    expect(symbols).toHaveLength(3)
    expect(symbols[0].querySelector('rect')).not.toBeNull()
    expect(symbols[1].querySelector('polygon')).not.toBeNull()
    expect(symbols[2]).toHaveTextContent('P')
    const separator = screen.getByTestId('night-separator')
    const hut = symbols[1].querySelector('svg')!
    const centre = (attr: string) => Number(hut.getAttribute(attr)) + STOP_SYMBOL_SIZE / 2
    expect(centre('x')).toBeCloseTo(Number(separator.getAttribute('x1')))
    expect(centre('y')).toBeCloseTo(Number(separator.getAttribute('y1')))
  })

  it('names start and destination in the caption while idle, without stop labels in the chart', () => {
    draw({ stops: ['Bahnhof Mayrhofen', 'Hütte A', 'Parkplatz Schlegeisspeicher'] })
    expect(screen.getByTestId('profile-caption')).toHaveTextContent('Bahnhof Mayrhofen → Parkplatz Schlegeisspeicher')
    expect(screen.queryByTestId('stop-label')).not.toBeInTheDocument()
  })

  it('labels only the lowest and highest elevation, without grid lines', () => {
    draw()
    expect(screen.getAllByTestId('elevation-label').map((n) => n.textContent))
      .toEqual([(1400).toLocaleString('de-DE'), (1000).toLocaleString('de-DE')])
    expect(screen.queryByTestId('grid-line')).not.toBeInTheDocument()
  })

  it('labels km at the night boundaries', () => {
    draw()
    expect(screen.getAllByTestId('km-label').map((n) => n.textContent)).toEqual(['0,0', '1,0', '1,5'])
  })

  it('fills only the highlighted leg and thickens its line', () => {
    draw({ highlightedLeg: 1 })
    expect(screen.getByTestId('leg-area-1')).toBeInTheDocument()
    expect(screen.queryByTestId('leg-area-0')).not.toBeInTheDocument()
    expect(screen.getByTestId('leg-segment-1')).toHaveAttribute('data-highlighted', 'true')
    expect(screen.getByTestId('leg-segment-0')).toHaveAttribute('data-highlighted', 'false')
  })

  it('draws no fill without a highlighted leg', () => {
    draw()
    expect(screen.queryByTestId(/^leg-area-/)).not.toBeInTheDocument()
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

  it('reads out km, elevation and stage in the caption while hovering, "Abstieg" on the exit leg', () => {
    draw()
    const svg = screen.getByTestId('profile-svg')
    const caption = screen.getByTestId('profile-caption')
    fireEvent.mouseMove(svg, { clientX: plotPx(0.163 / 1.5) })
    expect(caption).toHaveTextContent(`km 0,2 · ${(1000).toLocaleString('de-DE')} m · Etappe 1: Bahnhof X → Hütte A`)
    expect(screen.getByTestId('profile-cursor')).toBeInTheDocument()
    fireEvent.mouseMove(svg, { clientX: plotPx(1.2 / 1.5) })
    expect(caption).toHaveTextContent(`km 1,2 · ${(1400).toLocaleString('de-DE')} m · Abstieg: Hütte A → Bahnhof X`)
    fireEvent.mouseLeave(svg)
    expect(caption).toHaveTextContent('Bahnhof X → Bahnhof X')
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
