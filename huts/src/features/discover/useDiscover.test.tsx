// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook, act, waitFor, cleanup } from '@testing-library/react'
import { useDiscover } from './useDiscover.js'
import { makeTestAppData } from '@/testing/testAppData.js'
import type { SearchClient } from '@/search/searchClient.js'
import type { TourResult } from '@/tourSearch/types.js'
import { tourKey } from '@/tourSearch/tourKey.js'

afterEach(cleanup)

const chain = (startId: number): TourResult => ({ huts: [0], startId, exitStartId: startId, legs: [], totalDurationH: 1, totalAscentM: 0, totalDescentM: 0, totalDistanceM: 0 }) as TourResult
const fakeClient = (chains: TourResult[]): SearchClient => ({
  ready: Promise.resolve(), search: vi.fn().mockResolvedValue(chains), overlaps: () => Promise.resolve([]), dispose: () => {},
})

describe('useDiscover', () => {
  it('starts on the filters tab', () => {
    const data = makeTestAppData()
    const client = fakeClient([])
    const { result } = renderHook(() => useDiscover({ data, client, mapView: null, pointOf: () => null }))
    expect(result.current.tab).toBe('filters')
  })

  it('clears focusTours when the form changes', () => {
    const data = makeTestAppData()
    const client = fakeClient([])
    const { result } = renderHook(() => useDiscover({ data, client, mapView: null, pointOf: () => null }))
    act(() => result.current.setFocusTours(new Set(['x'])))
    expect(result.current.focusTours).not.toBeNull()
    act(() => result.current.patchForm({ onlyAvailable: !result.current.form.onlyAvailable }))
    expect(result.current.focusTours).toBeNull()
  })

  it('limits viewTours to the focused tour keys and lifts the limit again', async () => {
    const data = makeTestAppData()
    const client = fakeClient([chain(100), chain(101)])
    const { result } = renderHook(() => useDiscover({ data, client, mapView: null, pointOf: () => null }))
    await waitFor(() => expect(result.current.visibleTours.length).toBe(2))
    expect(result.current.viewTours).toHaveLength(2)
    const second = result.current.visibleTours[1]
    act(() => result.current.setFocusTours(new Set([tourKey(second)])))
    expect(result.current.viewTours.map(tourKey)).toEqual([tourKey(second)])
    act(() => result.current.setFocusTours(null))
    expect(result.current.viewTours).toHaveLength(2)
  })
})
