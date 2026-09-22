import { describe, it, expect } from 'vitest'
import { filterByAvailability, tourHasFullNight } from './availabilityFilter.js'
import type { PlannerTour } from './tours.js'
import type { FreeByOffset } from '../availability/types.js'

function tour(huts: number[]): PlannerTour {
  return {
    startId: 1, exitStartId: 1, huts, legs: huts.map(() => ({ durationH: 4, ascentM: 0, descentM: 0, distanceM: 0, edgeId: 1, reversed: false })),
    totalDurationH: 4 * huts.length, totalAscentM: 0, totalDescentM: 0, totalDistanceM: 0,
  } as PlannerTour
}

describe('tourHasFullNight', () => {
  it('is false when every night is free or unknown-OHRS', () => {
    const ohrsIdByHutIndex = new Map([[0, 'A'], [1, null]])
    const freeByOffset: FreeByOffset = new Map([[1, new Set(['A'])], [2, new Set(['B'])]])
    expect(tourHasFullNight(tour([0, 1]), ohrsIdByHutIndex, freeByOffset)).toBe(false)
  })
  it('is true when a night with a known OHRS id has no free beds', () => {
    const ohrsIdByHutIndex = new Map([[0, 'A']])
    const freeByOffset: FreeByOffset = new Map([[1, new Set(['other'])]])
    expect(tourHasFullNight(tour([0]), ohrsIdByHutIndex, freeByOffset)).toBe(true)
  })
  it('treats an unknown fetch result as available (kept)', () => {
    const ohrsIdByHutIndex = new Map([[0, 'A']])
    const freeByOffset: FreeByOffset = new Map([[1, 'unknown' as const]])
    expect(tourHasFullNight(tour([0]), ohrsIdByHutIndex, freeByOffset)).toBe(false)
  })
})

describe('filterByAvailability', () => {
  const ohrsIdByHutIndex = new Map([[0, 'A'], [1, 'B']])
  const freeByOffset: FreeByOffset = new Map([[1, new Set(['A'])], [2, new Set()]])
  const tours = [tour([0]), tour([1])] // tour([1]) is full at night 1

  it('passes everything through when disabled', () => {
    expect(filterByAvailability(tours, false, false, ohrsIdByHutIndex, freeByOffset)).toBe(tours)
  })
  it('passes everything through when there is no freeByOffset yet', () => {
    expect(filterByAvailability(tours, true, false, ohrsIdByHutIndex, null)).toBe(tours)
  })
  it('drops full tours when enabled and showFullToo is off', () => {
    expect(filterByAvailability(tours, true, false, ohrsIdByHutIndex, freeByOffset)).toEqual([tour([0])])
  })
  it('keeps full tours (marked, not hidden) when showFullToo is on', () => {
    expect(filterByAvailability(tours, true, true, ohrsIdByHutIndex, freeByOffset)).toBe(tours)
  })
})
