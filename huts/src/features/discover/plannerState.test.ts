import { describe, it, expect } from 'vitest'
import { DEFAULT_DRAFT, dayCountFromDraft, legCountRangeFromDraft } from './plannerState.js'

describe('legCountRangeFromDraft', () => {
  it('defaults to a 3-day range', () => {
    expect(legCountRangeFromDraft(DEFAULT_DRAFT)).toEqual([3, 3])
  })

  it('is exact from a date range: to - from + 1', () => {
    const draft = { ...DEFAULT_DRAFT, startDate: '2026-07-10', endDate: '2026-07-13' }
    expect(legCountRangeFromDraft(draft)).toEqual([4, 4])
  })
})

describe('dayCountFromDraft', () => {
  it('is the exact day count', () => {
    expect(dayCountFromDraft({ ...DEFAULT_DRAFT, startDate: '2026-07-10', endDate: '2026-07-13' })).toBe(4)
  })
})
