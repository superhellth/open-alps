import { describe, it, expect } from 'vitest'
import { formatDistanceKm } from './distance.js'

describe('formatDistanceKm', () => {
  it('formats meters as km with one decimal', () => {
    expect(formatDistanceKm(42_300)).toBe('42.3 km')
    expect(formatDistanceKm(0)).toBe('0.0 km')
    expect(formatDistanceKm(960)).toBe('1.0 km')
  })
})
