// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import StageRow from './StageRow.js'
import type { StageRowProps } from './StageRow.js'

afterEach(cleanup)

const props = (over: Partial<StageRowProps> = {}): StageRowProps => ({
  number: 2, title: 'Hütte B', timeH: 5.5, meta: <span>Fr 12.07.</span>, changed: false, highlighted: false, editMode: false,
  expanded: false, onToggleExpanded: () => {}, onHover: () => {}, edit: null, ...over,
})

describe('StageRow', () => {
  it('shows number, title, signpost time and the meta line', () => {
    render(<StageRow {...props()} />)
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText('Hütte B')).toBeInTheDocument()
    expect(screen.getByText('5½ Std')).toBeInTheDocument()
    expect(screen.getByText('Fr 12.07.')).toBeInTheDocument()
  })
  it('is addressed by its 0-based leg index and reports hover enter and leave', () => {
    const onHover = vi.fn()
    const { container } = render(<StageRow {...props({ onHover })} />)
    const row = container.querySelector('[data-stage="1"]')!
    fireEvent.mouseEnter(row)
    expect(onHover).toHaveBeenLastCalledWith(true)
    fireEvent.mouseLeave(row)
    expect(onHover).toHaveBeenLastCalledWith(false)
  })
  it('marks the highlighted row', () => {
    const { container } = render(<StageRow {...props({ highlighted: true })} />)
    expect(container.querySelector('[data-stage="1"]')).toHaveAttribute('data-highlighted', 'true')
  })
  it('toggles the details with the chevron and shows children when expanded', () => {
    const onToggleExpanded = vi.fn()
    const { rerender } = render(<StageRow {...props({ onToggleExpanded })}><span>Buchung</span></StageRow>)
    const chevron = screen.getByRole('button', { name: 'Details Etappe 2' })
    expect(chevron).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(chevron)
    expect(onToggleExpanded).toHaveBeenCalled()
    rerender(<StageRow {...props({ expanded: true })}><span>Buchung</span></StageRow>)
    expect(screen.getByRole('button', { name: 'Details Etappe 2' })).toHaveAttribute('aria-expanded', 'true')
  })
  it('a changed night is outlined and has no chevron', () => {
    const { container } = render(<StageRow {...props({ changed: true, timeH: undefined })} />)
    expect(container.querySelector('[data-variant="outline"]')).not.toBeNull()
    expect(screen.queryByRole('button', { name: 'Details Etappe 2' })).not.toBeInTheDocument()
  })
  it('edit mode hides the chevron and shows swap and remove', () => {
    const onSwap = vi.fn()
    const onTrim = vi.fn()
    render(<StageRow {...props({ editMode: true, edit: { trim: { ok: true }, onSwap, onTrim } })} />)
    expect(screen.queryByRole('button', { name: 'Details Etappe 2' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Hütte tauschen Etappe 2' }))
    fireEvent.click(screen.getByRole('button', { name: 'Hütte entfernen Etappe 2' }))
    expect(onSwap).toHaveBeenCalled()
    expect(onTrim).toHaveBeenCalled()
  })
  it('a disallowed remove is disabled and carries its reason', () => {
    const onTrim = vi.fn()
    render(<StageRow {...props({ editMode: true, edit: { trim: { ok: false, reason: 'Mindestens eine Hütte muss bleiben.' }, onSwap: () => {}, onTrim } })} />)
    const remove = screen.getByRole('button', { name: 'Hütte entfernen Etappe 2' })
    expect(remove).toBeDisabled()
    expect(screen.getByLabelText('Mindestens eine Hütte muss bleiben.')).toBeInTheDocument()
  })
})
