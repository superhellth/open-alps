// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import PartySizeStepper, { MAX_PARTY_SIZE } from './PartySizeStepper.js'

afterEach(cleanup)

describe('PartySizeStepper', () => {
  it('steps the party size by one', () => {
    const onChange = vi.fn()
    render(<PartySizeStepper value={2} onChange={onChange} />)
    expect(screen.getByText('2 Pers.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Eine Person mehr' }))
    expect(onChange).toHaveBeenLastCalledWith(3)
    fireEvent.click(screen.getByRole('button', { name: 'Eine Person weniger' }))
    expect(onChange).toHaveBeenLastCalledWith(1)
  })
  it('clamps at 1 and the maximum', () => {
    const { rerender } = render(<PartySizeStepper value={1} onChange={() => {}} />)
    expect(screen.getByRole('button', { name: 'Eine Person weniger' })).toBeDisabled()
    rerender(<PartySizeStepper value={MAX_PARTY_SIZE} onChange={() => {}} />)
    expect(screen.getByRole('button', { name: 'Eine Person mehr' })).toBeDisabled()
  })
})
