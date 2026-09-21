import { describe, it, expect } from 'vitest'
import { createSearchClient, SupersededError } from './searchClient.js'
import type { WorkerLike } from './searchClient.js'
import type { WorkerRequest, WorkerResponse } from './protocol.js'
import type { Query } from '../tourSearch/types.js'

class FakeWorker implements WorkerLike {
  sent: WorkerRequest[] = []
  terminated = false
  onmessage: WorkerLike['onmessage'] = null
  onerror: WorkerLike['onerror'] = null
  postMessage(m: WorkerRequest) { this.sent.push(m) }
  terminate() { this.terminated = true }
  reply(m: WorkerResponse) { this.onmessage?.({ data: m }) }
}

const query = { mode: 'transit', legCountMin: 2, legCountMax: 3, maxLegTimeH: 8 } as Query

function setup() {
  const workers: FakeWorker[] = []
  const client = createSearchClient(() => { const w = new FakeWorker(); workers.push(w); return w })
  return { workers, client }
}

describe('searchClient', () => {
  it('resolves ready when the worker reports ready', async () => {
    const { workers, client } = setup()
    workers[0].reply({ type: 'ready' })
    await expect(client.ready).resolves.toBeUndefined()
  })

  it('resolves a search with the chains of the matching id', async () => {
    const { workers, client } = setup()
    const p = client.search(query)
    const id = workers[0].sent[0].id
    workers[0].reply({ type: 'result', id, chains: [] })
    await expect(p).resolves.toEqual([])
  })

  it('a newer search terminates the worker, respawns it and rejects the old one as superseded', async () => {
    const { workers, client } = setup()
    const first = client.search(query)
    const second = client.search(query)
    await expect(first).rejects.toBeInstanceOf(SupersededError)
    expect(workers[0].terminated).toBe(true)
    expect(workers).toHaveLength(2)
    workers[1].reply({ type: 'result', id: workers[1].sent[0].id, chains: [] })
    await expect(second).resolves.toEqual([])
  })

  it('does not terminate the worker when the previous search already finished', async () => {
    const { workers, client } = setup()
    const first = client.search(query)
    workers[0].reply({ type: 'result', id: workers[0].sent[0].id, chains: [] })
    await first
    client.search(query)
    expect(workers).toHaveLength(1)
  })

  it('rejects with the worker message on an error response', async () => {
    const { workers, client } = setup()
    const p = client.search(query)
    workers[0].reply({ type: 'error', id: workers[0].sent[0].id, message: 'boom' })
    await expect(p).rejects.toThrow('boom')
  })

  it('rejects every pending request when the worker crashes', async () => {
    const { workers, client } = setup()
    const p = client.search(query)
    workers[0].onerror?.({ message: 'crash' })
    await expect(p).rejects.toThrow('crash')
  })

  it('round-trips overlap requests and re-posts pending ones after a respawn', async () => {
    const { workers, client } = setup()
    const o = client.overlaps([], false)
    client.search(query).catch(() => {})
    client.search(query) // supersedes: respawn
    const respawned = workers[1]
    const repost = respawned.sent.find((m) => m.type === 'overlaps')!
    respawned.reply({ type: 'overlaps', id: repost.id, pairs: [[0, 1]] })
    await expect(o).resolves.toEqual([[0, 1]])
  })

  it('dispose terminates the worker and rejects pending requests', async () => {
    const { workers, client } = setup()
    const p = client.search(query)
    client.dispose()
    expect(workers[0].terminated).toBe(true)
    await expect(p).rejects.toThrow()
  })
})
