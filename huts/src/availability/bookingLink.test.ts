import { describe, it, expect } from 'vitest'
import { buildBookingLink } from './bookingLink.js'

describe('buildBookingLink', () => {
  it('builds a one-night dateFrom/dateTo deep link to hut-reservation.org', () => {
    const link = buildBookingLink('179', new Date(Date.UTC(2026, 7, 20)))
    expect(link).toBe('https://www.hut-reservation.org/reservation/book-hut/179/wizard?dateFrom=20.08.2026&dateTo=21.08.2026')
  })
})
