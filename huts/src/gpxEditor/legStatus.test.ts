import { describe, it, expect } from 'vitest'
import { SnapContext } from './snap.js'
import { endpointRequiresHut, legShape, legStatus, tourDiscontinuous } from './legStatus.js'
import type { Hub } from './types.js'

const hut = (id: number, lon: number, lat: number): Hub => ({ id, type: 'hut', lon, lat, name: '' })
const parking = (id: number, lon: number, lat: number): Hub => ({ id, type: 'parking', lon, lat, name: '' })

describe('endpointRequiresHut', () => {
  it('only the first leg start and last leg end may be non-huts', () => {
    expect(endpointRequiresHut(0, 3)).toEqual({ start: false, end: true })
    expect(endpointRequiresHut(1, 3)).toEqual({ start: true, end: true })
    expect(endpointRequiresHut(2, 3)).toEqual({ start: true, end: false })
    expect(endpointRequiresHut(0, 1)).toEqual({ start: false, end: false })
  })
})

describe('legStatus', () => {
  const ctx = new SnapContext([hut(1, 11.0, 47.0), parking(2, 11.1, 47.1), hut(3, 11.2, 47.2)])
  const pts = [{ lon: 11.1, lat: 47.1 }, { lon: 11.1, lat: 47.1005 }, { lon: 11.2, lat: 47.2 }]

  it('first leg may start at parking; end at hut ok', () => {
    const s = legStatus(ctx, legShape(pts)!, 0, 2, 100)
    expect(s.startOk).toBe(true)
    expect(s.endOk).toBe(true)
  })

  it('interior start at parking is unsnapped (huts only)', () => {
    const s = legStatus(ctx, legShape(pts)!, 1, 3, 100)
    expect(s.startOk).toBe(false)
    expect(s.start.nearest?.type).toBe('hut')
  })

  it('flags a long segment', () => {
    const s = legStatus(ctx, legShape(pts)!, 0, 2, 100)
    expect(s.longSegment).toBe(true)
  })

  it('legShape of fewer than 2 points is null', () => {
    expect(legShape([{ lon: 1, lat: 1 }])).toBeNull()
  })
})

describe('tourDiscontinuous', () => {
  const ctx = new SnapContext([hut(1, 11.0, 47.0), hut(2, 11.1, 47.1), hut(3, 11.2, 47.2)])
  const leg = (a: Hub, b: Hub, pos: number, n: number) =>
    legStatus(ctx, legShape([a, b])!, pos, n, 100)

  it('false when leg N end hub == leg N+1 start hub', () => {
    expect(tourDiscontinuous([leg(ctx_h(1), ctx_h(2), 0, 2), leg(ctx_h(2), ctx_h(3), 1, 2)])).toBe(false)
  })

  it('true when they differ', () => {
    expect(tourDiscontinuous([leg(ctx_h(1), ctx_h(2), 0, 2), leg(ctx_h(3), ctx_h(1), 1, 2)])).toBe(true)
  })

  it('ignores unsnapped ends and nulls', () => {
    expect(tourDiscontinuous([null, leg(ctx_h(2), ctx_h(3), 1, 2)])).toBe(false)
  })

  function ctx_h(id: number): Hub {
    return [hut(1, 11.0, 47.0), hut(2, 11.1, 47.1), hut(3, 11.2, 47.2)][id - 1]!
  }
})
