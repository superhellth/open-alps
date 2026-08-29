import { loadHutEdgesData } from './loadHutEdges.js'
import { loadApproachesData } from './loadApproaches.js'
import { loadHutEdgeIdsData } from './loadHutEdgeIds.js'
import { searchChains } from './search.js'
import { dedupeReversePairs, suppressSimilar } from './diversity.js'
import type { GraphData, Query, SearchResult } from './types.js'

export async function loadTourSearchData(baseUrl = '/data'): Promise<GraphData> {
  const [hutEdges, approaches, hutEdgeIds] = await Promise.all([
    loadHutEdgesData(baseUrl),
    loadApproachesData(baseUrl),
    loadHutEdgeIdsData(baseUrl),
  ])
  return { hutEdges, approaches, hutEdgeIds }
}

export function findTours(query: Query, graphData: GraphData): SearchResult {
  const { chains, killCounters } = searchChains(query, graphData)
  const deduped = dedupeReversePairs(chains)
  const diverse = suppressSimilar(deduped)
  return { chains: diverse, killCounters }
}
