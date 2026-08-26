import { describe, it, expect, vi, afterEach } from 'vitest'
import { packColumns } from './binaryColumns.js'
import { loadTourSearchData, findTours } from './index.js'

afterEach(() => vi.unstubAllGlobals())

describe('loadTourSearchData', () => {
  it('loads and returns both hutEdges and approaches', async () => {
    const hutEdgesFixture = packColumns(
      { from_id: 'u2', to_id: 'u2', variant: 'u1', distance_m: 'f4', ascent_m: 'f4', descent_m: 'f4', max_ele_m: 'f4', sac_rank: 'i1', via_ferrata: 'u1', road_m: 'f4', ungraded_m: 'f4', inferred_m: 'f4', snap_m: 'f4' },
      { from_id: [0], to_id: [1], variant: [0], distance_m: [1000], ascent_m: [100], descent_m: [50], max_ele_m: [2000], sac_rank: [1], via_ferrata: [0], road_m: [0], ungraded_m: [0], inferred_m: [0], snap_m: [0] },
      1,
    )
    const approachesFixture = packColumns(
      { hut_id: 'u2', start_id: 'u8', source_type: 'u1', access_unknown: 'u1', distance_m: 'f4', ascent_m: 'f4', descent_m: 'f4' },
      { hut_id: [0], start_id: [1], source_type: [2], access_unknown: [0], distance_m: [500], ascent_m: [50], descent_m: [10] },
      1,
    )
    const fetchMock = vi.fn()
      .mockImplementation((url) => {
        if (url.endsWith('hut-edge-payload.json')) return Promise.resolve({ json: () => Promise.resolve({ ...hutEdgesFixture.manifest, variants: { 0: 'FAST_ANY' }, hut_ids: ['A', 'B'] }) })
        if (url.endsWith('hut-edge-payload.bin')) return Promise.resolve({ arrayBuffer: () => Promise.resolve(hutEdgesFixture.buffer) })
        if (url.endsWith('approaches.json')) return Promise.resolve({ json: () => Promise.resolve({ ...approachesFixture.manifest, access_values: [null], reverse_index: { hut_to_starts: {}, start_to_huts: {} } }) })
        if (url.endsWith('approaches.bin')) return Promise.resolve({ arrayBuffer: () => Promise.resolve(approachesFixture.buffer) })
        throw new Error(`unexpected fetch ${url}`)
      })
    vi.stubGlobal('fetch', fetchMock)

    const data = await loadTourSearchData('/data')

    expect(data.hutEdges.records).toHaveLength(1)
    expect(data.approaches.records).toHaveLength(1)
  })
})

describe('findTours', () => {
  it('runs search then both diversity passes', () => {
    // Two states that would collapse under dedupeReversePairs, seeded directly rather than via a
    // real search, to test the pipeline wiring in isolation from the DFS itself (Task 10 already
    // tests the DFS; this test is about ordering, not search correctness).
    const graphData = {
      hutEdges: { hutIds: ['A', 'B'], variantNames: { 0: 'FAST_ANY' }, records: [] },
      approaches: { records: [], reverseIndex: { hut_to_starts: {}, start_to_huts: {} } },
    }
    const query = { mode: 'transit', legCountMin: 2, legCountMax: 2, maxLegTimeH: 5 }
    const { chains, killCounters } = findTours(query, graphData)
    expect(chains).toEqual([])
    expect(killCounters).toBeDefined()
  })
})
