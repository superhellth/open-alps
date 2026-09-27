import type { WorkerLike } from './searchClient.js'

export function makeSearchWorker(): WorkerLike {
  return new Worker(new URL('./searchWorker.ts', import.meta.url), { type: 'module' }) as unknown as WorkerLike
}
