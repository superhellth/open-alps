import { describe, it, expect } from 'vitest'
import { newTrip } from './trip.js'
import { initialTripsState, isDraftDirty, tripsReducer } from './tripsReducer.js'

const trip = (id: string) => newTrip({
  name: id, startDate: null, partySize: 1, start: { startId: 1, sourceType: 1 }, huts: ['{A}'],
  exit: { startId: 1, sourceType: 1 }, variant: { sacCeiling: null, allowUngraded: false },
}, new Date('2026-06-01T00:00:00Z'), id)

const empty = initialTripsState({ trips: [], activeId: null, draft: null, activeIsDraft: false })

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
  it('closeActive returns to discover with no active trip', () => {
    const s0 = tripsReducer(empty, { type: 'create', trip: trip('a') })
    expect(tripsReducer(s0, { type: 'closeActive' }).activeId).toBeNull()
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

describe('draft lifecycle', () => {
  it('openDraft sets the draft, opens it, and takes a baseline snapshot', () => {
    const next = tripsReducer(empty, { type: 'openDraft', trip: trip('a') })
    expect(next.draft).toEqual(trip('a'))
    expect(next.draftBaseline).toEqual(trip('a'))
    expect(next.activeIsDraft).toBe(true)
    expect(next.activeId).toBeNull()
  })

  it('updateDraft replaces the draft in place without touching the baseline', () => {
    const t = trip('a')
    let state = tripsReducer(empty, { type: 'openDraft', trip: t })
    const edited = { ...t, partySize: 3 }
    state = tripsReducer(state, { type: 'updateDraft', trip: edited, now: new Date('2026-01-01T00:00:00Z') })
    expect(state.draft?.partySize).toBe(3)
    expect(state.draft?.updatedAt).toBe('2026-01-01T00:00:00.000Z')
    expect(state.draftBaseline).toEqual(t)
  })

  it('saveDraft moves the draft into trips and clears the slot', () => {
    const t = trip('a')
    let state = tripsReducer(empty, { type: 'openDraft', trip: t })
    state = tripsReducer(state, { type: 'saveDraft', now: new Date('2026-01-01T00:00:00Z') })
    expect(state.trips).toEqual([{ ...t, updatedAt: '2026-01-01T00:00:00.000Z' }])
    expect(state.draft).toBeNull()
    expect(state.draftBaseline).toBeNull()
    expect(state.activeIsDraft).toBe(false)
    expect(state.activeId).toBe(t.id)
  })

  it('saveDraft applies the given name', () => {
    const t = trip('a')
    let state = tripsReducer(empty, { type: 'openDraft', trip: t })
    state = tripsReducer(state, { type: 'saveDraft', name: 'Eigener Name' })
    expect(state.trips[0].name).toBe('Eigener Name')
  })

  it('unsave turns a saved trip back into the open draft', () => {
    const t = trip('a')
    const saved = tripsReducer(tripsReducer(empty, { type: 'openDraft', trip: t }), { type: 'saveDraft' })
    const state = tripsReducer(saved, { type: 'unsave', id: t.id })
    expect(state.trips).toEqual([])
    expect(state.draft).toEqual(saved.trips[0])
    expect(state.activeIsDraft).toBe(true)
    expect(state.activeId).toBeNull()
    expect(state.deleted).toBeNull()
    expect(state.unsaved).toEqual({ id: t.id, index: 0 })
  })

  it('undoUnsave puts the draft back at its list position and reopens it as saved', () => {
    const [a, b] = [trip('a'), trip('b')]
    let state = tripsReducer(tripsReducer(empty, { type: 'create', trip: a }), { type: 'create', trip: b })
    state = tripsReducer(state, { type: 'unsave', id: a.id })
    state = tripsReducer(state, { type: 'updateDraft', trip: { ...a, name: 'Umbenannt' } })
    state = tripsReducer(state, { type: 'undoUnsave' })
    expect(state.trips.map((t) => t.id)).toEqual([a.id, b.id])
    expect(state.trips[0].name).toBe('Umbenannt')
    expect(state.draft).toBeNull()
    expect(state.activeId).toBe(a.id)
    expect(state.activeIsDraft).toBe(false)
    expect(state.unsaved).toBeNull()
  })

  it('undoUnsave is a no-op once another draft replaced the unsaved trip', () => {
    const a = trip('a')
    let state = tripsReducer(empty, { type: 'create', trip: a })
    state = tripsReducer(state, { type: 'unsave', id: a.id })
    state = tripsReducer(state, { type: 'openDraft', trip: trip('b') })
    expect(state.unsaved).toBeNull()
    expect(tripsReducer(state, { type: 'undoUnsave' })).toBe(state)
  })

  it('saveDraft is a no-op when there is no draft', () => {
    expect(tripsReducer(empty, { type: 'saveDraft' })).toBe(empty)
  })

  it('closeActive clears activeId/activeIsDraft but keeps the draft', () => {
    const t = trip('a')
    let state = tripsReducer(empty, { type: 'openDraft', trip: t })
    state = tripsReducer(state, { type: 'closeActive' })
    expect(state.activeId).toBeNull()
    expect(state.activeIsDraft).toBe(false)
    expect(state.draft).toEqual(t)
  })

  it('setActive opens a saved trip and clears activeIsDraft', () => {
    const t = trip('a')
    const state = { ...tripsReducer(empty, { type: 'create', trip: t }), activeIsDraft: true, draft: trip('b') }
    const next = tripsReducer(state, { type: 'setActive', id: t.id })
    expect(next.activeId).toBe(t.id)
    expect(next.activeIsDraft).toBe(false)
  })

  it('reopenDraft makes the existing draft active again', () => {
    const draftTrip = trip('a')
    const withDraft = tripsReducer(empty, { type: 'openDraft', trip: draftTrip })
    const closed = tripsReducer(withDraft, { type: 'closeActive' })
    expect(closed.activeIsDraft).toBe(false)
    const reopened = tripsReducer(closed, { type: 'reopenDraft' })
    expect(reopened.activeIsDraft).toBe(true)
    expect(reopened.activeId).toBeNull()
    expect(reopened.draft).toBe(draftTrip)
  })

  it('reopenDraft is a no-op with no draft', () => {
    expect(tripsReducer(empty, { type: 'reopenDraft' })).toBe(empty)
  })
})

describe('isDraftDirty', () => {
  it('is false with no draft, or an unedited draft', () => {
    const opened = tripsReducer(empty, { type: 'openDraft', trip: trip('a') })
    expect(isDraftDirty(empty)).toBe(false)
    expect(isDraftDirty(opened)).toBe(false)
  })

  it('is true after huts, dates, party size, start or exit change', () => {
    const t = trip('a')
    const opened = tripsReducer(empty, { type: 'openDraft', trip: t })
    expect(isDraftDirty(tripsReducer(opened, { type: 'updateDraft', trip: { ...t, partySize: 2 } }))).toBe(true)
    expect(isDraftDirty(tripsReducer(opened, { type: 'updateDraft', trip: { ...t, huts: ['{A}', '{B}'] } }))).toBe(true)
    expect(isDraftDirty(tripsReducer(opened, { type: 'updateDraft', trip: { ...t, startDate: '2026-07-01' } }))).toBe(true)
    expect(isDraftDirty(tripsReducer(opened, { type: 'updateDraft', trip: { ...t, exit: { startId: 99, sourceType: 1 } } }))).toBe(true)
  })

  it('is false when only the name or booking status changes', () => {
    const t = trip('a')
    const opened = tripsReducer(empty, { type: 'openDraft', trip: t })
    expect(isDraftDirty(tripsReducer(opened, { type: 'updateDraft', trip: { ...t, name: 'Renamed' } }))).toBe(false)
  })
})
