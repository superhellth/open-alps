// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook, waitFor, cleanup } from '@testing-library/react'
import { useTripAvailability } from './useTripAvailability.js'
import * as detail from '../availability/fetchHutDetail.js'
import { newTrip } from '../trip/trip.js'
import type { HutDetail } from '../availability/types.js'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

const trip = (startDate: string | null) => newTrip({
  name: 't', startDate, partySize: 2, start: { startId: 100, sourceType: 1 }, huts: ['{A}', '{B}', '{X}'],
  exit: { startId: 100, sourceType: 1 }, variant: { sacCeiling: null, allowUngraded: false },
}, new Date(), 'id')
const ohrs = new Map([[0, { ohrsHutId: '100', tenantCode: 8 }], [1, { ohrsHutId: '101', tenantCode: 8 }], [5, { ohrsHutId: null, tenantCode: null }]])
const free = (n: number): HutDetail => ({ hutId: 1, hutName: '', calendarDays: [{ day: 'd', reservationMode: '', status: 'AVAILABLE', bedCategoriesData: [{ totalPlaces: 20, occupation: '', totalFreePlaces: n, label: '' }] }] })

describe('useTripAvailability', () => {
  it('is null without a start date and never fetches', () => {
    const spy = vi.spyOn(detail, 'fetchHutDetail')
    const { result } = renderHook(() => useTripAvailability(trip(null), [0, 1, 5], ohrs))
    expect(result.current).toBeNull()
    expect(spy).not.toHaveBeenCalled()
  })
  it('fetches one request per bookable night for its own date, and marks huts without OHRS id unknown', async () => {
    const spy = vi.spyOn(detail, 'fetchHutDetail').mockResolvedValueOnce(free(12)).mockResolvedValueOnce(free(3))
    const t = trip('2026-07-10')
    const indices = [0, 1, 5]
    const { result } = renderHook(() => useTripAvailability(t, indices, ohrs))
    await waitFor(() => expect(result.current?.every((v) => !v.loading)).toBe(true))
    expect(spy).toHaveBeenCalledTimes(2)
    expect(spy.mock.calls[0].slice(0, 2)).toEqual(['100', 8])
    expect(spy.mock.calls[0][2].toISOString().slice(0, 10)).toBe('2026-07-10')
    expect(spy.mock.calls[1][2].toISOString().slice(0, 10)).toBe('2026-07-11')
    expect(result.current!.map((v) => (v.loading ? null : v.availability.kind))).toEqual(['free', 'few', 'unknown'])
  })
  it('a failed fetch is unknown, not full', async () => {
    vi.spyOn(detail, 'fetchHutDetail').mockRejectedValue(new Error('x'))
    const t = trip('2026-07-10')
    const indices = [0]
    const { result } = renderHook(() => useTripAvailability(t, indices, ohrs))
    await waitFor(() => expect(result.current?.[0]).toEqual({ loading: false, availability: { kind: 'unknown' } }))
  })
})
