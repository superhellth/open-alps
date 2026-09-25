import { describe, it, expect } from 'vitest'
import { officialToTour } from './plannerTour.js'
import type { OfficialTourView } from './officialTours.js'

const leg = (legIndex: number, from: [string, number], to: [string, number], durationH: number) => ({
  legIndex, from: { type: from[0], id: from[1] }, to: { type: to[0], id: to[1] }, edgeId: legIndex, reversed: false as const,
  distanceM: 1000, ascentM: 100, descentM: 50, durationH, maxEleM: 2000,
}) as unknown as OfficialTourView['legs'][number]

const view = (legs: OfficialTourView['legs']): OfficialTourView => ({
  tourId: 7, name: 'Tour', legs, totalDistanceM: legs.length * 1000, totalAscentM: legs.length * 100,
  totalDescentM: legs.length * 50, totalDurationH: legs.reduce((s, l) => s + l.durationH, 0),
})

describe('officialToTour', () => {
  it('maps start point, intermediate huts, exit and leg summaries, tagged as official', () => {
    const t = officialToTour(view([
      leg(0, ['station', 100], ['hut', 4], 5), leg(1, ['hut', 4], ['hut', 5], 6), leg(2, ['hut', 5], ['station', 101], 4),
    ]))!
    expect(t).toMatchObject({ startId: 100, exitStartId: 101, huts: [4, 5], official: { tourId: 7, name: 'Tour' } })
    expect(t.legs.map((l) => l.durationH)).toEqual([5, 6, 4])
    expect(t.legs.every((l) => !l.reversed)).toBe(true)
    expect(t.totalDurationH).toBe(15)
  })
  it('is null when the tour begins or ends at a hut instead of a start point', () => {
    expect(officialToTour(view([leg(0, ['hut', 4], ['hut', 5], 5), leg(1, ['hut', 5], ['station', 1], 4)]))).toBeNull()
    expect(officialToTour(view([leg(0, ['station', 1], ['hut', 4], 5), leg(1, ['hut', 4], ['hut', 5], 4)]))).toBeNull()
  })
})
