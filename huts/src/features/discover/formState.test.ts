import { describe, it, expect } from 'vitest'
import { DEFAULT_FORM, buildQuery, isFilterSelectionValid, legTimeRangeFromCeiling, rankTargetsFromForm } from './formState.js'
import type { HutClass } from '@/data/hutClass.js'

const huts: (HutClass | null)[] = [
  { operator: 'av', serviced: true }, { operator: 'av', serviced: false },
  { operator: 'sonstige', serviced: true }, null,
]

describe('planner form', () => {
  it('has no date, party, or day-count fields (they live on the trip draft)', () => {
    expect('startDate' in DEFAULT_FORM).toBe(false)
    expect('legCountRange' in DEFAULT_FORM).toBe(false)
    expect('targetLegCount' in DEFAULT_FORM).toBe(false)
  })
  it('defaults allowUngraded and allowViaFerrata to off', () => {
    expect(DEFAULT_FORM.allowUngraded).toBe(false)
    expect(DEFAULT_FORM.allowViaFerrata).toBe(false)
  })
  it('defaults the leg-time ceiling to 7h, half that as the floor', () => {
    expect(DEFAULT_FORM.legTimeCeilingH).toBe(7)
    expect(legTimeRangeFromCeiling(7)).toEqual([3.5, 7])
    expect(legTimeRangeFromCeiling(5)).toEqual([2.5, 5])
    expect(legTimeRangeFromCeiling(9)).toEqual([4.5, 9])
  })
  it('buildQuery filters huts by class exactly like before, and takes an explicit leg-count range', () => {
    expect(buildQuery(DEFAULT_FORM, huts, [2, 4]).allowedHutIndices).toEqual(new Set([0, 2]))
    expect(buildQuery(DEFAULT_FORM, huts, [2, 4]).legCountMin).toBe(2)
    expect(buildQuery(DEFAULT_FORM, huts, [2, 4]).legCountMax).toBe(4)
    const withSelfService = { ...DEFAULT_FORM, allowedHutClasses: new Set([...DEFAULT_FORM.allowedHutClasses, 'av:self' as const]) }
    expect(buildQuery(withSelfService, huts, [2, 4]).allowedHutIndices).toEqual(new Set([0, 1, 2]))
  })
  it('rank target is the exact/target day count, clamped into the leg-count range', () => {
    expect(rankTargetsFromForm(DEFAULT_FORM, [2, 4], 3).legCountTarget).toBe(3)
    expect(rankTargetsFromForm(DEFAULT_FORM, [2, 4], 9).legCountTarget).toBe(4)
  })
  it('validates the hut class selection', () => {
    expect(isFilterSelectionValid(DEFAULT_FORM)).toBe(true)
    expect(isFilterSelectionValid({ ...DEFAULT_FORM, allowedHutClasses: new Set() })).toBe(false)
  })
})
