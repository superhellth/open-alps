// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import RangeCalendar from './RangeCalendar.js'

beforeEach(() => { vi.useFakeTimers({ toFake: ['Date'], now: new Date('2026-07-01T12:00:00Z') }) })
afterEach(() => { cleanup(); vi.useRealTimers() })

const day = (iso: string) => screen.getByRole('button', { name: iso })

function openCalendar(onChange = vi.fn()) {
  render(<RangeCalendar startDate="2026-07-03" endDate="2026-07-05" onChange={onChange} disabled={false} />)
  fireEvent.click(screen.getByRole('button', { name: /Juli|Jul|–/ }))
  return onChange
}

describe('RangeCalendar', () => {
  it('previews the range from the first click to the hovered day', () => {
    openCalendar()
    fireEvent.click(day('2026-07-10'))
    expect(day('2026-07-10')).toHaveAttribute('aria-pressed', 'true')
    expect(day('2026-07-14')).toHaveAttribute('aria-pressed', 'false')
    fireEvent.mouseEnter(day('2026-07-14'))
    expect(day('2026-07-10')).toHaveAttribute('aria-pressed', 'true')
    expect(day('2026-07-14')).toHaveAttribute('aria-pressed', 'true')
    fireEvent.mouseEnter(day('2026-07-07'))
    expect(day('2026-07-07')).toHaveAttribute('aria-pressed', 'true')
    expect(day('2026-07-14')).toHaveAttribute('aria-pressed', 'false')
  })

  it('reports the ordered range on the second click', () => {
    const onChange = openCalendar()
    fireEvent.click(day('2026-07-10'))
    fireEvent.click(day('2026-07-07'))
    expect(onChange).toHaveBeenCalledWith({ startDate: '2026-07-07', endDate: '2026-07-10' })
  })
})
