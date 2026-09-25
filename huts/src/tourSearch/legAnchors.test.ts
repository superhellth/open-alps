import { describe, it, expect } from 'vitest'
import { createLegAnchorLookup } from './legAnchors.js'
import type { ApproachRecord, HutEdgeRecord } from './types.js'

const hut = (over: Partial<HutEdgeRecord>): HutEdgeRecord => ({
  fromIndex: 0, toIndex: 1, variant: 0, distanceM: 1, ascentM: 0, descentM: 0, maxEleM: 0, sacRank: 0,
  viaFerrata: false, roadM: 0, ungradedM: 0, inferredM: 0, snapM: 0, edgeId: 0, ...over,
})
const approach = (over: Partial<ApproachRecord>): ApproachRecord => ({
  hutIndex: 1, startId: 9, sourceType: 1, variant: 0, accessUnknown: false, distanceM: 1, ascentM: 0, descentM: 0,
  access: null, edgeId: 40, ...over,
})
const hutCoordsById = new Map([[0, { lat: 47, lng: 11 }], [1, { lat: 47.1, lng: 11.2 }]])
const lookup = createLegAnchorLookup({
  hutEdges: { hutIds: [], variantNames: {}, records: [hut({ anchorOffsets: [10, 20, 30, 40, 50, 60] }), hut({ edgeId: 1 })] },
  approaches: { records: [approach({ anchorOffsets: [1, 2] }), approach({ edgeId: 41 })], reverseIndex: { hut_to_starts: {}, start_to_huts: {} } },
  hutCoordsById,
  officialTours: [{ tourId: 1, name: 't', totalDistanceM: 0, totalAscentM: 0, totalDescentM: 0, totalDurationH: 0, legs: [
    { legIndex: 0, from: { type: 'hut', id: 0 }, to: { type: 'hut', id: 1 }, edgeId: 7, reversed: false, distanceM: 1, ascentM: 0, descentM: 0, durationH: 0, maxEleM: 0, anchors: [{ lat: 1, lng: 2 }] },
  ] }],
})

describe('createLegAnchorLookup', () => {
  it('decodes hut-edge anchors relative to the from hut', () => {
    const a = lookup('hut_edges', 0)!
    expect(a).toHaveLength(3)
    expect(a[0].lat).toBeCloseTo(47.001, 9)
    expect(a[0].lng).toBeCloseTo(11.002, 9)
  })
  it('decodes approach anchors relative to the approach hut, keyed by start-edge id', () => {
    const [a] = lookup('start_edges', 40)!
    expect(a.lat).toBeCloseTo(47.1001, 9)
    expect(a.lng).toBeCloseTo(11.2002, 9)
  })
  it('returns the official leg anchors as shipped', () => {
    expect(lookup('tour_edges', 7)).toEqual([{ lat: 1, lng: 2 }])
  })
  it('returns null when no anchors shipped, the edge is unknown, or the id is negative', () => {
    expect(lookup('hut_edges', 1)).toBeNull()
    expect(lookup('start_edges', 41)).toBeNull()
    expect(lookup('start_edges', 999)).toBeNull()
    expect(lookup('hut_edges', -1)).toBeNull()
    expect(lookup('tour_edges', 1)).toBeNull()
  })
})
