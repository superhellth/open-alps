import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { loadHutEdgeIdsData, loadStartEdgeIdsData } from './loadHutEdgeIds.js'

function buildFixtureBuffer() {
  // 2 records: record 0 sorted=[10,20,30] prefix=[30,10,20,...-1] suffix=[20,10,30,...-1],
  // record 1 sorted=[40,50] prefix=[40,...-1] suffix=[50,...-1].
  const k = 8
  const sorted = Int32Array.from([10, 20, 30, 40, 50])
  const prefix = new Int32Array(2 * k).fill(-1)
  prefix.set([30, 10, 20], 0)
  prefix.set([40], k)
  const suffix = new Int32Array(2 * k).fill(-1)
  suffix.set([20, 10, 30], 0)
  suffix.set([50], k)

  const buffer = new ArrayBuffer(sorted.byteLength + prefix.byteLength + suffix.byteLength)
  new Int32Array(buffer, 0, sorted.length).set(sorted)
  new Int32Array(buffer, sorted.byteLength, prefix.length).set(prefix)
  new Int32Array(buffer, sorted.byteLength + prefix.byteLength, suffix.length).set(suffix)

  const manifest = {
    rows: 2, k,
    edge_id_count: [3, 2], prefix_count: [3, 1], suffix_count: [3, 1],
    sorted_bytes: sorted.byteLength, prefix_bytes: prefix.byteLength, suffix_bytes: suffix.byteLength,
  }
  return { buffer, manifest }
}

describe('loadHutEdgeIdsData', () => {
  const { buffer, manifest } = buildFixtureBuffer()

  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.endsWith('.json')) return { json: async () => manifest } as Response
      return { arrayBuffer: async () => buffer } as Response
    }))
  })
  afterEach(() => vi.unstubAllGlobals())

  it('slices sorted ids per record via the reconstructed prefix-sum offsets', async () => {
    const data = await loadHutEdgeIdsData('/data')
    expect(Array.from(data.getSortedIds(0))).toEqual([10, 20, 30])
    expect(Array.from(data.getSortedIds(1))).toEqual([40, 50])
  })

  it('slices prefix/suffix ids per record, dropping -1 padding via *_count', async () => {
    const data = await loadHutEdgeIdsData('/data')
    expect(Array.from(data.getPrefixIds(0))).toEqual([30, 10, 20])
    expect(Array.from(data.getSuffixIds(0))).toEqual([20, 10, 30])
    expect(Array.from(data.getPrefixIds(1))).toEqual([40])
    expect(Array.from(data.getSuffixIds(1))).toEqual([50])
  })
})

describe('loadStartEdgeIdsData', () => {
  const { buffer, manifest } = buildFixtureBuffer()
  let requestedUrls: string[] = []

  beforeEach(() => {
    requestedUrls = []
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      requestedUrls.push(url)
      if (url.endsWith('.json')) return { json: async () => manifest } as Response
      return { arrayBuffer: async () => buffer } as Response
    }))
  })
  afterEach(() => vi.unstubAllGlobals())

  it('fetches start-edge-ids.bin/.json, not the hut-edge-ids files', async () => {
    await loadStartEdgeIdsData('/data')
    expect(requestedUrls).toContain('/data/start-edge-ids.json')
    expect(requestedUrls).toContain('/data/start-edge-ids.bin')
    expect(requestedUrls.some((u) => u.includes('hut-edge-ids'))).toBe(false)
  })

  it('parses the same manifest/binary shape as loadHutEdgeIdsData', async () => {
    const data = await loadStartEdgeIdsData('/data')
    expect(Array.from(data.getSortedIds(0))).toEqual([10, 20, 30])
    expect(Array.from(data.getPrefixIds(1))).toEqual([40])
  })
})
