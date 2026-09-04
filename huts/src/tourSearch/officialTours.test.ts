import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { buildOfficialTourViews } from './officialTours.js'
import { loadOfficialTours } from './loadOfficialTours.js'
import { loadTourEdgesData } from './loadTourEdges.js'
import { readColumns } from './binaryColumns.js'
import type { RawTour } from './loadOfficialTours.js'
import type { TourEdgeRecord } from './loadTourEdges.js'

const completeTour: RawTour = {
  tourId: 1, name: 'Welser Höhenweg',
  legs: [
    { legIndex: 0, from: { type: 'parking', id: 1 }, to: { type: 'hut', id: 302 } },
    { legIndex: 1, from: { type: 'hut', id: 302 }, to: { type: 'hut', id: 376 } },
  ],
}
const completeRecords = new Map<string, TourEdgeRecord>([
  ['1:0', { distanceM: 6000, ascentM: 800, descentM: 100, maxEleM: 1400, sacRank: 3, viaFerrata: false, edgeId: 0 }],
  ['1:1', { distanceM: 10000, ascentM: 1000, descentM: 800, maxEleM: 2000, sacRank: 3, viaFerrata: false, edgeId: 1 }],
])

const gappedTour: RawTour = {
  tourId: 0, name: 'Kaisertour',
  legs: [
    { legIndex: 0, from: { type: 'parking', id: 5 }, to: { type: 'hut', id: 186 } },
    { legIndex: 1, from: null, to: null }, // a real gap leg (§1)
  ],
}

describe('buildOfficialTourViews', () => {
  it('includes a tour whose every leg has a resolved from/to and a matching payload row', () => {
    const views = buildOfficialTourViews([completeTour], completeRecords)
    expect(views).toHaveLength(1)
    expect(views[0].tourId).toBe(1)
    expect(views[0].legs).toHaveLength(2)
    expect(views[0].legs[0]).toMatchObject({
      legIndex: 0, from: { type: 'parking', id: 1 }, to: { type: 'hut', id: 302 }, edgeId: 0, reversed: false,
      distanceM: 6000, ascentM: 800, descentM: 100,
    })
    expect(views[0].totalDistanceM).toBe(16000)
    expect(views[0].totalAscentM).toBe(1800)
    expect(views[0].totalDescentM).toBe(900)
    // DIN duration of leg 0 (6000m, 800m up, 100m down) + leg 1 (10000m, 1000m up, 800m down),
    // computed the same way dinDuration.test.ts already verifies the formula.
    expect(views[0].totalDurationH).toBeGreaterThan(0)
  })

  it('drops a tour with a gap leg (null from/to) entirely, not partially', () => {
    const views = buildOfficialTourViews([gappedTour], completeRecords)
    expect(views).toHaveLength(0)
  })

  it('drops a tour whose leg has resolved from/to but no matching tourEdgeRecords entry', () => {
    const tour: RawTour = {
      tourId: 2, name: 'Missing Row',
      legs: [{ legIndex: 0, from: { type: 'hut', id: 1 }, to: { type: 'hut', id: 2 } }],
    }
    expect(buildOfficialTourViews([tour], new Map())).toHaveLength(0)
  })

  it('resolves a partner_betrieb endpoint and labels a mixed hut->station tour correctly', () => {
    const tour: RawTour = {
      tourId: 3, name: 'Mixed',
      legs: [{ legIndex: 0, from: { type: 'hut', id: 1 }, to: { type: 'partner_betrieb', id: 99 } }],
    }
    const records = new Map<string, TourEdgeRecord>([
      ['3:0', { distanceM: 1000, ascentM: 10, descentM: 20, maxEleM: 900, sacRank: 1, viaFerrata: false, edgeId: 0 }],
    ])
    const views = buildOfficialTourViews([tour], records)
    expect(views).toHaveLength(1)
    expect(views[0].legs[0].to).toEqual({ type: 'partner_betrieb', id: 99 })
  })
})

describe('buildOfficialTourViews against the real shipped payload', () => {
  const DATA_DIR = fileURLToPath(new URL('../../public/data/', import.meta.url))

  it('yields exactly Welser Höhenweg (Kaisertour is fully gapped as of the current pipeline run)', async () => {
    const tours: RawTour[] = JSON.parse(readFileSync(`${DATA_DIR}tours.json`, 'utf-8'))
    const manifest = JSON.parse(readFileSync(`${DATA_DIR}tour-edge-payload.json`, 'utf-8'))
    const binBuf = readFileSync(`${DATA_DIR}tour-edge-payload.bin`)
    const buffer = binBuf.buffer.slice(binBuf.byteOffset, binBuf.byteOffset + binBuf.byteLength) as ArrayBuffer
    const c = readColumns(buffer, manifest)
    const records = new Map<string, TourEdgeRecord>()
    for (let i = 0; i < manifest.rows; i++) {
      records.set(`${c.tour_id[i]}:${c.leg_index[i]}`, {
        distanceM: c.distance_m[i], ascentM: c.ascent_m[i], descentM: c.descent_m[i],
        maxEleM: c.max_ele_m[i], sacRank: c.sac_rank[i], viaFerrata: c.via_ferrata[i] === 1,
        edgeId: i,
      })
    }

    const views = buildOfficialTourViews(tours, records)

    expect(views).toHaveLength(1)
    expect(views[0].tourId).toBe(1)
    expect(views[0].name).toBe('Welser Höhenweg')
    expect(views[0].legs).toHaveLength(5)
    expect(views[0].legs.map((l) => l.legIndex)).toEqual([0, 1, 2, 3, 4])
    expect(views[0].totalDistanceM).toBeCloseTo(56746, 0)
    expect(views[0].totalAscentM).toBeCloseTo(3862, 0)
    expect(views[0].totalDescentM).toBeCloseTo(4012, 0)
    expect(views[0].totalDurationH).toBeCloseTo(28.4, 1)
  })

  it('loadOfficialTours/loadTourEdgesData read the same real files without throwing (fetch stubbed to disk)', async () => {
    const vi_fetch = async (url: string) => {
      const name = url.replace('/data/', '')
      if (name.endsWith('.bin')) {
        const buf = readFileSync(`${DATA_DIR}${name}`)
        const arrayBuffer = buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength) as ArrayBuffer
        return { arrayBuffer: () => Promise.resolve(arrayBuffer) } as Response
      }
      return { json: () => Promise.resolve(JSON.parse(readFileSync(`${DATA_DIR}${name}`, 'utf-8'))) } as Response
    }
    const originalFetch = globalThis.fetch
    // @ts-expect-error test-only stub
    globalThis.fetch = vi_fetch
    try {
      const tours = await loadOfficialTours('/data')
      const records = await loadTourEdgesData('/data')
      const views = buildOfficialTourViews(tours, records)
      expect(views).toHaveLength(1)
    } finally {
      globalThis.fetch = originalFetch
    }
  })
})
