// @vitest-environment jsdom
import { useState } from 'react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, renderHook, screen, fireEvent, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { useTripEditor } from './TripEditor.js'
import type { EditingState, TripEditorProps } from './TripEditor.js'
import { makeTestAppData } from './testAppData.js'
import { legsFromTrip } from '../tourSearch/tripLegs.js'
import { newTrip } from '../trip/trip.js'
import { makeStartLabel } from './labels.js'

afterEach(cleanup)

const data = makeTestAppData()
const trip = newTrip({
  name: 't', startDate: null, partySize: 1, start: { startId: 100, sourceType: 1 }, huts: ['{A}', '{B}', '{C}', '{D}'],
  exit: { startId: 100, sourceType: 1 }, variant: { sacCeiling: null, allowUngraded: false },
}, new Date(), 'id')

const defaultProps: TripEditorProps = {
  graph: data.graph, trip, tripLegs: legsFromTrip(data.graph, trip), hutNameById: data.hutNameById,
  startLabel: makeStartLabel(data.startById), editing: null, onEditing: () => {}, onChange: () => {},
}

function RowMenuHarness({ night, editing, onEditing, onChange }: { night: number; editing: EditingState; onEditing: (e: EditingState) => void; onChange: (t: typeof trip) => void }) {
  const editor = useTripEditor({ ...defaultProps, editing, onEditing, onChange })
  return <>{editor.renderRowMenu(night)}</>
}

describe('useTripEditor', () => {
  it('renderRowMenu offers Hütte tauschen and Hütte entfernen (disabled with reason when not allowed)', () => {
    render(<RowMenuHarness night={2} editing={null} onEditing={() => {}} onChange={() => {}} />)
    fireEvent.click(screen.getByLabelText('Weitere Aktionen Etappe 3'))
    expect(screen.getByText('Hütte tauschen')).toBeInTheDocument()
    // C: B-D has no edge -> disabled with reason appended to the label
    expect(screen.getByText(/Hütte entfernen/)).toHaveTextContent('Keine direkte Verbindung zwischen den Nachbarhütten.')
  })

  it('choosing Hütte tauschen enters swap mode: candidates appear, picking one applies applySwap', () => {
    const onChange = vi.fn()
    function Wrapper() {
      const [editing, setEditing] = useState<EditingState>(null)
      return <RowMenuHarness night={1} editing={editing} onEditing={setEditing} onChange={onChange} />
    }
    render(<Wrapper />)
    fireEvent.click(screen.getByLabelText('Weitere Aktionen Etappe 2'))
    fireEvent.click(screen.getByText('Hütte tauschen'))
    // Stage 1 (B) in [A,B,C,D]: prev A, next C -> X qualifies.
    fireEvent.click(screen.getByRole('button', { name: /Hütte X/ }))
    expect(onChange).toHaveBeenCalled()
    expect(onChange.mock.calls[0][0].huts).toEqual(['{A}', '{X}', '{C}', '{D}'])
  })

  it('renderEndpointMenu("start") offers Anderen Start wählen and lists candidates as buttons', () => {
    const { result } = renderHook(() => useTripEditor({ ...defaultProps, editing: { kind: 'start' } }))
    render(<>{result.current.renderEndpointMenu('start')}</>)
    expect(screen.getByText('Anderen Start wählen')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Bahnhof Y/ })).toBeInTheDocument()
  })

  it('renderExtendButtons offers Etappe voranstellen/anhängen only when the trip fully resolves', () => {
    const { result } = renderHook(() => useTripEditor(defaultProps))
    render(<>{result.current.renderExtendButtons()}</>)
    expect(screen.getByText('Etappe anhängen')).toBeInTheDocument()
    expect(screen.getByText('Etappe voranstellen')).toBeInTheDocument()
  })

  it('start/exit candidates carry startId/sourceType, not hutIndex', () => {
    const { result } = renderHook(() => useTripEditor({ ...defaultProps, editing: { kind: 'exit' } }))
    expect(result.current.candidates.length).toBeGreaterThan(0)
    for (const c of result.current.candidates) {
      expect(c.startId).toBeDefined()
      expect(c.hutIndex).toBeUndefined()
    }
  })

  it('activeLabel names the current candidate mode for the map status bar', () => {
    const { result } = renderHook(() => useTripEditor({ ...defaultProps, editing: { kind: 'swap', index: 1 } }))
    expect(result.current.activeLabel).toBe('Neue Hütte für Etappe 2 wählen')
  })

  it('picking an extend candidate applies applyExtend', () => {
    const onChange = vi.fn()
    const { result } = renderHook(() => useTripEditor({ ...defaultProps, onChange, editing: { kind: 'extend', side: 'last' } }))
    expect(result.current.candidates.length).toBeGreaterThan(0)
    result.current.pickCandidate({ hutIndex: result.current.candidates[0].hutIndex })
    expect(onChange).toHaveBeenCalled()
  })

  it('cancels an active edit', () => {
    const onEditing = vi.fn()
    const { result } = renderHook(() => useTripEditor({ ...defaultProps, onEditing, editing: { kind: 'swap', index: 1 } }))
    render(<>{result.current.renderRowMenu(1)}</>)
    fireEvent.click(screen.getByRole('button', { name: 'Abbrechen' }))
    expect(onEditing).toHaveBeenCalledWith(null)
  })
})
