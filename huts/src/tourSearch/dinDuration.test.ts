import { describe, it, expect } from 'vitest'
import { dinDurationH } from './dinDuration.js'

describe('dinDurationH', () => {
  it('blends horizontal and vertical time (8km, 600m up, 500m down -> 4.0h)', () => {
    // t_h = 2.0, t_v = 2.0 + 1.0 = 3.0 -> 3.0 + 1.0 = 4.0 h. Same fixture as
    // pipeline/tests/test_speed.py::test_din_duration_blends_horizontal_and_vertical.
    expect(dinDurationH(8000, 600, 500)).toBeCloseTo(4.0, 6)
  })

  it('is purely horizontal on the flat', () => {
    expect(dinDurationH(4000, 0, 0)).toBeCloseTo(1.0, 6)
  })

  it('handles zero-length legs without dividing by zero', () => {
    expect(dinDurationH(0, 0, 0)).toBe(0)
  })
})
