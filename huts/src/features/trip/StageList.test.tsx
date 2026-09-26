// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import StageList from './StageList.js'
import { makeTestAppData } from '@/testing/testAppData.js'
import { makeEditorStub } from '@/testing/editorStub.js'
import { legsFromTrip } from '@/trip/tripLegs.js'
import { newTrip } from '@/trip/trip.js'
import { makeStartLabel } from '@/data/labels.js'

afterEach(cleanup)

const data = makeTestAppData()
const trip = (huts: string[], startDate: string | null = '2026-07-10') => newTrip({
  name: 't', startDate, partySize: 2, start: { startId: 100, sourceType: 1 }, huts,
  exit: { startId: 100, sourceType: 1 }, variant: { sacCeiling: null, allowUngraded: false },
}, new Date(), 'id')

function renderList(t = trip(['{D}', '{E}']), overrides: Partial<Parameters<typeof StageList>[0]> = {}) {
  const props = {
    trip: t, tripLegs: legsFromTrip(data.graph, t), hutNameById: data.hutNameById, hutOhrsByIndex: data.hutOhrsByIndex,
    startLabel: makeStartLabel(data.startById), nightViews: null, highlightedLeg: null, onHoverLeg: vi.fn(),
    editor: makeEditorStub(), editMode: false, onEditModeChange: vi.fn(), onNightStatusChange: vi.fn(), ...overrides,
  }
  const view = render(<StageList {...props} />)
  return { ...props, container: view.container }
}

describe('StageList view mode', () => {
  it('lists the start, one row per night and the descent, with signpost-style times', () => {
    renderList(trip(['{A}']))
    expect(screen.getByText('Start: Bahnhof X')).toBeInTheDocument()
    expect(screen.getByText('Hütte A')).toBeInTheDocument()
    expect(screen.getByText('Abstieg nach Bahnhof X')).toBeInTheDocument()
    expect(screen.getAllByText(/Std$/).length).toBe(2)
  })
  it('names a car trip descent "Abstieg zum Start"', () => {
    renderList(trip(['{A}']), { editor: makeEditorStub({ car: true }) })
    expect(screen.getByText('Abstieg zum Start')).toBeInTheDocument()
  })
  it('shows date, ascent/descent and booking status on line 2', () => {
    renderList(trip(['{D}']))
    expect(screen.getByText(/10\.07\./)).toBeInTheDocument()
    expect(screen.getByText('offen')).toBeInTheDocument()
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
  it('marks a night that no longer resolves with the outline and the notice, and does not expand it', () => {
    const { container } = renderList(trip(['{A}', '{GONE}']))
    expect(screen.getByText('Seit dem Speichern geändert – nicht mehr im Wegenetz')).toBeInTheDocument()
    expect(container.querySelectorAll('[data-variant="outline"]').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByLabelText('Details Etappe 1')).toBeInTheDocument()
    expect(screen.queryByLabelText('Details Etappe 2')).not.toBeInTheDocument()
  })
  it('hides booking detail until the chevron expands it, then shows link and status toggle', () => {
    renderList(trip(['{D}', '{E}']))
    expect(screen.queryByRole('link', { name: 'Auf hut-reservation.org buchen' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Buchungsstatus Nacht 1')).not.toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Details Etappe 1'))
    expect(screen.getByRole('link', { name: 'Auf hut-reservation.org buchen' })).toBeInTheDocument()
    expect(screen.getByLabelText('Buchungsstatus Nacht 1')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Details Etappe 1'))
    expect(screen.queryByLabelText('Buchungsstatus Nacht 1')).not.toBeInTheDocument()
  })
  it('links a bookable hut for its own night and tells about direct-booking huts', () => {
    renderList(trip(['{A}', '{B}', '{C}', '{D}']))
    fireEvent.click(screen.getByLabelText('Details Etappe 4'))
    expect(screen.getByRole('link', { name: 'Auf hut-reservation.org buchen' })).toHaveAttribute('href', expect.stringContaining('/103/wizard?dateFrom=13.07.2026&dateTo=14.07.2026'))
    fireEvent.click(screen.getByLabelText('Details Etappe 1'))
    expect(screen.getByText(/Direktbuchung/)).toBeInTheDocument()
  })
  it('an undated trip shows no date, no availability and no booking link, but still expands to the status toggle', () => {
    renderList(trip(['{D}'], null), { nightViews: [{ loading: false, availability: { kind: 'free', places: 3 } }] })
    expect(screen.queryByText(/Plätze frei/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Details Etappe 1'))
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Buchungsstatus Nacht 1')).toBeInTheDocument()
  })
  it('reports a status change from the expanded detail', () => {
    const { onNightStatusChange } = renderList(trip(['{D}']))
    fireEvent.click(screen.getByLabelText('Details Etappe 1'))
    fireEvent.click(screen.getByRole('button', { name: 'bestätigt' }))
    expect(onNightStatusChange).toHaveBeenCalledWith(0, 'confirmed')
  })
  it('shows overlap warnings under the exit row', () => {
    renderList(trip(['{D}']), { warnings: ['Überschneidung mit Tour X'] })
    expect(screen.getByRole('alert')).toHaveTextContent('Überschneidung mit Tour X')
  })
})

describe('StageList hover', () => {
  it('a stage row hovers its own leg, the descent row hovers the last leg, the start row nothing', () => {
    const { onHoverLeg, container } = renderList(trip(['{D}', '{E}']))
    fireEvent.mouseEnter(screen.getByText('Hütte E').closest('[data-stage]')!)
    expect(onHoverLeg).toHaveBeenLastCalledWith(1)
    fireEvent.mouseLeave(screen.getByText('Hütte E').closest('[data-stage]')!)
    expect(onHoverLeg).toHaveBeenLastCalledWith(null)
    fireEvent.mouseEnter(container.querySelector('[data-stage="exit"]')!)
    expect(onHoverLeg).toHaveBeenLastCalledWith(2)
    vi.mocked(onHoverLeg).mockClear()
    fireEvent.mouseEnter(screen.getByText('Start: Bahnhof X'))
    expect(onHoverLeg).not.toHaveBeenCalled()
  })
  it('marks the row of the highlighted leg', () => {
    const { container } = renderList(trip(['{D}', '{E}']), { highlightedLeg: 1 })
    expect(container.querySelector('[data-stage="1"]')).toHaveAttribute('data-highlighted', 'true')
    expect(container.querySelector('[data-stage="0"]')).toHaveAttribute('data-highlighted', 'false')
    expect(container.querySelector('[data-stage="exit"]')).toHaveAttribute('data-highlighted', 'false')
  })
  it('marks the descent row when the last leg is highlighted', () => {
    const { container } = renderList(trip(['{D}', '{E}']), { highlightedLeg: 2 })
    expect(container.querySelector('[data-stage="exit"]')).toHaveAttribute('data-highlighted', 'true')
  })
})

describe('StageList edit mode', () => {
  it('the toggle reads Bearbeiten / Fertig and reports the change', () => {
    const { onEditModeChange } = renderList()
    fireEvent.click(screen.getByRole('button', { name: 'Bearbeiten' }))
    expect(onEditModeChange).toHaveBeenCalledWith(true)
    cleanup()
    const on = renderList(trip(['{D}', '{E}']), { editMode: true })
    fireEvent.click(screen.getByRole('button', { name: 'Fertig' }))
    expect(on.onEditModeChange).toHaveBeenCalledWith(false)
  })
  it('shows swap, remove, extend and change controls and no chevrons', () => {
    renderList(trip(['{D}', '{E}']), { editMode: true })
    expect(screen.getByLabelText('Hütte tauschen Etappe 1')).toBeInTheDocument()
    expect(screen.getByLabelText('Hütte entfernen Etappe 2')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '+ Etappe voranstellen' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '+ Etappe anhängen' })).toBeInTheDocument()
    expect(screen.getByLabelText('Start ändern')).toBeInTheDocument()
    expect(screen.getByLabelText('Ziel ändern')).toBeInTheDocument()
    expect(screen.queryByLabelText('Details Etappe 1')).not.toBeInTheDocument()
  })
  it('a car trip cannot change its exit', () => {
    renderList(trip(['{D}']), { editMode: true, editor: makeEditorStub({ car: true }) })
    expect(screen.queryByLabelText('Ziel ändern')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Start ändern')).toBeInTheDocument()
  })
  it('offers no edit controls while the trip cannot be edited', () => {
    renderList(trip(['{A}', '{GONE}']), { editMode: true, editor: makeEditorStub({ editable: false }) })
    expect(screen.queryByLabelText(/Hütte tauschen/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Etappe voranstellen/ })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Start ändern')).not.toBeInTheDocument()
  })
  it('the buttons start the matching editor action', () => {
    const editor = makeEditorStub()
    renderList(trip(['{D}', '{E}']), { editMode: true, editor })
    fireEvent.click(screen.getByLabelText('Hütte tauschen Etappe 2'))
    expect(editor.startSwap).toHaveBeenCalledWith(1)
    fireEvent.click(screen.getByLabelText('Hütte entfernen Etappe 1'))
    expect(editor.trim).toHaveBeenCalledWith(0)
    fireEvent.click(screen.getByRole('button', { name: '+ Etappe voranstellen' }))
    expect(editor.startExtend).toHaveBeenCalledWith('first')
    fireEvent.click(screen.getByRole('button', { name: '+ Etappe anhängen' }))
    expect(editor.startExtend).toHaveBeenCalledWith('last')
    fireEvent.click(screen.getByLabelText('Start ändern'))
    expect(editor.startEndpoint).toHaveBeenCalledWith('start')
    fireEvent.click(screen.getByLabelText('Ziel ändern'))
    expect(editor.startEndpoint).toHaveBeenCalledWith('exit')
  })
  it('a disallowed remove is disabled and shows its reason', () => {
    const editor = makeEditorStub({ trimAllowed: (n) => (n === 1 ? { ok: false, reason: 'Keine direkte Verbindung.' } : { ok: true }) })
    renderList(trip(['{D}', '{E}']), { editMode: true, editor })
    expect(screen.getByLabelText('Hütte entfernen Etappe 2')).toBeDisabled()
    expect(screen.getByLabelText('Hütte entfernen Etappe 1')).toBeEnabled()
    expect(screen.getByLabelText('Keine direkte Verbindung.')).toBeInTheDocument()
  })
  it('shows a swap candidate list only under the swapped row and picks from it', () => {
    const editor = makeEditorStub({ editing: { kind: 'swap', index: 0 }, candidates: [{ hutIndex: 5, legInH: 2, legOutH: 3 }] })
    const { container } = renderList(trip(['{D}', '{E}']), { editMode: true, editor })
    const first = container.querySelector('[data-stage="0"]')!
    const second = container.querySelector('[data-stage="1"]')!
    expect(first).toHaveTextContent('Hütte X')
    expect(second).not.toHaveTextContent('Hütte X')
    fireEvent.click(screen.getByRole('button', { name: /Hütte X/ }))
    expect(editor.pickCandidate).toHaveBeenCalledWith({ hutIndex: 5, startId: undefined })
  })
  it('shows start, extend and exit candidate lists under the row that started the edit', () => {
    const list = { candidates: [{ startId: 101, legH: 1 }] }
    const { container } = renderList(trip(['{D}']), { editMode: true, editor: makeEditorStub({ editing: { kind: 'start' }, ...list }) })
    expect(container.querySelector('[data-stage="0"]')).not.toHaveTextContent('Bahnhof Y')
    expect(screen.getByRole('button', { name: /Bahnhof Y/ })).toBeInTheDocument()
    cleanup()
    const exit = renderList(trip(['{D}']), { editMode: true, editor: makeEditorStub({ editing: { kind: 'exit' }, ...list }) })
    expect(exit.container.querySelector('[data-stage="exit"]')).toHaveTextContent('Bahnhof Y')
    cleanup()
    const extend = renderList(trip(['{D}']), { editMode: true, editor: makeEditorStub({ editing: { kind: 'extend', side: 'last' }, candidates: [{ hutIndex: 5, legH: 1 }] }) })
    expect(screen.getByRole('button', { name: /Hütte X/ })).toBeInTheDocument()
    expect(extend.container.querySelector('[data-stage="exit"]')).not.toHaveTextContent('Hütte X')
  })

  it('collapses expanded rows when the edit-mode toggle is pressed', () => {
    const t = trip(['{D}', '{E}'])
    const props = {
      trip: t, tripLegs: legsFromTrip(data.graph, t), hutNameById: data.hutNameById, hutOhrsByIndex: data.hutOhrsByIndex,
      startLabel: makeStartLabel(data.startById), nightViews: null, highlightedLeg: null, onHoverLeg: vi.fn(),
      editor: makeEditorStub(), editMode: false, onEditModeChange: vi.fn(), onNightStatusChange: vi.fn(),
    }
    const { rerender } = render(<StageList {...props} />)
    fireEvent.click(screen.getByLabelText('Details Etappe 1'))
    fireEvent.click(screen.getByRole('button', { name: 'Bearbeiten' }))
    rerender(<StageList {...props} editMode={false} />)
    expect(screen.queryByLabelText('Buchungsstatus Nacht 1')).not.toBeInTheDocument()
  })
})
