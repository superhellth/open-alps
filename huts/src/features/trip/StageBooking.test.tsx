// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import StageBooking from './StageBooking.js'

afterEach(cleanup)

const bookable = { ohrsHutId: '103', tenantCode: 8 }
const direct = { ohrsHutId: null, tenantCode: null }
const date = new Date(Date.UTC(2026, 6, 13))
const base = { date, ohrs: bookable }

describe('StageBooking', () => {
  it('links a bookable hut to hut-reservation.org for its own night', () => {
    render(<StageBooking {...base} />)
    expect(screen.getByRole('link', { name: 'Auf hut-reservation.org buchen' })).toHaveAttribute('href', expect.stringContaining('/103/wizard?dateFrom=13.07.2026&dateTo=14.07.2026'))
  })
  it('tells to contact a direct-booking hut, with or without a date', () => {
    const { rerender } = render(<StageBooking {...base} ohrs={direct} />)
    expect(screen.getByText('Direktbuchung: die Hütte selbst kontaktieren.')).toBeInTheDocument()
    rerender(<StageBooking {...base} ohrs={direct} date={null} />)
    expect(screen.getByText('Direktbuchung: die Hütte selbst kontaktieren.')).toBeInTheDocument()
  })
  it('asks for a date instead of a booking link while the trip has none', () => {
    render(<StageBooking {...base} date={null} />)
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.getByText('Datum wählen, um zu buchen.')).toBeInTheDocument()
  })
})
