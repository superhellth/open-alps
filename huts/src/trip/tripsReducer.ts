import type { Trip, TripEndpoint } from './trip.js'
import type { StoredTrips } from './tripStorage.js'

export interface TripsState extends StoredTrips {
  /** Snapshot of `draft` as it was when opened; compared against the live draft to detect edits. */
  draftBaseline: Trip | null
  /** The most recent deletion, kept so it can be undone. */
  deleted: { trip: Trip; index: number } | null
}

export type TripsAction =
  | { type: 'create'; trip: Trip }
  | { type: 'update'; trip: Trip; now?: Date }
  | { type: 'openDraft'; trip: Trip }
  | { type: 'updateDraft'; trip: Trip; now?: Date }
  | { type: 'saveDraft'; now?: Date }
  | { type: 'setActive'; id: string }
  | { type: 'closeActive' }
  | { type: 'delete'; id: string }
  | { type: 'undoDelete' }
  | { type: 'import'; trips: Trip[]; makeId?: () => string }
  | { type: 'reopenDraft' }

export function initialTripsState(stored: StoredTrips): TripsState {
  return { ...stored, draftBaseline: stored.draft, deleted: null }
}

function sameEndpoint(a: TripEndpoint, b: TripEndpoint): boolean {
  return a.startId === b.startId && a.sourceType === b.sourceType
}

/** Compares only the fields the "discard draft?" prompt cares about (huts, start/exit, dates,
 *  party size) — renaming the draft or changing booking status never counts as an edit. */
export function isDraftDirty(state: TripsState): boolean {
  if (!state.draft || !state.draftBaseline) return false
  const a = state.draft
  const b = state.draftBaseline
  if (a.startDate !== b.startDate || a.partySize !== b.partySize) return true
  if (!sameEndpoint(a.start, b.start) || !sameEndpoint(a.exit, b.exit)) return true
  if (a.huts.length !== b.huts.length || a.huts.some((h, i) => h !== b.huts[i])) return true
  return false
}

export function tripsReducer(state: TripsState, action: TripsAction): TripsState {
  switch (action.type) {
    case 'create':
      return { ...state, trips: [...state.trips, action.trip], activeId: action.trip.id, activeIsDraft: false }
    case 'update': {
      const updatedAt = (action.now ?? new Date()).toISOString()
      return {
        ...state,
        trips: state.trips.map((t) => (t.id === action.trip.id ? { ...action.trip, updatedAt } : t)),
      }
    }
    case 'openDraft':
      return { ...state, draft: action.trip, draftBaseline: action.trip, activeId: null, activeIsDraft: true }
    case 'updateDraft': {
      if (!state.draft) return state
      const updatedAt = (action.now ?? new Date()).toISOString()
      return { ...state, draft: { ...action.trip, updatedAt } }
    }
    case 'saveDraft': {
      if (!state.draft) return state
      const updatedAt = (action.now ?? new Date()).toISOString()
      const trip = { ...state.draft, updatedAt }
      return { ...state, trips: [...state.trips, trip], draft: null, draftBaseline: null, activeId: trip.id, activeIsDraft: false }
    }
    case 'reopenDraft':
      return state.draft ? { ...state, activeId: null, activeIsDraft: true } : state
    case 'setActive':
      return { ...state, activeId: action.id, activeIsDraft: false }
    case 'closeActive':
      return { ...state, activeId: null, activeIsDraft: false }
    case 'delete': {
      const index = state.trips.findIndex((t) => t.id === action.id)
      if (index === -1) return state
      return {
        ...state,
        trips: state.trips.filter((t) => t.id !== action.id),
        activeId: state.activeId === action.id ? null : state.activeId,
        deleted: { trip: state.trips[index], index },
      }
    }
    case 'undoDelete': {
      if (!state.deleted) return state
      const trips = [...state.trips]
      trips.splice(state.deleted.index, 0, state.deleted.trip)
      return { ...state, trips, deleted: null }
    }
    case 'import': {
      const makeId = action.makeId ?? (() => crypto.randomUUID())
      const taken = new Set(state.trips.map((t) => t.id))
      const added = action.trips.map((t) => {
        const id = taken.has(t.id) ? makeId() : t.id
        taken.add(id)
        return { ...t, id }
      })
      return { ...state, trips: [...state.trips, ...added] }
    }
  }
}
