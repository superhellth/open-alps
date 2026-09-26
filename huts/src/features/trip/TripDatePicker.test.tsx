// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import TripDatePicker from './TripDatePicker.js'
import * as availability from '@/availability/fetchAvailability.js'
import { newTrip } from '@/trip/trip.js'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

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
  it('marks the seven start dates around the first night with their verdict', async () => {
    // maxShift 3, base = firstNight - 4, hut i on shift s reads offset s + 3 + i + 1; only shift 0 has both huts free.
    const free = new Map([[4, new Set(['H0'])], [5, new Set(['H1'])]]) as never
    const spy = vi.spyOn(availability, 'fetchAvailabilityByOffset').mockResolvedValue(free)
    open('2026-07-10')
    await waitFor(() => expect(document.querySelectorAll('[data-verdict]').length).toBe(7))
    expect(spy).toHaveBeenCalledTimes(1)
    expect(spy.mock.calls[0][0].toISOString().slice(0, 10)).toBe('2026-07-06')
    const day = screen.getByRole('button', { name: '2026-07-10' })
    expect(day.querySelector('[data-verdict]')).toHaveAttribute('data-verdict', 'bookable')
    expect(screen.getByRole('button', { name: '2026-07-07' }).querySelector('[data-verdict]')).toHaveAttribute('data-verdict', 'unclear')
    expect(screen.getByRole('button', { name: '2026-07-14' }).querySelector('[data-verdict]')).toBeNull()
  })
  it('picking a day sets it as the first night and closes the calendar', async () => {
    vi.spyOn(availability, 'fetchAvailabilityByOffset').mockResolvedValue(new Map())
    const onChange = open('2026-07-10')
    fireEvent.click(screen.getByRole('button', { name: '2026-07-11' }))
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ startDate: '2026-07-11' }))
    await waitFor(() => expect(screen.queryByRole('button', { name: '2026-07-11' })).not.toBeInTheDocument())
  })
  it('an undated trip opens on today without marks or fetches', () => {
    const spy = vi.spyOn(availability, 'fetchAvailabilityByOffset').mockResolvedValue(new Map())
    open(null)
    expect(screen.getByText('Tag der ersten Nacht wählen')).toBeInTheDocument()
    expect(spy).not.toHaveBeenCalled()
  })
})
