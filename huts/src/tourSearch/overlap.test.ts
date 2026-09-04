import { describe, it, expect } from 'vitest'
import { trimSharedHubIds, hasOverlap, nearHubIds } from './overlap.js'

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

describe('nearHubIds', () => {
  const tables = {
    hut: {
      getSortedIds: () => new Int32Array(0),
      getPrefixIds: (id: number) => Int32Array.from([100 + id]),
      getSuffixIds: (id: number) => Int32Array.from([200 + id]),
    },
    start: {
      getSortedIds: () => new Int32Array(0),
      getPrefixIds: (id: number) => Int32Array.from([300 + id]),
      getSuffixIds: (id: number) => Int32Array.from([400 + id]),
    },
  }

  it('an arriving, non-reversed hut leg reads the suffix (near its arrival end)', () => {
    expect(Array.from(nearHubIds(tables, { edgeId: 1, reversed: false, kind: 'hut' }, 'arriving'))).toEqual([201])
  })

  it('an arriving, reversed hut leg reads the prefix', () => {
    expect(Array.from(nearHubIds(tables, { edgeId: 1, reversed: true, kind: 'hut' }, 'arriving'))).toEqual([101])
  })

  it('a departing, non-reversed hut leg reads the prefix', () => {
    expect(Array.from(nearHubIds(tables, { edgeId: 1, reversed: false, kind: 'hut' }, 'departing'))).toEqual([101])
  })

  it('a departing, reversed hut leg reads the suffix', () => {
    expect(Array.from(nearHubIds(tables, { edgeId: 1, reversed: true, kind: 'hut' }, 'departing'))).toEqual([201])
  })

  it('dispatches to the start table for kind "start"', () => {
    expect(Array.from(nearHubIds(tables, { edgeId: 1, reversed: false, kind: 'start' }, 'arriving'))).toEqual([401])
  })
})
