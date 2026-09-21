import { describe, it, expect } from 'vitest'
import { newTrip } from '../trip/trip.js'
import {
  applyEndpoint, applyExtend, applySwap, applyTrim, endpointCandidates, extendCandidates,
  modeOfTrip, swapCandidates, trimAllowed,
} from './tripEdit.js'
import { makeTripGraph } from './tripTestGraph.js'

const graph = makeTripGraph()
const variant = { sacCeiling: null, allowUngraded: false }
const station = { startId: 100, sourceType: 1 as const }
const mk = (huts: string[], over: Partial<Parameters<typeof newTrip>[0]> = {}) =>
  newTrip({ name: 't', startDate: null, partySize: 1, start: station, huts, exit: station, variant, ...over }, new Date(), 'id')

describe('modeOfTrip', () => {
  it('derives the mode from the start source type', () => {
    expect(modeOfTrip(mk(['{A}']))).toBe('transit')
    expect(modeOfTrip(mk(['{A}'], { start: { startId: 200, sourceType: 2 } }))).toBe('car')
    expect(modeOfTrip(mk(['{A}'], { start: { startId: 5, sourceType: 3 } }))).toBe('village')
  })
})

describe('swapCandidates / applySwap', () => {
  it('offers huts linked to both neighbours and not already in the trip', () => {
    const trip = mk(['{A}', '{B}', '{C}'])
    expect(swapCandidates(graph, trip, 1).map((c) => c.hutGuid)).toEqual(['{X}'])
  })
  it('reports both leg times', () => {
    const [c] = swapCandidates(graph, mk(['{A}', '{B}', '{C}']), 1)
    expect(c.legInH).toBeGreaterThan(0)
    expect(c.legOutH).toBeGreaterThan(0)
  })
  it('constrains an end hut by its approach/exit legs', () => {
    // Last hut of [A,B,C] -> candidates need an edge from B and an exit to station 100: only D qualifies.
    const trip = mk(['{A}', '{B}', '{C}'])
    expect(swapCandidates(graph, trip, 2).map((c) => c.hutGuid)).toEqual([])
    const single = mk(['{A}'])
    expect(swapCandidates(graph, single, 0).map((c) => c.hutGuid).sort()).toEqual(['{D}', '{E}'])
  })
  it('returns nothing when a neighbour no longer resolves', () => {
    expect(swapCandidates(graph, mk(['{A}', '{GONE}', '{C}']), 0)).toEqual([])
  })
  it('applySwap replaces the hut, resets that night and drops the official source', () => {
    const trip = { ...mk(['{A}', '{B}', '{C}']), source: { kind: 'official' as const, tourId: 1 } }
    trip.nights[1] = { status: 'confirmed' }
    const next = applySwap(graph, trip, 1, 5)
    expect(next.huts).toEqual(['{A}', '{X}', '{C}'])
    expect(next.nights[1]).toEqual({ status: 'open' })
    expect(next.source).toBeUndefined()
  })
})

describe('extendCandidates / applyExtend', () => {
  it('lists reachable huts whose ends stay routable', () => {
    const trip = mk(['{A}', '{B}', '{C}'])
    // From C: D (has exit 100) qualifies, X (no exit) does not, A/B are already in the trip.
    expect(extendCandidates(graph, trip, 'last').map((c) => c.hutGuid)).toEqual(['{D}'])
    expect(extendCandidates(graph, mk(['{B}', '{C}', '{D}']), 'first').map((c) => c.hutGuid)).toEqual(['{A}'])
  })
  it('applyExtend appends a night and keeps start/exit when still linked', () => {
    const next = applyExtend(graph, mk(['{A}', '{B}', '{C}']), 'last', 3)!
    expect(next.huts).toEqual(['{A}', '{B}', '{C}', '{D}'])
    expect(next.nights).toHaveLength(4)
    expect(next.exit).toEqual(station)
  })
  it('applyExtend repairs the exit to the fastest station exit when the old one is unreachable', () => {
    const trip = mk(['{A}', '{B}', '{C}', '{D}'], { exit: { startId: 101, sourceType: 1 } })
    const next = applyExtend(graph, trip, 'last', 4)! // E only has an exit to station 100
    expect(next.exit.startId).toBe(100)
    expect(next.start.startId).toBe(100)
  })
  it('applyExtend returns null when no valid end exists', () => {
    expect(applyExtend(graph, mk(['{A}', '{B}', '{C}']), 'last', 5)).toBeNull()
  })
  it('car mode keeps start and exit identical', () => {
    const car = { startId: 200, sourceType: 2 as const }
    const trip = mk(['{A}', '{B}', '{C}'], { start: car, exit: car })
    const next = applyExtend(graph, trip, 'last', 3)!
    expect(next.start).toEqual(car)
    expect(next.exit).toEqual(car)
  })
})

describe('trimAllowed / applyTrim', () => {
  const trip = mk(['{A}', '{B}', '{C}', '{D}'])
  it('allows removing an interior hut when its neighbours share an edge', () => {
    expect(trimAllowed(graph, trip, 1)).toEqual({ ok: true }) // A-C exists
    expect(applyTrim(graph, trip, 1)!.huts).toEqual(['{A}', '{C}', '{D}'])
  })
  it('disables removal with a reason when neighbours have no edge', () => {
    const r = trimAllowed(graph, trip, 2) // B-D does not exist
    expect(r.ok).toBe(false)
    expect(!r.ok && r.reason.length).toBeGreaterThan(0)
    expect(applyTrim(graph, trip, 2)).toBeNull()
  })
  it('disables removal of the only hut', () => {
    expect(trimAllowed(graph, mk(['{A}']), 0).ok).toBe(false)
  })
  it('disables removing an end hut whose successor has no approach', () => {
    expect(trimAllowed(graph, trip, 0).ok).toBe(false) // B has no approach from station 100
  })
  it('allows removing the last hut when the new last hut still has an exit', () => {
    const t = mk(['{D}', '{E}'])
    expect(trimAllowed(graph, t, 1)).toEqual({ ok: true })
    expect(applyTrim(graph, t, 1)!.huts).toEqual(['{D}'])
  })
})

describe('endpointCandidates / applyEndpoint', () => {
  const trip = mk(['{A}', '{B}', '{C}', '{D}'])
  it('lists other approach/exit points of the same source type, fastest first', () => {
    expect(endpointCandidates(graph, trip, 'start').map((c) => c.startId)).toEqual([101])
    expect(endpointCandidates(graph, trip, 'exit').map((c) => c.startId)).toEqual([101])
  })
  it('in car mode the exit is locked and start candidates need both approach and exit', () => {
    const car = { startId: 200, sourceType: 2 as const }
    const t = mk(['{A}', '{B}', '{C}', '{D}'], { start: car, exit: car })
    expect(endpointCandidates(graph, t, 'exit')).toEqual([])
    expect(endpointCandidates(graph, t, 'start').map((c) => c.startId)).toEqual([201])
    const next = applyEndpoint(t, 'start', { startId: 201, sourceType: 2, durationH: 1 })
    expect(next.start).toEqual({ startId: 201, sourceType: 2 })
    expect(next.exit).toEqual({ startId: 201, sourceType: 2 })
  })
  it('applyEndpoint in transit mode changes only the chosen end', () => {
    const next = applyEndpoint(trip, 'exit', { startId: 101, sourceType: 1, durationH: 1 })
    expect(next.exit.startId).toBe(101)
    expect(next.start.startId).toBe(100)
  })
})
