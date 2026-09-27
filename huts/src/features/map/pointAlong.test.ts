import { describe, it, expect } from 'vitest'
import { pointAlong } from './pointAlong.js'

describe('pointAlong', () => {
  const line: [number, number][] = [[0, 0], [0, 10]]

  it('returns the first and last coordinate at fractions 0 and 1', () => {
    expect(pointAlong(line, 0)).toEqual([0, 0])
    expect(pointAlong(line, 1)).toEqual([0, 10])
  })
  it('interpolates the midpoint of a single segment', () => {
    const [lat, lng] = pointAlong(line, 0.5)
    expect(lat).toBeCloseTo(0)
    expect(lng).toBeCloseTo(5)
  })
  it('weights segments by length (uneven segments)', () => {
    // segments of length 3 and 4, total 7
    const bent: [number, number][] = [[0, 0], [0, 3], [4, 3]]
    const atCorner = pointAlong(bent, 3 / 7)
    expect(atCorner[0]).toBeCloseTo(0)
    expect(atCorner[1]).toBeCloseTo(3)
    const inSecond = pointAlong(bent, 5 / 7)
    expect(inSecond[0]).toBeCloseTo(2)
    expect(inSecond[1]).toBeCloseTo(3)
  })
  it('clamps fractions outside 0..1', () => {
    expect(pointAlong(line, -1)).toEqual([0, 0])
    expect(pointAlong(line, 2)).toEqual([0, 10])
  })
  it('returns the only coordinate of a single-point or zero-length line', () => {
    expect(pointAlong([[1, 2]], 0.5)).toEqual([1, 2])
    expect(pointAlong([[1, 2], [1, 2]], 0.5)).toEqual([1, 2])
  })
  it('throws on an empty coordinate list', () => {
    expect(() => pointAlong([], 0.5)).toThrow()
  })
})
