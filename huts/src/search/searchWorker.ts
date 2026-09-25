import { findTours, loadTourSearchData } from '../tourSearch/index.js'
import { tripOverlaps } from '@/trip/tripOverlaps.js'
import type { WorkerRequest, WorkerResponse } from './protocol.js'

const scope = self as unknown as {
  postMessage(message: WorkerResponse): void
  onmessage: ((event: { data: WorkerRequest }) => void) | null
}

// The worker owns the full graph including the large overlap tables; the main thread never loads them.
const graph = loadTourSearchData()
graph.then(
  () => scope.postMessage({ type: 'ready' }),
  (e: Error) => scope.postMessage({ type: 'error', id: null, message: e.message }),
)

scope.onmessage = async ({ data }) => {
  try {
    const g = await graph
    if (data.type === 'search') {
      const { chains } = findTours(data.query, g, { similarityScope: 'perStart' })
      scope.postMessage({ type: 'result', id: data.id, chains })
    } else {
      const pairs = tripOverlaps({ hut: g.hutEdgeIds, start: g.startEdgeIds }, data.legs, data.loopClosure)
      scope.postMessage({ type: 'overlaps', id: data.id, pairs })
    }
  } catch (e) {
    scope.postMessage({ type: 'error', id: data.id, message: (e as Error).message })
  }
}
