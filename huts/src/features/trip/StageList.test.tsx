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
    editor: makeEditorStub(), editMode: false, onEditModeChange: vi.fn(), ...overrides,
  }
  const view = render(<StageList {...props} />)
  return { ...props, container: view.container }
}

describe('StageList view mode', () => {
  it('lists start, leg, hut, exit leg and destination in timeline order, with signpost-style times', () => {
    const { container } = renderList(trip(['{A}']))
    const order = [...container.querySelectorAll('[data-node], [data-leg], [data-night]')]
      .map((el) => el.getAttribute('data-node') ?? (el.hasAttribute('data-leg') ? `leg${el.getAttribute('data-leg')}` : `night${el.getAttribute('data-night')}`))
    expect(order).toEqual(['start', 'leg0', 'night0', 'leg1', 'exit'])
    expect(screen.getByText('Start: Bahnhof X')).toBeInTheDocument()
    expect(screen.getByText('Hütte A')).toBeInTheDocument()
    expect(screen.getByText('Ziel: Bahnhof X')).toBeInTheDocument()
    expect(screen.getAllByText(/Std$/).length).toBe(2)
  })
  it('draws the map symbols on the rail: start and exit by their type, a hut per night', () => {
    const { container } = renderList(trip(['{A}', '{B}']))
    expect([...container.querySelectorAll('[data-stop]')].map((el) => el.getAttribute('data-stop'))).toEqual(['end', 'hut', 'hut', 'end'])
  })
  it('names a car trip destination "Zurück am Start"', () => {
    renderList(trip(['{A}']), { editor: makeEditorStub({ car: true }) })
    expect(screen.getByText('Zurück am Start')).toBeInTheDocument()
  })
  it('shows the date of each night next to the hut', () => {
    renderList(trip(['{D}']))
    expect(screen.getByText(/10\.07\./)).toBeInTheDocument()
  })
  it('shows availability with shape and text once night views exist, "unknown" distinct from "full"', () => {
    renderList(trip(['{D}', '{E}']), {
      nightViews: [
        { loading: false, availability: { kind: 'free', places: 12 } },
        { loading: false, availability: { kind: 'unknown' } },
      ],
    })
    expect(screen.getByText('12 Plätze frei')).toBeInTheDocument()
    expect(screen.getByText('Plätze unbekannt')).toBeInTheDocument()
    expect(screen.queryByText('ausgebucht')).not.toBeInTheDocument()
  })
  it('marks a night that no longer resolves with an outlined hut symbol and the notice, without a booking link', () => {
    const { container } = renderList(trip(['{D}', '{GONE}']), {
      nightViews: [{ loading: false, availability: { kind: 'free', places: 3 } }, { loading: false, availability: { kind: 'unknown' } }],
    })
    expect(screen.getByText('Seit dem Speichern geändert – nicht mehr im Wegenetz')).toBeInTheDocument()
    expect(container.querySelectorAll('[data-variant="outline"]').length).toBeGreaterThanOrEqual(1)
    const fills = [...container.querySelectorAll('[data-stop="hut"] polygon')].map((el) => el.getAttribute('fill'))
    expect(new Set(fills).size).toBe(2)
    expect(container.querySelector('[data-night="1"]')!.querySelector('a')).toBeNull()
  })
  it('shows the booking link inline next to the availability of each dated bookable night', () => {
    const { container } = renderList(trip(['{A}', '{B}', '{C}', '{D}']), {
      nightViews: [0, 1, 2, 3].map(() => ({ loading: false, availability: { kind: 'free', places: 5 } })),
    })
    const night3 = container.querySelector('[data-night="3"]')!
    expect(night3.querySelector('a')).toHaveAttribute('href', expect.stringContaining('/103/wizard?dateFrom=13.07.2026&dateTo=14.07.2026'))
    expect(night3).toHaveTextContent('5 Plätze frei')
  })
  it('names a direct-booking hut instead of its unknowable availability, without a link', () => {
    const { container } = renderList(trip(['{A}']), { nightViews: [{ loading: false, availability: { kind: 'unknown' } }] })
    const night = container.querySelector('[data-night="0"]')!
    expect(night).toHaveTextContent('Direktbuchung – Hütte kontaktieren')
    expect(night).not.toHaveTextContent('Plätze unbekannt')
    expect(night.querySelector('a')).toBeNull()
  })
  it('an undated trip shows no date, no availability and no booking link', () => {
    renderList(trip(['{D}'], null), { nightViews: [{ loading: false, availability: { kind: 'free', places: 3 } }] })
    expect(screen.queryByText(/Plätze frei/)).not.toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })
  it('shows overlap warnings under the timeline', () => {
    renderList(trip(['{D}']), { warnings: ['Überschneidung mit Tour X'] })
    expect(screen.getByRole('alert')).toHaveTextContent('Überschneidung mit Tour X')
  })
})

describe('StageList hover', () => {
  it('a highlighted leg lights its whole rail from stop to stop, nothing else', () => {
    const { container } = renderList(trip(['{D}', '{E}']), { highlightedLeg: 1 })
    const row = (i: number) => container.querySelector(`[data-night="${i}"]`)!.parentElement!.parentElement!
    const night = (i: number, part: string) => row(i).querySelector(`[data-rail="${part}"]`)!
    expect(night(0, 'below')).toHaveAttribute('data-highlighted', 'true')
    expect(container.querySelector('[data-leg="1"] [data-rail="below"]')).toHaveAttribute('data-highlighted', 'true')
    expect(night(1, 'above')).toHaveAttribute('data-highlighted', 'true')
    expect(night(0, 'above')).toHaveAttribute('data-highlighted', 'false')
    expect(night(1, 'below')).toHaveAttribute('data-highlighted', 'false')
    expect(container.querySelectorAll('[data-rail][data-highlighted="true"]').length).toBe(3)
  })
  it('each leg row hovers its own leg; huts and endpoints hover nothing', () => {
    const { onHoverLeg, container } = renderList(trip(['{D}', '{E}']))
    fireEvent.mouseEnter(container.querySelector('[data-leg="1"]')!)
    expect(onHoverLeg).toHaveBeenLastCalledWith(1)
    fireEvent.mouseLeave(container.querySelector('[data-leg="1"]')!)
    expect(onHoverLeg).toHaveBeenLastCalledWith(null)
    fireEvent.mouseEnter(container.querySelector('[data-leg="2"]')!)
    expect(onHoverLeg).toHaveBeenLastCalledWith(2)
    vi.mocked(onHoverLeg).mockClear()
    fireEvent.mouseEnter(container.querySelector('[data-night="0"]')!)
    fireEvent.mouseEnter(container.querySelector('[data-node="start"]')!)
    fireEvent.mouseEnter(container.querySelector('[data-node="exit"]')!)
    expect(onHoverLeg).not.toHaveBeenCalled()
  })
  it('marks the highlighted leg, including the exit leg', () => {
    const { container } = renderList(trip(['{D}', '{E}']), { highlightedLeg: 1 })
    expect(container.querySelector('[data-leg="1"]')).toHaveAttribute('data-highlighted', 'true')
    expect(container.querySelector('[data-leg="0"]')).toHaveAttribute('data-highlighted', 'false')
    cleanup()
    const exit = renderList(trip(['{D}', '{E}']), { highlightedLeg: 2 })
    expect(exit.container.querySelector('[data-leg="2"]')).toHaveAttribute('data-highlighted', 'true')
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
  it('shows swap, remove, extend and change controls and no booking links', () => {
    renderList(trip(['{D}', '{E}']), {
      editMode: true, nightViews: [0, 1].map(() => ({ loading: false, availability: { kind: 'free', places: 5 } })),
    })
    expect(screen.getByLabelText('Hütte tauschen Etappe 1')).toBeInTheDocument()
    expect(screen.getByLabelText('Hütte entfernen Etappe 2')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '+ Etappe voranstellen' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '+ Etappe anhängen' })).toBeInTheDocument()
    expect(screen.getByLabelText('Start ändern')).toBeInTheDocument()
    expect(screen.getByLabelText('Ziel ändern')).toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
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
    const first = container.querySelector('[data-night="0"]')!
    const second = container.querySelector('[data-night="1"]')!
    expect(first).toHaveTextContent('Hütte X')
    expect(second).not.toHaveTextContent('Hütte X')
    fireEvent.click(screen.getByRole('button', { name: /Hütte X/ }))
    expect(editor.pickCandidate).toHaveBeenCalledWith({ hutIndex: 5, startId: undefined })
  })
  it('shows start, extend and exit candidate lists under the control that started the edit', () => {
    const list = { candidates: [{ startId: 101, legH: 1 }] }
    const { container } = renderList(trip(['{D}']), { editMode: true, editor: makeEditorStub({ editing: { kind: 'start' }, ...list }) })
    expect(container.querySelector('[data-night="0"]')).not.toHaveTextContent('Bahnhof Y')
    expect(screen.getByRole('button', { name: /Bahnhof Y/ })).toBeInTheDocument()
    cleanup()
    const exit = renderList(trip(['{D}']), { editMode: true, editor: makeEditorStub({ editing: { kind: 'exit' }, ...list }) })
    expect(exit.container.querySelector('[data-node="exit"]')!.parentElement).toHaveTextContent('Bahnhof Y')
    cleanup()
    const extend = renderList(trip(['{D}']), { editMode: true, editor: makeEditorStub({ editing: { kind: 'extend', side: 'last' }, candidates: [{ hutIndex: 5, legH: 1 }] }) })
    expect(screen.getByRole('button', { name: /Hütte X/ })).toBeInTheDocument()
    expect(extend.container.querySelector('[data-node="exit"]')!.parentElement).not.toHaveTextContent('Hütte X')
  })

})
