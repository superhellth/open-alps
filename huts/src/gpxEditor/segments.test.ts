import { describe, it, expect } from 'vitest'
import { LONG_SEGMENT_M, nearestSegment, segmentLengthsM } from './segments.js'

describe('segments', () => {
  it('computes haversine lengths per segment', () => {
    const l = segmentLengthsM([{ lon: 11, lat: 47 }, { lon: 11, lat: 47.001 }, { lon: 11, lat: 47.003 }])
    expect(l).toHaveLength(2)
    expect(l[0]).toBeCloseTo(111.2, 0)
    expect(l[1]).toBeCloseTo(222.4, 0)
  })

  it('threshold constant is 150 m', () => {
    expect(LONG_SEGMENT_M).toBe(150)
  })

  it('finds the segment nearest a click', () => {
    const px = [{ x: 0, y: 0 }, { x: 100, y: 0 }, { x: 100, y: 100 }]
    expect(nearestSegment(px, { x: 50, y: 3 }).index).toBe(0)
    const r = nearestSegment(px, { x: 97, y: 60 })
    expect(r.index).toBe(1)
    expect(r.distPx).toBeCloseTo(3, 5)
  })
})
