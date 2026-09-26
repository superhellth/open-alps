import { cachedPromise } from '@/lib/cachedPromise.js'
import type { GeometryLayer } from './loadLegGeometry.js'

/**
 * Byte-range-fetchable per-edge elevation profile: <layer>-elevation.bin is every edge's
 * downsampled elevation series, back to back in edge_id order, each value an f4 (4 bytes, no
 * framing) - <layer>-elevation.json's profile_counts gives each edge's value count, from which a
 * byte range is a prefix sum. Structurally identical to loadLegGeometry.ts, one f4 value per point
 * instead of an f4 lon/lat pair.
 */
interface ElevationManifest {
  profile_counts: number[]
}

interface LayerState {
  offsets: number[] // length profile_counts.length + 1, in values (not bytes)
  wholeFileFetch: Promise<ArrayBuffer> | null
}

const VALUE_BYTES = 4 // f4 elevation

const LAYER_FILES: Record<GeometryLayer, { json: string; bin: string }> = {
  hut_edges: { json: 'hut-edge-elevation.json', bin: 'hut-edge-elevation.bin' },
  start_edges: { json: 'start-edge-elevation.json', bin: 'start-edge-elevation.bin' },
  tour_edges: { json: 'tour-edge-elevation.json', bin: 'tour-edge-elevation.bin' },
}

let manifestCache = new Map<GeometryLayer, Promise<LayerState>>()
let legCache = new Map<string, Promise<number[]>>()

function loadLayerState(layer: GeometryLayer, baseUrl: string): Promise<LayerState> {
  return cachedPromise(manifestCache, layer, async () => {
    const manifest: ElevationManifest = await (await fetch(`${baseUrl}/${LAYER_FILES[layer].json}`)).json()
    const offsets = new Array<number>(manifest.profile_counts.length + 1)
    offsets[0] = 0
    for (let i = 0; i < manifest.profile_counts.length; i++) {
      offsets[i + 1] = offsets[i] + manifest.profile_counts[i]
    }
    return { offsets, wholeFileFetch: null }
  })
}

function decodeValues(buffer: ArrayBuffer, byteOffset: number, valueCount: number): number[] {
  const view = new DataView(buffer, byteOffset, valueCount * VALUE_BYTES)
  const values: number[] = new Array(valueCount)
  for (let i = 0; i < valueCount; i++) {
    values[i] = view.getFloat32(i * VALUE_BYTES, true)
  }
  return values
}

async function fetchLegValues(layer: GeometryLayer, edgeId: number, baseUrl: string): Promise<number[]> {
  const state = await loadLayerState(layer, baseUrl)
  const startValue = state.offsets[edgeId]
  const valueCount = state.offsets[edgeId + 1] - startValue
  const byteStart = startValue * VALUE_BYTES
  const byteEnd = byteStart + valueCount * VALUE_BYTES - 1

  if (state.wholeFileFetch) {
    return decodeValues(await state.wholeFileFetch, byteStart, valueCount)
  }

  const url = `${baseUrl}/${LAYER_FILES[layer].bin}`
  const res = await fetch(url, { headers: { Range: `bytes=${byteStart}-${byteEnd}` } })
  if (res.status === 206) {
    return decodeValues(await res.arrayBuffer(), 0, valueCount)
  }
  if (res.status !== 200) throw new Error(`${url}: HTTP ${res.status}`)

  // Host ignored Range and answered 200 with the entire body - do not retry with another Range
  // request. Decode this leg out of the full body, and cache the full body itself so this
  // (large) download happens at most once per layer per session.
  if (!state.wholeFileFetch) {
    const body = res.arrayBuffer()
    state.wholeFileFetch = body
    body.catch(() => { if (state.wholeFileFetch === body) state.wholeFileFetch = null })
  }
  return decodeValues(await state.wholeFileFetch, byteStart, valueCount)
}

export async function loadLegElevation(
  layer: GeometryLayer,
  edgeId: number,
  reversed: boolean,
  baseUrl = '/data',
): Promise<number[]> {
  const values = await cachedPromise(legCache, `${layer}:${edgeId}`, () => fetchLegValues(layer, edgeId, baseUrl))
  return reversed ? [...values].reverse() : values
}

export function _resetLegElevationCachesForTests(): void {
  manifestCache = new Map()
  legCache = new Map()
}
