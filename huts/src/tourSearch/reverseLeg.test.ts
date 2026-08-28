import { describe, it, expect } from 'vitest'
import { forwardHutLeg, reverseHutLeg, forwardStartLeg, reverseStartLeg } from './reverseLeg.js'
import type { HutEdgeRecord, ApproachRecord } from './types.js'
import { SOURCE_TYPE_STATION } from './types.js'

const record: HutEdgeRecord = {
  fromIndex: 0, toIndex: 1, variant: 2, distanceM: 8000, ascentM: 600, descentM: 500,
  maxEleM: 2400, sacRank: 3, viaFerrata: false, roadM: 100, ungradedM: 0, inferredM: 50, snapM: 5,
  edgeId: 42,
}

describe('reverseHutLeg', () => {
  it('swaps ascent/descent, swaps endpoints, recomputes duration, and leaves everything else unchanged', () => {
    const reversed = reverseHutLeg(record)
    expect(reversed.fromIndex).toBe(1)
    expect(reversed.toIndex).toBe(0)
    expect(reversed.ascentM).toBe(500)
    expect(reversed.descentM).toBe(600)
    // reversed: distance 8000, ascent 500, descent 600 -> t_h=2, t_v=500/300+600/500=2.867 -> 2.867+1=3.867h
    expect(reversed.durationH).toBeCloseTo(3.8667, 3)
    expect(reversed.edgeId).toBe(42)
    expect(reversed.reversed).toBe(true)
    const fields: (keyof HutEdgeRecord)[] = ['distanceM', 'roadM', 'sacRank', 'viaFerrata', 'maxEleM', 'ungradedM', 'inferredM']
    for (const field of fields) {
      expect(reversed[field]).toEqual(record[field])
    }
  })
})

describe('forwardHutLeg', () => {
  it('computes duration without altering any other field', () => {
    const forward = forwardHutLeg(record)
    expect(forward.ascentM).toBe(600)
    expect(forward.descentM).toBe(500)
    expect(forward.durationH).toBeCloseTo(4.0, 6) // same fixture as dinDuration.test.js
    expect(forward.edgeId).toBe(42)
    expect(forward.reversed).toBe(false)
  })
})

describe('start-edge reversal (approach/exit)', () => {
  const approach: ApproachRecord = {
    hutIndex: 15, startId: 32854131, sourceType: SOURCE_TYPE_STATION, accessUnknown: false,
    distanceM: 4000, ascentM: 300, descentM: 100, access: null, edgeId: 7,
  }

  it('forwardStartLeg computes duration in the stored (start->hut) direction', () => {
    // t_h = 4000/4000 = 1.0, t_v = 300/300 + 100/500 = 1.2 -> max(1.2,1.0) + min(1.2,1.0)/2 = 1.7h
    expect(forwardStartLeg(approach).durationH).toBeCloseTo(1.7, 3)
    expect(forwardStartLeg(approach).edgeId).toBe(7)
    expect(forwardStartLeg(approach).reversed).toBe(false)
  })

  it('reverseStartLeg swaps ascent/descent for the hut->start (exit) direction', () => {
    const exit = reverseStartLeg(approach)
    expect(exit.ascentM).toBe(100)
    expect(exit.descentM).toBe(300)
    expect(exit.startId).toBe(32854131)
    expect(exit.edgeId).toBe(7)
    expect(exit.reversed).toBe(true)
  })
})
