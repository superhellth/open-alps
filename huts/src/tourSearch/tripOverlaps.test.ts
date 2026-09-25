import { describe, it, expect } from 'vitest'
import { overlapLegsOf, tripOverlaps } from './tripOverlaps.js'
import type { EdgeIdTables } from './overlap.js'
import type { HutEdgeIdsData } from './types.js'
import { legsFromTrip } from './tripLegs.js'
import { makeTripGraph } from '@/testing/tripTestGraph.js'
import { newTrip } from '../trip/trip.js'

function table(rows: { sorted: number[]; prefix: number[]; suffix: number[] }[]): HutEdgeIdsData {
  return {
    getSortedIds: (e) => Int32Array.from(rows[e].sorted),
    getPrefixIds: (e) => Int32Array.from(rows[e].prefix),
    getSuffixIds: (e) => Int32Array.from(rows[e].suffix),
  }
}
const empty = table([])

describe('tripOverlaps', () => {
  it('reports two hut legs that share trail segments', () => {
    const hut = table([
      { sorted: [1, 2, 3], prefix: [1], suffix: [3] },
      { sorted: [3, 4, 5], prefix: [3], suffix: [5] },
      { sorted: [9, 10], prefix: [9], suffix: [10] },
    ])
    const tables: EdgeIdTables = { hut, start: empty }
    const legs = [0, 1, 2].map((edgeId) => ({ edgeId, reversed: false, kind: 'hut' as const }))
    // legs 0 and 1 meet at a hut through segment 3 (the shared run out of the hut is exempt) -> no warning
    expect(tripOverlaps(tables, legs, false)).toEqual([])
  })

  it('warns when the shared segments are not the contiguous run out of the shared hut', () => {
    const hut = table([
      { sorted: [1, 2, 7], prefix: [1], suffix: [2] },
      { sorted: [3, 7, 5], prefix: [3], suffix: [5] },
    ])
    const legs = [0, 1].map((edgeId) => ({ edgeId, reversed: false, kind: 'hut' as const }))
    expect(tripOverlaps({ hut, start: empty }, legs, false)).toEqual([[0, 1]])
  })

  it('checks non-adjacent legs without any exemption', () => {
    const hut = table([
      { sorted: [1, 2], prefix: [1], suffix: [2] },
      { sorted: [3, 4], prefix: [3], suffix: [4] },
      { sorted: [2, 6], prefix: [2], suffix: [6] },
    ])
    const legs = [0, 1, 2].map((edgeId) => ({ edgeId, reversed: false, kind: 'hut' as const }))
    expect(tripOverlaps({ hut, start: empty }, legs, false)).toEqual([[0, 2]])
  })

  it('exempts the trail out of a shared start point on a loop closure', () => {
    const start = table([
      { sorted: [1, 2], prefix: [1], suffix: [2] },
      { sorted: [1, 3], prefix: [1], suffix: [3] },
    ])
    const legs = [
      { edgeId: 0, reversed: false, kind: 'start' as const },
      { edgeId: 1, reversed: true, kind: 'start' as const },
    ]
    expect(tripOverlaps({ hut: empty, start }, legs, true)).toEqual([])
    expect(tripOverlaps({ hut: empty, start }, legs, false)).toEqual([[0, 1]])
  })
})

describe('overlapLegsOf', () => {
  const graph = makeTripGraph()
  const trip = (huts: string[]) => newTrip({
    name: 't', startDate: null, partySize: 1, start: { startId: 100, sourceType: 1 }, huts,
    exit: { startId: 100, sourceType: 1 }, variant: { sacCeiling: null, allowUngraded: false },
  }, new Date(), 'id')

  it('marks the first and last legs as start-kind and the rest as hut-kind', () => {
    const legs = overlapLegsOf(legsFromTrip(graph, trip(['{A}', '{B}', '{C}', '{D}'])))!
    expect(legs.map((l) => l.kind)).toEqual(['start', 'hut', 'hut', 'hut', 'start'])
  })
  it('is null when any leg is missing', () => {
    expect(overlapLegsOf(legsFromTrip(graph, trip(['{A}', '{D}'])))).toBeNull()
  })
})
