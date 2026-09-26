import { describe, it, expect } from 'vitest'
import { tourBoardLabel } from './tourBoard.js'
import type { PlannerTour } from '@/tourSearch/plannerTour.js'
import type { StartPoint } from '@/data/types.js'

const start = (name: string | null, sourceType: number): StartPoint => ({ name, sourceType, lat: 47, lng: 11 }) as StartPoint
const startById = new Map<number, StartPoint>([
  [1, start('Kaprun', 1)], [2, start('Kaunertal', 2)], [3, start(null, 2)],
])
const tour = (over: Partial<PlannerTour> = {}): PlannerTour => ({
  huts: [], startId: 1, exitStartId: 2, totalDurationH: 18.4, totalAscentM: 3210, totalDescentM: 0, totalDistanceM: 42_300, legs: [], ...over,
} as PlannerTour)

describe('tourBoardLabel', () => {
  it('shows distance and ascent, with route and walking time in the title', () => {
    const l = tourBoardLabel(tour(), startById)
    expect(l.text).toBe('42.3 km')
    expect(l.detail).toBe('↑ 3.210 m')
    expect(l.title).toBe('Kaprun → Kaunertal (Parkplatz) · 42.3 km · ↑ 3.210 m · 18½ Std')
  })
  it('marks a round trip', () => {
    const l = tourBoardLabel(tour({ exitStartId: 1 }), startById)
    expect(l.text).toBe('42.3 km')
    expect(l.roundTrip).toBe(true)
    expect(l.title).toContain('Rundtour ab Kaprun')
  })
  it('falls back to the kind label for an unnamed exit', () => {
    expect(tourBoardLabel(tour({ exitStartId: 3 }), startById).title).toContain('→ Parkplatz ·')
  })
  it('does not crash when the exit is missing from startById', () => {
    expect(tourBoardLabel(tour({ exitStartId: 99 }), startById).title).toContain('→ Startpunkt 99')
  })
})
