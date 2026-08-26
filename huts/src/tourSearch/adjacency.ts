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
