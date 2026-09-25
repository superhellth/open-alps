import { describe, expect, it } from 'vitest'
import { tokenCssVariables, tokens } from './tokens.js'

describe('tokenCssVariables', () => {
  it('has one --color-<kebab> entry per token with the same value, and nothing else', () => {
    expect(tokenCssVariables).toEqual({
      '--color-paper': tokens.paper,
      '--color-ink': tokens.ink,
      '--color-signpost': tokens.signpost,
      '--color-trail-red': tokens.trailRed,
      '--color-alpine-blue': tokens.alpineBlue,
    })
  })
})
