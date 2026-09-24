// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import ResultsList from './ResultsList.js'
import type { PlannerTour } from './tours.js'

afterEach(cleanup)

const tour = (huts: number[], over: Partial<PlannerTour> = {}): PlannerTour => ({
  huts, startId: 1, exitStartId: 1, totalDurationH: 10.5, totalAscentM: 1800, totalDescentM: 1700, totalDistanceM: 25000,
  legs: huts.concat(0).map(() => ({ durationH: 3.5, ascentM: 600, descentM: 500, distanceM: 8000, edgeId: 0, reversed: false })), ...over,
})
const hutNameById = new Map([[0, 'Hut A'], [1, 'Hut B'], [2, 'Hut C'], [3, 'Hut D'], [4, 'Hut E']])
const props = () => ({
  tours: [tour([0, 1]), tour([2], { official: { tourId: 3, name: 'Kaisertour' } })],
  totalCount: 2, onShowAll: vi.fn(), isHighlighted: () => false, noMatches: false, sortKey: 'fit' as const, sortDir: 'asc' as const,
  onSortChange: vi.fn(), onSortDirChange: vi.fn(), onPreview: vi.fn(), onPick: vi.fn(), onOpenFilters: vi.fn(),
  hutNameById,
})

describe('ResultsList', () => {
  it('lists tours by their hut chain and signpost-style totals, official ones tagged', () => {
    render(<ResultsList {...props()} />)
    expect(screen.getByText('Hut A – Hut B')).toBeInTheDocument()
    expect(screen.getAllByText(/10½ Std/).length).toBe(2)
    expect(screen.getByText('Offiziell: Kaisertour')).toBeInTheDocument()
  })
  it('folds long hut chains to first – last plus a count chip', () => {
    render(<ResultsList {...props()} tours={[tour([0, 1, 2, 3, 4])]} />)
    expect(screen.getByText('Hut A – Hut E')).toBeInTheDocument()
    expect(screen.getByText('+3 Hütten')).toBeInTheDocument()
  })
  it('previews on hover and on keyboard focus, clears on leave, picks on click', () => {
    const p = props()
    render(<ResultsList {...p} />)
    const row = screen.getAllByRole('button').find((b) => b.textContent?.includes('Hut A'))!
    fireEvent.mouseEnter(row)
    expect(p.onPreview).toHaveBeenLastCalledWith(p.tours[0])
    fireEvent.mouseLeave(row)
    expect(p.onPreview).toHaveBeenLastCalledWith(null)
    fireEvent.focus(row)
    expect(p.onPreview).toHaveBeenLastCalledWith(p.tours[0])
    fireEvent.click(row)
    expect(p.onPick).toHaveBeenCalledWith(p.tours[0])
  })
  it('shows the fixed no-match hint with a button back to filters', () => {
    const onOpenFilters = vi.fn()
    render(<ResultsList {...props()} tours={[]} noMatches onOpenFilters={onOpenFilters} />)
    expect(screen.getByText('Keine Touren für diese Filter. Mehr Tage oder längere Gehzeit pro Tag zulassen.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Filter anpassen' }))
    expect(onOpenFilters).toHaveBeenCalled()
  })
  it('tapping the active chip flips sort direction, tapping fit chip does not toggle dir', () => {
    const p = props()
    render(<ResultsList {...p} />)
    fireEvent.click(screen.getByText('Empfehlung'))
    expect(p.onSortDirChange).not.toHaveBeenCalled()
    expect(p.onSortChange).not.toHaveBeenCalled()
    cleanup()
    const p2 = { ...props(), sortKey: 'duration' as const }
    render(<ResultsList {...p2} />)
    fireEvent.click(screen.getByText('Gesamtdauer'))
    expect(p2.onSortDirChange).toHaveBeenCalledWith('desc')
  })
  it('tapping another chip picks that sort key', () => {
    const p = props()
    render(<ResultsList {...p} />)
    fireEvent.click(screen.getByText('Gesamtdauer'))
    expect(p.onSortChange).toHaveBeenCalledWith('duration')
  })
  it('pages long lists', () => {
    const many = Array.from({ length: 30 }, (_, i) => tour([0], { startId: i, exitStartId: i }))
    render(<ResultsList {...props()} tours={many} />)
    expect(screen.getAllByRole('button').filter((b) => b.textContent?.includes('Hut A'))).toHaveLength(25)
    fireEvent.click(screen.getByRole('button', { name: 'Go to page 2' }))
    expect(screen.getAllByRole('button').filter((b) => b.textContent?.includes('Hut A'))).toHaveLength(5)
  })

  it('offers a show-all button only when fewer tours than the total are listed', () => {
    const p = props()
    const { rerender } = render(<ResultsList {...p} />)
    expect(screen.queryByText(/Touren anzeigen/)).toBeNull()
    rerender(<ResultsList {...p} tours={[p.tours[0]]} />)
    fireEvent.click(screen.getByText('← Alle 2 Touren anzeigen'))
    expect(p.onShowAll).toHaveBeenCalled()
  })
})
