import { describe, it, expect } from 'vitest'
import { tourBoardLabel } from './tourBoard.js'
import type { PlannerTour } from '@/tourSearch/plannerTour.js'
import type { StartPoint } from '@/data/types.js'

const start = (name: string | null, sourceType: number): StartPoint => ({ name, sourceType, lat: 47, lng: 11 }) as StartPoint
const startById = new Map<number, StartPoint>([
  [1, start('Kaprun', 1)], [2, start('Kaunertal', 2)], [3, start(null, 2)],
])
const tour = (over: Partial<PlannerTour> = {}): PlannerTour => ({
  huts: [], startId: 1, exitStartId: 2, totalDurationH: 1, totalAscentM: 0, totalDescentM: 0, totalDistanceM: 42_300, legs: [], ...over,
} as PlannerTour)

describe('tourBoardLabel', () => {
  it('shows the bare exit name, the distance and the exit kind', () => {
    const l = tourBoardLabel(tour(), startById)
    expect(l.text).toBe('Kaunertal')
    expect(l.distance).toBe('42.3 km')
    expect(l.sourceType).toBe(2)
    expect(l.title).toContain('Kaunertal (Parkplatz)')
  })
  it('reads Rundtour when the exit is the start', () => {
    expect(tourBoardLabel(tour({ exitStartId: 1 }), startById).text).toBe('Rundtour')
  })
  it('falls back to the kind label for an unnamed exit', () => {
    expect(tourBoardLabel(tour({ exitStartId: 3 }), startById).text).toBe('Parkplatz')
  })
  it('does not crash when the exit is missing from startById', () => {
    const l = tourBoardLabel(tour({ exitStartId: 99 }), startById)
    expect(l.text).toBe('Startpunkt')
    expect(l.distance).toBe('42.3 km')
  })
})
