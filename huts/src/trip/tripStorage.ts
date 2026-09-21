import { parseTrip } from './trip.js'
import type { Trip } from './trip.js'

const STORAGE_KEY = 'open-alps.trips.v1'

export interface StoredTrips {
  trips: Trip[]
  activeId: string | null
}

type StorageLike = Pick<Storage, 'getItem' | 'setItem'>

export function browserStorage(): StorageLike | null {
  try {
    return window.localStorage
  } catch {
    return null
  }
}

function normalize(raw: unknown): StoredTrips {
  const record = typeof raw === 'object' && raw !== null ? (raw as Record<string, unknown>) : {}
  const trips = (Array.isArray(record.trips) ? record.trips : [])
    .map(parseTrip)
    .filter((t): t is Trip => t !== null)
  const activeId = typeof record.activeId === 'string' && trips.some((t) => t.id === record.activeId)
    ? record.activeId
    : null
  return { trips, activeId }
}

export function loadTrips(storage: StorageLike | null = browserStorage()): StoredTrips {
  try {
    const text = storage?.getItem(STORAGE_KEY)
    return text ? normalize(JSON.parse(text)) : { trips: [], activeId: null }
  } catch {
    return { trips: [], activeId: null }
  }
}

/** True when the write went through. */
export function saveTrips(state: StoredTrips, storage: StorageLike | null = browserStorage()): boolean {
  try {
    if (!storage) return false
    storage.setItem(STORAGE_KEY, JSON.stringify(state))
    return true
  } catch {
    return false
  }
}

export function exportTripsJson(state: StoredTrips): string {
  return JSON.stringify({ trips: state.trips, activeId: state.activeId }, null, 2)
}

/** Null when the text is not JSON at all; invalid trip entries are skipped. */
export function parseTripsJson(json: string): Trip[] | null {
  try {
    return normalize(JSON.parse(json)).trips
  } catch {
    return null
  }
}
