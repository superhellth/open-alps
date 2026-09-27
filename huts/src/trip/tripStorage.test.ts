import { describe, it, expect } from 'vitest'
import { newTrip } from './trip.js'
import { loadTrips, saveTrips, exportTripsJson, parseTripsJson } from './tripStorage.js'
import type { StorageLike } from './tripStorage.js'

const trip = (id: string) => newTrip({
  name: id, startDate: null, partySize: 1, start: { startId: 1, sourceType: 1 }, huts: ['{A}'],
  exit: { startId: 1, sourceType: 1 }, variant: { sacCeiling: null, allowUngraded: false },
}, new Date('2026-06-01T00:00:00Z'), id)

function memoryStorage(initial: Record<string, string> = {}): StorageLike {
  const data = new Map<string, string>(Object.entries(initial))
  return { getItem: (k) => data.get(k) ?? null, setItem: (k, v) => { data.set(k, v) } }
}

describe('tripStorage', () => {
  it('round-trips trips and the active id', () => {
    const storage = memoryStorage()
    saveTrips({ trips: [trip('a'), trip('b')], activeId: 'b', draft: null, activeIsDraft: false }, storage)
    expect(loadTrips(storage)).toEqual({ trips: [trip('a'), trip('b')], activeId: 'b', draft: null, activeIsDraft: false })
  })
  it('returns an empty state when nothing is stored', () => {
    expect(loadTrips(memoryStorage())).toEqual({ trips: [], activeId: null, draft: null, activeIsDraft: false })
  })
  it('drops invalid trips and an active id that points nowhere', () => {
    const storage = memoryStorage({
      'open-alps.trips.v1': JSON.stringify({ trips: [trip('a'), { junk: true }], activeId: 'gone' }),
    })
    expect(loadTrips(storage)).toEqual({ trips: [trip('a')], activeId: null, draft: null, activeIsDraft: false })
  })
  it('survives corrupt JSON', () => {
    expect(loadTrips(memoryStorage({ 'open-alps.trips.v1': '{not json' }))).toEqual({ trips: [], activeId: null, draft: null, activeIsDraft: false })
  })
  it('survives unavailable storage (null, throwing get/set)', () => {
    expect(loadTrips(null)).toEqual({ trips: [], activeId: null, draft: null, activeIsDraft: false })
    expect(saveTrips({ trips: [], activeId: null, draft: null, activeIsDraft: false }, null)).toBe(false)
    const throwing = { getItem: () => { throw new Error('denied') }, setItem: () => { throw new Error('quota') } }
    expect(loadTrips(throwing)).toEqual({ trips: [], activeId: null, draft: null, activeIsDraft: false })
    expect(saveTrips({ trips: [], activeId: null, draft: null, activeIsDraft: false }, throwing)).toBe(false)
  })
  it('exports and re-imports a backup, skipping invalid entries', () => {
    const json = exportTripsJson({ trips: [trip('a')], activeId: 'a', draft: null, activeIsDraft: false })
    expect(parseTripsJson(json)).toEqual([trip('a')])
    expect(parseTripsJson('{"trips":[{"x":1}]}')).toEqual([])
    expect(parseTripsJson('nope')).toBeNull()
  })
  it('round-trips a draft through save/load', () => {
    const storage = memoryStorage()
    const draft = trip('d1')
    saveTrips({ trips: [], activeId: null, draft, activeIsDraft: true }, storage)
    expect(loadTrips(storage)).toEqual({ trips: [], activeId: null, draft, activeIsDraft: true })
  })
  it('drops an invalid draft and clears activeIsDraft when loading', () => {
    const storage = memoryStorage()
    storage.setItem('open-alps.trips.v1', JSON.stringify({ trips: [], activeId: null, draft: { not: 'a trip' }, activeIsDraft: true }))
    expect(loadTrips(storage)).toEqual({ trips: [], activeId: null, draft: null, activeIsDraft: false })
  })
  it('defaults draft/activeIsDraft when absent (pre-draft-model storage)', () => {
    const storage = memoryStorage()
    storage.setItem('open-alps.trips.v1', JSON.stringify({ trips: [], activeId: null }))
    expect(loadTrips(storage)).toEqual({ trips: [], activeId: null, draft: null, activeIsDraft: false })
  })
})
