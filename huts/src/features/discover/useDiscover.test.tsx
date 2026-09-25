// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook, act, waitFor, cleanup } from '@testing-library/react'
import { useDiscover } from './useDiscover.js'
import { makeTestAppData } from '@/testing/testAppData.js'
import type { SearchClient } from '@/search/searchClient.js'
import type { TourResult } from '@/tourSearch/types.js'

afterEach(cleanup)

const chain = (startId: number): TourResult => ({ huts: [0], startId, exitStartId: startId, legs: [], totalDurationH: 1, totalAscentM: 0, totalDescentM: 0, totalDistanceM: 0 }) as TourResult
const fakeClient = (chains: TourResult[]): SearchClient => ({
  ready: Promise.resolve(), search: vi.fn().mockResolvedValue(chains), overlaps: () => Promise.resolve([]), dispose: () => {},
})

describe('useDiscover', () => {
  it('starts on the filters tab', () => {
    const data = makeTestAppData()
    const client = fakeClient([])
    const { result } = renderHook(() => useDiscover({ data, client, mapView: null }))
    expect(result.current.tab).toBe('filters')
  })

  it('clears focusStarts when the form changes', () => {
    const data = makeTestAppData()
    const client = fakeClient([])
    const { result } = renderHook(() => useDiscover({ data, client, mapView: null }))
    act(() => result.current.setFocusStarts(new Set([100])))
    expect(result.current.focusStarts).not.toBeNull()
    act(() => result.current.patchForm({ onlyAvailable: true }))
    expect(result.current.focusStarts).toBeNull()
  })

  it('viewTours holds only the focused starts when set', async () => {
    const data = makeTestAppData()
    const client = fakeClient([chain(100), chain(101)])
    const { result } = renderHook(() => useDiscover({ data, client, mapView: null }))
    await waitFor(() => expect(result.current.visibleTours.length).toBe(2))
    expect(result.current.viewTours).toHaveLength(2)
    act(() => result.current.setFocusStarts(new Set([101])))
    expect(result.current.viewTours.map((t) => t.startId)).toEqual([101])
  })
})
