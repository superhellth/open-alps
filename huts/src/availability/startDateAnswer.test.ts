import { describe, it, expect } from 'vitest'
import { answerWindow, shiftAnswers } from './startDateAnswer.js'
import type { FreeByOffset } from './types.js'

// maxShift 1 -> shifts -1,0,+1; base = firstNight - 2; hut i at shift s reads offset s + 1 + 1 + i = s + i + 2
describe('shiftAnswers', () => {
  const free = (...ids: string[][]): FreeByOffset => new Map(ids.map((set, i) => [i + 1, new Set(set)] as const))

  it('is bookable when every hut is free on its night', () => {
    // huts H1,H2. shift 0: H1@offset 2, H2@offset 3
    const map = free([], ['H1'], ['H2'], [], [])
    const a = shiftAnswers(['H1', 'H2'], map, 1)
    expect(a.map((x) => x.shiftDays)).toEqual([-1, 0, 1])
    expect(a[1].verdict).toBe('bookable')
  })
  it('is blocked when a hut with an OHRS id is not in the free set', () => {
    const map = free([], ['H1'], [], [], [])
    expect(shiftAnswers(['H1', 'H2'], map, 1)[1].verdict).toBe('blocked')
  })
  it('is unclear when nothing is blocked but a hut is direct-booking or its night failed to load', () => {
    const map: FreeByOffset = new Map<number, Set<string> | 'unknown'>([[1, new Set()], [2, new Set(['H1'])], [3, 'unknown'], [4, new Set()], [5, new Set()]])
    expect(shiftAnswers(['H1', 'H2'], map, 1)[1].verdict).toBe('unclear')
    expect(shiftAnswers(['H1', null], free([], ['H1'], [], [], []), 1)[1].verdict).toBe('unclear')
  })
  it('blocked wins over unclear', () => {
    const map: FreeByOffset = new Map<number, Set<string> | 'unknown'>([[1, new Set()], [2, new Set()], [3, 'unknown'], [4, new Set()], [5, new Set()]])
    expect(shiftAnswers(['H1', 'H2'], map, 1)[1].verdict).toBe('blocked')
  })
})

describe('answerWindow', () => {
  it('starts one day before the earliest shifted first night and covers every shifted night', () => {
    const w = answerWindow(new Date('2026-07-10T00:00:00Z'), 3)
    expect(w.base.toISOString().slice(0, 10)).toBe('2026-07-06')
    expect(w.maxOffset(3)).toBe(9) // shifts -3..+3 (7 start dates) + 3 nights - 1
  })
})
