import { createContext, useContext, useEffect, useMemo, useReducer } from 'react'
import type { ReactNode } from 'react'
import type { Trip } from './trip.js'
import { initialTripsState, tripsReducer } from './tripsReducer.js'
import type { TripsAction, TripsState } from './tripsReducer.js'
import { browserStorage, loadTrips, saveTrips } from './tripStorage.js'

export interface TripsContextValue {
  state: TripsState
  dispatch: (action: TripsAction) => void
  activeTrip: Trip | null
}

const TripsContext = createContext<TripsContextValue | null>(null)

// Lives above the router so switching Planen <-> Meine Touren keeps the same in-memory state.
// Autosave: every state change is written straight to storage, so there is no unsaved state.
export function TripsProvider({ children, storage }: { children: ReactNode; storage?: Parameters<typeof loadTrips>[0] }) {
  const resolvedStorage = storage === undefined ? browserStorage() : storage
  const [state, dispatch] = useReducer(tripsReducer, undefined, () => initialTripsState(loadTrips(resolvedStorage)))

  useEffect(() => {
    saveTrips({ trips: state.trips, activeId: state.activeId }, resolvedStorage)
  }, [state.trips, state.activeId, resolvedStorage])

  const value = useMemo<TripsContextValue>(() => ({
    state, dispatch, activeTrip: state.trips.find((t) => t.id === state.activeId) ?? null,
  }), [state])
  return <TripsContext.Provider value={value}>{children}</TripsContext.Provider>
}

export function useTrips(): TripsContextValue {
  const value = useContext(TripsContext)
  if (!value) throw new Error('useTrips must be used inside <TripsProvider>')
  return value
}
