import { describe, it, expect } from 'vitest'
import theme, { SIGNPOST_FONT, tokens } from './theme.js'
import { fontSize, fonts, rem } from './tokens.js'

describe('theme', () => {
  it('uses the spec colors', () => {
    expect(tokens).toMatchObject({ paper: '#EDEFE9', ink: '#23272B', signpost: '#F5B700', trailRed: '#C8102E', alpineBlue: '#1F5FA8' })
  })
  it('signpost yellow is the primary fill with dark text on it', () => {
    expect(theme.palette.primary.main).toBe(tokens.signpost)
    expect(theme.palette.primary.contrastText).toBe(tokens.ink)
  })
  it('panels are paper with ink text', () => {
    expect(theme.palette.background.paper).toBe(tokens.paper)
    expect(theme.palette.text.primary).toBe(tokens.ink)
  })
  it('body text is Barlow, signposts use the semi-condensed cut', () => {
    expect(theme.typography.fontFamily).toBe(fonts.body)
    expect(SIGNPOST_FONT).toBe(fonts.signpost)
    expect(SIGNPOST_FONT).toContain('Barlow Semi Condensed')
  })
  it('typography variants read from fontSize', () => {
    expect(theme.typography.caption.fontSize).toBe(rem(fontSize.xs))
    expect(theme.typography.body2.fontSize).toBe(rem(fontSize.sm))
    expect(theme.typography.subtitle2.fontSize).toBe(rem(fontSize.sm))
    expect(theme.typography.body1.fontSize).toBe(rem(fontSize.md))
    expect(theme.typography.h6.fontSize).toBe(rem(fontSize.xl))
  })
})
