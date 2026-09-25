// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import TripPanel from './TripPanel.js'
import { makeTestAppData } from '@/testing/testAppData.js'
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

function renderPanel(onChange = vi.fn(), onBack = vi.fn(), isDraft = false, onSave = vi.fn(), backLabel = '← Ergebnisse', t = trip) {
  vi.spyOn(availability, 'fetchAvailabilityByOffset').mockResolvedValue(new Map())
  vi.spyOn(detail, 'fetchHutDetail').mockResolvedValue({ hutId: 1, hutName: '', calendarDays: [] })
  render(
    <TripPanel
      trip={t} tripLegs={legsFromTrip(data.graph, t)} data={data} startLabel={makeStartLabel(data.startById)}
      isDraft={isDraft} onChange={onChange} onSave={onSave} onBack={onBack} onHoverLeg={() => {}} backLabel={backLabel}
    />,
  )
  return { onChange, onBack, onSave }
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
  it('edits date and party size on the trip via the date summary popover', () => {
    const { onChange } = renderPanel()
    fireEvent.click(screen.getByText('10.07.–12.07. · 2 Pers.'))
    fireEvent.change(screen.getByLabelText('Startdatum (erste Nacht)'), { target: { value: '2026-07-12' } })
    expect(onChange).toHaveBeenLastCalledWith({ ...trip, startDate: '2026-07-12' })
    fireEvent.change(screen.getByLabelText('Personen'), { target: { value: '4' } })
    expect(onChange).toHaveBeenLastCalledWith({ ...trip, partySize: 4 })
  })
  it('renames a saved trip', () => {
    const { onChange } = renderPanel()
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Neu' } })
    expect(onChange).toHaveBeenLastCalledWith({ ...trip, name: 'Neu' })
  })
  it('sliding the start date moves the whole trip by a day', () => {
    const { onChange } = renderPanel()
    fireEvent.click(screen.getByRole('button', { name: '+1 Tag' }))
    expect(onChange).toHaveBeenLastCalledWith({ ...trip, startDate: '2026-07-11' })
  })
  it('shows an Entwurf badge and Speichern button, no name field, while a draft', () => {
    renderPanel(vi.fn(), vi.fn(), true)
    expect(screen.getByText('Entwurf')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Speichern' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Name')).not.toBeInTheDocument()
  })
  it('calls onSave when Speichern is clicked', () => {
    const { onSave } = renderPanel(vi.fn(), vi.fn(), true)
    fireEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    expect(onSave).toHaveBeenCalled()
  })
  it('shows the editable name field, no badge, for a saved trip', () => {
    renderPanel(vi.fn(), vi.fn(), false)
    expect(screen.getByLabelText('Name')).toBeInTheDocument()
    expect(screen.queryByText('Entwurf')).not.toBeInTheDocument()
  })
  it('renders endpointControls above the stage list and extendControls below it', () => {
    vi.spyOn(availability, 'fetchAvailabilityByOffset').mockResolvedValue(new Map())
    vi.spyOn(detail, 'fetchHutDetail').mockResolvedValue({ hutId: 1, hutName: '', calendarDays: [] })
    render(
      <TripPanel
        trip={trip} tripLegs={legsFromTrip(data.graph, trip)} data={data} startLabel={makeStartLabel(data.startById)}
        isDraft={false} onChange={vi.fn()} onSave={vi.fn()} onBack={vi.fn()} onHoverLeg={() => {}} backLabel="← Ergebnisse"
        endpointControls={<span data-testid="ep" />} extendControls={<span data-testid="ex" />}
      />,
    )
    const ep = screen.getByTestId('ep')
    const ex = screen.getByTestId('ex')
    expect(ep.compareDocumentPosition(ex) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })
  it('renders the caller-supplied back label', () => {
    renderPanel(vi.fn(), vi.fn(), false, vi.fn(), '← Meine Touren')
    expect(screen.getByRole('button', { name: '← Meine Touren' })).toBeInTheDocument()
  })
  it('a notes field calls onChange with updated notes', () => {
    const onChange = vi.fn()
    renderPanel(onChange)
    fireEvent.change(screen.getByLabelText('Notizen'), { target: { value: 'Wetter prüfen' } })
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ notes: 'Wetter prüfen' }))
  })
  it('the night-status toggle calls onChange with the updated night', () => {
    const onChange = vi.fn()
    const oneNightTrip = newTrip({
      name: 'Eine Nacht', startDate: '2026-07-10', partySize: 2, start: { startId: 100, sourceType: 1 }, huts: ['{D}'],
      exit: { startId: 100, sourceType: 1 }, variant: { sacCeiling: null, allowUngraded: false },
    }, new Date(), 'id2')
    renderPanel(onChange, vi.fn(), false, vi.fn(), '← Ergebnisse', oneNightTrip)
    fireEvent.click(screen.getByLabelText('Buchungsstatus Nacht 1'))
    fireEvent.click(screen.getByRole('button', { name: 'bestätigt' }))
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ nights: expect.arrayContaining([expect.objectContaining({ status: 'confirmed' })]) }))
  })
})
