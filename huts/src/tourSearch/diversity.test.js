import { describe, it, expect } from 'vitest'
import { dedupeReversePairs } from './diversity.js'

describe('dedupeReversePairs', () => {
  it('collapses a chain and its exact reverse, keeping the faster one', () => {
    const chains = [
      { huts: [0, 1, 2], totalDurationH: 10 },
      { huts: [2, 1, 0], totalDurationH: 8 }, // same tour walked backwards, faster this way
    ]
    const result = dedupeReversePairs(chains)
    expect(result).toHaveLength(1)
    expect(result[0].totalDurationH).toBe(8)
  })

  it('does NOT collapse a different permutation sharing the same hut set', () => {
    // h1->h2->h3 and h1->h3->h2 are different tours, not a reverse pair (spec Part 6).
    const chains = [
      { huts: [0, 1, 2], totalDurationH: 10 },
      { huts: [0, 2, 1], totalDurationH: 9 },
    ]
    const result = dedupeReversePairs(chains)
    expect(result).toHaveLength(2)
  })

  it('leaves a chain with no reverse twin untouched', () => {
    const chains = [{ huts: [0, 1], totalDurationH: 5 }]
    expect(dedupeReversePairs(chains)).toEqual(chains)
  })
})
