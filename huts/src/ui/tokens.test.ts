import { describe, expect, it } from 'vitest'
import { fontSize, fonts, marker, opacity, rem, space, tokenCssVariables, tokens } from './tokens.js'

describe('tokenCssVariables', () => {
  it('has exactly one variable per token across all groups, with matching values', () => {
    expect(tokenCssVariables).toEqual({
      '--color-paper': tokens.paper,
      '--color-ink': tokens.ink,
      '--color-signpost': tokens.signpost,
      '--color-trail-red': tokens.trailRed,
      '--color-alpine-blue': tokens.alpineBlue,
      '--color-white': tokens.white,
      '--color-hut-av': tokens.hutAv,
      '--color-hut-other': tokens.hutOther,
      '--color-hut-partner': tokens.hutPartner,
      '--space-inline': '4px',
      '--space-item': '8px',
      '--space-row': '12px',
      '--space-group': '16px',
      '--space-section': '24px',
      '--space-inset': '16px',
      '--font-size-xs': '0.75rem',
      '--font-size-sm': '0.875rem',
      '--font-size-md': '1rem',
      '--font-size-lg': '1.125rem',
      '--font-size-xl': '1.25rem',
      '--font-body': fonts.body,
      '--font-signpost': fonts.signpost,
      '--opacity-dimmed': '0.45',
      '--opacity-hover-tint': '0.05',
      '--opacity-hover-tint-strong': '0.09',
      '--opacity-muted': '0.6',
      '--opacity-shadow': '0.15',
      '--opacity-outline': '0.23',
      '--marker-board-h': '26px',
      '--marker-mast-h': '24px',
      '--marker-board-max-w': '220px',
      '--marker-board-pad-near': '8px',
      '--marker-board-pad-far': '16px',
      '--marker-board-gap': '6px',
      '--marker-arrow-w': '10px',
      '--marker-board-font': marker.boardFont,
    })
  })
})

describe('token values', () => {
  it('space steps are 4, 8, 12, 16, 24 px', () => {
    expect(Object.values(space).map((u) => u * 8)).toEqual([4, 8, 12, 16, 24, 16])
  })
  it('marker.boardFont is a resolved canvas font string built from fontSize.sm and fonts.signpost', () => {
    expect(marker.boardFont).toBe(`600 ${rem(fontSize.sm)} ${fonts.signpost}`)
    expect(marker.boardFont).not.toContain('var(')
  })
  it('opacity levels are fractions', () => {
    for (const v of Object.values(opacity)) {
      expect(v).toBeGreaterThan(0)
      expect(v).toBeLessThan(1)
    }
  })
})
