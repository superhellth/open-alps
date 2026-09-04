import { describe, it, expect, vi, afterEach } from 'vitest'
import { loadOfficialTours } from './loadOfficialTours.js'

afterEach(() => vi.unstubAllGlobals())

describe('loadOfficialTours', () => {
  it('fetches tours.json and passes the parsed tours through as-is', async () => {
    const body = [
      {
        tourId: 1, name: 'Welser Höhenweg',
        legs: [
          { legIndex: 0, from: { type: 'parking', id: 360050560 }, to: { type: 'hut', id: 302 } },
          { legIndex: 1, from: { type: 'hut', id: 302 }, to: { type: 'hut', id: 376 } },
        ],
      },
    ]
    const fetchMock = vi.fn().mockResolvedValue({ json: () => Promise.resolve(body) })
    vi.stubGlobal('fetch', fetchMock)

    const tours = await loadOfficialTours('/data')

    expect(fetchMock).toHaveBeenCalledWith('/data/tours.json')
    expect(tours).toEqual(body)
  })
})
