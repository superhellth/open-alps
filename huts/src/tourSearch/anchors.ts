export const ANCHOR_UNIT_DEG = 1e-4

export interface LatLng { lat: number; lng: number }

const ANCHOR_COLUMNS = [['a25_dlat', 'a25_dlng'], ['a50_dlat', 'a50_dlng'], ['a75_dlat', 'a75_dlng']] as const

/** Flat `[dlat0, dlng0, dlat1, dlng1, ...]` of the anchor columns the payload carries, in arc-length order; null when it carries none. */
export function readAnchorOffsets(columns: Record<string, number[]>, row: number): number[] | null {
  const out: number[] = []
  for (const [dlat, dlng] of ANCHOR_COLUMNS) {
    if (columns[dlat] && columns[dlng]) out.push(columns[dlat][row], columns[dlng][row])
  }
  return out.length > 0 ? out : null
}

/** Absolute anchors of an edge in its stored direction; offsets count 1e-4 degrees from `ref`. */
export function decodeAnchors(offsets: readonly number[], ref: LatLng): LatLng[] {
  const out: LatLng[] = []
  for (let i = 0; i + 1 < offsets.length; i += 2) {
    out.push({ lat: ref.lat + offsets[i] * ANCHOR_UNIT_DEG, lng: ref.lng + offsets[i + 1] * ANCHOR_UNIT_DEG })
  }
  return out
}

/** Arc-length fractions of `count` evenly spread anchors: 3 gives 25/50/75 %, 1 gives 50 %. */
export function anchorFractions(count: number): number[] {
  return Array.from({ length: count }, (_, i) => (i + 1) / (count + 1))
}
