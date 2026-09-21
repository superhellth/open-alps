import { describe, it, expect } from 'vitest'
import { addUtcDays, formatOhrsDate } from './formatDate.js'

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

describe('addUtcDays', () => {
  it('adds whole UTC days across a month boundary', () => {
    expect(addUtcDays(new Date('2026-07-31T00:00:00Z'), 1).toISOString().slice(0, 10)).toBe('2026-08-01')
  })
})
