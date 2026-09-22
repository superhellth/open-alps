import { describe, it, expect } from 'vitest'
import { filterOfficial, nightStateOf, sortTours } from './rankTours.js'
import { DEFAULT_FORM, rankTargetsFromForm } from './formState.js'
import type { PlannerTour } from './tours.js'
import type { FreeByOffset } from '../availability/types.js'

const tour = (huts: number[], durations: number[], over: Partial<PlannerTour> = {}): PlannerTour => ({
  huts, startId: 1, exitStartId: 1, totalDurationH: durations.reduce((s, d) => s + d, 0), totalAscentM: durations.length * 100,
  totalDescentM: 0, totalDistanceM: durations.length * 1000,
  legs: durations.map((durationH) => ({ durationH, ascentM: 100, descentM: 0, distanceM: 1000, edgeId: 0, reversed: false })), ...over,
})
const ohrs = new Map<number, string | null>([[0, 'H0'], [1, null], [2, 'H2']])

describe('nightStateOf', () => {
  const free: FreeByOffset = new Map<number, Set<string> | 'unknown'>([[1, new Set(['H0'])], [2, 'unknown'], [3, new Set()]])
  it('reads night n at offset n+1', () => {
    expect(nightStateOf(tour([0], [5, 5]), 0, ohrs, free)).toBe('free')
    expect(nightStateOf(tour([2, 2, 2], [5, 5, 5, 5]), 2, ohrs, free)).toBe('full')
  })
  it('is unknown for a hut without OHRS id, a failed night, or no availability at all', () => {
    expect(nightStateOf(tour([1], [5, 5]), 0, ohrs, free)).toBe('unknown')
    expect(nightStateOf(tour([2, 2], [5, 5, 5]), 1, ohrs, free)).toBe('unknown')
    expect(nightStateOf(tour([0], [5, 5]), 0, ohrs, null)).toBe('unknown')
  })
})

describe('sortTours', () => {
  const targets = rankTargetsFromForm(DEFAULT_FORM, [2, 4], 3)
  const args = { targets, ohrsIdByHutIndex: ohrs, freeByOffset: null }
  const balanced = tour([0, 1], [6, 6, 6])
  const short = tour([0], [3, 3])
  it('fit puts the tour nearest the targets first', () => {
    expect(sortTours([short, balanced], 'fit', args)[0]).toBe(balanced)
  })
  it('fit demotes tours with a full night when a date is set', () => {
    const free: FreeByOffset = new Map([[1, new Set(['H0'])], [2, new Set()]])
    const a = tour([0, 2], [6, 6, 6]) // night 1 at offset 2: H2 not free -> full
    const b = tour([0, 1], [6, 6, 6]) // night 1: no OHRS id -> unknown
    expect(sortTours([a, b], 'fit', { ...args, freeByOffset: free })[0]).toBe(b)
  })
  it('the other keys sort ascending', () => {
    expect(sortTours([balanced, short], 'duration', args)[0]).toBe(short)
    expect(sortTours([balanced, short], 'ascent', args)[0]).toBe(short)
    expect(sortTours([balanced, short], 'distance', args)[0]).toBe(short)
  })
  it('does not mutate its input', () => {
    const input = [balanced, short]
    sortTours(input, 'duration', args)
    expect(input[0]).toBe(balanced)
  })
})

describe('filterOfficial', () => {
  const startById = new Map([[1, { name: 'S', sourceType: 1, lat: 0, lng: 0 }], [2, { name: 'P', sourceType: 2, lat: 0, lng: 0 }]])
  const form = { ...DEFAULT_FORM, mode: 'transit' as const, legTimeCeilingH: 7 as const }
  it('keeps official tours inside the leg-count range and the leg-time ceiling', () => {
    const ok = tour([0], [5, 5], { official: { tourId: 1, name: 'a' } })
    const tooManyLegs = tour([0, 1, 2, 3, 4], [5, 5, 5, 5, 5, 5], { official: { tourId: 2, name: 'b' } })
    const tooLong = tour([0], [5, 9], { official: { tourId: 3, name: 'c' } })
    const wrongMode = tour([0], [5, 5], { startId: 2, exitStartId: 2, official: { tourId: 4, name: 'd' } })
    expect(filterOfficial([ok, tooManyLegs, tooLong, wrongMode], form, [2, 4], startById)).toEqual([ok])
  })
})
