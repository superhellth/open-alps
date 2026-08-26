import { describe, it, expect } from 'vitest'
import { buildAdjacency } from './adjacency.js'
import type { HutEdgesData } from './types.js'

const hutEdgesData: HutEdgesData = {
  hutIds: ['A', 'B', 'C'],
  variantNames: { 0: 'FAST_ANY', 1: 'FAST_T2' },
  records: [
    { fromIndex: 0, toIndex: 1, variant: 0, distanceM: 5000, ascentM: 400, descentM: 200, maxEleM: 2000, sacRank: 1, viaFerrata: false, roadM: 0, ungradedM: 0, inferredM: 0, snapM: 0 },
    { fromIndex: 0, toIndex: 2, variant: 1, distanceM: 6000, ascentM: 500, descentM: 300, maxEleM: 2100, sacRank: 2, viaFerrata: false, roadM: 0, ungradedM: 0, inferredM: 0, snapM: 0 },
  ],
}

describe('buildAdjacency', () => {
  it('includes only edges of the requested variant, in both directions', () => {
    const adjacency = buildAdjacency(hutEdgesData, 0)
    expect(adjacency.get(0)).toHaveLength(1)
    expect(adjacency.get(0)?.[0]).toMatchObject({ toIndex: 1, ascentM: 400, descentM: 200 })
    expect(adjacency.get(1)).toHaveLength(1)
    expect(adjacency.get(1)?.[0]).toMatchObject({ toIndex: 0, ascentM: 200, descentM: 400 }) // swapped
    expect(adjacency.has(2)).toBe(false) // variant-1 edge excluded
  })

  it('a hut with no edges in this variant is simply absent from the map', () => {
    const adjacency = buildAdjacency(hutEdgesData, 1)
    expect(adjacency.get(0)).toHaveLength(1)
    expect(adjacency.has(1)).toBe(false)
  })
})
