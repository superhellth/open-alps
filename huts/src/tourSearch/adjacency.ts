import { forwardHutLeg, reverseHutLeg } from './reverseLeg.js'
import type { HutEdgesData, HutLeg } from './types.js'

export function buildAdjacency(hutEdgesData: HutEdgesData, variant: number): Map<number, HutLeg[]> {
  const adjacency = new Map<number, HutLeg[]>()
  const push = (hutIndex: number, leg: HutLeg) => {
    if (!adjacency.has(hutIndex)) adjacency.set(hutIndex, [])
    adjacency.get(hutIndex)!.push(leg)
  }
  for (const record of hutEdgesData.records) {
    if (record.variant !== variant) continue
    push(record.fromIndex, forwardHutLeg(record))
    push(record.toIndex, reverseHutLeg(record))
  }
  return adjacency
}

const adjacencyCache = new WeakMap<HutEdgesData, Map<number, Map<number, HutLeg[]>>>()

/** buildAdjacency, memoised per payload object and variant (trip editing asks repeatedly). */
export function getAdjacency(hutEdgesData: HutEdgesData, variant: number): Map<number, HutLeg[]> {
  let byVariant = adjacencyCache.get(hutEdgesData)
  if (!byVariant) {
    byVariant = new Map()
    adjacencyCache.set(hutEdgesData, byVariant)
  }
  let adjacency = byVariant.get(variant)
  if (!adjacency) {
    adjacency = buildAdjacency(hutEdgesData, variant)
    byVariant.set(variant, adjacency)
  }
  return adjacency
}
