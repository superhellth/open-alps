// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import BookingLink from './BookingLink.js'

afterEach(cleanup)

describe('BookingLink', () => {
  it('links the hut to hut-reservation.org for its own night, in a new tab', () => {
    render(<BookingLink hutName="Hütte D" ohrsHutId="103" date={new Date(Date.UTC(2026, 6, 13))} />)
    const link = screen.getByRole('link', { name: 'Hütte D auf hut-reservation.org buchen' })
    expect(link).toHaveAttribute('href', expect.stringContaining('/103/wizard?dateFrom=13.07.2026&dateTo=14.07.2026'))
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveTextContent('Buchen')
  })
})
