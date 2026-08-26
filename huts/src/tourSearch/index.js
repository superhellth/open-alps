import { loadHutEdgesData } from './loadHutEdges.js'
import { loadApproachesData } from './loadApproaches.js'
import { searchChains } from './search.js'
import { dedupeReversePairs, suppressSimilar } from './diversity.js'

export async function loadTourSearchData(baseUrl = '/data') {
  const [hutEdges, approaches] = await Promise.all([
    loadHutEdgesData(baseUrl),
    loadApproachesData(baseUrl),
  ])
  return { hutEdges, approaches }
}

export function findTours(query, graphData, { overlapThreshold = 0.5 } = {}) {
  const { chains, killCounters } = searchChains(query, graphData)
  const deduped = dedupeReversePairs(chains)
  const diverse = suppressSimilar(deduped, overlapThreshold)
  return { chains: diverse, killCounters }
}
