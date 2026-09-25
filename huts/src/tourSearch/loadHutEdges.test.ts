import { describe, it, expect, vi, afterEach } from 'vitest'
import { packColumns } from './binaryColumns.js'
import { loadHutEdgesData } from './loadHutEdges.js'

afterEach(() => vi.unstubAllGlobals())

describe('loadHutEdgesData', () => {
  it('fetches the manifest and binary, and normalizes rows into camelCase records', async () => {
    const { manifest, buffer } = packColumns(
      {
        from_id: 'u2', to_id: 'u2', variant: 'u1', distance_m: 'f4', ascent_m: 'f4', descent_m: 'f4',
        max_ele_m: 'f4', sac_rank: 'i1', via_ferrata: 'u1', road_m: 'f4', ungraded_m: 'f4',
        inferred_m: 'f4', snap_m: 'f4',
      },
      {
        from_id: [0], to_id: [1], variant: [2], distance_m: [1200], ascent_m: [300], descent_m: [100],
        max_ele_m: [2400], sac_rank: [3], via_ferrata: [1], road_m: [50], ungraded_m: [0],
        inferred_m: [200], snap_m: [15],
      },
      1,
    )
    const fullManifest = { ...manifest, variants: { 0: 'FAST_ANY', 2: 'FAST_T3' }, hut_ids: ['hutA', 'hutB'] }
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ json: () => Promise.resolve(fullManifest) })
      .mockResolvedValueOnce({ arrayBuffer: () => Promise.resolve(buffer) })
    vi.stubGlobal('fetch', fetchMock)

    const data = await loadHutEdgesData('/data')

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/data/hut-edge-payload.json')
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/data/hut-edge-payload.bin')
    expect(data.hutIds).toEqual(['hutA', 'hutB'])
    expect(data.variantNames).toEqual({ 0: 'FAST_ANY', 2: 'FAST_T3' })
    expect(data.records).toHaveLength(1)
    expect(data.records[0]).toMatchObject({
      fromIndex: 0, toIndex: 1, variant: 2, distanceM: 1200, ascentM: 300, descentM: 100,
      maxEleM: 2400, sacRank: 3, viaFerrata: true, roadM: 50, ungradedM: 0, inferredM: 200, snapM: 15,
      edgeId: 0,
    })
  })

  it('exposes anchor offsets when the payload carries anchor columns, null otherwise', async () => {
    const base = {
      from_id: 'u2', to_id: 'u2', variant: 'u1', distance_m: 'f4', ascent_m: 'f4', descent_m: 'f4',
      max_ele_m: 'f4', sac_rank: 'i1', via_ferrata: 'u1', road_m: 'f4', ungraded_m: 'f4',
      inferred_m: 'f4', snap_m: 'f4',
    } as const
    const vals = {
      from_id: [0], to_id: [1], variant: [0], distance_m: [1], ascent_m: [0], descent_m: [0],
      max_ele_m: [0], sac_rank: [0], via_ferrata: [0], road_m: [0], ungraded_m: [0], inferred_m: [0], snap_m: [0],
    }
    const withAnchors = packColumns(
      { ...base, a25_dlat: 'i2', a25_dlng: 'i2', a50_dlat: 'i2', a50_dlng: 'i2', a75_dlat: 'i2', a75_dlng: 'i2' },
      { ...vals, a25_dlat: [1], a25_dlng: [-2], a50_dlat: [3], a50_dlng: [4], a75_dlat: [5], a75_dlng: [6] },
      1,
    )
    const plain = packColumns(base, vals, 1)
    const run = async (p: typeof plain) => {
      vi.stubGlobal('fetch', vi.fn()
        .mockResolvedValueOnce({ json: () => Promise.resolve({ ...p.manifest, variants: {}, hut_ids: ['a', 'b'] }) })
        .mockResolvedValueOnce({ arrayBuffer: () => Promise.resolve(p.buffer) }))
      return (await loadHutEdgesData('/data')).records[0]
    }
    expect((await run(withAnchors)).anchorOffsets).toEqual([1, -2, 3, 4, 5, 6])
    expect((await run(plain)).anchorOffsets).toBeNull()
  })
})
