import type { Trip } from './trip.js'
import type { StoredTrips } from './tripStorage.js'

export interface TripsState extends StoredTrips {
  /** The most recent deletion, kept so it can be undone. */
  deleted: { trip: Trip; index: number } | null
}

export type TripsAction =
  | { type: 'create'; trip: Trip }
  | { type: 'update'; trip: Trip; now?: Date }
  | { type: 'setActive'; id: string | null }
  | { type: 'delete'; id: string }
  | { type: 'undoDelete' }
  | { type: 'import'; trips: Trip[]; makeId?: () => string }

export function initialTripsState(stored: StoredTrips): TripsState {
  return { ...stored, deleted: null }
}

export function tripsReducer(state: TripsState, action: TripsAction): TripsState {
  switch (action.type) {
    case 'create':
      return { ...state, trips: [...state.trips, action.trip], activeId: action.trip.id }
    case 'update': {
      const updatedAt = (action.now ?? new Date()).toISOString()
      return {
        ...state,
        trips: state.trips.map((t) => (t.id === action.trip.id ? { ...action.trip, updatedAt } : t)),
      }
    }
    case 'setActive':
      return { ...state, activeId: action.id }
    case 'delete': {
      const index = state.trips.findIndex((t) => t.id === action.id)
      if (index === -1) return state
      return {
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
