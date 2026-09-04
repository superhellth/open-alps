import { describe, it, expect } from 'vitest'
import { formatOhrsDate } from './formatDate.js'

describe('formatOhrsDate', () => {
  it('formats a Date as DD.MM.YYYY with zero-padding', () => {
    expect(formatOhrsDate(new Date(Date.UTC(2026, 7, 5)))).toBe('05.08.2026')
  })

  it('adds offsetDays before formatting', () => {
    expect(formatOhrsDate(new Date(Date.UTC(2026, 7, 30)), 3)).toBe('02.09.2026')
  })

  it('offsetDays defaults to 0', () => {
    expect(formatOhrsDate(new Date(Date.UTC(2026, 0, 1)))).toBe('01.01.2026')
  })

  it('crosses a year boundary correctly', () => {
    expect(formatOhrsDate(new Date(Date.UTC(2026, 11, 31)), 1)).toBe('01.01.2027')
  })
})
