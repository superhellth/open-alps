import { describe, it, expect } from 'vitest'
import theme, { SIGNPOST_FONT, tokens } from './theme.js'

describe('theme', () => {
  it('uses the spec tokens', () => {
    expect(tokens).toEqual({ paper: '#EDEFE9', ink: '#23272B', signpost: '#F5B700', trailRed: '#C8102E', alpineBlue: '#1F5FA8' })
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
    expect(String(theme.typography.fontFamily)).toContain('Barlow')
    expect(SIGNPOST_FONT).toContain('Barlow Semi Condensed')
  })
})
