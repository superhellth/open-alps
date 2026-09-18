import { describe, it, expect } from 'vitest'
import { chooseHandles } from './decimate.js'

const VP = { minX: 0, minY: 0, maxX: 100, maxY: 100 }

describe('chooseHandles', () => {
  it('keeps both endpoints even when outside the viewport', () => {
    const px = [{ x: -500, y: 0 }, { x: 50, y: 50 }, { x: 900, y: 0 }]
    expect(chooseHandles(px, VP, 12)).toEqual([0, 1, 2])
  })

  it('thins points closer than the spacing', () => {
    const px = Array.from({ length: 41 }, (_, i) => ({ x: i * 2, y: 10 }))
    const idx = chooseHandles(px, VP, 12)
    expect(idx[0]).toBe(0)
    expect(idx[idx.length - 1]).toBe(40)
    for (let i = 1; i < idx.length - 1; i++) {
      const a = px[idx[i - 1]!]!
      const b = px[idx[i]!]!
      expect(Math.hypot(a.x - b.x, a.y - b.y)).toBeGreaterThanOrEqual(12)
    }
  })

  it('drops an interior handle that crowds the end endpoint', () => {
    const px = [{ x: 0, y: 0 }, { x: 50, y: 0 }, { x: 55, y: 0 }]
    expect(chooseHandles(px, VP, 12)).toEqual([0, 2])
  })

  it('skips interior points outside the viewport', () => {
    const px = [{ x: 0, y: 0 }, { x: 5000, y: 5000 }, { x: 60, y: 60 }]
    expect(chooseHandles(px, VP, 12)).toEqual([0, 2])
  })
})
