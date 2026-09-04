import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { loadLegGeometry, _resetLegGeometryCachesForTests } from './loadLegGeometry.js'

// [lon, lat] pairs per synthetic edge, matching the pipeline's on-disk point order.
const EDGE0: [number, number][] = [[11.0, 47.0], [11.25, 47.25]]
const EDGE1: [number, number][] = [[12.0, 48.0], [12.25, 48.25], [12.5, 48.5]]
const MANIFEST = { point_counts: [EDGE0.length, EDGE1.length] }

function makeBinary(edges: [number, number][][]): ArrayBuffer {
  const points = edges.flat()
  const buffer = new ArrayBuffer(points.length * 8)
  const view = new DataView(buffer)
  points.forEach(([lon, lat], i) => {
    view.setFloat32(i * 8, lon, true)
    view.setFloat32(i * 8 + 4, lat, true)
  })
  return buffer
}

const BINARY = makeBinary([EDGE0, EDGE1])

beforeEach(() => _resetLegGeometryCachesForTests())
afterEach(() => vi.unstubAllGlobals())

describe('loadLegGeometry', () => {
  it('builds the prefix-sum offset table from the manifest and range-fetches the right bytes', async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (url === '/data/hut-edge-geometry.json') {
        return Promise.resolve({ json: () => Promise.resolve(MANIFEST) } as Response)
      }
      if (url === '/data/hut-edge-geometry.bin') {
        // edge_id=1 starts after edge 0's 2 points (16 bytes) and is 3 points (24 bytes) long.
        expect(init?.headers).toMatchObject({ Range: 'bytes=16-39' })
        return Promise.resolve({
          status: 206,
          arrayBuffer: () => Promise.resolve(BINARY.slice(16, 40)),
        } as Response)
      }
      throw new Error(`unexpected fetch ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    const points = await loadLegGeometry('hut_edges', 1, false)

    expect(points).toEqual([[48.0, 12.0], [48.25, 12.25], [48.5, 12.5]])
  })

  it('reverses point order when reversed is true, without mutating the cached forward result', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.endsWith('.json')) return Promise.resolve({ json: () => Promise.resolve(MANIFEST) } as Response)
      return Promise.resolve({ status: 206, arrayBuffer: () => Promise.resolve(BINARY.slice(0, 16)) } as Response)
    }))

    const forward = await loadLegGeometry('hut_edges', 0, false)
    const reversed = await loadLegGeometry('hut_edges', 0, true)

    expect(forward).toEqual([[47.0, 11.0], [47.25, 11.25]])
    expect(reversed).toEqual([[47.25, 11.25], [47.0, 11.0]])
  })

  it('caches by edgeId so a repeated lookup does not refetch', async () => {
    const fetchMock = vi.fn((url: string) => {
      if (url.endsWith('.json')) return Promise.resolve({ json: () => Promise.resolve(MANIFEST) } as Response)
      return Promise.resolve({ status: 206, arrayBuffer: () => Promise.resolve(BINARY.slice(0, 16)) } as Response)
    })
    vi.stubGlobal('fetch', fetchMock)

    await loadLegGeometry('hut_edges', 0, false)
    await loadLegGeometry('hut_edges', 0, false)
    await loadLegGeometry('hut_edges', 0, true)

    const manifestCalls = fetchMock.mock.calls.filter(([url]) => (url as string).endsWith('.json'))
    const binCalls = fetchMock.mock.calls.filter(([url]) => (url as string).endsWith('.bin'))
    expect(manifestCalls).toHaveLength(1)
    expect(binCalls).toHaveLength(1)
  })

  it('falls back to slicing the full body when the server ignores Range and answers 200', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.endsWith('.json')) return Promise.resolve({ json: () => Promise.resolve(MANIFEST) } as Response)
      return Promise.resolve({ status: 200, arrayBuffer: () => Promise.resolve(BINARY) } as Response)
    }))

    const points = await loadLegGeometry('hut_edges', 1, false)

    expect(points).toEqual([[48.0, 12.0], [48.25, 12.25], [48.5, 12.5]])
  })

  it('after one 200 fallback, a later leg on the same layer reuses the whole-file buffer instead of refetching it', async () => {
    let binFetchCount = 0
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.endsWith('.json')) return Promise.resolve({ json: () => Promise.resolve(MANIFEST) } as Response)
      binFetchCount++
      return Promise.resolve({ status: 200, arrayBuffer: () => Promise.resolve(BINARY) } as Response)
    }))

    await loadLegGeometry('hut_edges', 0, false)
    await loadLegGeometry('hut_edges', 1, false)

    expect(binFetchCount).toBe(1)
  })

  it('supports the tour_edges layer via tour-edge-geometry.bin/.json', async () => {
    const fetchMock = vi.fn((url: string) => {
      if (url === '/data/tour-edge-geometry.json') {
        return Promise.resolve({ json: () => Promise.resolve(MANIFEST) } as Response)
      }
      if (url === '/data/tour-edge-geometry.bin') {
        return Promise.resolve({ status: 206, arrayBuffer: () => Promise.resolve(BINARY.slice(0, 16)) } as Response)
      }
      throw new Error(`unexpected fetch ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    const points = await loadLegGeometry('tour_edges', 0, false)

    expect(points).toEqual([[47.0, 11.0], [47.25, 11.25]])
  })
})
