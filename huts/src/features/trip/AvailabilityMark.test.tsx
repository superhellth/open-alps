// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import AvailabilityMark from './AvailabilityMark.js'

afterEach(cleanup)

describe('AvailabilityMark', () => {
  it.each([
    [{ kind: 'free', places: 12 } as const, 'filled', '12 Plätze frei'],
    [{ kind: 'few', places: 3 } as const, 'half', '3 Plätze frei'],
    [{ kind: 'full' } as const, 'crossed', 'ausgebucht'],
    [{ kind: 'unknown' } as const, 'question', 'Verfügbarkeit unbekannt – direkt anfragen'],
  ])('%j pairs shape %s with text', (availability, shape, text) => {
    const { container } = render(<AvailabilityMark availability={availability} />)
    expect(screen.getByText(text)).toBeInTheDocument()
    expect(container.querySelector(`[data-shape="${shape}"]`)).not.toBeNull()
  })
})
