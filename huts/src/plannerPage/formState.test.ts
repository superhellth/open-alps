import { describe, it, expect } from 'vitest'
import { DEFAULT_FORM, buildQuery, isFilterSelectionValid, rankTargetsFromForm } from './formState.js'
import { LEG_COUNT_SLIDER_MAX } from '../tourSearch/limits.js'
import type { HutClass } from '../hutClass.js'

const huts: (HutClass | null)[] = [
  { operator: 'av', serviced: true }, { operator: 'av', serviced: false },
  { operator: 'sonstige', serviced: true }, null,
]

describe('planner form', () => {
  it('has no date or party fields (they live on the trip draft)', () => {
    expect('startDate' in DEFAULT_FORM).toBe(false)
    expect('numOfPeople' in DEFAULT_FORM).toBe(false)
  })
  it('default leg range stays inside the slider ceiling', () => {
    expect(DEFAULT_FORM.legCountRange[1]).toBeLessThanOrEqual(LEG_COUNT_SLIDER_MAX)
  })
  it('buildQuery filters huts by class exactly like the old form', () => {
    expect(buildQuery(DEFAULT_FORM, huts).allowedHutIndices).toEqual(new Set([0, 2]))
    expect(buildQuery({ ...DEFAULT_FORM, allowSelfService: true }, huts).allowedHutIndices).toEqual(new Set([0, 1, 2]))
  })
  it('only passes availability when onlyAvailable is set', () => {
    const availability = { ohrsIdByHutIndex: new Map(), freeByOffset: new Map() }
    expect(buildQuery(DEFAULT_FORM, huts, availability).availability).toBeUndefined()
    expect(buildQuery({ ...DEFAULT_FORM, onlyAvailable: true }, huts, availability).availability).toBe(availability)
  })
  it('rank target defaults to the middle of the leg range and is clamped into it', () => {
    expect(rankTargetsFromForm({ ...DEFAULT_FORM, legCountRange: [2, 4], targetLegCount: null }).legCountTarget).toBe(3)
    expect(rankTargetsFromForm({ ...DEFAULT_FORM, legCountRange: [2, 4], targetLegCount: 9 }).legCountTarget).toBe(4)
  })
  it('validates the hut class selection', () => {
    expect(isFilterSelectionValid(DEFAULT_FORM)).toBe(true)
    expect(isFilterSelectionValid({ ...DEFAULT_FORM, allowedOperators: new Set() })).toBe(false)
  })
})
