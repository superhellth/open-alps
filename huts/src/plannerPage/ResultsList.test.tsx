// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import ResultsList from './ResultsList.js'
import type { PlannerTour } from './tours.js'

afterEach(cleanup)

const tour = (huts: number[], over: Partial<PlannerTour> = {}): PlannerTour => ({
  huts, startId: 1, exitStartId: 1, totalDurationH: 10.5, totalAscentM: 1800, totalDescentM: 1700, totalDistanceM: 25000,
  legs: huts.concat(0).map(() => ({ durationH: 3.5, ascentM: 600, descentM: 500, distanceM: 8000, edgeId: 0, reversed: false })), ...over,
})
const props = () => ({
  tours: [tour([0, 1]), tour([2], { official: { tourId: 3, name: 'Kaisertour' } })],
  selectionActive: true, totalMatches: 2, noMatches: false, sortKey: 'fit' as const,
  onSortChange: vi.fn(), onPreview: vi.fn(), onPick: vi.fn(),
  hutNameById: new Map([[0, 'Hütte A'], [1, 'Hütte B'], [2, 'Hütte C']]),
  hutClassByIndex: new Map([[0, { operator: 'av' as const, serviced: true }]]),
  startLabel: (id: number) => `Start ${id}`,
})

describe('ResultsList', () => {
  it('lists tours with hut names and signpost-style totals, official ones tagged', () => {
    render(<ResultsList {...props()} />)
    expect(screen.getByText(/Hütte A/)).toBeInTheDocument()
    expect(screen.getAllByText('10½ Std').length).toBe(2)
    expect(screen.getByText('Offiziell: Kaisertour')).toBeInTheDocument()
  })
  it('previews on hover and on keyboard focus, clears on leave, picks on click', () => {
    const p = props()
    render(<ResultsList {...p} />)
    const row = screen.getAllByRole('button', { name: /Hütte/ })[0]
    fireEvent.mouseEnter(row)
    expect(p.onPreview).toHaveBeenLastCalledWith(p.tours[0])
    fireEvent.mouseLeave(row)
    expect(p.onPreview).toHaveBeenLastCalledWith(null)
    fireEvent.focus(row)
    expect(p.onPreview).toHaveBeenLastCalledWith(p.tours[0])
    fireEvent.click(row)
    expect(p.onPick).toHaveBeenCalledWith(p.tours[0])
  })
  it('shows the fixed no-match hint', () => {
    render(<ResultsList {...props()} tours={[]} noMatches />)
    expect(screen.getByText('Keine Touren für diese Filter. Mehr Tage oder längere Gehzeit pro Tag zulassen.')).toBeInTheDocument()
  })
  it('asks for a marker click before any area is chosen', () => {
    render(<ResultsList {...props()} tours={[]} selectionActive={false} totalMatches={12} />)
    expect(screen.getByText(/12 Touren/)).toBeInTheDocument()
    expect(screen.getByText(/Marker/)).toBeInTheDocument()
  })
  it('shows a "voll" chip for tours isFull marks, none otherwise', () => {
    const p = props()
    render(<ResultsList {...p} isFull={(t) => t === p.tours[1]} />)
    const rows = screen.getAllByRole('button', { name: /Hütte/ })
    expect(within(rows[1]).getByText('voll')).toBeInTheDocument()
    expect(within(rows[0]).queryByText('voll')).not.toBeInTheDocument()
  })
  it('shows no "voll" chip when isFull is not provided', () => {
    render(<ResultsList {...props()} />)
    expect(screen.queryByText('voll')).not.toBeInTheDocument()
  })
  it('pages long lists', () => {
    const many = Array.from({ length: 30 }, (_, i) => tour([0], { startId: i }))
    render(<ResultsList {...props()} tours={many} totalMatches={30} />)
    expect(screen.getAllByRole('button', { name: /Hütte A/ })).toHaveLength(25)
    fireEvent.click(screen.getByRole('button', { name: 'Go to page 2' }))
    expect(screen.getAllByRole('button', { name: /Hütte A/ })).toHaveLength(5)
  })
})
