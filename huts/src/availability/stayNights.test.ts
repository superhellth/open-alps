import { describe, it, expect } from 'vitest'
import { nightVerdicts, stayVerdict } from './stayNights.js'
import type { FreeByOffset } from './types.js'

describe('nightVerdicts', () => {
  it('reads night i of hut i from offset i + 1', () => {
    const free: FreeByOffset = new Map<number, Set<string> | 'unknown'>([[1, new Set(['A'])], [2, new Set(['A'])], [3, 'unknown']])
    expect(nightVerdicts(['A', 'B', 'C', null], free)).toEqual(['free', 'full', 'unclear', 'unclear'])
  })
})

describe('stayVerdict', () => {
  it('is blocked by any full night, before unclear ones', () => {
    expect(stayVerdict(['free', 'unclear', 'full'])).toBe('blocked')
    expect(stayVerdict(['free', 'unclear'])).toBe('unclear')
    expect(stayVerdict(['free', 'free'])).toBe('bookable')
  })
})
