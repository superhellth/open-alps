import { useEffect, useMemo, useReducer } from 'react'
import type { ReactNode } from 'react'
import { initialTripsState, isDraftDirty, tripsReducer } from './tripsReducer.js'
import { TripsContext } from './tripsContext.js'
import type { TripsContextValue } from './tripsContext.js'
import { browserStorage, loadTrips, saveTrips } from './tripStorage.js'

// Lives above the router so switching Planen <-> Meine Touren keeps the same in-memory state.
// Autosave: every state change is written straight to storage, so there is no unsaved state.
export function TripsProvider({ children, storage }: { children: ReactNode; storage?: Parameters<typeof loadTrips>[0] }) {
  const resolvedStorage = storage === undefined ? browserStorage() : storage
  const [state, dispatch] = useReducer(tripsReducer, undefined, () => initialTripsState(loadTrips(resolvedStorage)))

  useEffect(() => {
    saveTrips({ trips: state.trips, activeId: state.activeId, draft: state.draft, activeIsDraft: state.activeIsDraft }, resolvedStorage)
  }, [state.trips, state.activeId, state.draft, state.activeIsDraft, resolvedStorage])

  const value = useMemo<TripsContextValue>(() => ({
    state, dispatch,
    activeTrip: state.activeIsDraft ? state.draft : state.trips.find((t) => t.id === state.activeId) ?? null,
    isDraft: state.activeIsDraft,
    draftDirty: isDraftDirty(state),
  }), [state])
  return <TripsContext.Provider value={value}>{children}</TripsContext.Provider>
}
