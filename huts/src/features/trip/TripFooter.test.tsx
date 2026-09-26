// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import TripFooter from './TripFooter.js'
import { newTrip } from '@/trip/trip.js'

afterEach(cleanup)

const trip = newTrip({
  name: 't', startDate: null, partySize: 1, start: { startId: 100, sourceType: 1 }, huts: ['{A}'],
  exit: { startId: 100, sourceType: 1 }, variant: { sacCeiling: null, allowUngraded: false },
}, new Date(), 'id')

describe('TripFooter', () => {
  it('shows the notes and reports edits', () => {
    const onChange = vi.fn()
    render(<TripFooter trip={{ ...trip, notes: 'Regen' }} onChange={onChange} />)
    expect(screen.getByLabelText('Notizen')).toHaveValue('Regen')
    fireEvent.change(screen.getByLabelText('Notizen'), { target: { value: 'Wetter prüfen' } })
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ notes: 'Wetter prüfen' }))
  })
})
