// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import StartDateStrip from './StartDateStrip.js'
import * as availability from '@/availability/fetchAvailability.js'
import { newTrip } from '@/trip/trip.js'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

const trip = (startDate: string | null) => newTrip({
  name: 't', startDate, partySize: 2, start: { startId: 100, sourceType: 1 }, huts: ['{A}', '{B}'],
  exit: { startId: 100, sourceType: 1 }, variant: { sacCeiling: null, allowUngraded: false },
}, new Date(), 'id')
const ohrs = new Map([[0, { ohrsHutId: 'H0', tenantCode: 8 }], [1, { ohrsHutId: 'H1', tenantCode: 8 }]])

describe('StartDateStrip', () => {
  it('renders nothing for an undated trip', () => {
    const { container } = render(<StartDateStrip trip={trip(null)} hutIndices={[0, 1]} hutOhrsByIndex={ohrs} onShift={() => {}} />)
    expect(container).toBeEmptyDOMElement()
  })
  it('fetches the shared window once and answers seven start dates as chips with a mark', async () => {
    // maxShift 3, base = firstNight - 4, hut i on shift s reads offset s + 3 + i + 1; only shift 0 has both huts free.
    const free = new Map([[4, new Set(['H0'])], [5, new Set(['H1'])]]) as never
    const spy = vi.spyOn(availability, 'fetchAvailabilityByOffset').mockResolvedValue(free)
    const { container } = render(<StartDateStrip trip={trip('2026-07-10')} hutIndices={[0, 1]} hutOhrsByIndex={ohrs} onShift={() => {}} />)
    await waitFor(() => expect(container.querySelectorAll('[data-shift]').length).toBe(7))
    expect(spy).toHaveBeenCalledTimes(1)
    expect(spy.mock.calls[0][0].toISOString().slice(0, 10)).toBe('2026-07-06')
    expect(screen.getAllByText('●')).toHaveLength(1)
    expect(container.querySelector('[data-shift="0"]')).toBeDisabled()
    expect(container.querySelector('[data-shift="0"]')).toHaveAttribute('aria-label', expect.stringContaining('alles frei'))
  })
  it('clicking another day shifts the whole trip by that many days', async () => {
    vi.spyOn(availability, 'fetchAvailabilityByOffset').mockResolvedValue(new Map())
    const onShift = vi.fn()
    const { container } = render(<StartDateStrip trip={trip('2026-07-10')} hutIndices={[0, 1]} hutOhrsByIndex={ohrs} onShift={onShift} />)
    await waitFor(() => expect(container.querySelectorAll('[data-shift]').length).toBe(7))
    fireEvent.click(container.querySelector('[data-shift="1"]')!)
    expect(onShift).toHaveBeenLastCalledWith(1)
    fireEvent.click(container.querySelector('[data-shift="-3"]')!)
    expect(onShift).toHaveBeenLastCalledWith(-3)
    fireEvent.click(container.querySelector('[data-shift="0"]')!)
    expect(onShift).toHaveBeenCalledTimes(2)
  })
  it('has no separate −1/+1 buttons', async () => {
    vi.spyOn(availability, 'fetchAvailabilityByOffset').mockResolvedValue(new Map())
    render(<StartDateStrip trip={trip('2026-07-10')} hutIndices={[0, 1]} hutOhrsByIndex={ohrs} onShift={() => {}} />)
    expect(screen.queryByRole('button', { name: '+1 Tag' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '−1 Tag' })).not.toBeInTheDocument()
  })
})
