// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import StageLeg from './StageLeg.js'
import type { Leg } from '@/tourSearch/types.js'

afterEach(cleanup)

const leg = { durationH: 5.5, distanceM: 8300, ascentM: 900, descentM: 120 } as Leg

describe('StageLeg', () => {
  it('shows signpost time, distance and ascent/descent', () => {
    render(<StageLeg index={0} leg={leg} highlighted={false} onHover={() => {}} />)
    expect(screen.getByText('5½ Std')).toBeInTheDocument()
    expect(screen.getByText('8.3 km')).toBeInTheDocument()
    expect(screen.getByText(/↑ 900/)).toBeInTheDocument()
    expect(screen.getByText(/↓ 120/)).toBeInTheDocument()
  })
  it('reports its leg on hover enter and null on leave, and marks itself highlighted', () => {
    const onHover = vi.fn()
    const { container } = render(<StageLeg index={3} leg={leg} highlighted onHover={onHover} />)
    const row = container.querySelector('[data-leg="3"]')!
    expect(row).toHaveAttribute('data-highlighted', 'true')
    fireEvent.mouseEnter(row)
    expect(onHover).toHaveBeenLastCalledWith(3)
    fireEvent.mouseLeave(row)
    expect(onHover).toHaveBeenLastCalledWith(null)
  })
  it('the rail beside the figures is part of the hover target', () => {
    const onHover = vi.fn()
    const { container } = render(<StageLeg index={2} leg={leg} highlighted={false} onHover={onHover} />)
    fireEvent.mouseEnter(container.querySelector('[data-leg="2"] [aria-hidden="true"]')!)
    expect(onHover).toHaveBeenLastCalledWith(2)
  })
  it('a missing leg keeps its hover target but shows no figures', () => {
    const { container } = render(<StageLeg index={1} leg={null} highlighted={false} onHover={() => {}} />)
    expect(container.querySelector('[data-leg="1"]')).not.toHaveTextContent(/./)
  })
})
