import type { Query, TourResult } from '../tourSearch/types.js'
import type { OverlapLeg } from '../tourSearch/tripOverlaps.js'
import type { WorkerRequest, WorkerResponse } from './protocol.js'

export class SupersededError extends Error {
  constructor() {
    super('Suche wurde durch eine neuere ersetzt')
  }
}

export interface WorkerLike {
  postMessage(message: WorkerRequest): void
  terminate(): void
  onmessage: ((event: { data: WorkerResponse }) => void) | null
  onerror: ((event: { message?: string }) => void) | null
}

export interface SearchClient {
  /** Resolves when the first worker has loaded the whole graph. */
  ready: Promise<void>
  search(query: Query): Promise<TourResult[]>
  overlaps(legs: OverlapLeg[], loopClosure: boolean): Promise<[number, number][]>
  dispose(): void
}

interface Pending {
  request: WorkerRequest
  resolve(value: never): void
  reject(error: Error): void
}

export function createSearchClient(makeWorker: () => WorkerLike): SearchClient {
  let nextId = 1
  const pending = new Map<number, Pending>()
  let resolveReady!: () => void
  let rejectReady!: (e: Error) => void
  const ready = new Promise<void>((resolve, reject) => { resolveReady = resolve; rejectReady = reject })
  ready.catch(() => {}) // an unobserved rejection must not surface as an unhandled one

  function failAll(error: Error) {
    for (const p of pending.values()) p.reject(error)
    pending.clear()
  }

  function spawn(): WorkerLike {
    const w = makeWorker()
    w.onmessage = ({ data }) => {
      if (data.type === 'ready') { resolveReady(); return }
      if (data.type === 'error' && data.id === null) { rejectReady(new Error(data.message)); failAll(new Error(data.message)); return }
      const id = data.id as number
      const p = pending.get(id)
      if (!p) return // stale response of a superseded request
      pending.delete(id)
      if (data.type === 'error') p.reject(new Error(data.message))
      else if (data.type === 'result') p.resolve(data.chains as never)
      else if (data.type === 'overlaps') p.resolve(data.pairs as never)
    }
    w.onerror = (e) => {
      const error = new Error(e.message ?? 'Suchworker abgestürzt')
      rejectReady(error)
      failAll(error)
    }
    return w
  }

  let worker = spawn()

  function post<T>(request: WorkerRequest): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      pending.set(request.id, { request, resolve: resolve as (v: never) => void, reject })
      worker.postMessage(request)
    })
  }

  return {
    ready,
    search(query) {
      let superseded = false
      for (const [id, p] of pending) {
        if (p.request.type !== 'search') continue
        p.reject(new SupersededError())
        pending.delete(id)
        superseded = true
      }
      if (superseded) {
        worker.terminate()
        worker = spawn()
        for (const p of pending.values()) worker.postMessage(p.request) // overlap requests survive the respawn
      }
      return post<TourResult[]>({ type: 'search', id: nextId++, query })
    },
    overlaps(legs, loopClosure) {
      return post<[number, number][]>({ type: 'overlaps', id: nextId++, legs, loopClosure })
    },
    dispose() {
      worker.terminate()
      failAll(new Error('Suchclient beendet'))
    },
  }
}
