import { describe, it, expect, vi, afterEach } from 'vitest'
import { packColumns } from './binaryColumns.js'
import { loadTourEdgesData } from './loadTourEdges.js'

afterEach(() => vi.unstubAllGlobals())

describe('loadTourEdgesData', () => {
  it('fetches the manifest and binary, and keys records by "tourId:legIndex"', async () => {
    const { manifest, buffer } = packColumns(
      {
        tour_id: 'u1', leg_index: 'u1', distance_m: 'f4', ascent_m: 'f4', descent_m: 'f4',
        max_ele_m: 'f4', sac_rank: 'i1', via_ferrata: 'u1',
      },
      {
        tour_id: [1, 1], leg_index: [0, 1], distance_m: [6559, 10807], ascent_m: [863, 1031],
        descent_m: [65, 820], max_ele_m: [1415, 2064], sac_rank: [3, 3], via_ferrata: [0, 0],
      },
      2,
    )
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ json: () => Promise.resolve(manifest) })
      .mockResolvedValueOnce({ arrayBuffer: () => Promise.resolve(buffer) })
    vi.stubGlobal('fetch', fetchMock)

    const records = await loadTourEdgesData('/data')

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/data/tour-edge-payload.json')
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/data/tour-edge-payload.bin')
    expect(records.size).toBe(2)
    expect(records.get('1:0')).toMatchObject({
      distanceM: 6559, ascentM: 863, descentM: 65, maxEleM: 1415, sacRank: 3, viaFerrata: false,
      edgeId: 0,
    })
    expect(records.get('1:1')).toMatchObject({ edgeId: 1, distanceM: 10807 })
  })
})
