import type { ElevationManifest } from './types.js'

/** Decodes hut-edge-elevation.bin's flat f4 elevation-value stream (edge_id order, no framing)
 *  into one number[] per edge, using profile_counts as a prefix-sum offset table. Structurally
 *  identical to decodeEdgeGeometry.ts, one value per manifest slot instead of one [lon,lat] pair. */
export function decodeEdgeElevation(manifest: ElevationManifest, buffer: ArrayBuffer): number[][] {
  const floats = new Float32Array(buffer)
  const perEdge: number[][] = new Array(manifest.profile_counts.length)
  let valueOffset = 0
  for (let i = 0; i < manifest.profile_counts.length; i++) {
    const count = manifest.profile_counts[i]
    const values: number[] = new Array(count)
    for (let p = 0; p < count; p++) {
      values[p] = floats[valueOffset + p]
    }
    perEdge[i] = values
    valueOffset += count
  }
  return perEdge
}
