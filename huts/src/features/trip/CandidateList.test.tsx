// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import CandidateList from './CandidateList.js'
import { makeEditorStub } from '@/testing/editorStub.js'

afterEach(cleanup)

const names = new Map([[5, 'Hütte X']])
const startLabel = (id: number) => (id === 101 ? 'Bahnhof Y' : String(id))

describe('CandidateList', () => {
  it('renders nothing without an active edit', () => {
    const { container } = render(<CandidateList editor={makeEditorStub()} hutNameById={names} startLabel={startLabel} />)
    expect(container).toBeEmptyDOMElement()
  })
  it('lists swap candidates with both leg times, picks one and cancels', () => {
    const editor = makeEditorStub({ editing: { kind: 'swap', index: 1 }, candidates: [{ hutIndex: 5, legInH: 2, legOutH: 3 }] })
    render(<CandidateList editor={editor} hutNameById={names} startLabel={startLabel} />)
    const button = screen.getByRole('button', { name: /Hütte X/ })
    expect(button).toHaveTextContent('2 Std · 3 Std')
    fireEvent.click(button)
    expect(editor.pickCandidate).toHaveBeenCalledWith({ hutIndex: 5, startId: undefined })
    fireEvent.click(screen.getByRole('button', { name: 'Abbrechen' }))
    expect(editor.cancel).toHaveBeenCalled()
  })
  it('lists start candidates by their label with the leg time', () => {
    const editor = makeEditorStub({ editing: { kind: 'start' }, candidates: [{ startId: 101, legH: 1.5 }] })
    render(<CandidateList editor={editor} hutNameById={names} startLabel={startLabel} />)
    fireEvent.click(screen.getByRole('button', { name: /Bahnhof Y/ }))
    expect(editor.pickCandidate).toHaveBeenCalledWith({ hutIndex: undefined, startId: 101 })
  })
  it('says so when there is no candidate, differently for huts and start points', () => {
    const { rerender } = render(<CandidateList editor={makeEditorStub({ editing: { kind: 'extend', side: 'last' } })} hutNameById={names} startLabel={startLabel} />)
    expect(screen.getByText('Keine passende Hütte im Wegenetz.')).toBeInTheDocument()
    rerender(<CandidateList editor={makeEditorStub({ editing: { kind: 'exit' } })} hutNameById={names} startLabel={startLabel} />)
    expect(screen.getByText('Keine Alternative im Wegenetz.')).toBeInTheDocument()
  })
})
