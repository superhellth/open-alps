// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import StageNode from './StageNode.js'
import type { StageNodeProps } from './StageNode.js'

afterEach(cleanup)

const props = (over: Partial<StageNodeProps> = {}): StageNodeProps => ({
  number: 2, title: 'Hütte B', date: 'Fr., 12.07.', meta: <span>12 Plätze frei</span>, changed: false,
  edit: null, ...over,
})

describe('StageNode', () => {
  it('shows number, title and date in one row, the meta line below, addressed by its 0-based night', () => {
    const { container } = render(<StageNode {...props()} />)
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText('Hütte B').parentElement).toContainElement(screen.getByText('Fr., 12.07.'))
    expect(screen.getByText('12 Plätze frei')).toBeInTheDocument()
    expect(container.querySelector('[data-night="1"]')).not.toBeNull()
  })
  it('has no toggle: the face is static text', () => {
    render(<StageNode {...props()} />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
  it('a changed night is outlined', () => {
    const { container } = render(<StageNode {...props({ changed: true })} />)
    expect(container.querySelector('[data-variant="outline"]')).not.toBeNull()
  })
  it('edit shows swap and remove', () => {
    const onSwap = vi.fn()
    const onTrim = vi.fn()
    render(<StageNode {...props({ edit: { trim: { ok: true }, onSwap, onTrim } })} />)
    fireEvent.click(screen.getByRole('button', { name: 'Hütte tauschen Etappe 2' }))
    fireEvent.click(screen.getByRole('button', { name: 'Hütte entfernen Etappe 2' }))
    expect(onSwap).toHaveBeenCalled()
    expect(onTrim).toHaveBeenCalled()
  })
  it('a disallowed remove is disabled and carries its reason', () => {
    render(<StageNode {...props({ edit: { trim: { ok: false, reason: 'Mindestens eine Hütte muss bleiben.' }, onSwap: () => {}, onTrim: vi.fn() } })} />)
    expect(screen.getByRole('button', { name: 'Hütte entfernen Etappe 2' })).toBeDisabled()
    expect(screen.getByLabelText('Mindestens eine Hütte muss bleiben.')).toBeInTheDocument()
  })
})
