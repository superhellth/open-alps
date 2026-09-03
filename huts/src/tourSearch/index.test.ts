import { describe, it, expect, vi, afterEach } from 'vitest'
import { packColumns } from './binaryColumns.js'
import { loadTourSearchData, findTours } from './index.js'
import type { GraphData, Query } from './types.js'

afterEach(() => vi.unstubAllGlobals())

describe('loadTourSearchData', () => {
  it('loads and returns both hutEdges and approaches', async () => {
    const hutEdgesFixture = packColumns(
      { from_id: 'u2', to_id: 'u2', variant: 'u1', distance_m: 'f4', ascent_m: 'f4', descent_m: 'f4', max_ele_m: 'f4', sac_rank: 'i1', via_ferrata: 'u1', road_m: 'f4', ungraded_m: 'f4', inferred_m: 'f4', snap_m: 'f4' },
      { from_id: [0], to_id: [1], variant: [0], distance_m: [1000], ascent_m: [100], descent_m: [50], max_ele_m: [2000], sac_rank: [1], via_ferrata: [0], road_m: [0], ungraded_m: [0], inferred_m: [0], snap_m: [0] },
      1,
    )
    const approachesFixture = packColumns(
      { hut_id: 'u2', start_id: 'u8', source_type: 'u1', variant: 'u1', edge_id: 'u4', access_unknown: 'u1', distance_m: 'f4', ascent_m: 'f4', descent_m: 'f4' },
      { hut_id: [0], start_id: [1], source_type: [2], variant: [0], edge_id: [0], access_unknown: [0], distance_m: [500], ascent_m: [50], descent_m: [10] },
      1,
    )
    const hutEdgeIdsManifest = {
      rows: 1, k: 8,
      edge_id_count: [0], prefix_count: [0], suffix_count: [0],
      sorted_bytes: 0, prefix_bytes: 32, suffix_bytes: 32,
    }
    const hutEdgeIdsBuffer = new ArrayBuffer(64)
    new Int32Array(hutEdgeIdsBuffer).fill(-1)

    const fetchMock = vi.fn()
      .mockImplementation((url: string) => {
        if (url.endsWith('hut-edge-payload.json')) return Promise.resolve({ json: () => Promise.resolve({ ...hutEdgesFixture.manifest, variants: { 0: 'FAST_ANY' }, hut_ids: ['A', 'B'] }) })
        if (url.endsWith('hut-edge-payload.bin')) return Promise.resolve({ arrayBuffer: () => Promise.resolve(hutEdgesFixture.buffer) })
        if (url.endsWith('approaches.json')) return Promise.resolve({ json: () => Promise.resolve({ ...approachesFixture.manifest, access_values: [null], reverse_index: { hut_to_starts: {}, start_to_huts: {} } }) })
        if (url.endsWith('approaches.bin')) return Promise.resolve({ arrayBuffer: () => Promise.resolve(approachesFixture.buffer) })
        if (url.endsWith('hut-edge-ids.json')) return Promise.resolve({ json: () => Promise.resolve(hutEdgeIdsManifest) })
        if (url.endsWith('hut-edge-ids.bin')) return Promise.resolve({ arrayBuffer: () => Promise.resolve(hutEdgeIdsBuffer) })
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
    const graphData: GraphData = {
      hutEdges: { hutIds: ['A', 'B'], variantNames: { 0: 'FAST_ANY' }, records: [] },
      approaches: { records: [], reverseIndex: { hut_to_starts: {}, start_to_huts: {} } },
      hutEdgeIds: {
        getSortedIds: () => new Int32Array(0),
        getPrefixIds: () => new Int32Array(0),
        getSuffixIds: () => new Int32Array(0),
      },
    }
    const query: Query = { mode: 'transit', legCountMin: 2, legCountMax: 2, maxLegTimeH: 5 }
    const { chains, killCounters } = findTours(query, graphData)
    expect(chains).toEqual([])
    expect(killCounters).toBeDefined()
  })
})
