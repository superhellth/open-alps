import { loadHutEdgesData } from './loadHutEdges.js'
import { loadApproachesData } from './loadApproaches.js'
import { loadHutEdgeIdsData, loadStartEdgeIdsData } from './loadHutEdgeIds.js'
import { searchChains } from './search.js'
import { dedupeReversePairs, suppressSimilar } from './diversity.js'
import type { GraphData, Query, SearchResult } from './types.js'

export async function loadTourSearchData(baseUrl = '/data'): Promise<GraphData> {
  const [hutEdges, approaches, hutEdgeIds, startEdgeIds] = await Promise.all([
    loadHutEdgesData(baseUrl),
    loadApproachesData(baseUrl),
    loadHutEdgeIdsData(baseUrl),
    loadStartEdgeIdsData(baseUrl),
  ])
  return { hutEdges, approaches, hutEdgeIds, startEdgeIds }
}

export function findTours(query: Query, graphData: GraphData): SearchResult {
  const { chains, killCounters } = searchChains(query, graphData)
  const deduped = dedupeReversePairs(chains)
  const diverse = suppressSimilar(deduped)
  return { chains: diverse, killCounters }
}
