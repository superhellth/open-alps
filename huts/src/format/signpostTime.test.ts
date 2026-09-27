import { describe, it, expect } from 'vitest'
import { formatSignpostTime } from './signpostTime.js'

describe('formatSignpostTime', () => {
  it.each([
    [3.5, '3½ Std'], [0.75, '¾ Std'], [5.25, '5¼ Std'], [4, '4 Std'],
    [3.4, '3½ Std'], [3.6, '3½ Std'], [3.7, '3¾ Std'], [0.25, '¼ Std'], [0.1, '0 Std'],
  ])('%f h -> %s', (hours, text) => {
    expect(formatSignpostTime(hours)).toBe(text)
  })
})
