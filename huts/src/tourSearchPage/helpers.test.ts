import { describe, it, expect } from 'vitest'
import { SOURCE_TYPE_LABEL, killCounterGuidance, VILLAGE_EMPTY_STATE_HINT } from './helpers.js'
import { SOURCE_TYPE_PARTNER } from '../tourSearch/types.js'

describe('SOURCE_TYPE_LABEL', () => {
  it('labels partner points as Partnerbetrieb', () => {
    expect(SOURCE_TYPE_LABEL[SOURCE_TYPE_PARTNER]).toBe('Partnerbetrieb')
  })
})

describe('killCounterGuidance hutFiltered', () => {
  it('explains that the hut filter excluded stage destinations, with a count', () => {
    const msgs = killCounterGuidance({
      maxLegTime: 0, minLegTime: 0, legAscentCap: 0, maxEleM: 0, viaFerrata: 0, revisit: 0, hutFiltered: 7,
    })
    expect(msgs.some((m) => m.includes('7') && m.includes('Hüttenfilter'))).toBe(true)
  })
})

describe('VILLAGE_EMPTY_STATE_HINT', () => {
  it('mentions Bergsteigerdorf/Partnerbetrieb rather than implying the user filters are at fault', () => {
    expect(VILLAGE_EMPTY_STATE_HINT).toMatch(/Bergsteigerdorf|Partnerbetrieb/)
  })
})
