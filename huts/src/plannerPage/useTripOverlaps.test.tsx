// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook, waitFor, cleanup } from '@testing-library/react'
import { useTripOverlaps } from './useTripOverlaps.js'
import { legsFromTrip } from '@/trip/tripLegs.js'
import { makeTripGraph } from '@/testing/tripTestGraph.js'
import { newTrip } from '../trip/trip.js'
import type { SearchClient } from '../search/searchClient.js'

afterEach(cleanup)

const graph = makeTripGraph()
const trip = (huts: string[]) => newTrip({
  name: 't', startDate: null, partySize: 1, start: { startId: 100, sourceType: 1 }, huts,
  exit: { startId: 100, sourceType: 1 }, variant: { sacCeiling: null, allowUngraded: false },
}, new Date(), 'id')
const client = (overlaps: SearchClient['overlaps']): SearchClient => ({ ready: Promise.resolve(), search: () => Promise.resolve([]), overlaps, dispose: () => {} })

describe('useTripOverlaps', () => {
  it('turns overlapping leg pairs into German warnings, numbered by stage', async () => {
    const overlaps = vi.fn().mockResolvedValue([[0, 2]])
    const t = trip(['{A}', '{B}', '{C}', '{D}'])
    const legs = legsFromTrip(graph, t)
    const c = client(overlaps)
    const { result } = renderHook(() => useTripOverlaps(c, t, legs))
    await waitFor(() => expect(result.current).toEqual(['Etappe 3 überschneidet sich mit Etappe 1']))
    expect(overlaps.mock.calls[0][1]).toBe(true) // start === exit is a loop closure
  })
  it('asks nothing while a leg is missing', () => {
    const overlaps = vi.fn()
    const t = trip(['{A}', '{D}'])
    const legs = legsFromTrip(graph, t)
    const c = client(overlaps)
    const { result } = renderHook(() => useTripOverlaps(c, t, legs))
    expect(result.current).toEqual([])
    expect(overlaps).not.toHaveBeenCalled()
  })
  it('treats a failed request as no warnings', async () => {
    const t = trip(['{A}', '{B}'])
    const legs = legsFromTrip(graph, { ...t, exit: { startId: 100, sourceType: 1 } })
    const c = client(vi.fn().mockRejectedValue(new Error('x')))
    const { result } = renderHook(() => useTripOverlaps(c, t, legs))
    expect(result.current).toEqual([])
  })
})
