// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import type { ReactNode } from 'react'
import { renderHook, act, cleanup } from '@testing-library/react'
import { useTripSession } from './useTripSession.js'
import { TripsProvider } from '@/trip/TripsProvider.js'
import { useTrips } from '@/trip/tripsContext.js'
import { newTrip } from '@/trip/trip.js'
import { saveTrips } from '@/trip/tripStorage.js'
import { makeTestAppData } from '@/testing/testAppData.js'
import type { SearchClient } from '@/search/searchClient.js'

afterEach(cleanup)

const trip = (id: string, huts: string[]) => newTrip({
  name: id, startDate: null, partySize: 1, start: { startId: 100, sourceType: 1 }, huts,
  exit: { startId: 100, sourceType: 1 }, variant: { sacCeiling: null, allowUngraded: false },
}, new Date('2026-06-01T00:00:00Z'), id)

const memoryStorage = () => {
  const data: Record<string, string> = {}
  return { getItem: (k: string) => data[k] ?? null, setItem: (k: string, v: string) => { data[k] = v } }
}
const data = makeTestAppData()
const client: SearchClient = { ready: Promise.resolve(), search: vi.fn(), overlaps: () => Promise.resolve([]), dispose: () => {} }
const startLabel = (id: number) => String(id)

function setup(storage = memoryStorage()) {
  const wrapper = ({ children }: { children: ReactNode }) => <TripsProvider storage={storage}>{children}</TripsProvider>
  return renderHook(() => ({ session: useTripSession({ data, client, startLabel }), trips: useTrips() }), { wrapper })
}

describe('useTripSession', () => {
  it('is in discover mode until a saved trip is set active', () => {
    const storage = memoryStorage()
    saveTrips({ trips: [trip('a', ['{D}', '{E}'])], activeId: null, draft: null, activeIsDraft: false }, storage)
    const { result } = setup(storage)
    expect(result.current.session.mode).toBe('discover')
    act(() => result.current.trips.dispatch({ type: 'setActive', id: 'a' }))
    expect(result.current.session.mode).toBe('trip')
    expect(result.current.session.tripLegs).not.toBeNull()
  })

  it('openDraft opens a clean draft directly', () => {
    const { result } = setup()
    let opened = false
    act(() => { opened = result.current.session.openDraft(trip('d1', ['{D}', '{E}'])) })
    expect(opened).toBe(true)
    expect(result.current.session.pendingPick).toBeNull()
    expect(result.current.session.activeTrip?.id).toBe('d1')
  })

  it('openDraft while the draft has unsaved edits waits in pendingPick until confirmed', () => {
    const { result } = setup()
    act(() => { result.current.session.openDraft(trip('d1', ['{D}', '{E}'])) })
    act(() => result.current.trips.dispatch({ type: 'updateDraft', trip: { ...trip('d1', ['{D}']) } }))
    expect(result.current.trips.draftDirty).toBe(true)
    let opened = true
    const next = trip('d2', ['{D}', '{E}'])
    act(() => { opened = result.current.session.openDraft(next) })
    expect(opened).toBe(false)
    expect(result.current.session.pendingPick).toBe(next)
    expect(result.current.session.activeTrip?.id).toBe('d1')
    act(() => result.current.session.confirmDiscardDraft())
    expect(result.current.session.pendingPick).toBeNull()
    expect(result.current.session.activeTrip?.id).toBe('d2')
  })
})
