// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import TripDatePicker from './TripDatePicker.js'
import * as availability from '@/availability/fetchAvailability.js'
import { newTrip } from '@/trip/trip.js'

beforeEach(() => { vi.useFakeTimers({ toFake: ['Date'], now: new Date('2026-07-01T12:00:00Z') }) })
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.useRealTimers() })

const trip = (startDate: string | null) => newTrip({
  name: 't', startDate, partySize: 2, start: { startId: 100, sourceType: 1 }, huts: ['{A}', '{B}'],
  exit: { startId: 100, sourceType: 1 }, variant: { sacCeiling: null, allowUngraded: false },
}, new Date(), 'id')
const ohrs = new Map([[0, { ohrsHutId: 'H0', tenantCode: 8 }], [1, { ohrsHutId: 'H1', tenantCode: 8 }]])

function open(startDate: string | null, onChange = vi.fn()) {
  render(<TripDatePicker trip={trip(startDate)} hutIndices={[0, 1]} hutOhrsByIndex={ohrs} onChange={onChange} />)
  fireEvent.click(screen.getByRole('button', { name: startDate ? /–/ : 'Datum wählen' }))
  return onChange
}

describe('TripDatePicker', () => {
  it('labels the field with first night to departure day', () => {
    render(<TripDatePicker trip={trip('2026-07-10')} hutIndices={[0, 1]} hutOhrsByIndex={ohrs} onChange={() => {}} />)
    expect(screen.getByRole('button', { name: '10.07. – 12.07.' })).toBeInTheDocument()
  })
  it('fetches nothing until opened', () => {
    const spy = vi.spyOn(availability, 'fetchAvailabilityByOffset').mockResolvedValue(new Map())
    render(<TripDatePicker trip={trip('2026-07-10')} hutIndices={[0, 1]} hutOhrsByIndex={ohrs} onChange={() => {}} />)
    expect(spy).not.toHaveBeenCalled()
  })
  it('marks each night of the stay with its own hut and prefetches ±3 arrival days', async () => {
    // Night 1 (10.07.) hut H0 free, night 2 (11.07.) hut H1 full.
    const spy = vi.spyOn(availability, 'fetchAvailabilityByOffset').mockImplementation(async (base, _p, max) =>
      max === 2 && base.toISOString().startsWith('2026-07-09') ? new Map([[1, new Set(['H0'])], [2, new Set(['H0'])]]) : new Map())
    open('2026-07-10')
    await waitFor(() => expect(document.querySelectorAll('[data-night]').length).toBe(2))
    expect(screen.getByRole('button', { name: '2026-07-10' }).querySelector('[data-night]')).toHaveAttribute('data-night', 'free')
    expect(screen.getByRole('button', { name: '2026-07-11' }).querySelector('[data-night]')).toHaveAttribute('data-night', 'full')
    expect(screen.getByRole('button', { name: '2026-07-12' }).querySelector('[data-night]')).toBeNull()
    expect(screen.getByText('10.07. – 12.07.: ✕ belegt')).toBeInTheDocument()
    const prefetch = spy.mock.calls.find((c) => c[2] === 8)!
    expect(prefetch[0].toISOString().slice(0, 10)).toBe('2026-07-06')
  })
  it('hovering a day moves the stay and re-marks its nights', async () => {
    vi.spyOn(availability, 'fetchAvailabilityByOffset').mockImplementation(async (base, _p, max) =>
      max === 2 && base.toISOString().startsWith('2026-07-10') ? new Map([[1, new Set(['H0'])], [2, new Set(['H1'])]]) : new Map())
    open('2026-07-10')
    fireEvent.mouseEnter(screen.getByRole('button', { name: '2026-07-11' }))
    expect(screen.getByRole('button', { name: '2026-07-10' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: '2026-07-13' })).toHaveAttribute('aria-pressed', 'true')
    await waitFor(() => expect(screen.getByText('11.07. – 13.07.: ● alles frei')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: '2026-07-12' }).querySelector('[data-night]')).toHaveAttribute('data-night', 'free')
    expect(screen.getByRole('button', { name: '2026-07-10' }).querySelector('[data-night]')).toBeNull()
  })
  it('huts without OHRS id are unclear nights', async () => {
    vi.spyOn(availability, 'fetchAvailabilityByOffset').mockResolvedValue(new Map([[1, new Set(['H0'])], [2, new Set(['H1'])]]))
    render(<TripDatePicker trip={trip('2026-07-10')} hutIndices={[0, null]} hutOhrsByIndex={ohrs} onChange={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: /–/ }))
    await waitFor(() => expect(screen.getByText('10.07. – 12.07.: ? unklar')).toBeInTheDocument())
  })
  it('picking a day sets it as the first night and closes the calendar', async () => {
    vi.spyOn(availability, 'fetchAvailabilityByOffset').mockResolvedValue(new Map())
    const onChange = open('2026-07-10')
    fireEvent.click(screen.getByRole('button', { name: '2026-07-11' }))
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ startDate: '2026-07-11' }))
    await waitFor(() => expect(screen.queryByRole('button', { name: '2026-07-11' })).not.toBeInTheDocument())
  })
  it('an undated trip opens without marks or fetches until a day is hovered', () => {
    const spy = vi.spyOn(availability, 'fetchAvailabilityByOffset').mockResolvedValue(new Map())
    open(null)
    expect(screen.getByText('Anreisetag wählen · 2 Nächte')).toBeInTheDocument()
    expect(screen.getByText('Der Aufenthalt folgt dem Anreisetag.')).toBeInTheDocument()
    expect(spy).not.toHaveBeenCalled()
  })
  it('prefetches no past nights', () => {
    vi.setSystemTime(new Date('2026-07-09T12:00:00Z'))
    const spy = vi.spyOn(availability, 'fetchAvailabilityByOffset').mockResolvedValue(new Map())
    open('2026-07-10')
    const prefetch = spy.mock.calls.find((c) => c[2] === 8)!
    expect(prefetch[0].toISOString().slice(0, 10)).toBe('2026-07-06')
    expect(prefetch[3]).toBe(3)
  })
  it('does not prefetch when every nearby night is past', () => {
    vi.setSystemTime(new Date('2026-08-01T12:00:00Z'))
    const spy = vi.spyOn(availability, 'fetchAvailabilityByOffset').mockResolvedValue(new Map())
    open('2026-07-10')
    expect(spy.mock.calls.find((c) => c[2] === 8)).toBeUndefined()
  })
  it('ignores clicks on past days', () => {
    vi.setSystemTime(new Date('2026-07-09T12:00:00Z'))
    vi.spyOn(availability, 'fetchAvailabilityByOffset').mockResolvedValue(new Map())
    const onChange = open('2026-07-10')
    fireEvent.click(screen.getByRole('button', { name: '2026-07-08' }))
    expect(onChange).not.toHaveBeenCalled()
  })
})
