/**
 * Byte-range-fetchable per-edge trail geometry (docs/superpowers/specs/2026-08-27-tour-geometry-design.md
 * §A/§E): <layer>-geometry.bin is every edge's simplified [lon, lat] points, back to back in
 * edge_id order, each point an f4 pair (8 bytes, no framing) - <layer>-geometry.json's
 * point_counts gives each edge's point count, from which a byte range is a prefix sum.
 */
export type GeometryLayer = 'hut_edges' | 'start_edges' | 'tour_edges'

interface GeometryManifest {
  point_counts: number[]
}

interface LayerState {
  offsets: number[] // length point_counts.length + 1, in points (not bytes)
  // Set once a host is discovered to ignore Range and answer 200 with the whole body - every
  // later leg on this layer reuses it instead of re-downloading the whole file (spec §E).
  wholeFileFetch: Promise<ArrayBuffer> | null
}

const POINT_BYTES = 8 // f4 lon + f4 lat

const LAYER_FILES: Record<GeometryLayer, { json: string; bin: string }> = {
  hut_edges: { json: 'hut-edge-geometry.json', bin: 'hut-edge-geometry.bin' },
  start_edges: { json: 'start-edge-geometry.json', bin: 'start-edge-geometry.bin' },
  tour_edges: { json: 'tour-edge-geometry.json', bin: 'tour-edge-geometry.bin' },
}

let manifestCache = new Map<GeometryLayer, Promise<LayerState>>()
let legCache = new Map<string, Promise<[number, number][]>>()

function loadLayerState(layer: GeometryLayer, baseUrl: string): Promise<LayerState> {
  let cached = manifestCache.get(layer)
  if (!cached) {
    cached = (async () => {
      const manifest: GeometryManifest = await (await fetch(`${baseUrl}/${LAYER_FILES[layer].json}`)).json()
      const offsets = new Array<number>(manifest.point_counts.length + 1)
      offsets[0] = 0
      for (let i = 0; i < manifest.point_counts.length; i++) {
        offsets[i + 1] = offsets[i] + manifest.point_counts[i]
      }
      return { offsets, wholeFileFetch: null }
    })()
    manifestCache.set(layer, cached)
  }
  return cached
}

function decodePoints(buffer: ArrayBuffer, byteOffset: number, pointCount: number): [number, number][] {
  const view = new DataView(buffer, byteOffset, pointCount * POINT_BYTES)
  const points: [number, number][] = new Array(pointCount)
  for (let i = 0; i < pointCount; i++) {
    const lon = view.getFloat32(i * POINT_BYTES, true)
    const lat = view.getFloat32(i * POINT_BYTES + 4, true)
    points[i] = [lat, lon]
  }
  return points
}

async function fetchLegPoints(layer: GeometryLayer, edgeId: number, baseUrl: string): Promise<[number, number][]> {
  const state = await loadLayerState(layer, baseUrl)
  const startPoint = state.offsets[edgeId]
  const pointCount = state.offsets[edgeId + 1] - startPoint
  const byteStart = startPoint * POINT_BYTES
  const byteEnd = byteStart + pointCount * POINT_BYTES - 1

  if (state.wholeFileFetch) {
    return decodePoints(await state.wholeFileFetch, byteStart, pointCount)
  }

  const url = `${baseUrl}/${LAYER_FILES[layer].bin}`
  const res = await fetch(url, { headers: { Range: `bytes=${byteStart}-${byteEnd}` } })
  if (res.status === 206) {
    return decodePoints(await res.arrayBuffer(), 0, pointCount)
  }

  // Host ignored Range and answered 200 with the entire body - do not retry with another Range
  // request. Decode this leg out of the full body, and cache the full body itself so this
  // (large) download happens at most once per layer per session.
  if (!state.wholeFileFetch) state.wholeFileFetch = res.arrayBuffer()
  return decodePoints(await state.wholeFileFetch, byteStart, pointCount)
}

export async function loadLegGeometry(
  layer: GeometryLayer,
  edgeId: number,
  reversed: boolean,
  baseUrl = '/data',
): Promise<[number, number][]> {
  const cacheKey = `${layer}:${edgeId}`
  let cached = legCache.get(cacheKey)
  if (!cached) {
    cached = fetchLegPoints(layer, edgeId, baseUrl)
    legCache.set(cacheKey, cached)
  }
  const points = await cached
  return reversed ? [...points].reverse() : points
}

export function _resetLegGeometryCachesForTests(): void {
  manifestCache = new Map()
  legCache = new Map()
}
