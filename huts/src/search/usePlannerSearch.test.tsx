// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook, waitFor, cleanup } from '@testing-library/react'
import { usePlannerSearch } from './usePlannerSearch.js'
import { DEFAULT_FORM } from '../plannerPage/formState.js'
import { DEFAULT_DRAFT } from '../plannerPage/plannerState.js'
import { SupersededError } from './searchClient.js'
import type { SearchClient } from './searchClient.js'
import type { AppData } from '../data/buildAppData.js'
import type { TourResult } from '../tourSearch/types.js'
import * as availability from '../availability/fetchAvailability.js'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

const data = { hutsByIndex: [{ operator: 'av', serviced: true }], hutOhrsByIndex: new Map([[0, { ohrsHutId: '179', tenantCode: 8 }]]) } as unknown as AppData
const chain = { huts: [0], startId: 1, exitStartId: 1, legs: [], totalDurationH: 1, totalAscentM: 0, totalDescentM: 0, totalDistanceM: 0 } as TourResult
const fakeClient = (search: SearchClient['search']): SearchClient => ({
  ready: Promise.resolve(), search, overlaps: () => Promise.resolve([]), dispose: () => {},
})

describe('usePlannerSearch', () => {
  it('runs one search with the query built from the form and exposes the chains', async () => {
    const search = vi.fn().mockResolvedValue([chain])
    const client = fakeClient(search)
    const { result } = renderHook(() => usePlannerSearch({ client, data, form: DEFAULT_FORM, draft: DEFAULT_DRAFT, debounceMs: 0 }))
    await waitFor(() => expect(result.current.status).toBe('done'))
    expect(search).toHaveBeenCalledTimes(1)
    expect(search.mock.calls[0][0]).toMatchObject({ mode: 'transit', legCountMin: 2, legCountMax: 4 })
    expect(result.current.chains).toEqual([chain])
  })

  it('does nothing until client and data exist', () => {
    const { result } = renderHook(() => usePlannerSearch({ client: null, data: null, form: DEFAULT_FORM, draft: DEFAULT_DRAFT, debounceMs: 0 }))
    expect(result.current.status).toBe('idle')
  })

  it('ignores a superseded search and reports other failures', async () => {
    const search = vi.fn().mockRejectedValue(new Error('boom'))
    const client = fakeClient(search)
    const { result } = renderHook(() => usePlannerSearch({ client, data, form: DEFAULT_FORM, draft: DEFAULT_DRAFT, debounceMs: 0 }))
    await waitFor(() => expect(result.current.status).toBe('error'))
    expect(result.current.error).toBe('boom')
    const superseded = vi.fn().mockRejectedValue(new SupersededError())
    const client2 = fakeClient(superseded)
    const r2 = renderHook(() => usePlannerSearch({ client: client2, data, form: DEFAULT_FORM, draft: DEFAULT_DRAFT, debounceMs: 0 }))
    await waitFor(() => expect(superseded).toHaveBeenCalled())
    expect(r2.result.current.status).toBe('searching')
  })

  it('fetches availability with base date startDate-1 only when a date is set', async () => {
    const fetchSpy = vi.spyOn(availability, 'fetchAvailabilityByOffset').mockResolvedValue(new Map())
    const client = fakeClient(vi.fn().mockResolvedValue([]))
    const draft = { startDate: '2026-07-10', partySize: 3 }
    const { result } = renderHook(() => usePlannerSearch({ client, data, form: DEFAULT_FORM, draft, debounceMs: 0 }))
    await waitFor(() => expect(result.current.freeByOffset).not.toBeNull())
    const [base, party, maxOffset] = fetchSpy.mock.calls[0]
    expect(base.toISOString().slice(0, 10)).toBe('2026-07-09')
    expect(party).toBe(3)
    expect(maxOffset).toBe(DEFAULT_FORM.legCountRange[1] - 1)
  })
})
