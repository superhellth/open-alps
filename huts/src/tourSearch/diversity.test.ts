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

import { suppressSimilar } from './diversity.js'

describe('suppressSimilar', () => {
  it('drops a candidate that shares more than the threshold fraction of huts with an accepted chain', () => {
    const chains = [
      { huts: [0, 1, 2], startId: 100, totalDurationH: 5 },
      { huts: [0, 1, 3], startId: 200, totalDurationH: 6 }, // shares 2/3 huts with the first
    ]
    const result = suppressSimilar(chains, 0.5)
    expect(result).toHaveLength(1)
    expect(result[0].totalDurationH).toBe(5)
  })

  it('keeps a candidate below the overlap threshold', () => {
    const chains = [
      { huts: [0, 1, 2], startId: 100, totalDurationH: 5 },
      { huts: [3, 4, 5], startId: 200, totalDurationH: 6 }, // disjoint
    ]
    expect(suppressSimilar(chains, 0.5)).toHaveLength(2)
  })

  it('drops a candidate sharing its start point with an accepted chain, even with low hut overlap', () => {
    const chains = [
      { huts: [0, 1, 2], startId: 100, totalDurationH: 5 },
      { huts: [3, 4, 5], startId: 100, totalDurationH: 6 }, // same trailhead
    ]
    expect(suppressSimilar(chains, 0.5)).toHaveLength(1)
  })

  it('processes candidates in the given (ranked) order, always keeping the first', () => {
    const chains = [
      { huts: [0], startId: 1, totalDurationH: 1 },
      { huts: [0], startId: 1, totalDurationH: 2 },
      { huts: [0], startId: 1, totalDurationH: 3 },
    ]
    const result = suppressSimilar(chains, 0.5)
    expect(result).toHaveLength(1)
    expect(result[0].totalDurationH).toBe(1)
  })
})
