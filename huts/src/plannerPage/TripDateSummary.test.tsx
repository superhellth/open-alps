// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import TripDateSummary from './TripDateSummary.js'
import { newTrip } from '../trip/trip.js'

afterEach(cleanup)

function makeTrip(overrides: Partial<Parameters<typeof newTrip>[0]> = {}) {
  return newTrip({
    name: 'T', startDate: null, partySize: 2,
    start: { startId: 1, sourceType: 1 }, huts: ['a', 'b'], exit: { startId: 1, sourceType: 1 },
    variant: { sacCeiling: null, allowUngraded: false }, ...overrides,
  })
}

describe('TripDateSummary', () => {
  it('shows "ohne Datum" with the party size when undated', () => {
    render(<TripDateSummary trip={makeTrip()} onChange={() => {}} />)
    expect(screen.getByText('ohne Datum · 2 Pers.')).toBeInTheDocument()
  })

  it('shows the date range and nights when dated', () => {
    render(<TripDateSummary trip={makeTrip({ startDate: '2026-07-12' })} onChange={() => {}} />)
    expect(screen.getByText('12.07.–14.07. · 2 Pers.')).toBeInTheDocument()
  })

  it('opens a popover with editable date and party size on click', () => {
    const onChange = vi.fn()
    render(<TripDateSummary trip={makeTrip({ startDate: '2026-07-12' })} onChange={onChange} />)
    fireEvent.click(screen.getByText('12.07.–14.07. · 2 Pers.'))
    fireEvent.change(screen.getByLabelText('Startdatum (erste Nacht)'), { target: { value: '2026-07-13' } })
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ startDate: '2026-07-13' }))
  })
})
