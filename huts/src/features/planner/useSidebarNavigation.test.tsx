// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import type { ReactNode } from 'react'
import { renderHook, act, cleanup } from '@testing-library/react'
import { useSidebarNavigation } from './useSidebarNavigation.js'
import { TripsProvider } from '@/trip/TripsProvider.js'
import { useTrips } from '@/trip/tripsContext.js'
import { newTrip } from '@/trip/trip.js'
import { saveTrips } from '@/trip/tripStorage.js'

beforeEach(() => { window.location.hash = '' })
afterEach(cleanup)

const trip = (id: string) => newTrip({
  name: id, startDate: null, partySize: 1, start: { startId: 1, sourceType: 1 }, huts: ['{A}'],
  exit: { startId: 1, sourceType: 1 }, variant: { sacCeiling: null, allowUngraded: false },
}, new Date('2026-06-01T00:00:00Z'), id)

function setup(mode: 'trip' | 'discover', openedFrom: 'results' | 'saved' = 'results', activeId: string | null = null) {
  const data: Record<string, string> = {}
  const storage = { getItem: (k: string) => data[k] ?? null, setItem: (k: string, v: string) => { data[k] = v } }
  saveTrips({ trips: [trip('a')], activeId, draft: null, activeIsDraft: false }, storage)
  const setOpenedFrom = vi.fn()
  const onBackFromTrip = vi.fn()
  const wrapper = ({ children }: { children: ReactNode }) => <TripsProvider storage={storage}>{children}</TripsProvider>
  const hook = renderHook(
    () => ({ nav: useSidebarNavigation({ mode, openedFrom, setOpenedFrom, onBackFromTrip }), trips: useTrips() }), { wrapper })
  return { ...hook, setOpenedFrom, onBackFromTrip }
}

describe('useSidebarNavigation', () => {
  it('shows trip when a trip is open, saved for #trips, else discover', () => {
    expect(setup('trip').result.current.nav.sidebarView).toBe('trip')
    expect(setup('discover').result.current.nav.sidebarView).toBe('discover')
    window.location.hash = '#trips'
    expect(setup('discover').result.current.nav.sidebarView).toBe('saved')
    expect(setup('trip').result.current.nav.sidebarView).toBe('trip')
  })

  it('goMeineTouren closes the active trip and sets #trips; goPlanen clears the hash', () => {
    const { result } = setup('trip', 'results', 'a')
    expect(result.current.trips.activeTrip?.id).toBe('a')
    act(() => result.current.nav.goMeineTouren())
    expect(window.location.hash).toBe('#trips')
    expect(result.current.trips.activeTrip).toBeNull()
    act(() => result.current.nav.goPlanen())
    expect(window.location.hash).toBe('')
  })

  it('goHome closes the trip and clears the hash', () => {
    window.location.hash = '#trips'
    const { result } = setup('trip', 'results', 'a')
    act(() => result.current.nav.goHome())
    expect(window.location.hash).toBe('')
    expect(result.current.trips.activeTrip).toBeNull()
  })

  it('openSavedTrip remembers the origin and activates the trip', () => {
    const { result, setOpenedFrom } = setup('discover')
    act(() => result.current.nav.openSavedTrip('a'))
    expect(setOpenedFrom).toHaveBeenCalledWith('saved')
    expect(result.current.trips.activeTrip?.id).toBe('a')
  })

  it('backFromTrip returns to #trips only when opened from saved', () => {
    const fromResults = setup('trip', 'results', 'a')
    act(() => fromResults.result.current.nav.backFromTrip())
    expect(fromResults.onBackFromTrip).toHaveBeenCalled()
    expect(window.location.hash).toBe('')
    const fromSaved = setup('trip', 'saved', 'a')
    act(() => fromSaved.result.current.nav.backFromTrip())
    expect(window.location.hash).toBe('#trips')
  })
})
