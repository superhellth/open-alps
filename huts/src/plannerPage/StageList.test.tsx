// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import StageList from './StageList.js'
import { makeTestAppData } from '@/testing/testAppData.js'
import { legsFromTrip } from '@/trip/tripLegs.js'
import { newTrip } from '../trip/trip.js'
import { makeStartLabel } from './labels.js'

afterEach(cleanup)

const data = makeTestAppData()
const trip = (huts: string[], startDate: string | null = '2026-07-10') => newTrip({
  name: 't', startDate, partySize: 2, start: { startId: 100, sourceType: 1 }, huts,
  exit: { startId: 100, sourceType: 1 }, variant: { sacCeiling: null, allowUngraded: false },
}, new Date(), 'id')

function renderList(t = trip(['{D}', '{E}']), overrides: Partial<Parameters<typeof StageList>[0]> = {}) {
  const props = {
    trip: t, tripLegs: legsFromTrip(data.graph, t), hutNameById: data.hutNameById, hutOhrsByIndex: data.hutOhrsByIndex,
    startLabel: makeStartLabel(data.startById), nightViews: null, onHoverLeg: vi.fn(), ...overrides,
  }
  render(<StageList {...props} />)
  return props
}

describe('StageList', () => {
  it('shows one signpost per night plus the descent, with signpost-style times', () => {
    renderList(trip(['{A}']))
    expect(screen.getByText('Hütte A')).toBeInTheDocument()
    expect(screen.getByText(/Bahnhof X/)).toBeInTheDocument() // the exit signpost
    expect(screen.getAllByText(/Std$/).length).toBe(2)
  })
  it('marks a night that no longer resolves with the outline signpost and the notice, and offers no replacement', () => {
    renderList(trip(['{A}', '{GONE}']))
    expect(screen.getByText('Seit dem Speichern geändert – nicht mehr im Wegenetz')).toBeInTheDocument()
    const outline = document.querySelectorAll('[data-variant="outline"]')
    expect(outline.length).toBeGreaterThanOrEqual(1)
  })
  it('renders no booking-status control', () => {
    renderList()
    expect(screen.queryByLabelText(/Buchungsstatus/)).not.toBeInTheDocument()
  })
  it('links bookable huts to the booking system for their own night and tells about direct-booking huts', () => {
    renderList(trip(['{A}', '{B}', '{C}', '{D}']))
    const link = screen.getByRole('link', { name: 'Auf hut-reservation.org buchen' })
    expect(link).toHaveAttribute('href', expect.stringContaining('/103/wizard?dateFrom=13.07.2026&dateTo=14.07.2026'))
    expect(screen.getAllByText(/Direktbuchung/)).toHaveLength(3)
  })
  it('shows availability with shape and text once night views exist, "unknown" distinct from "full"', () => {
    renderList(trip(['{D}', '{E}']), {
      nightViews: [
        { loading: false, availability: { kind: 'free', places: 12 } },
        { loading: false, availability: { kind: 'unknown' } },
      ],
    })
    expect(screen.getByText('12 Plätze frei')).toBeInTheDocument()
    expect(screen.getByText('Verfügbarkeit unbekannt – direkt anfragen')).toBeInTheDocument()
    expect(screen.queryByText('ausgebucht')).not.toBeInTheDocument()
  })
  it('reports the hovered leg so the map can highlight it', () => {
    const props = renderList()
    fireEvent.mouseEnter(screen.getByText('Hütte E').closest('[data-stage]')!)
    expect(props.onHoverLeg).toHaveBeenCalledWith(1)
  })
  it('renders a booking-status toggle per night and reports changes', () => {
    const onNightStatusChange = vi.fn()
    renderList(trip(['{D}']), { onNightStatusChange })
    fireEvent.click(screen.getByLabelText('Buchungsstatus Nacht 1'))
    fireEvent.click(screen.getByRole('button', { name: 'bestätigt' }))
    expect(onNightStatusChange).toHaveBeenCalledWith(0, 'confirmed')
  })
})
