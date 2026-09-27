// @vitest-environment jsdom
import { describe, it, expect, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { useTripElevation } from './useTripElevation.js'
import type { TripLegs } from '@/trip/tripLegs.js'

vi.mock('@/tourSearch/loadLegElevation.js', () => ({
  loadLegElevation: vi.fn(async (_layer: string, edgeId: number) => {
    // edge 1: 3 samples over 1km; edge 2: 2 samples over 0.5km — distanceM comes from the leg, not this mock
    return edgeId === 1 ? [1000, 1050, 1020] : [1020, 1010]
  }),
}))

function makeLegs(): TripLegs {
  return {
    variantId: 0,
    hutIndices: [0],
    legs: [
      { startId: 1, sourceType: 1, distanceM: 1000, ascentM: 50, descentM: 0, durationH: 1, edgeId: 1, reversed: false } as never,
      { startId: 2, sourceType: 1, distanceM: 500, ascentM: 0, descentM: 20, durationH: 0.5, edgeId: 2, reversed: false } as never,
    ],
    changed: [false],
  }
}

describe('useTripElevation', () => {
  it('concatenates every leg into one distance-ordered series', async () => {
    const { result } = renderHook(() => useTripElevation(makeLegs()))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.points.map((p) => p.elevationM)).toEqual([1000, 1050, 1020, 1020, 1010])
    expect(result.current.points.at(-1)!.distanceKm).toBeCloseTo(1.5, 5)
  })

  it('records night boundaries at cumulative distance per leg end', async () => {
    const { result } = renderHook(() => useTripElevation(makeLegs()))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.nightBoundariesKm).toEqual([0, 1, 1.5])
  })

  it('is loading true synchronously, false once every leg resolves', async () => {
    const { result } = renderHook(() => useTripElevation(makeLegs()))
    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.loading).toBe(false))
  })

  it('skips a null leg (unresolved/changed) without throwing', async () => {
    const legs = makeLegs()
    legs.legs[1] = null as never
    const { result } = renderHook(() => useTripElevation(legs))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.points.every((p) => p.legIndex !== 1)).toBe(true)
  })
})
