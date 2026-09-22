import { describe, it, expect } from 'vitest'
import { DEFAULT_DRAFT, dayCountFromDraft, legCountRangeFromDraft } from './plannerState.js'

describe('legCountRangeFromDraft', () => {
  it('defaults to the 3-day stepper, undated, inflexible', () => {
    expect(DEFAULT_DRAFT.dayCount).toBe(3)
    expect(DEFAULT_DRAFT.flexible).toBe(false)
    expect(legCountRangeFromDraft(DEFAULT_DRAFT)).toEqual([3, 3])
  })

  it('widens by one day each way when flexible and undated', () => {
    expect(legCountRangeFromDraft({ ...DEFAULT_DRAFT, flexible: true })).toEqual([2, 4])
  })

  it('never goes below 2 days when flexible at the stepper floor', () => {
    expect(legCountRangeFromDraft({ ...DEFAULT_DRAFT, dayCount: 2, flexible: true })).toEqual([2, 3])
  })

  it('is exact from a date range: to - from + 1', () => {
    const draft = { ...DEFAULT_DRAFT, startDate: '2026-07-10', endDate: '2026-07-13' }
    expect(legCountRangeFromDraft(draft)).toEqual([4, 4])
  })

  it('ignores flexible when dates are set', () => {
    const draft = { ...DEFAULT_DRAFT, startDate: '2026-07-10', endDate: '2026-07-13', flexible: true }
    expect(legCountRangeFromDraft(draft)).toEqual([4, 4])
  })
})

describe('dayCountFromDraft', () => {
  it('is the exact day count when dated', () => {
    expect(dayCountFromDraft({ ...DEFAULT_DRAFT, startDate: '2026-07-10', endDate: '2026-07-13' })).toBe(4)
  })
  it('is the stepper value when undated', () => {
    expect(dayCountFromDraft({ ...DEFAULT_DRAFT, dayCount: 5 })).toBe(5)
  })
})
