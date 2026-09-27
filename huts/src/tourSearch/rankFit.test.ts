import { describe, it, expect } from 'vitest'
import { fitScore, rankFit } from './rankFit.js'
import type { FitTour, RankTargets } from './rankFit.js'

const targets: RankTargets = { legCountTarget: 4, legCountRange: [2, 6], legTimeRangeH: [4, 8] }
const tour = (durations: number[], huts = durations.length - 1): FitTour & { id: string } => ({
  id: durations.join(','), huts: Array.from({ length: huts }, (_, i) => i), legs: durations.map((durationH) => ({ durationH })),
})

describe('fitScore', () => {
  it('prefers the target day count', () => {
    expect(fitScore(tour([6, 6, 6, 6]), targets)).toBeLessThan(fitScore(tour([6, 6]), targets))
  })
  it('prefers per-day time near the middle of the range', () => {
    expect(fitScore(tour([6, 6, 6, 6]), targets)).toBeLessThan(fitScore(tour([4, 4, 4, 4]), targets))
  })
  it('prefers even days over uneven ones with the same mean', () => {
    expect(fitScore(tour([6, 6, 6, 6]), targets)).toBeLessThan(fitScore(tour([4, 8, 4, 8]), targets))
  })
  it('scores unknown availability between free and full', () => {
    const t = tour([6, 6, 6, 6])
    const of = (state: 'free' | 'full' | 'unknown') => fitScore(t, targets, () => state)
    expect(of('free')).toBeLessThan(of('unknown'))
    expect(of('unknown')).toBeLessThan(of('full'))
  })
})

describe('rankFit', () => {
  it('sorts best fit first and keeps input order for ties', () => {
    const a = tour([6, 6, 6, 6]); const b = tour([6, 6]); const c = { ...a, id: 'c' }
    expect(rankFit([b, a, c], targets).map((t) => t.id)).toEqual(['6,6,6,6', 'c', '6,6'])
  })
  it('passes the tour and night index to the availability callback', () => {
    const calls: [string, number][] = []
    rankFit([tour([6, 6, 6])], targets, (t, night) => { calls.push([t.id, night]); return 'free' })
    expect(calls).toEqual([['6,6,6', 0], ['6,6,6', 1]])
  })
})
