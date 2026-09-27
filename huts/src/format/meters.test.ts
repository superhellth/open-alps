import { describe, it, expect } from 'vitest'
import { formatAscent, formatDescent, formatMeters } from './meters.js'

describe('formatMeters', () => {
  it('rounds and appends the unit', () => {
    expect(formatMeters(820.4)).toBe('820 m')
  })
  it('groups thousands the German way', () => {
    expect(formatMeters(2340)).toBe(`${(2340).toLocaleString('de-DE')} m`)
  })
})

describe('formatAscent / formatDescent', () => {
  it('prefix the arrow', () => {
    expect(formatAscent(820.4)).toBe('↑ 820 m')
    expect(formatDescent(240)).toBe('↓ 240 m')
  })
})
