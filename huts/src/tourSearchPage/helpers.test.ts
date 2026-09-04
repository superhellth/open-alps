import { describe, it, expect } from 'vitest'
import {
  SOURCE_TYPE_LABEL, killCounterGuidance, VILLAGE_EMPTY_STATE_HINT, hutAvailabilityBadge,
  chainToRoute, legLayer, officialTourToRoute,
} from './helpers.js'
import { SOURCE_TYPE_PARTNER } from '../tourSearch/types.js'
import type { TourResult } from '../tourSearch/types.js'
import type { OfficialTourView } from '../tourSearch/officialTours.js'
import type { StartPoint } from './types.js'

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

describe('legLayer', () => {
  it('routes the first and last leg on start_edges, and every interior leg on hut_edges', () => {
    expect(legLayer(0, 3)).toBe('start_edges')
    expect(legLayer(2, 3)).toBe('start_edges')
    expect(legLayer(1, 3)).toBe('hut_edges')
  })
})

describe('chainToRoute', () => {
  const hutCoordsById = new Map([[0, { lat: 47.1, lng: 11.1 }]])
  const startById = new Map<number, StartPoint>([
    [100, { name: 'Start', sourceType: 2, lat: 47.0, lng: 11.0 }],
    [200, { name: 'End', sourceType: 2, lat: 47.2, lng: 11.2 }],
  ])
  const chain: TourResult = {
    huts: [0], startId: 100, exitStartId: 200,
    totalDurationH: 3, totalAscentM: 300, totalDescentM: 300, totalDistanceM: 6000,
    legs: [
      { durationH: 1.5, ascentM: 150, descentM: 150, distanceM: 3000, edgeId: 5, reversed: false },
      { durationH: 1.5, ascentM: 150, descentM: 150, distanceM: 3000, edgeId: 6, reversed: true },
    ],
  }

  it('builds waypoints from start/huts/end and legs with the right layer per position', () => {
    const route = chainToRoute(chain, hutCoordsById, startById)
    expect(route.waypoints).toEqual([{ lat: 47.0, lng: 11.0 }, { lat: 47.1, lng: 11.1 }, { lat: 47.2, lng: 11.2 }])
    expect(route.legs).toEqual([
      { edgeId: 5, reversed: false, layer: 'start_edges' },
      { edgeId: 6, reversed: true, layer: 'start_edges' },
    ])
  })
})

describe('officialTourToRoute', () => {
  const hutCoordsById = new Map([[302, { lat: 47.5, lng: 13.9 }], [376, { lat: 47.6, lng: 14.0 }]])
  const startById = new Map<number, StartPoint>([[1, { name: 'P', sourceType: 2, lat: 47.4, lng: 13.8 }]])
  const tour: OfficialTourView = {
    tourId: 1, name: 'Welser Höhenweg',
    legs: [
      {
        legIndex: 0, from: { type: 'parking', id: 1 }, to: { type: 'hut', id: 302 }, edgeId: 0,
        reversed: false, distanceM: 6000, ascentM: 800, descentM: 100, durationH: 2, maxEleM: 1400, sacRank: 3, viaFerrata: false,
      },
      {
        legIndex: 1, from: { type: 'hut', id: 302 }, to: { type: 'hut', id: 376 }, edgeId: 1,
        reversed: false, distanceM: 10000, ascentM: 1000, descentM: 800, durationH: 3, maxEleM: 2000, sacRank: 3, viaFerrata: false,
      },
    ],
    totalDistanceM: 16000, totalAscentM: 1800, totalDescentM: 900, totalDurationH: 5,
  }

  it('resolves hut waypoints via hutCoordsById and non-hut waypoints via startById, all legs on tour_edges', () => {
    const route = officialTourToRoute(tour, hutCoordsById, startById)
    expect(route).toEqual({
      waypoints: [{ lat: 47.4, lng: 13.8 }, { lat: 47.5, lng: 13.9 }, { lat: 47.6, lng: 14.0 }],
      legs: [
        { edgeId: 0, reversed: false, layer: 'tour_edges' },
        { edgeId: 1, reversed: false, layer: 'tour_edges' },
      ],
    })
  })

  it('returns null when an endpoint cannot be resolved from either lookup map', () => {
    expect(officialTourToRoute(tour, new Map(), new Map())).toBeNull()
  })
})
