import { describe, it, expect, vi, afterEach } from 'vitest'
import { packColumns } from './binaryColumns.js'
import { loadApproachesData } from './loadApproaches.js'

afterEach(() => vi.unstubAllGlobals())

describe('loadApproachesData', () => {
  it('fetches the manifest and binary, normalizes records, and passes the reverse index through', async () => {
    const { manifest, buffer } = packColumns(
      { hut_id: 'u2', start_id: 'u8', source_type: 'u1', variant: 'u1', edge_id: 'u4', access_unknown: 'u1', distance_m: 'f4', ascent_m: 'f4', descent_m: 'f4' },
      { hut_id: [15], start_id: [32854131], source_type: [1], variant: [0], edge_id: [4201], access_unknown: [0], distance_m: [19812.6], ascent_m: [746.2], descent_m: [488.2] },
      1,
    )
    const reverseIndex = {
      hut_to_starts: { 15: [{ hut_id: 15, start_id: 32854131, source_type: 1, variant: 0, distance_m: 19812.6, ascent_m: 746.2, descent_m: 488.2 }] },
      start_to_huts: { 32854131: [{ hut_id: 15, start_id: 32854131, source_type: 1, variant: 0, distance_m: 19812.6, ascent_m: 746.2, descent_m: 488.2 }] },
    }
    const fullManifest = { ...manifest, access_values: ['customers'], reverse_index: reverseIndex }
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ json: () => Promise.resolve(fullManifest) })
      .mockResolvedValueOnce({ arrayBuffer: () => Promise.resolve(buffer) })
    vi.stubGlobal('fetch', fetchMock)

    const data = await loadApproachesData('/data')

    expect(data.records).toHaveLength(1)
    expect(data.records[0]).toMatchObject({
      hutIndex: 15, startId: 32854131, sourceType: 1, variant: 0, accessUnknown: false, edgeId: 4201,
      distanceM: expect.closeTo(19812.6, 1), access: 'customers',
    })
    expect(data.reverseIndex).toBe(reverseIndex)
  })
})
