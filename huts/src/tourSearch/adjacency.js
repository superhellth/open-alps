import { forwardHutLeg, reverseHutLeg } from './reverseLeg.js'

export function buildAdjacency(hutEdgesData, variant) {
  const adjacency = new Map()
  const push = (hutIndex, leg) => {
    if (!adjacency.has(hutIndex)) adjacency.set(hutIndex, [])
    adjacency.get(hutIndex).push(leg)
  }
  for (const record of hutEdgesData.records) {
    if (record.variant !== variant) continue
    push(record.fromIndex, forwardHutLeg(record))
    push(record.toIndex, reverseHutLeg(record))
  }
  return adjacency
}
