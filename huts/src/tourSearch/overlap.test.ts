import { describe, it, expect } from 'vitest'
import { trimSharedHubIds, hasOverlap } from './overlap.js'

describe('trimSharedHubIds', () => {
  it('exempts the matching run walking outward from the shared hub', () => {
    const exempt = trimSharedHubIds([100, 200, 300], [100, 200, 999])
    expect(exempt).toEqual(new Set([100, 200]))
  })

  it('stops at the first mismatch, even if a later id matches too', () => {
    const exempt = trimSharedHubIds([100, 999, 300], [100, 200, 300])
    expect(exempt).toEqual(new Set([100]))
  })

  it('is empty when the two legs share no run out of the hub at all', () => {
    const exempt = trimSharedHubIds([100], [200])
    expect(exempt).toEqual(new Set())
  })

  it('handles arrays of different lengths', () => {
    const exempt = trimSharedHubIds([100, 200], [100])
    expect(exempt).toEqual(new Set([100]))
  })
})

describe('hasOverlap', () => {
  it('is true when a non-exempt id is already used', () => {
    expect(hasOverlap([100, 200], new Set(), new Set([200, 300]))).toBe(true)
  })

  it('is false when every used id is exempted', () => {
    expect(hasOverlap([100, 200], new Set([200]), new Set([200, 300]))).toBe(false)
  })

  it('is false when the id sets are genuinely disjoint', () => {
    expect(hasOverlap([100, 200], new Set(), new Set([300, 400]))).toBe(false)
  })
})
