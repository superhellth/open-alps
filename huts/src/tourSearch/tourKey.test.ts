import { describe, it, expect } from 'vitest'
import { tourKey, NO_TOURS } from './tourKey.js'
import type { PlannerTour } from './plannerTour.js'

const tour = (over: Partial<PlannerTour> = {}): PlannerTour => ({
  huts: [3, 4], startId: 1, exitStartId: 1, totalDurationH: 1, totalAscentM: 0, totalDescentM: 0, totalDistanceM: 0, legs: [], ...over,
} as PlannerTour)

describe('tourKey', () => {
  it('differs when only the exit point differs', () => {
    expect(tourKey(tour({ exitStartId: 1 }))).not.toBe(tourKey(tour({ exitStartId: 2 })))
  })
  it('is stable for equal tours', () => {
    expect(tourKey(tour())).toBe(tourKey(tour()))
  })
})

describe('NO_TOURS', () => {
  it('is empty', () => { expect(NO_TOURS.size).toBe(0) })
})
