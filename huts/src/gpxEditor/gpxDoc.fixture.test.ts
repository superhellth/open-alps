// @vitest-environment jsdom
import { readFileSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, it, expect } from 'vitest'
import { deleteEdit, insertEdit, moveEdit, parseGpx, serializeGpx } from './gpxDoc.js'
import { composite } from './history.js'

// jsdom replaces the global URL class, so resolve paths through node:path instead of new URL().
const dir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../pipeline/tests/fixtures/gpx_edited')

describe('gpx round-trip fixture', () => {
  it('source + (move 1, insert after 2, delete 0) serializes to edited.gpx', () => {
    const g = parseGpx(readFileSync(path.join(dir, 'source.gpx'), 'utf-8'))
    composite([
      moveEdit(g, 1, { lon: 11.25, lat: 47.25 }),
      insertEdit(g, 2, [{ lon: 11.35, lat: 47.35 }]),
      deleteEdit(g, 0),
    ]).apply()
    const out = serializeGpx(g)
    if (process.env.UPDATE_FIXTURE) writeFileSync(path.join(dir, 'edited.gpx'), out)
    expect(out).toBe(readFileSync(path.join(dir, 'edited.gpx'), 'utf-8'))
  })
})
