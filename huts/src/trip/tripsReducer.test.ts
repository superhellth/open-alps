import { describe, it, expect } from 'vitest'
import { newTrip } from './trip.js'
import { initialTripsState, tripsReducer } from './tripsReducer.js'

const trip = (id: string) => newTrip({
  name: id, startDate: null, partySize: 1, start: { startId: 1, sourceType: 1 }, huts: ['{A}'],
  exit: { startId: 1, sourceType: 1 }, variant: { sacCeiling: null, allowUngraded: false },
}, new Date('2026-06-01T00:00:00Z'), id)

const empty = initialTripsState({ trips: [], activeId: null })

describe('tripsReducer', () => {
  it('create adds the trip and makes it active', () => {
    const s = tripsReducer(empty, { type: 'create', trip: trip('a') })
    expect(s.trips.map((t) => t.id)).toEqual(['a'])
    expect(s.activeId).toBe('a')
  })
  it('update replaces the trip by id and bumps updatedAt', () => {
    const s0 = tripsReducer(empty, { type: 'create', trip: trip('a') })
    const s1 = tripsReducer(s0, { type: 'update', trip: { ...trip('a'), name: 'neu' }, now: new Date('2026-07-01T00:00:00Z') })
    expect(s1.trips[0].name).toBe('neu')
    expect(s1.trips[0].updatedAt).toBe('2026-07-01T00:00:00.000Z')
  })
  it('setActive(null) returns to discover with no active trip', () => {
    const s0 = tripsReducer(empty, { type: 'create', trip: trip('a') })
    expect(tripsReducer(s0, { type: 'setActive', id: null }).activeId).toBeNull()
  })
  it('delete removes the trip, clears activeId if it was active, and undo restores it at the same index', () => {
    let s = empty
    for (const id of ['a', 'b', 'c']) s = tripsReducer(s, { type: 'create', trip: trip(id) })
    s = tripsReducer(s, { type: 'setActive', id: 'b' })
    s = tripsReducer(s, { type: 'delete', id: 'b' })
    expect(s.trips.map((t) => t.id)).toEqual(['a', 'c'])
    expect(s.activeId).toBeNull()
    s = tripsReducer(s, { type: 'undoDelete' })
    expect(s.trips.map((t) => t.id)).toEqual(['a', 'b', 'c'])
    expect(s.deleted).toBeNull()
  })
  it('import appends trips and re-ids any whose id already exists', () => {
    const s0 = tripsReducer(empty, { type: 'create', trip: trip('a') })
    const s1 = tripsReducer(s0, { type: 'import', trips: [trip('a'), trip('z')], makeId: () => 'fresh' })
    expect(s1.trips.map((t) => t.id)).toEqual(['a', 'fresh', 'z'])
  })
})
