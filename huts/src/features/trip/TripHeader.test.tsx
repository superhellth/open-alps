// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import TripHeader from './TripHeader.js'
import { makeTestAppData } from '@/testing/testAppData.js'
import { legsFromTrip } from '@/trip/tripLegs.js'
import { newTrip } from '@/trip/trip.js'
import type { Trip } from '@/trip/trip.js'
import * as availability from '@/availability/fetchAvailability.js'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

const data = makeTestAppData()
const make = (startDate: string | null = '2026-07-10'): Trip => newTrip({
  name: 'Testtour', startDate, partySize: 2, start: { startId: 100, sourceType: 1 }, huts: ['{D}', '{E}'],
  exit: { startId: 100, sourceType: 1 }, variant: { sacCeiling: null, allowUngraded: false },
}, new Date(), 'id')

function renderHeader(over: Partial<Parameters<typeof TripHeader>[0]> = {}) {
  vi.spyOn(availability, 'fetchAvailabilityByOffset').mockResolvedValue(new Map())
  const trip = over.trip ?? make()
  const props = {
    trip, tripLegs: legsFromTrip(data.graph, trip), hutOhrsByIndex: data.hutOhrsByIndex, isDraft: false,
    onChange: vi.fn(), onSave: vi.fn(), onUnsave: vi.fn(), onBack: vi.fn(), backLabel: '← Ergebnisse', onShare: vi.fn(), ...over,
  }
  render(<TripHeader {...props} />)
  return props
}

describe('TripHeader', () => {
  it('shows the trip name on the plate with nights, km and ascent/descent', () => {
    renderHeader()
    expect(screen.getByText('Testtour')).toBeInTheDocument()
    expect(screen.getByText(/2 Nächte · \d+ km · ↑ .+ m ↓ .+ m/)).toBeInTheDocument()
    expect(screen.getByText(/Std$/)).toBeInTheDocument()
  })
  it('calls back and share', () => {
    const { onBack, onShare } = renderHeader({ backLabel: '← Meine Touren' })
    fireEvent.click(screen.getByRole('button', { name: '← Meine Touren' }))
    fireEvent.click(screen.getByRole('button', { name: 'Teilen' }))
    expect(onBack).toHaveBeenCalled()
    expect(onShare).toHaveBeenCalled()
  })
  it('shows no share button without onShare', () => {
    renderHeader({ onShare: undefined })
    expect(screen.queryByRole('button', { name: 'Teilen' })).not.toBeInTheDocument()
  })
  it('a draft shows its name, is marked nicht gespeichert, saves to Meine Touren under the name from the dialog', async () => {
    const { onSave } = renderHeader({ isDraft: true })
    expect(screen.getByText(/^nicht gespeichert · 2 Nächte/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Merken' }))
    fireEvent.change(screen.getByLabelText('Tourname'), { target: { value: 'Mein Name' } })
    fireEvent.click(screen.getByRole('button', { name: 'Merken' }))
    expect(onSave).toHaveBeenCalledWith('Mein Name')
  })
  it('the name is not editable by clicking it', () => {
    renderHeader()
    fireEvent.click(screen.getByText('Testtour'))
    expect(screen.queryByLabelText('Tourname')).not.toBeInTheDocument()
  })
  it('a saved trip shows Gespeichert instead of Merken and no nicht gespeichert mark', () => {
    renderHeader()
    expect(screen.queryByText(/nicht gespeichert/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Merken' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Gespeichert' })).toBeInTheDocument()
  })
  it('Gespeichert removes the trip without a confirmation dialog', () => {
    const { onUnsave } = renderHeader()
    fireEvent.click(screen.getByRole('button', { name: 'Gespeichert' }))
    expect(onUnsave).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
  it('edits date and party size through the date summary popover', () => {
    const { onChange, trip } = renderHeader()
    fireEvent.click(screen.getByText('10.07.–12.07. · 2 Pers.'))
    fireEvent.change(screen.getByLabelText('Startdatum (erste Nacht)'), { target: { value: '2026-07-12' } })
    expect(onChange).toHaveBeenLastCalledWith({ ...trip, startDate: '2026-07-12' })
  })
  it('clicking a start-day chip shifts the start date by that many days', async () => {
    const { onChange, trip } = renderHeader()
    await waitFor(() => expect(document.querySelectorAll('[data-shift]').length).toBe(7))
    fireEvent.click(document.querySelector('[data-shift="1"]')!)
    expect(onChange).toHaveBeenLastCalledWith({ ...trip, startDate: '2026-07-11' })
  })
  it('an undated trip reads "Datum wählen" and shows no chips', () => {
    renderHeader({ trip: make(null) })
    expect(screen.getByText('Datum wählen · 2 Pers.')).toBeInTheDocument()
    expect(document.querySelectorAll('[data-shift]').length).toBe(0)
  })
})
