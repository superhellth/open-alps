import { describe, it, expect } from 'vitest'
import { getApproachLegs, getExitLegs } from './approaches.js'
import { SOURCE_TYPE_PARKING, SOURCE_TYPE_STATION } from './types.js'
import type { ApproachesData } from './types.js'

const approachesData: ApproachesData = {
  records: [
    { hutIndex: 15, startId: 32854131, sourceType: SOURCE_TYPE_STATION, accessUnknown: false, distanceM: 19812, ascentM: 746, descentM: 488, access: null },
    { hutIndex: 16, startId: 999, sourceType: SOURCE_TYPE_PARKING, accessUnknown: false, distanceM: 3000, ascentM: 200, descentM: 100, access: null },
  ],
  reverseIndex: {
    hut_to_starts: {
      15: [
        { hut_id: 15, start_id: 32854131, source_type: SOURCE_TYPE_STATION, variant: 0, distance_m: 19812, ascent_m: 746, descent_m: 488 },
        { hut_id: 15, start_id: 32854131, source_type: SOURCE_TYPE_STATION, variant: 1, distance_m: 20500, ascent_m: 760, descent_m: 500 },
        { hut_id: 15, start_id: 40000000, source_type: SOURCE_TYPE_STATION, variant: 0, distance_m: 9000, ascent_m: 300, descent_m: 250 },
      ],
    },
    start_to_huts: {},
  },
}

describe('getApproachLegs', () => {
  it('returns only the requested hut\'s FAST_ANY approach-table rows, start->hut oriented', () => {
    const legs = getApproachLegs(15, approachesData)
    expect(legs).toHaveLength(1)
    expect(legs[0]).toMatchObject({ startId: 32854131, ascentM: 746, descentM: 488 })
  })

  it('a hut with no approach rows gets an empty array', () => {
    expect(getApproachLegs(999, approachesData)).toEqual([])
  })
})

describe('getExitLegs', () => {
  it('reads the reverse index backwards (ascent/descent swapped), filtered to the given variant', () => {
    const legs = getExitLegs(15, 0, approachesData)
    expect(legs).toHaveLength(2) // both start points at variant 0
    const toOrigin = legs.find((l) => l.startId === 32854131)
    expect(toOrigin?.ascentM).toBe(488) // swapped from the stored 746/488
    expect(toOrigin?.descentM).toBe(746)
  })

  it('a variant not present in the reverse index for this hut yields no exits', () => {
    expect(getExitLegs(15, 2, approachesData)).toEqual([])
  })

  it('a hut absent from the reverse index yields no exits', () => {
    expect(getExitLegs(999, 0, approachesData)).toEqual([])
  })
})
