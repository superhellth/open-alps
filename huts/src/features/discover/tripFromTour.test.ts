import { describe, it, expect } from 'vitest'
import { tripFromTour } from './tripFromTour.js'
import type { PlannerTour } from '@/tourSearch/plannerTour.js'

const ctx = {
  hutIds: ['{A}', '{B}', '{C}'],
  startById: new Map([[100, { name: 'Bahnhof X', sourceType: 1, lat: 0, lng: 0 }]]),
  hutNameById: new Map([[0, 'Hütte A'], [2, 'Hütte C']]),
  startLabel: (id: number) => (id === 100 ? 'Bahnhof X' : `Startpunkt ${id}`),
  form: { sacCeiling: 3 as number | 'any', allowUngraded: true },
  draft: { startDate: '2026-07-10', endDate: '2026-07-12', partySize: 2 },
}
const chain: PlannerTour = {
  huts: [0, 2], startId: 100, exitStartId: 100, totalDurationH: 10, totalAscentM: 0, totalDescentM: 0, totalDistanceM: 0, legs: [],
}

describe('tripFromTour', () => {
  it('stores GUIDs and start ids, copies date, party and the difficulty variant from the search', () => {
    const t = tripFromTour(chain, ctx)!
    expect(t.huts).toEqual(['{A}', '{C}'])
    expect(t.start).toEqual({ startId: 100, sourceType: 1 })
    expect(t.exit).toEqual({ startId: 100, sourceType: 1 })
    expect(t.startDate).toBe('2026-07-10')
    expect(t.partySize).toBe(2)
    expect(t.variant).toEqual({ sacCeiling: 3, allowUngraded: true })
    expect(t.nights).toEqual([{ status: 'open' }, { status: 'open' }])
    expect(t.name).toBe('Bahnhof X: Hütte A – Hütte C')
    expect(t.source).toBeUndefined()
  })
  it('an unset difficulty ceiling is stored as null; an empty date as null', () => {
    const t = tripFromTour(chain, { ...ctx, form: { sacCeiling: 'any', allowUngraded: false }, draft: { startDate: '', endDate: '', partySize: 1 } })!
    expect(t.variant).toEqual({ sacCeiling: null, allowUngraded: false })
    expect(t.startDate).toBeNull()
  })
  it('an official tour keeps its name and source and resolves its graph with the unconstrained variant', () => {
    const t = tripFromTour({ ...chain, official: { tourId: 7, name: 'Kaisertour' } }, ctx)!
    expect(t.name).toBe('Kaisertour')
    expect(t.source).toEqual({ kind: 'official', tourId: 7 })
    expect(t.variant).toEqual({ sacCeiling: null, allowUngraded: true })
  })
  it('is null when a start point is unknown', () => {
    expect(tripFromTour({ ...chain, startId: 5 }, ctx)).toBeNull()
  })
})
