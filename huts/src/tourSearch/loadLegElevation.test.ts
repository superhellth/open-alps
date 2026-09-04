import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { loadLegElevation, _resetLegElevationCachesForTests } from './loadLegElevation.js'

const EDGE0 = [1500.0, 1520.5]
const EDGE1 = [2000.0, 2050.25, 2100.5]
const MANIFEST = { profile_counts: [EDGE0.length, EDGE1.length] }

function makeBinary(edges: number[][]): ArrayBuffer {
  const values = edges.flat()
  const buffer = new ArrayBuffer(values.length * 4)
  const view = new DataView(buffer)
  values.forEach((v, i) => view.setFloat32(i * 4, v, true))
  return buffer
}

const BINARY = makeBinary([EDGE0, EDGE1])

beforeEach(() => _resetLegElevationCachesForTests())
afterEach(() => vi.unstubAllGlobals())

describe('loadLegElevation', () => {
  it('builds the prefix-sum offset table from the manifest and range-fetches the right bytes', async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (url === '/data/hut-edge-elevation.json') {
        return Promise.resolve({ json: () => Promise.resolve(MANIFEST) } as Response)
      }
      if (url === '/data/hut-edge-elevation.bin') {
        // edge_id=1 starts after edge 0's 2 values (8 bytes) and is 3 values (12 bytes) long.
        expect(init?.headers).toMatchObject({ Range: 'bytes=8-19' })
        return Promise.resolve({
          status: 206,
          arrayBuffer: () => Promise.resolve(BINARY.slice(8, 20)),
        } as Response)
      }
      throw new Error(`unexpected fetch ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    const values = await loadLegElevation('hut_edges', 1, false)

    expect(values).toEqual(EDGE1)
  })

  it('reverses value order when reversed is true, without mutating the cached forward result', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.endsWith('.json')) return Promise.resolve({ json: () => Promise.resolve(MANIFEST) } as Response)
      return Promise.resolve({ status: 206, arrayBuffer: () => Promise.resolve(BINARY.slice(0, 8)) } as Response)
    }))

    const forward = await loadLegElevation('hut_edges', 0, false)
    const reversed = await loadLegElevation('hut_edges', 0, true)

    expect(forward).toEqual(EDGE0)
    expect(reversed).toEqual([...EDGE0].reverse())
  })

  it('caches by edgeId so a repeated lookup does not refetch', async () => {
    const fetchMock = vi.fn((url: string) => {
      if (url.endsWith('.json')) return Promise.resolve({ json: () => Promise.resolve(MANIFEST) } as Response)
      return Promise.resolve({ status: 206, arrayBuffer: () => Promise.resolve(BINARY.slice(0, 8)) } as Response)
    })
    vi.stubGlobal('fetch', fetchMock)

    await loadLegElevation('hut_edges', 0, false)
    await loadLegElevation('hut_edges', 0, false)
    await loadLegElevation('hut_edges', 0, true)

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

    const values = await loadLegElevation('hut_edges', 1, false)

    expect(values).toEqual(EDGE1)
  })

  it('after one 200 fallback, a later leg on the same layer reuses the whole-file buffer instead of refetching it', async () => {
    let binFetchCount = 0
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.endsWith('.json')) return Promise.resolve({ json: () => Promise.resolve(MANIFEST) } as Response)
      binFetchCount++
      return Promise.resolve({ status: 200, arrayBuffer: () => Promise.resolve(BINARY) } as Response)
    }))

    await loadLegElevation('hut_edges', 0, false)
    await loadLegElevation('hut_edges', 1, false)

    expect(binFetchCount).toBe(1)
  })

  it('supports the tour_edges layer via tour-edge-elevation.bin/.json', async () => {
    const fetchMock = vi.fn((url: string) => {
      if (url === '/data/tour-edge-elevation.json') {
        return Promise.resolve({ json: () => Promise.resolve(MANIFEST) } as Response)
      }
      if (url === '/data/tour-edge-elevation.bin') {
        return Promise.resolve({ status: 206, arrayBuffer: () => Promise.resolve(BINARY.slice(0, 8)) } as Response)
      }
      throw new Error(`unexpected fetch ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    const values = await loadLegElevation('tour_edges', 0, false)

    expect(values).toEqual(EDGE0)
  })
})
