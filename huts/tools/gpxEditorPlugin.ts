import { promises as fs } from 'node:fs'
import type { IncomingMessage, ServerResponse } from 'node:http'
import path from 'node:path'
import type { Plugin } from 'vite'

export interface GpxApiPaths {
  toursDir: string
  hubsPath: string
  configPath: string
}

class HttpError extends Error {
  constructor(readonly status: number, message: string) {
    super(message)
  }
}

const MAX_BODY_BYTES = 32 * 1024 * 1024

function sendJson(res: ServerResponse, status: number, body: unknown, headers: Record<string, string> = {}) {
  res.statusCode = status
  res.setHeader('Content-Type', 'application/json; charset=utf-8')
  for (const [k, v] of Object.entries(headers)) res.setHeader(k, v)
  res.end(JSON.stringify(body))
}

async function readBody(req: IncomingMessage): Promise<string> {
  const chunks: Buffer[] = []
  let size = 0
  for await (const chunk of req) {
    size += (chunk as Buffer).length
    if (size > MAX_BODY_BYTES) throw new HttpError(413, 'body too large')
    chunks.push(chunk as Buffer)
  }
  return Buffer.concat(chunks).toString('utf-8')
}

async function resolveTourDir(toursDir: string, name: string): Promise<string> {
  const wanted = name.normalize('NFC')
  const entries = await fs.readdir(toursDir, { withFileTypes: true })
  const hit = entries.find((e) => e.isDirectory() && e.name.normalize('NFC') === wanted)
  if (!hit) throw new HttpError(404, `unknown tour: ${name}`)
  return path.join(toursDir, hit.name)
}

async function resolveLegFile(tourDir: string, leg: string): Promise<string> {
  if (!/^\d+$/.test(leg)) throw new HttpError(400, 'leg must be an integer')
  const file = path.join(tourDir, `${leg}.gpx`)
  try {
    await fs.stat(file)
  } catch {
    throw new HttpError(404, `unknown leg: ${leg}`)
  }
  return file
}

async function listTours(toursDir: string) {
  const entries = await fs.readdir(toursDir, { withFileTypes: true })
  const tours = []
  for (const e of entries.filter((d) => d.isDirectory()).sort((a, b) => (a.name < b.name ? -1 : 1))) {
    const files = await fs.readdir(path.join(toursDir, e.name))
    const legs = files.filter((f) => /^\d+\.gpx$/.test(f)).map((f) => parseInt(f, 10)).sort((a, b) => a - b)
    tours.push({ name: e.name, legs })
  }
  return tours
}

async function readJsonFile(file: string, missingMessage: string): Promise<unknown> {
  try {
    return JSON.parse(await fs.readFile(file, 'utf-8'))
  } catch (e) {
    if ((e as NodeJS.ErrnoException).code === 'ENOENT') throw new HttpError(404, missingMessage)
    throw e
  }
}

async function handle(paths: GpxApiPaths, req: IncomingMessage, res: ServerResponse, segments: string[]) {
  const [head, tourName, leg] = segments
  if (head === 'tours' && segments.length === 1 && req.method === 'GET') {
    return sendJson(res, 200, await listTours(paths.toursDir))
  }
  if (head === 'tours' && segments.length === 3 && tourName !== undefined && leg !== undefined) {
    const file = await resolveLegFile(await resolveTourDir(paths.toursDir, tourName), leg)
    if (req.method === 'GET') {
      const [text, st] = await Promise.all([fs.readFile(file, 'utf-8'), fs.stat(file)])
      res.statusCode = 200
      res.setHeader('Content-Type', 'application/gpx+xml; charset=utf-8')
      res.setHeader('X-Gpx-Mtime', String(st.mtimeMs))
      return void res.end(text)
    }
    if (req.method === 'PUT') {
      const body = await readBody(req)
      if (!body.includes('<gpx')) throw new HttpError(400, 'body is not a GPX document')
      if (String((await fs.stat(file)).mtimeMs) !== req.headers['if-gpx-mtime']) {
        throw new HttpError(409, 'file changed on disk since it was loaded')
      }
      const tmp = `${file}.tmp-${process.pid}-${Date.now()}`
      try {
        await fs.writeFile(tmp, body, 'utf-8')
        await fs.rename(tmp, file)
      } catch (e) {
        await fs.rm(tmp, { force: true })
        throw e
      }
      return sendJson(res, 200, { mtime: String((await fs.stat(file)).mtimeMs) })
    }
  }
  if (head === 'hubs' && segments.length === 1 && req.method === 'GET') {
    return sendJson(res, 200, await readJsonFile(paths.hubsPath,
      'data/osm/hubs.json not found - run `doit match_tour_edges` first'))
  }
  if (head === 'config' && segments.length === 1 && req.method === 'GET') {
    const cfg = (await readJsonFile(paths.configPath, 'pipeline/pipeline.config.json not found')) as
      { graph?: { maxSnapM?: number } }
    const maxSnapM = cfg.graph?.maxSnapM
    if (typeof maxSnapM !== 'number') throw new HttpError(500, 'graph.maxSnapM missing in pipeline.config.json')
    return sendJson(res, 200, { maxSnapM })
  }
  throw new HttpError(404, 'no such gpx api route')
}

export function createGpxApi(paths: GpxApiPaths) {
  return (req: IncomingMessage, res: ServerResponse, next: () => void): void => {
    const { pathname } = new URL(req.url ?? '/', 'http://localhost')
    if (!pathname.startsWith('/api/gpx/')) return next()
    let segments: string[]
    try {
      segments = pathname.slice('/api/gpx/'.length).split('/').map(decodeURIComponent)
    } catch {
      return sendJson(res, 400, { error: 'bad url encoding' })
    }
    handle(paths, req, res, segments).catch((e: unknown) => {
      const status = e instanceof HttpError ? e.status : 500
      sendJson(res, status, { error: e instanceof Error ? e.message : String(e) })
    })
  }
}

export function gpxEditorPlugin(repoRoot: string): Plugin {
  return {
    name: 'gpx-editor-api',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use(createGpxApi({
        toursDir: path.join(repoRoot, 'pipeline', 'tours'),
        hubsPath: path.join(repoRoot, 'data', 'osm', 'hubs.json'),
        configPath: path.join(repoRoot, 'pipeline', 'pipeline.config.json'),
      }))
    },
  }
}
