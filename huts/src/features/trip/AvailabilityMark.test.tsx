// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import AvailabilityMark, { DirectBookingMark } from './AvailabilityMark.js'

afterEach(cleanup)

describe('AvailabilityMark', () => {
  it.each([
    [{ kind: 'free', places: 12 } as const, 'free', '12 Plätze frei'],
    [{ kind: 'few', places: 3 } as const, 'few', '3 Plätze frei'],
    [{ kind: 'full' } as const, 'full', 'ausgebucht'],
    [{ kind: 'unknown' } as const, 'unknown', 'Plätze unbekannt'],
  ])('%j pairs icon %s with text', (availability, shape, text) => {
    const { container } = render(<AvailabilityMark availability={availability} />)
    expect(screen.getByText(text)).toBeInTheDocument()
    expect(container.querySelector(`[data-shape="${shape}"]`)).not.toBeNull()
  })
  it('marks a direct-booking hut with a phone icon and text', () => {
    const { container } = render(<DirectBookingMark />)
    expect(screen.getByText('Direktbuchung – Hütte kontaktieren')).toBeInTheDocument()
    expect(container.querySelector('[data-shape="phone"]')).not.toBeNull()
  })
})
