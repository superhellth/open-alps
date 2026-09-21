import { getAdjacency } from './adjacency.js'
import { resolveHutGuids } from './hutIdentity.js'
import { bestStartLegs, linkLeg, variantOf } from './tripLegs.js'
import type { Endpoint, TripGraph } from './tripLegs.js'
import { SOURCE_TYPE_PARKING, SOURCE_TYPE_PARTNER } from './types.js'
import type { SourceType, TourMode } from './types.js'
import type { Trip, TripEndpoint } from '../trip/trip.js'

export function modeOfTrip(trip: Trip): TourMode {
  if (trip.start.sourceType === SOURCE_TYPE_PARKING) return 'car'
  if (trip.start.sourceType === SOURCE_TYPE_PARTNER) return 'village'
  return 'transit'
}

const hut = (index: number): Endpoint => ({ kind: 'hut', index })
const startPoint = (e: TripEndpoint): Endpoint => ({ kind: 'start', ...e })

function resolved(graph: TripGraph, trip: Trip): number[] | null {
  const indices = resolveHutGuids(graph.hutEdges.hutIds, trip.huts)
  return indices.every((i): i is number => i !== null) ? (indices as number[]) : null
}

/** Chooses start and exit for a hut sequence: the trip's current ones when they still link, else
 *  the fastest replacement of the trip's source type. Car mode needs one point that links to both
 *  ends. Null when no routable start/exit exists. */
export function connectEnds(
  graph: TripGraph, trip: Trip, hutIndices: number[],
): { start: TripEndpoint; exit: TripEndpoint } | null {
  if (hutIndices.length === 0) return null
  const variantId = variantOf(graph, trip.variant)
  const first = hutIndices[0]
  const last = hutIndices[hutIndices.length - 1]
  const sourceType = trip.start.sourceType
  const approaches = bestStartLegs(graph, variantId, first, 'approach', sourceType)
  const exits = bestStartLegs(graph, variantId, last, 'exit', sourceType)

  if (modeOfTrip(trip) === 'car') {
    const keep = trip.start
    if (approaches.has(keep.startId) && exits.has(keep.startId)) return { start: keep, exit: keep }
    let best: { startId: number; total: number } | null = null
    for (const [startId, leg] of approaches) {
      const out = exits.get(startId)
      if (!out) continue
      const total = leg.durationH + out.durationH
      if (!best || total < best.total) best = { startId, total }
    }
    if (!best) return null
    const point = { startId: best.startId, sourceType }
    return { start: point, exit: point }
  }

  const fastest = (legs: typeof approaches): TripEndpoint | null => {
    let best: { startId: number; durationH: number } | null = null
    for (const [startId, leg] of legs) if (!best || leg.durationH < best.durationH) best = { startId, durationH: leg.durationH }
    return best ? { startId: best.startId, sourceType } : null
  }
  const start = approaches.has(trip.start.startId) ? trip.start : fastest(approaches)
  const exit = exits.has(trip.exit.startId) ? trip.exit : fastest(exits)
  return start && exit ? { start, exit } : null
}

function edited(trip: Trip, patch: Partial<Trip>): Trip {
  const { source: _dropped, ...rest } = trip
  return { ...rest, ...patch }
}

// ---- swap -------------------------------------------------------------------------------------

export interface SwapCandidate {
  hutIndex: number
  hutGuid: string
  legInH: number
  legOutH: number
}

export function swapCandidates(graph: TripGraph, trip: Trip, index: number): SwapCandidate[] {
  const indices = resolved(graph, trip)
  if (!indices || index < 0 || index >= indices.length) return []
  const variantId = variantOf(graph, trip.variant)
  const prev = index === 0 ? startPoint(trip.start) : hut(indices[index - 1])
  const next = index === indices.length - 1 ? startPoint(trip.exit) : hut(indices[index + 1])
  const inTrip = new Set(indices)
  const out: SwapCandidate[] = []
  graph.hutEdges.hutIds.forEach((guid, h) => {
    if (inTrip.has(h)) return
    const legIn = linkLeg(graph, variantId, prev, hut(h))
    const legOut = legIn && linkLeg(graph, variantId, hut(h), next)
    if (legIn && legOut) out.push({ hutIndex: h, hutGuid: guid, legInH: legIn.durationH, legOutH: legOut.durationH })
  })
  return out
}

export function applySwap(graph: TripGraph, trip: Trip, index: number, hutIndex: number): Trip {
  const huts = [...trip.huts]
  huts[index] = graph.hutEdges.hutIds[hutIndex]
  const nights = trip.nights.map((n, i) => (i === index ? { status: 'open' as const } : n))
  return edited(trip, { huts, nights })
}

// ---- extend -----------------------------------------------------------------------------------

export interface ExtendCandidate {
  hutIndex: number
  hutGuid: string
  legH: number
}

export function extendCandidates(graph: TripGraph, trip: Trip, side: 'first' | 'last'): ExtendCandidate[] {
  const indices = resolved(graph, trip)
  if (!indices || indices.length === 0) return []
  const variantId = variantOf(graph, trip.variant)
  const end = side === 'first' ? indices[0] : indices[indices.length - 1]
  const inTrip = new Set(indices)
  const fastest = new Map<number, number>()
  for (const leg of getAdjacency(graph.hutEdges, variantId).get(end) ?? []) {
    if (inTrip.has(leg.toIndex)) continue
    const known = fastest.get(leg.toIndex)
    if (known === undefined || leg.durationH < known) fastest.set(leg.toIndex, leg.durationH)
  }
  const out: ExtendCandidate[] = []
  for (const [h, legH] of fastest) {
    const sequence = side === 'first' ? [h, ...indices] : [...indices, h]
    if (connectEnds(graph, trip, sequence)) out.push({ hutIndex: h, hutGuid: graph.hutEdges.hutIds[h], legH })
  }
  return out
}

export function applyExtend(graph: TripGraph, trip: Trip, side: 'first' | 'last', hutIndex: number): Trip | null {
  const indices = resolved(graph, trip)
  if (!indices) return null
  const sequence = side === 'first' ? [hutIndex, ...indices] : [...indices, hutIndex]
  const ends = connectEnds(graph, trip, sequence)
  if (!ends) return null
  const guid = graph.hutEdges.hutIds[hutIndex]
  const open = { status: 'open' as const }
  return edited(trip, {
    huts: side === 'first' ? [guid, ...trip.huts] : [...trip.huts, guid],
    nights: side === 'first' ? [open, ...trip.nights] : [...trip.nights, open],
    start: ends.start,
    exit: ends.exit,
  })
}

// ---- trim -------------------------------------------------------------------------------------

export type TrimCheck = { ok: true } | { ok: false; reason: string }

function trimmedIndices(indices: number[], index: number): number[] {
  return indices.filter((_, i) => i !== index)
}

export function trimAllowed(graph: TripGraph, trip: Trip, index: number): TrimCheck {
  if (trip.huts.length <= 1) return { ok: false, reason: 'Mindestens eine Hütte muss bleiben.' }
  const indices = resolved(graph, trip)
  if (!indices) return { ok: false, reason: 'Eine Hütte ist nicht mehr im Wegenetz.' }
  const variantId = variantOf(graph, trip.variant)
  const isEnd = index === 0 || index === indices.length - 1
  if (!isEnd) {
    return linkLeg(graph, variantId, hut(indices[index - 1]), hut(indices[index + 1]))
      ? { ok: true }
      : { ok: false, reason: 'Keine direkte Verbindung zwischen den Nachbarhütten.' }
  }
  return connectEnds(graph, trip, trimmedIndices(indices, index))
    ? { ok: true }
    : { ok: false, reason: 'Von der neuen Endhütte gibt es keinen Zu- oder Abstieg.' }
}

export function applyTrim(graph: TripGraph, trip: Trip, index: number): Trip | null {
  if (!trimAllowed(graph, trip, index).ok) return null
  const indices = resolved(graph, trip)!
  const ends = connectEnds(graph, trip, trimmedIndices(indices, index))!
  return edited(trip, {
    huts: trip.huts.filter((_, i) => i !== index),
    nights: trip.nights.filter((_, i) => i !== index),
    start: ends.start,
    exit: ends.exit,
  })
}

// ---- start / exit -----------------------------------------------------------------------------

export interface EndpointCandidate {
  startId: number
  sourceType: SourceType
  durationH: number
}

export function endpointCandidates(graph: TripGraph, trip: Trip, which: 'start' | 'exit'): EndpointCandidate[] {
  const indices = resolved(graph, trip)
  if (!indices || indices.length === 0) return []
  const car = modeOfTrip(trip)
  if (car === 'car' && which === 'exit') return []
  const variantId = variantOf(graph, trip.variant)
  const sourceType = trip.start.sourceType
  const first = indices[0]
  const last = indices[indices.length - 1]
  const approaches = bestStartLegs(graph, variantId, first, 'approach', sourceType)
  const exits = bestStartLegs(graph, variantId, last, 'exit', sourceType)
  const pool = which === 'start' ? approaches : exits
  const current = which === 'start' ? trip.start.startId : trip.exit.startId
  const out: EndpointCandidate[] = []
  for (const [startId, leg] of pool) {
    if (startId === current) continue
    if (car === 'car' && !(approaches.has(startId) && exits.has(startId))) continue
    out.push({ startId, sourceType, durationH: leg.durationH })
  }
  return out.sort((a, b) => a.durationH - b.durationH)
}

export function applyEndpoint(trip: Trip, which: 'start' | 'exit', candidate: EndpointCandidate): Trip {
  const point = { startId: candidate.startId, sourceType: candidate.sourceType }
  if (modeOfTrip(trip) === 'car') return edited(trip, { start: point, exit: point })
  return edited(trip, which === 'start' ? { start: point } : { exit: point })
}
