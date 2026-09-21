// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import TripPanel from './TripPanel.js'
import { makeTestAppData } from './testAppData.js'
import { legsFromTrip } from '../tourSearch/tripLegs.js'
import { newTrip } from '../trip/trip.js'
import { makeStartLabel } from './labels.js'
import * as availability from '../availability/fetchAvailability.js'
import * as detail from '../availability/fetchHutDetail.js'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

const data = makeTestAppData()
const trip = newTrip({
  name: 'Testtour', startDate: '2026-07-10', partySize: 2, start: { startId: 100, sourceType: 1 }, huts: ['{D}', '{E}'],
  exit: { startId: 100, sourceType: 1 }, variant: { sacCeiling: null, allowUngraded: false },
}, new Date(), 'id')

function renderPanel(onChange = vi.fn(), onBack = vi.fn()) {
  vi.spyOn(availability, 'fetchAvailabilityByOffset').mockResolvedValue(new Map())
  vi.spyOn(detail, 'fetchHutDetail').mockResolvedValue({ hutId: 1, hutName: '', calendarDays: [] })
  render(
    <TripPanel
      trip={trip} tripLegs={legsFromTrip(data.graph, trip)} data={data} startLabel={makeStartLabel(data.startById)}
      onChange={onChange} onBack={onBack} onHoverLeg={() => {}}
    />,
  )
  return { onChange, onBack }
}

describe('TripPanel', () => {
  it('shows name, totals and the stages', () => {
    renderPanel()
    expect(screen.getByDisplayValue('Testtour')).toBeInTheDocument()
    expect(screen.getByText(/2 Nächte/)).toBeInTheDocument()
    expect(screen.getByText('Hütte D')).toBeInTheDocument()
    expect(screen.getByText('Hütte E')).toBeInTheDocument()
  })
  it('goes back to the results', () => {
    const { onBack } = renderPanel()
    fireEvent.click(screen.getByRole('button', { name: '← Ergebnisse' }))
    expect(onBack).toHaveBeenCalled()
  })
  it('edits date and party size on the trip', () => {
    const { onChange } = renderPanel()
    fireEvent.change(screen.getByLabelText('Startdatum (erste Nacht)'), { target: { value: '2026-07-12' } })
    expect(onChange).toHaveBeenLastCalledWith({ ...trip, startDate: '2026-07-12' })
    fireEvent.change(screen.getByLabelText('Personen'), { target: { value: '4' } })
    expect(onChange).toHaveBeenLastCalledWith({ ...trip, partySize: 4 })
  })
  it('renames and stores notes', () => {
    const { onChange } = renderPanel()
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Neu' } })
    expect(onChange).toHaveBeenLastCalledWith({ ...trip, name: 'Neu' })
    fireEvent.change(screen.getByLabelText('Notizen'), { target: { value: 'Seil mitnehmen' } })
    expect(onChange).toHaveBeenLastCalledWith({ ...trip, notes: 'Seil mitnehmen' })
  })
  it('a booking status change updates only that night', () => {
    const { onChange } = renderPanel()
    fireEvent.click(screen.getAllByRole('button', { name: 'angefragt' })[1])
    const updated = onChange.mock.calls.at(-1)![0]
    expect(updated.nights).toEqual([{ status: 'open' }, { status: 'requested' }])
  })
  it('sliding the start date moves the whole trip by a day', () => {
    const { onChange } = renderPanel()
    fireEvent.click(screen.getByRole('button', { name: '+1 Tag' }))
    expect(onChange).toHaveBeenLastCalledWith({ ...trip, startDate: '2026-07-11' })
  })
})
