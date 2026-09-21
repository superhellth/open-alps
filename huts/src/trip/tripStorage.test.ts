import { describe, it, expect } from 'vitest'
import { newTrip } from './trip.js'
import { loadTrips, saveTrips, exportTripsJson, parseTripsJson } from './tripStorage.js'

const trip = (id: string) => newTrip({
  name: id, startDate: null, partySize: 1, start: { startId: 1, sourceType: 1 }, huts: ['{A}'],
  exit: { startId: 1, sourceType: 1 }, variant: { sacCeiling: null, allowUngraded: false },
}, new Date('2026-06-01T00:00:00Z'), id)

function memoryStorage(initial: Record<string, string> = {}) {
  const data = { ...initial }
  return {
    getItem: (k: string) => data[k] ?? null,
    setItem: (k: string, v: string) => { data[k] = v },
    data,
  }
}

describe('tripStorage', () => {
  it('round-trips trips and the active id', () => {
    const storage = memoryStorage()
    saveTrips({ trips: [trip('a'), trip('b')], activeId: 'b' }, storage)
    expect(loadTrips(storage)).toEqual({ trips: [trip('a'), trip('b')], activeId: 'b' })
  })
  it('returns an empty state when nothing is stored', () => {
    expect(loadTrips(memoryStorage())).toEqual({ trips: [], activeId: null })
  })
  it('drops invalid trips and an active id that points nowhere', () => {
    const storage = memoryStorage({
      'open-alps.trips.v1': JSON.stringify({ trips: [trip('a'), { junk: true }], activeId: 'gone' }),
    })
    expect(loadTrips(storage)).toEqual({ trips: [trip('a')], activeId: null })
  })
  it('survives corrupt JSON', () => {
    expect(loadTrips(memoryStorage({ 'open-alps.trips.v1': '{not json' }))).toEqual({ trips: [], activeId: null })
  })
  it('survives unavailable storage (null, throwing get/set)', () => {
    expect(loadTrips(null)).toEqual({ trips: [], activeId: null })
    expect(saveTrips({ trips: [], activeId: null }, null)).toBe(false)
    const throwing = { getItem: () => { throw new Error('denied') }, setItem: () => { throw new Error('quota') } }
    expect(loadTrips(throwing)).toEqual({ trips: [], activeId: null })
    expect(saveTrips({ trips: [], activeId: null }, throwing)).toBe(false)
  })
  it('exports and re-imports a backup, skipping invalid entries', () => {
    const json = exportTripsJson({ trips: [trip('a')], activeId: 'a' })
    expect(parseTripsJson(json)).toEqual([trip('a')])
    expect(parseTripsJson('{"trips":[{"x":1}]}')).toEqual([])
    expect(parseTripsJson('nope')).toBeNull()
  })
})
