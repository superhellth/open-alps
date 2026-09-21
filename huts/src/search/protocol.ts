import type { Query, TourResult } from '../tourSearch/types.js'
import type { OverlapLeg } from '../tourSearch/tripOverlaps.js'

export type WorkerRequest =
  | { type: 'search'; id: number; query: Query }
  | { type: 'overlaps'; id: number; legs: OverlapLeg[]; loopClosure: boolean }

export type WorkerResponse =
  | { type: 'ready' }
  | { type: 'result'; id: number; chains: TourResult[] }
  | { type: 'overlaps'; id: number; pairs: [number, number][] }
  | { type: 'error'; id: number | null; message: string }
