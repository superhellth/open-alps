import type { HutEdgeIdsData } from './types.js'

interface HutEdgeIdsManifest {
  rows: number
  k: number
  edge_id_count: number[]
  prefix_count: number[]
  suffix_count: number[]
  sorted_bytes: number
  prefix_bytes: number
  suffix_bytes: number
}

/** Loads hut-edge-ids.bin/.json (pipeline/phases/postprocessing/build_edge_ids.py) - the
 *  trail-segment identity behind the "avoid overlapping tracks" check. Fetched wholesale like
 *  hut-edge-payload.bin, not lazily per-leg like geometry: the overlap check runs during search,
 *  before any tour is chosen (spec §2 of docs/superpowers/specs/
 *  2026-08-29-avoid-overlapping-tracks-design.md). edgeId indexes into this exactly like it
 *  indexes into hut-edge-payload.bin (same row order, HutEdgeRecord.edgeId). */
export async function loadHutEdgeIdsData(baseUrl = '/data'): Promise<HutEdgeIdsData> {
  const manifest: HutEdgeIdsManifest = await (await fetch(`${baseUrl}/hut-edge-ids.json`)).json()
  const buffer = await (await fetch(`${baseUrl}/hut-edge-ids.bin`)).arrayBuffer()

  const sortedOffsets = new Array<number>(manifest.rows + 1)
  sortedOffsets[0] = 0
  for (let i = 0; i < manifest.rows; i++) {
    sortedOffsets[i + 1] = sortedOffsets[i] + manifest.edge_id_count[i]
  }

  const k = manifest.k
  const sortedStart = 0
  const prefixStart = manifest.sorted_bytes
  const suffixStart = prefixStart + manifest.prefix_bytes

  const sortedView = new Int32Array(buffer, sortedStart, manifest.sorted_bytes / 4)
  const prefixView = new Int32Array(buffer, prefixStart, manifest.prefix_bytes / 4)
  const suffixView = new Int32Array(buffer, suffixStart, manifest.suffix_bytes / 4)

  return {
    getSortedIds(edgeId: number): Int32Array {
      return sortedView.subarray(sortedOffsets[edgeId], sortedOffsets[edgeId + 1])
    },
    getPrefixIds(edgeId: number): Int32Array {
      return prefixView.subarray(edgeId * k, edgeId * k + manifest.prefix_count[edgeId])
    },
    getSuffixIds(edgeId: number): Int32Array {
      return suffixView.subarray(edgeId * k, edgeId * k + manifest.suffix_count[edgeId])
    },
  }
}
