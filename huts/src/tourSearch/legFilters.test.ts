import { describe, it, expect } from 'vitest'
import { legPasses, createKillCounters } from './legFilters.js'

const baseLeg = { durationH: 5, ascentM: 800, descentM: 800, distanceM: 12000, maxEleM: 2200, viaFerrata: false }
const baseConstraints = { maxLegTimeH: 7, minLegTimeH: 2, legAscentCapM: 1000, maxEleM: 2500, allowViaFerrata: true }

describe('legPasses', () => {
  it('passes a leg within every constraint', () => {
    const counters = createKillCounters()
    expect(legPasses(baseLeg, baseConstraints, counters)).toBe(true)
    expect(counters.maxLegTime).toBe(0)
  })

  it('rejects and counts a leg over maxLegTimeH', () => {
    const counters = createKillCounters()
    expect(legPasses({ ...baseLeg, durationH: 8 }, baseConstraints, counters)).toBe(false)
    expect(counters.maxLegTime).toBe(1)
  })

  it('rejects and counts a leg under minLegTimeH', () => {
    const counters = createKillCounters()
    expect(legPasses({ ...baseLeg, durationH: 1 }, baseConstraints, counters)).toBe(false)
    expect(counters.minLegTime).toBe(1)
  })

  it('rejects and counts a leg over legAscentCapM', () => {
    const counters = createKillCounters()
    expect(legPasses({ ...baseLeg, ascentM: 1200 }, baseConstraints, counters)).toBe(false)
    expect(counters.legAscentCap).toBe(1)
  })

  it('rejects and counts a leg over maxEleM when a cap is set', () => {
    const counters = createKillCounters()
    expect(legPasses({ ...baseLeg, maxEleM: 2600 }, baseConstraints, counters)).toBe(false)
    expect(counters.maxEleM).toBe(1)
  })

  it('does not apply a maxEleM check when no cap is given', () => {
    const counters = createKillCounters()
    const constraints = { ...baseConstraints, maxEleM: null }
    expect(legPasses({ ...baseLeg, maxEleM: 9000 }, constraints, counters)).toBe(true)
  })

  it('rejects and counts a via-ferrata leg when disallowed', () => {
    const counters = createKillCounters()
    const constraints = { ...baseConstraints, allowViaFerrata: false }
    expect(legPasses({ ...baseLeg, viaFerrata: true }, constraints, counters)).toBe(false)
    expect(counters.viaFerrata).toBe(1)
  })

  it('a start leg with no maxEleM/viaFerrata fields is not rejected by those checks', () => {
    const counters = createKillCounters()
    const startLeg = { durationH: 3, ascentM: 400, descentM: 100, distanceM: 5000 } // approach/exit legs carry no maxEleM/viaFerrata
    expect(legPasses(startLeg, baseConstraints, counters)).toBe(true)
  })
})
