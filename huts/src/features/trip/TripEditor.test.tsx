// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook, cleanup } from '@testing-library/react'
import { useTripEditor } from './TripEditor.js'
import type { TripEditorProps } from './TripEditor.js'
import { makeTestAppData } from '@/testing/testAppData.js'
import { legsFromTrip } from '@/trip/tripLegs.js'
import { newTrip } from '@/trip/trip.js'

afterEach(cleanup)

const data = makeTestAppData()
const trip = newTrip({
  name: 't', startDate: null, partySize: 1, start: { startId: 100, sourceType: 1 }, huts: ['{A}', '{B}', '{C}', '{D}'],
  exit: { startId: 100, sourceType: 1 }, variant: { sacCeiling: null, allowUngraded: false },
}, new Date(), 'id')

const defaultProps: TripEditorProps = {
  graph: data.graph, trip, tripLegs: legsFromTrip(data.graph, trip), editing: null, onEditing: () => {}, onChange: () => {},
}

describe('useTripEditor', () => {
  it('offers nothing while trip or legs are null', () => {
    const onChange = vi.fn()
    const { result } = renderHook(() => useTripEditor({ ...defaultProps, trip: null, tripLegs: null, editing: { kind: 'swap', index: 1 }, onChange }))
    expect(result.current.candidates).toEqual([])
    expect(result.current.activeLabel).toBeNull()
    expect(result.current.editable).toBe(false)
    expect(result.current.trimAllowed(0).ok).toBe(false)
    result.current.pickCandidate({ hutIndex: 1 })
    result.current.trim(0)
    expect(onChange).not.toHaveBeenCalled()
  })

  it('is editable when every night resolves and reports the trip mode', () => {
    const { result } = renderHook(() => useTripEditor(defaultProps))
    expect(result.current.editable).toBe(true)
    expect(result.current.car).toBe(false)
  })

  it('is not editable while a night no longer resolves', () => {
    const broken = { ...trip, huts: ['{A}', '{GONE}'] }
    const { result } = renderHook(() => useTripEditor({ ...defaultProps, trip: broken, tripLegs: legsFromTrip(data.graph, broken) }))
    expect(result.current.editable).toBe(false)
  })

  it('trimAllowed carries the reason when a hut cannot be removed', () => {
    const { result } = renderHook(() => useTripEditor(defaultProps))
    expect(result.current.trimAllowed(1).ok).toBe(true)
    const blocked = result.current.trimAllowed(2)
    expect(blocked).toEqual({ ok: false, reason: 'Keine direkte Verbindung zwischen den Nachbarhütten.' })
  })

  it('trim applies applyTrim', () => {
    const onChange = vi.fn()
    const { result } = renderHook(() => useTripEditor({ ...defaultProps, onChange }))
    result.current.trim(1)
    expect(onChange.mock.calls[0][0].huts).toEqual(['{A}', '{C}', '{D}'])
  })

  it('start actions set the editing state, cancel clears it', () => {
    const onEditing = vi.fn()
    const { result } = renderHook(() => useTripEditor({ ...defaultProps, onEditing }))
    result.current.startSwap(2)
    expect(onEditing).toHaveBeenLastCalledWith({ kind: 'swap', index: 2 })
    result.current.startExtend('first')
    expect(onEditing).toHaveBeenLastCalledWith({ kind: 'extend', side: 'first' })
    result.current.startEndpoint('exit')
    expect(onEditing).toHaveBeenLastCalledWith({ kind: 'exit' })
    result.current.cancel()
    expect(onEditing).toHaveBeenLastCalledWith(null)
  })

  it('a swap edit lists candidates and picking one applies applySwap and ends the edit', () => {
    const onChange = vi.fn()
    const onEditing = vi.fn()
    const { result } = renderHook(() => useTripEditor({ ...defaultProps, onChange, onEditing, editing: { kind: 'swap', index: 1 } }))
    // Stage 1 (B) in [A,B,C,D]: prev A, next C -> X (index 5) qualifies.
    expect(result.current.candidates.map((c) => c.hutIndex)).toContain(5)
    result.current.pickCandidate({ hutIndex: 5 })
    expect(onChange.mock.calls[0][0].huts).toEqual(['{A}', '{X}', '{C}', '{D}'])
    expect(onEditing).toHaveBeenLastCalledWith(null)
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
})
