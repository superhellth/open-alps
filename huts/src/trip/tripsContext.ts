import { createContext, useContext } from 'react'
import type { Trip } from './trip.js'
import type { TripsAction, TripsState } from './tripsReducer.js'

export interface TripsContextValue {
  state: TripsState
  dispatch: (action: TripsAction) => void
  activeTrip: Trip | null
  isDraft: boolean
  draftDirty: boolean
}

export const TripsContext = createContext<TripsContextValue | null>(null)

export function useTrips(): TripsContextValue {
  const value = useContext(TripsContext)
  if (!value) throw new Error('useTrips must be used inside <TripsProvider>')
  return value
}
