import { createServer, type Server } from 'node:http'
import type { AddressInfo } from 'node:net'
import { mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest'
import { createGpxApi } from './gpxEditorPlugin.js'

const GPX = '<?xml version="1.0"?><gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg></trkseg></trk></gpx>'
const NEW_GPX = GPX.replace('<trkseg>', '<trkseg><trkpt lat="1" lon="2"/>')

let root: string
let toursDir: string
let server: Server
let base: string

beforeAll(async () => {
  root = mkdtempSync(path.join(tmpdir(), 'gpx-api-'))
  toursDir = path.join(root, 'tours')
  const api = createGpxApi({
    toursDir,
    hubsPath: path.join(root, 'hubs.json'),
    configPath: path.join(root, 'pipeline.config.json'),
  })
  server = createServer((req, res) => api(req, res, () => { res.statusCode = 418; res.end() }))
  await new Promise<void>((r) => server.listen(0, r))
  base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`
})

afterAll(() => {
  server.close()
  rmSync(root, { recursive: true, force: true })
})

beforeEach(() => {
  rmSync(toursDir, { recursive: true, force: true })
  mkdirSync(path.join(toursDir, 'Kaisertour'), { recursive: true })
  for (const n of ['1', '2', '10']) writeFileSync(path.join(toursDir, 'Kaisertour', `${n}.gpx`), GPX)
  // NFD on disk, requested as NFC below
  mkdirSync(path.join(toursDir, 'Welser Höhenweg'))
  writeFileSync(path.join(toursDir, 'Welser Höhenweg', '1.gpx'), GPX)
})

const leg = (tour: string, n: string) => `${base}/api/gpx/tours/${encodeURIComponent(tour)}/${n}`

describe('gpx api', () => {
  it('passes non-api urls to next', async () => {
    expect((await fetch(`${base}/other`)).status).toBe(418)
  })

  it('lists tours with numerically sorted legs', async () => {
    const body = await (await fetch(`${base}/api/gpx/tours`)).json()
    expect(body).toEqual([
      { name: 'Kaisertour', legs: [1, 2, 10] },
      { name: 'Welser Höhenweg', legs: [1] },
    ])
  })

  it('GET leg returns raw text and mtime header', async () => {
    const res = await fetch(leg('Kaisertour', '1'))
    expect(res.status).toBe(200)
    expect(await res.text()).toBe(GPX)
    expect(Number(res.headers.get('x-gpx-mtime'))).toBeGreaterThan(0)
  })

  it('resolves a non-ASCII, space-containing tour name (NFC request, NFD folder)', async () => {
    expect((await fetch(leg('Welser Höhenweg', '1'))).status).toBe(200)
  })

  it('rejects traversal and bad legs', async () => {
    expect((await fetch(`${base}/api/gpx/tours/..%2F..%2Fetc/1`)).status).toBe(404)
    expect((await fetch(`${base}/api/gpx/tours/../1`)).status).toBeGreaterThanOrEqual(400)
    expect((await fetch(leg('Kaisertour', '1a'))).status).toBe(400)
    expect((await fetch(leg('Kaisertour', '99'))).status).toBe(404)
    expect((await fetch(leg('Nope', '1'))).status).toBe(404)
  })

  it('PUT with matching mtime writes atomically and returns new mtime', async () => {
    const get = await fetch(leg('Kaisertour', '1'))
    const mtime = get.headers.get('x-gpx-mtime')!
    const put = await fetch(leg('Kaisertour', '1'), { method: 'PUT', headers: { 'If-Gpx-Mtime': mtime }, body: NEW_GPX })
    expect(put.status).toBe(200)
    expect(typeof (await put.json()).mtime).toBe('string')
    expect(readFileSync(path.join(toursDir, 'Kaisertour', '1.gpx'), 'utf-8')).toBe(NEW_GPX)
    expect(readdirSync(path.join(toursDir, 'Kaisertour')).sort()).toEqual(['1.gpx', '10.gpx', '2.gpx'])
  })

  it('PUT with stale or missing mtime returns 409 and writes nothing', async () => {
    const stale = await fetch(leg('Kaisertour', '1'), { method: 'PUT', headers: { 'If-Gpx-Mtime': '1' }, body: NEW_GPX })
    expect(stale.status).toBe(409)
    const missing = await fetch(leg('Kaisertour', '1'), { method: 'PUT', body: NEW_GPX })
    expect(missing.status).toBe(409)
    expect(readFileSync(path.join(toursDir, 'Kaisertour', '1.gpx'), 'utf-8')).toBe(GPX)
  })

  it('PUT rejects a body that is not GPX', async () => {
    const mtime = (await fetch(leg('Kaisertour', '1'))).headers.get('x-gpx-mtime')!
    const put = await fetch(leg('Kaisertour', '1'), { method: 'PUT', headers: { 'If-Gpx-Mtime': mtime }, body: 'hello' })
    expect(put.status).toBe(400)
  })

  it('hubs: 404 naming the missing file, then contents once present', async () => {
    const miss = await fetch(`${base}/api/gpx/hubs`)
    expect(miss.status).toBe(404)
    expect((await miss.json()).error).toContain('data/build/tour-edges/hubs.json')
    writeFileSync(path.join(root, 'hubs.json'), '[{"id":0}]')
    expect(await (await fetch(`${base}/api/gpx/hubs`)).json()).toEqual([{ id: 0 }])
  })

  it('config returns graph.maxSnapM', async () => {
    writeFileSync(path.join(root, 'pipeline.config.json'), '{"graph":{"maxSnapM":100}}')
    expect(await (await fetch(`${base}/api/gpx/config`)).json()).toEqual({ maxSnapM: 100 })
  })
})
