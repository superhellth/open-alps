import { loadHutEdgesData } from './loadHutEdges.js'
import { loadApproachesData } from './loadApproaches.js'
import { loadHutEdgeIdsData, loadStartEdgeIdsData } from './loadHutEdgeIds.js'
import { searchChains } from './search.js'
import { dedupeReversePairs, suppressSimilar } from './diversity.js'
import type { GraphData, Query, SearchResult } from './types.js'
import type { TripGraph } from './tripLegs.js'

export async function loadTourSearchData(baseUrl = '/data'): Promise<GraphData> {
  const [hutEdges, approaches, hutEdgeIds, startEdgeIds] = await Promise.all([
    loadHutEdgesData(baseUrl),
    loadApproachesData(baseUrl),
    loadHutEdgeIdsData(baseUrl),
    loadStartEdgeIdsData(baseUrl),
  ])
  return { hutEdges, approaches, hutEdgeIds, startEdgeIds }
}

/** The main-thread graph: routing edges and approaches only (the multi-hundred-MB overlap tables
 *  are loaded by the search worker). */
export async function loadTripGraph(baseUrl = '/data'): Promise<TripGraph> {
  const [hutEdges, approaches] = await Promise.all([loadHutEdgesData(baseUrl), loadApproachesData(baseUrl)])
  return { hutEdges, approaches }
}

export function findTours(
  query: Query,
  graphData: GraphData,
  options: { similarityScope?: 'global' | 'perStart' } = {},
): SearchResult {
  const { chains, killCounters } = searchChains(query, graphData)
  const deduped = dedupeReversePairs(chains)
  const diverse = suppressSimilar(deduped, { scope: options.similarityScope })
  return { chains: diverse, killCounters }
}
