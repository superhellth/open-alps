import { loadHutEdgesData } from './loadHutEdges.js'
import { loadApproachesData } from './loadApproaches.js'
import { searchChains } from './search.js'
import { dedupeReversePairs, suppressSimilar } from './diversity.js'
import type { GraphData, Query, SearchResult } from './types.js'

export async function loadTourSearchData(baseUrl = '/data'): Promise<GraphData> {
  const [hutEdges, approaches] = await Promise.all([
    loadHutEdgesData(baseUrl),
    loadApproachesData(baseUrl),
  ])
  return { hutEdges, approaches }
}

export function findTours(
  query: Query,
  graphData: GraphData,
  { overlapThreshold = 0.5 }: { overlapThreshold?: number } = {},
): SearchResult {
  const { chains, killCounters } = searchChains(query, graphData)
  const deduped = dedupeReversePairs(chains)
  const diverse = suppressSimilar(deduped, overlapThreshold)
  return { chains: diverse, killCounters }
}
