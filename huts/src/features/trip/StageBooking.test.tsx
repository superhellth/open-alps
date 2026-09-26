// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import StageBooking from './StageBooking.js'

afterEach(cleanup)

const bookable = { ohrsHutId: '103', tenantCode: 8 }
const direct = { ohrsHutId: null, tenantCode: null }
const date = new Date(Date.UTC(2026, 6, 13))
const base = { night: 0, date, ohrs: bookable, view: undefined, status: 'open' as const, onStatusChange: () => {} }

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
  it('offers no booking link without a date', () => {
    render(<StageBooking {...base} date={null} />)
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })
  it('shows loading and availability states', () => {
    const { rerender } = render(<StageBooking {...base} view={{ loading: true }} />)
    expect(screen.getByText('Verfügbarkeit lädt …')).toBeInTheDocument()
    rerender(<StageBooking {...base} view={{ loading: false, availability: { kind: 'free', places: 12 } }} />)
    expect(screen.getByText('12 Plätze frei')).toBeInTheDocument()
  })
  it('reports a status change from the toggle', () => {
    const onStatusChange = vi.fn()
    render(<StageBooking {...base} onStatusChange={onStatusChange} />)
    fireEvent.click(screen.getByRole('button', { name: 'bestätigt' }))
    expect(onStatusChange).toHaveBeenCalledWith('confirmed')
    expect(screen.getByLabelText('Buchungsstatus Nacht 1')).toBeInTheDocument()
  })
})
