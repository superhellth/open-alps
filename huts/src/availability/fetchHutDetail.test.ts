import { describe, it, expect, vi, afterEach } from 'vitest'
import { fetchHutDetail } from './fetchHutDetail.js'

afterEach(() => vi.unstubAllGlobals())

const RAW_RESPONSE = [{
  page: 0, resultsPerPage: 1, totalPages: 1,
  hutsAvailability: [{
    hutID: 179, hutName: 'Pfeis-Hütte',
    calendarDays: [{
      day: '20.08.2026', reservationMode: 'SERVICED', status: 'RESERVATION_NOT_POSSIBLE',
      bedCategoriesData: [{
        totalPlaces: 37, occupation: 'HIGH', totalFreePlaces: 0,
        hutBedCategoryLanguagesData: [{ language: 'DE_DE', label: 'Matratzenlager', shortLabel: 'ML' }],
      }],
    }],
  }],
}]

describe('fetchHutDetail', () => {
  it('parses the OHRS per-hut response into HutDetail, picking the DE_DE label', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(RAW_RESPONSE) } as Response)
    vi.stubGlobal('fetch', fetchMock)

    const detail = await fetchHutDetail('179', 8, new Date(Date.UTC(2026, 7, 20)), 2)

    expect(fetchMock).toHaveBeenCalledWith('https://caa.alpenverein.at/service/server/callOHRS_REST.php', expect.objectContaining({ method: 'POST' }))
    const body = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(body).toMatchObject({ startDate: '20.08.2026', endDate: '21.08.2026', huts: ['179'], numOfPeople: '2', tenantCode: 8 })
    expect(detail.hutId).toBe(179)
    expect(detail.hutName).toBe('Pfeis-Hütte')
    expect(detail.calendarDays[0]).toMatchObject({ day: '20.08.2026', status: 'RESERVATION_NOT_POSSIBLE' })
    expect(detail.calendarDays[0].bedCategoriesData[0]).toEqual({
      totalPlaces: 37, occupation: 'HIGH', totalFreePlaces: 0, label: 'Matratzenlager',
    })
  })

  it("falls back to a TECHNICAL_ERROR HutDetail on a failed request", async () => {
    // Distinct ohrsHutId from other tests in this file - the module-level cache persists across
    // tests within a file, and a shared key would let an earlier test's success mask this case.
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network error')))

    const detail = await fetchHutDetail('180', 8, new Date(Date.UTC(2026, 7, 20)), 2)

    expect(detail.calendarDays).toEqual([{ day: '20.08.2026', reservationMode: '', status: 'TECHNICAL_ERROR', bedCategoriesData: [] }])
  })

  it("falls back to TECHNICAL_ERROR when tenantCode is wrong (OHRS 400)", async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false, json: () => Promise.resolve({ messageId: 302, description: 'Tenant code not found', statusCode: 400 }),
    } as Response))

    const detail = await fetchHutDetail('181', 999, new Date(Date.UTC(2026, 7, 20)), 2)

    expect(detail.calendarDays[0].status).toBe('TECHNICAL_ERROR')
  })

  it('caches by (ohrsHutId, date, numOfPeople): a repeated call does not refetch', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(RAW_RESPONSE) } as Response)
    vi.stubGlobal('fetch', fetchMock)

    await fetchHutDetail('182', 8, new Date(Date.UTC(2026, 7, 20)), 2)
    await fetchHutDetail('182', 8, new Date(Date.UTC(2026, 7, 20)), 2)

    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
