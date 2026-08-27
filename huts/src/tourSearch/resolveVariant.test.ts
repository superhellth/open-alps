import { describe, it, expect } from 'vitest'
import { resolveVariant } from './resolveVariant.js'

const variantNames = { 0: 'FAST_ANY', 1: 'FAST_T2', 2: 'FAST_T3', 3: 'FAST_T3_UNGRADED' }

describe('resolveVariant', () => {
  it('a T2 ceiling resolves to the FAST_T2 row (fully-graded guarantee)', () => {
    expect(resolveVariant({ sacCeiling: 2 }, variantNames)).toBe(1)
  })

  it('a T3 ceiling with no ungraded terrain allowed resolves to FAST_T3', () => {
    expect(resolveVariant({ sacCeiling: 3, allowUngraded: false }, variantNames)).toBe(2)
  })

  it('a T3 ceiling with ungraded terrain allowed resolves to FAST_T3_UNGRADED', () => {
    expect(resolveVariant({ sacCeiling: 3, allowUngraded: true }, variantNames)).toBe(3)
  })

  it('no ceiling (or T4+) resolves to FAST_ANY, which carries no grading guarantee', () => {
    expect(resolveVariant({}, variantNames)).toBe(0)
    expect(resolveVariant({ sacCeiling: 5 }, variantNames)).toBe(0)
  })
})
