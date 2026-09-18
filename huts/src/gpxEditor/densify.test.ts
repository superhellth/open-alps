import { describe, it, expect } from 'vitest'
import { densify } from './densify.js'
import { haversineM } from './snap.js'

describe('densify', () => {
  it('returns no points when already within one step', () => {
    expect(densify({ lon: 11, lat: 47 }, { lon: 11, lat: 47.0002 })).toEqual([])
  })

  it('fills a 2 km gap with steps <= 25 m, strictly between the endpoints', () => {
    const a = { lon: 11, lat: 47 }
    const b = { lon: 11.02, lat: 47.01 }
    const mid = densify(a, b)
    const chain = [a, ...mid, b]
    expect(mid.length).toBeGreaterThan(50)
    for (let i = 1; i < chain.length; i++) expect(haversineM(chain[i - 1]!, chain[i]!)).toBeLessThanOrEqual(25.5)
  })
})
