// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import TripPanel from './TripPanel.js'
import { makeTestAppData } from '@/testing/testAppData.js'
import { makeEditorStub } from '@/testing/editorStub.js'
import { legsFromTrip } from '@/trip/tripLegs.js'
import { newTrip } from '@/trip/trip.js'
import { makeStartLabel } from '@/data/labels.js'
import * as availability from '@/availability/fetchAvailability.js'
import * as detail from '@/availability/fetchHutDetail.js'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

const data = makeTestAppData()
const trip = newTrip({
  name: 'Testtour', startDate: '2026-07-10', partySize: 2, start: { startId: 100, sourceType: 1 }, huts: ['{D}', '{E}'],
  exit: { startId: 100, sourceType: 1 }, variant: { sacCeiling: null, allowUngraded: false },
}, new Date(), 'id')

function renderPanel(over: Partial<Parameters<typeof TripPanel>[0]> = {}) {
  vi.spyOn(availability, 'fetchAvailabilityByOffset').mockResolvedValue(new Map())
  vi.spyOn(detail, 'fetchHutDetail').mockResolvedValue({ hutId: 1, hutName: '', calendarDays: [] })
  const t = over.trip ?? trip
  const props = {
    trip: t, tripLegs: legsFromTrip(data.graph, t), data, startLabel: makeStartLabel(data.startById), isDraft: false,
    onChange: vi.fn(), onSave: vi.fn(), onUnsave: vi.fn(), onBack: vi.fn(), backLabel: '← Ergebnisse', highlightedLeg: null, onHoverLeg: vi.fn(),
    editor: makeEditorStub(), editMode: false, onEditModeChange: vi.fn(), ...over,
  }
  render(<TripPanel {...props} />)
  return props
}

describe('TripPanel', () => {
  it('composes header, stages and notes', () => {
    renderPanel()
    expect(screen.getByRole('button', { name: 'Testtour' })).toBeInTheDocument()
    expect(screen.getByText(/2 Nächte/)).toBeInTheDocument()
    expect(screen.getByText('Hütte D')).toBeInTheDocument()
    expect(screen.getByText('Hütte E')).toBeInTheDocument()
    expect(screen.getByLabelText('Notizen')).toBeInTheDocument()
  })
  it('goes back with the caller-supplied label', () => {
    const { onBack } = renderPanel({ backLabel: '← Meine Touren' })
    fireEvent.click(screen.getByRole('button', { name: '← Meine Touren' }))
    expect(onBack).toHaveBeenCalled()
  })
  it('marks a draft nicht gespeichert and saves', () => {
    const { onSave } = renderPanel({ isDraft: true })
    expect(screen.getByText(/^nicht gespeichert ·/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Merken' }))
    fireEvent.click(screen.getByRole('button', { name: 'Merken' }))
    expect(onSave).toHaveBeenCalled()
  })
  it('a notes edit calls onChange with updated notes', () => {
    const { onChange } = renderPanel()
    fireEvent.change(screen.getByLabelText('Notizen'), { target: { value: 'Wetter prüfen' } })
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ notes: 'Wetter prüfen' }))
  })
  it('a night status change calls onChange with the updated night', () => {
    const oneNight = newTrip({
      name: 'Eine Nacht', startDate: '2026-07-10', partySize: 2, start: { startId: 100, sourceType: 1 }, huts: ['{D}'],
      exit: { startId: 100, sourceType: 1 }, variant: { sacCeiling: null, allowUngraded: false },
    }, new Date(), 'id2')
    const { onChange } = renderPanel({ trip: oneNight })
    fireEvent.click(screen.getByLabelText('Details Etappe 1'))
    fireEvent.click(screen.getByRole('button', { name: 'bestätigt' }))
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ nights: [{ status: 'confirmed' }] }))
  })
  it('forwards stage hover and the edit-mode toggle', () => {
    const { onHoverLeg, onEditModeChange } = renderPanel()
    fireEvent.mouseEnter(screen.getByText('Hütte D').closest('[data-stage]')!)
    expect(onHoverLeg).toHaveBeenCalledWith(0)
    fireEvent.click(screen.getByRole('button', { name: 'Bearbeiten' }))
    expect(onEditModeChange).toHaveBeenCalledWith(true)
  })
})
