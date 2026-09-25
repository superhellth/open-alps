import { describe, it, expect } from 'vitest'
import { anchorFractions, decodeAnchors, readAnchorOffsets } from './anchors.js'

describe('anchors', () => {
  it('reads every present anchor column pair as flat offsets, null when none', () => {
    const cols = { a25_dlat: [1], a25_dlng: [2], a50_dlat: [3], a50_dlng: [4], a75_dlat: [5], a75_dlng: [6] }
    expect(readAnchorOffsets(cols, 0)).toEqual([1, 2, 3, 4, 5, 6])
    expect(readAnchorOffsets({ a50_dlat: [3], a50_dlng: [4] }, 0)).toEqual([3, 4])
    expect(readAnchorOffsets({}, 0)).toBeNull()
  })
  it('decodes offsets relative to the reference in 1e-4 degree units', () => {
    const [a] = decodeAnchors([10, -20], { lat: 47, lng: 11 })
    expect(a.lat).toBeCloseTo(47.001, 9)
    expect(a.lng).toBeCloseTo(10.998, 9)
  })
  it('spaces fractions evenly', () => {
    expect(anchorFractions(3)).toEqual([0.25, 0.5, 0.75])
    expect(anchorFractions(1)).toEqual([0.5])
  })
})
