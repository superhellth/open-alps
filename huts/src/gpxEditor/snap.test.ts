import { readFileSync } from 'node:fs'
import { describe, it, expect } from 'vitest'
import { SnapContext, haversineM, snapPoint } from './snap.js'
import type { Hub, HubType } from './types.js'

interface FixtureHub { id: number; type: HubType; lon: number; lat: number }
interface Case {
  name: string; maxSnapM: number; requireHut: boolean; point: [number, number]; hubs: FixtureHub[]
  expect: {
    chosen: { id: number; type: string } | null
    nearest: { id: number; type: string } | null
    nearestDistM: number | null
  }
}

const cases: Case[] = JSON.parse(
  readFileSync(new URL('../../../pipeline/tests/fixtures/snap_cases.json', import.meta.url), 'utf-8'),
).cases

describe('snapPoint shared fixture', () => {
  it.each(cases)('$name', (c) => {
    const hubs: Hub[] = c.hubs.map((h) => ({ ...h, name: '' }))
    const r = snapPoint(new SnapContext(hubs), { lon: c.point[0], lat: c.point[1] }, c.maxSnapM, c.requireHut)
    const key = (h: Hub | null) => (h ? { id: h.id, type: h.type } : null)
    expect(key(r.chosen)).toEqual(c.expect.chosen)
    expect(key(r.nearest)).toEqual(c.expect.nearest)
    if (c.expect.nearestDistM !== null) {
      expect(Math.abs(r.nearestDistM - c.expect.nearestDistM)).toBeLessThan(0.5)
    } else {
      expect(r.nearestDistM).toBe(Infinity)
    }
  })
})

describe('haversineM', () => {
  it('matches the pipeline formula (R = 6371000 m)', () => {
    expect(haversineM({ lon: 11.0005, lat: 47.0 }, { lon: 11.0, lat: 47.0 })).toBeCloseTo(37.917, 2)
  })
})
