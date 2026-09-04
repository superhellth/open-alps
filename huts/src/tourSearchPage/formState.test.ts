import { describe, it, expect } from 'vitest'
import { DEFAULT_FORM, buildQuery, isFilterSelectionValid } from './formState.js'
import type { HutClass } from '../hutClass.js'

const hutsByIndex: (HutClass | null)[] = [
  { operator: 'av', serviced: true },     // 0
  { operator: 'av', serviced: false },    // 1
  { operator: 'sonstige', serviced: true }, // 2
  null,                                    // 3 - failed join, must never pass
]

describe('buildQuery hut filtering', () => {
  it('default form allows av+sonstige, serviced only -> excludes self-service and unresolved huts', () => {
    const q = buildQuery(DEFAULT_FORM, hutsByIndex)
    expect(q.allowedHutIndices).toEqual(new Set([0, 2]))
  })

  it('enabling allowSelfService includes self-service huts of allowed operators', () => {
    const form = { ...DEFAULT_FORM, allowSelfService: true }
    const q = buildQuery(form, hutsByIndex)
    expect(q.allowedHutIndices).toEqual(new Set([0, 1, 2]))
  })

  it('restricting allowedOperators to av-only excludes sonstige regardless of servicing', () => {
    const form = { ...DEFAULT_FORM, allowedOperators: new Set<'av' | 'sonstige'>(['av']), allowSelfService: true }
    const q = buildQuery(form, hutsByIndex)
    expect(q.allowedHutIndices).toEqual(new Set([0, 1]))
  })

  it('a null hut class (failed GUID join) is never included', () => {
    const form = { ...DEFAULT_FORM, allowSelfService: true }
    const q = buildQuery(form, hutsByIndex)
    expect(q.allowedHutIndices!.has(3)).toBe(false)
  })
})

describe('isFilterSelectionValid', () => {
  it('is valid for the default form', () => {
    expect(isFilterSelectionValid(DEFAULT_FORM)).toBe(true)
  })
  it('is invalid when allowedOperators is empty', () => {
    expect(isFilterSelectionValid({ ...DEFAULT_FORM, allowedOperators: new Set() })).toBe(false)
  })
  it('is invalid when neither servicing box is checked', () => {
    expect(isFilterSelectionValid({ ...DEFAULT_FORM, allowServiced: false, allowSelfService: false })).toBe(false)
  })
})

describe('buildQuery availability wiring', () => {
  const availability = { ohrsIdByHutIndex: new Map([[0, 'ohrsA']]), freeByOffset: new Map([[1, new Set(['ohrsA'])]]) }

  it('attaches availability when onlyAvailable is checked', () => {
    const form = { ...DEFAULT_FORM, startDate: '2026-08-20', onlyAvailable: true }
    const q = buildQuery(form, hutsByIndex, availability)
    expect(q.availability).toBe(availability)
  })

  it('omits availability when onlyAvailable is unchecked, even if data was fetched', () => {
    const form = { ...DEFAULT_FORM, startDate: '2026-08-20', onlyAvailable: false }
    const q = buildQuery(form, hutsByIndex, availability)
    expect(q.availability).toBeUndefined()
  })

  it('omits availability when no data was fetched, even if onlyAvailable is checked', () => {
    const form = { ...DEFAULT_FORM, startDate: '', onlyAvailable: true }
    const q = buildQuery(form, hutsByIndex)
    expect(q.availability).toBeUndefined()
  })
})
