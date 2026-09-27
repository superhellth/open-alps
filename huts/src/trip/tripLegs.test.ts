import { describe, it, expect } from 'vitest'
import { newTrip } from './trip.js'
import { legsFromTrip, linkLeg, summarizeLegs, variantOf } from './tripLegs.js'
import { makeTripGraph } from '@/testing/tripTestGraph.js'

const graph = makeTripGraph()
const variant = { sacCeiling: null, allowUngraded: false }
const mk = (huts: string[], over: Partial<Parameters<typeof newTrip>[0]> = {}) =>
  newTrip({
    name: 't', startDate: '2026-07-10', partySize: 2,
    start: { startId: 100, sourceType: 1 }, huts, exit: { startId: 100, sourceType: 1 }, variant, ...over,
  }, new Date(), 'id')

describe('variantOf', () => {
  it('resolves the trip variant against the payload', () => {
    expect(variantOf(graph, variant)).toBe(0)
  })
})

describe('linkLeg', () => {
  it('finds hut->hut in both directions, reversing ascent/descent', () => {
    const fwd = linkLeg(graph, 0, { kind: 'hut', index: 0 }, { kind: 'hut', index: 1 })
    const back = linkLeg(graph, 0, { kind: 'hut', index: 1 }, { kind: 'hut', index: 0 })
    expect(fwd && 'reversed' in fwd && fwd.reversed).toBe(false)
    expect(back && 'reversed' in back && back.reversed).toBe(true)
    expect(back?.ascentM).toBe(fwd?.descentM)
  })
  it('returns null when no edge exists', () => {
    expect(linkLeg(graph, 0, { kind: 'hut', index: 0 }, { kind: 'hut', index: 3 })).toBeNull()
  })
  it('finds an approach and an exit for a start point, and null for an unknown start', () => {
    expect(linkLeg(graph, 0, { kind: 'start', startId: 100, sourceType: 1 }, { kind: 'hut', index: 0 })).not.toBeNull()
    expect(linkLeg(graph, 0, { kind: 'hut', index: 3 }, { kind: 'start', startId: 101, sourceType: 1 })).not.toBeNull()
    expect(linkLeg(graph, 0, { kind: 'start', startId: 999, sourceType: 1 }, { kind: 'hut', index: 0 })).toBeNull()
  })
})

describe('legsFromTrip', () => {
  it('derives approach, hut-hut and exit legs for a resolvable trip', () => {
    const r = legsFromTrip(graph, mk(['{A}', '{B}', '{C}', '{D}']))
    expect(r.hutIndices).toEqual([0, 1, 2, 3])
    expect(r.legs).toHaveLength(5)
    expect(r.legs.every((l) => l !== null)).toBe(true)
    expect(r.changed).toEqual([false, false, false, false])
  })
  it('marks a night changed when its hut GUID no longer resolves, and the following night (no leg into it)', () => {
    const r = legsFromTrip(graph, mk(['{A}', '{GONE}', '{C}']))
    expect(r.hutIndices).toEqual([0, null, 2])
    expect(r.changed).toEqual([false, true, true])
  })
  it('marks a night changed when a hut pair has no edge in the graph', () => {
    const r = legsFromTrip(graph, mk(['{A}', '{D}']))
    expect(r.legs[1]).toBeNull()
    expect(r.changed).toEqual([false, true])
  })
  it('marks the last night changed when the exit leg is missing', () => {
    const r = legsFromTrip(graph, mk(['{A}', '{B}'], { exit: { startId: 999, sourceType: 1 } }))
    expect(r.legs[2]).toBeNull()
    expect(r.changed).toEqual([false, true])
  })
  it('marks the first night changed when the start point does not resolve', () => {
    const r = legsFromTrip(graph, mk(['{A}'], { start: { startId: 999, sourceType: 1 } }))
    expect(r.changed).toEqual([true])
  })
})

describe('summarizeLegs', () => {
  it('sums the present legs and ignores nulls', () => {
    const r = legsFromTrip(graph, mk(['{A}', '{B}']))
    const total = summarizeLegs(r.legs)
    expect(total.durationH).toBeCloseTo(r.legs.reduce((s, l) => s + (l?.durationH ?? 0), 0))
    expect(summarizeLegs([null, null]).durationH).toBe(0)
  })
})
