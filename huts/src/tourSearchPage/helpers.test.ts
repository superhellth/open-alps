import { describe, it, expect } from 'vitest'
import { SOURCE_TYPE_LABEL, killCounterGuidance, VILLAGE_EMPTY_STATE_HINT, hutAvailabilityBadge } from './helpers.js'
import { SOURCE_TYPE_PARTNER } from '../tourSearch/types.js'

describe('SOURCE_TYPE_LABEL', () => {
  it('labels partner points as Partnerbetrieb', () => {
    expect(SOURCE_TYPE_LABEL[SOURCE_TYPE_PARTNER]).toBe('Partnerbetrieb')
  })
})

describe('killCounterGuidance hutFiltered', () => {
  it('explains that the hut filter excluded stage destinations, with a count', () => {
    const msgs = killCounterGuidance({
      maxLegTime: 0, minLegTime: 0, legAscentCap: 0, maxEleM: 0, viaFerrata: 0, revisit: 0, hutFiltered: 7, trackOverlap: 0, availability: 0,
    })
    expect(msgs.some((m) => m.includes('7') && m.includes('Hüttenfilter'))).toBe(true)
  })
})

describe('VILLAGE_EMPTY_STATE_HINT', () => {
  it('mentions Bergsteigerdorf/Partnerbetrieb rather than implying the user filters are at fault', () => {
    expect(VILLAGE_EMPTY_STATE_HINT).toMatch(/Bergsteigerdorf|Partnerbetrieb/)
  })
})

describe('hutAvailabilityBadge', () => {
  const ohrsIdByHutIndex = new Map<number, string | null>([[0, 'ohrsA'], [1, null]])

  it('returns null when no availability data was fetched (badges-off state)', () => {
    expect(hutAvailabilityBadge(0, 1, null, null)).toBeNull()
  })

  it('returns "direct" for a hut with no ohrsHutId, regardless of freeByOffset', () => {
    const freeByOffset = new Map<number, Set<string> | 'unknown'>([[1, new Set<string>()]])
    expect(hutAvailabilityBadge(1, 1, ohrsIdByHutIndex, freeByOffset)).toBe('direct')
  })

  it('returns "unknown" when the offset fetch failed', () => {
    const freeByOffset = new Map<number, Set<string> | 'unknown'>([[1, 'unknown']])
    expect(hutAvailabilityBadge(0, 1, ohrsIdByHutIndex, freeByOffset)).toBe('unknown')
  })

  it('returns "free" when the hut\'s ohrsHutId is in that offset\'s free set', () => {
    const freeByOffset = new Map<number, Set<string> | 'unknown'>([[1, new Set(['ohrsA'])]])
    expect(hutAvailabilityBadge(0, 1, ohrsIdByHutIndex, freeByOffset)).toBe('free')
  })

  it('returns "unavailable" when the hut\'s ohrsHutId is missing from that offset\'s free set', () => {
    const freeByOffset = new Map<number, Set<string> | 'unknown'>([[1, new Set(['someoneElse'])]])
    expect(hutAvailabilityBadge(0, 1, ohrsIdByHutIndex, freeByOffset)).toBe('unavailable')
  })
})
