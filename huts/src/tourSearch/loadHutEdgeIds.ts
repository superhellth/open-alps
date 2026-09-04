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

/** Loads a <basename>.bin/.json pair built by pipeline/phases/postprocessing/build_edge_ids.py -
 *  the trail-segment identity the "avoid overlapping tracks" search-time check needs (spec §2 of
 *  docs/superpowers/specs/2026-08-29-avoid-overlapping-tracks-design.md, extended to start_edges
 *  by docs/superpowers/specs/2026-09-04-approach-exit-overlap-avoidance-design.md §2). Fetched
 *  wholesale, not lazily per-leg like geometry: the overlap check runs during search, before any
 *  tour is chosen. edgeId indexes into this exactly like it indexes into hut-edge-payload.bin /
 *  approaches.bin (same row order). build_edge_ids.py is generic over its --edges-dir, so the same
 *  manifest/binary shape serves both hut_edges and start_edges - hence one implementation here. */
async function loadEdgeIdsData(baseUrl: string, binName: string, jsonName: string): Promise<HutEdgeIdsData> {
  const manifest: HutEdgeIdsManifest = await (await fetch(`${baseUrl}/${jsonName}`)).json()
  const buffer = await (await fetch(`${baseUrl}/${binName}`)).arrayBuffer()

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

export function loadHutEdgeIdsData(baseUrl = '/data'): Promise<HutEdgeIdsData> {
  return loadEdgeIdsData(baseUrl, 'hut-edge-ids.bin', 'hut-edge-ids.json')
}

export function loadStartEdgeIdsData(baseUrl = '/data'): Promise<HutEdgeIdsData> {
  return loadEdgeIdsData(baseUrl, 'start-edge-ids.bin', 'start-edge-ids.json')
}
