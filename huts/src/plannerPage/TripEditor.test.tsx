// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { useTripEditor } from './TripEditor.js'
import type { EditingState } from './TripEditor.js'
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

function Harness({ editing, onEditing, onChange }: { editing: EditingState; onEditing: (e: EditingState) => void; onChange: (t: typeof trip) => void }) {
  const editor = useTripEditor({
    graph: data.graph, trip, tripLegs: legsFromTrip(data.graph, trip), hutNameById: data.hutNameById,
    startLabel: makeStartLabel(data.startById), editing, onEditing, onChange,
  })
  return (
    <div>
      {trip.huts.map((_, i) => <div key={i}>{editor.renderStageControls(i)}</div>)}
      {editor.extra}
      <output data-testid="candidates">{editor.candidates.map((c) => c.hutIndex).join(',')}</output>
    </div>
  )
}

describe('useTripEditor', () => {
  it('offers swap and remove per stage; removal is disabled with its reason when the neighbours are not linked', () => {
    render(<Harness editing={null} onEditing={() => {}} onChange={() => {}} />)
    expect(screen.getAllByRole('button', { name: 'Hütte tauschen' })).toHaveLength(4)
    const remove = screen.getAllByRole('button', { name: 'Hütte entfernen' })
    expect(remove[1]).toBeEnabled() // B: A-C edge exists ... index 1 is hut B
    expect(remove[2]).toBeDisabled() // C: B-D has no edge
    expect(screen.getByText('Keine direkte Verbindung zwischen den Nachbarhütten.')).toBeInTheDocument()
  })
  it('starts a swap for a stage and lists that stage\'s candidates on the map', () => {
    const onEditing = vi.fn()
    render(<Harness editing={null} onEditing={onEditing} onChange={() => {}} />)
    fireEvent.click(screen.getAllByRole('button', { name: 'Hütte tauschen' })[1])
    expect(onEditing).toHaveBeenCalledWith({ kind: 'swap', index: 1 })
  })
  it('with a swap active, candidates are the linked huts and picking one applies the swap', () => {
    const onChange = vi.fn()
    render(<Harness editing={{ kind: 'swap', index: 1 }} onEditing={() => {}} onChange={onChange} />)
    // Stage 1 (B) in [A,B,C,D]: prev A, next C -> X qualifies (index 5).
    expect(screen.getByTestId('candidates')).toHaveTextContent('5')
    fireEvent.click(screen.getByRole('button', { name: /Hütte X/ }))
    expect(onChange.mock.calls[0][0].huts).toEqual(['{A}', '{X}', '{C}', '{D}'])
  })
  it('offers extending at both ends and lists reachable huts while extending', () => {
    const onEditing = vi.fn()
    const { rerender } = render(<Harness editing={null} onEditing={onEditing} onChange={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: 'Etappe anhängen' }))
    expect(onEditing).toHaveBeenCalledWith({ kind: 'extend', side: 'last' })
    rerender(<Harness editing={{ kind: 'extend', side: 'last' }} onEditing={onEditing} onChange={() => {}} />)
    expect(screen.getByTestId('candidates')).toHaveTextContent('4') // E follows D
  })
  it('changes the start point and keeps the exit in transit mode', () => {
    const onChange = vi.fn()
    render(<Harness editing={null} onEditing={() => {}} onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name: 'Start: Bahnhof Y wählen' }))
    expect(onChange.mock.calls[0][0].start.startId).toBe(101)
    expect(onChange.mock.calls[0][0].exit.startId).toBe(100)
  })
  it('cancels an active edit', () => {
    const onEditing = vi.fn()
    render(<Harness editing={{ kind: 'swap', index: 1 }} onEditing={onEditing} onChange={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: 'Abbrechen' }))
    expect(onEditing).toHaveBeenCalledWith(null)
  })
})
