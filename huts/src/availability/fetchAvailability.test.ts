import { describe, it, expect, vi, afterEach } from 'vitest'
import { fetchAvailabilityByOffset } from './fetchAvailability.js'

afterEach(() => vi.unstubAllGlobals())

function jsonResponse(body: unknown, ok = true) {
  return Promise.resolve({ ok, json: () => Promise.resolve(body) } as Response)
}

describe('fetchAvailabilityByOffset', () => {
  it('fires one POST per offset day, in parallel, with the right body', async () => {
    const fetchMock = vi.fn().mockImplementation((_url: string, init: RequestInit) => {
      const body = JSON.parse(init.body as string) as { startDate: string; numOfPeople: number; collectAll: boolean }
      if (body.startDate === '21.08.2026') return jsonResponse([1, 2])
      if (body.startDate === '22.08.2026') return jsonResponse([2, 3])
      throw new Error(`unexpected startDate ${body.startDate}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchAvailabilityByOffset(new Date(Date.UTC(2026, 7, 20)), 2, 2)

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(fetchMock.mock.calls[0][0]).toBe('https://caa.alpenverein.at/service/server/callOHRS_REST.php')
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).numOfPeople).toBe(2)
    expect(result.get(1)).toEqual(new Set(['1', '2']))
    expect(result.get(2)).toEqual(new Set(['2', '3']))
  })

  it("marks an offset 'unknown' when its request fails, without affecting other offsets", async () => {
    const fetchMock = vi.fn().mockImplementation((_url: string, init: RequestInit) => {
      const body = JSON.parse(init.body as string) as { startDate: string }
      if (body.startDate === '21.08.2026') return Promise.reject(new Error('network error'))
      return jsonResponse([5])
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchAvailabilityByOffset(new Date(Date.UTC(2026, 7, 20)), 1, 2)

    expect(result.get(1)).toBe('unknown')
    expect(result.get(2)).toEqual(new Set(['5']))
  })

  it("marks an offset 'unknown' on a non-ok HTTP response", async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, json: () => Promise.resolve([]) } as Response))

    const result = await fetchAvailabilityByOffset(new Date(Date.UTC(2026, 7, 20)), 1, 1)

    expect(result.get(1)).toBe('unknown')
  })

  it('caches by (date, numOfPeople): a second call for the same night+party size does not refetch', async () => {
    // A date/numOfPeople combo not used by any other test in this file - the module-level cache
    // persists across tests within a file, so reusing another test's key would make this pass
    // vacuously (0 calls, cache already warm) rather than proving the second call was a cache hit.
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([9]) } as Response)
    vi.stubGlobal('fetch', fetchMock)

    await fetchAvailabilityByOffset(new Date(Date.UTC(2026, 8, 1)), 3, 1)
    await fetchAvailabilityByOffset(new Date(Date.UTC(2026, 8, 1)), 3, 1)

    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
