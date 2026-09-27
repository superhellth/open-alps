import { getAdjacency } from '@/tourSearch/adjacency.js'
import { getApproachLegs, getExitLegs } from '@/tourSearch/approaches.js'
import { resolveHutGuids } from '@/tourSearch/hutIdentity.js'
import { resolveVariant } from '@/tourSearch/resolveVariant.js'
import type { HutLeg, Leg, SourceType, StartLeg, TripGraph } from '@/tourSearch/types.js'
import type { Trip, TripVariant } from './trip.js'

export type Endpoint =
  | { kind: 'start'; startId: number; sourceType: SourceType }
  | { kind: 'hut'; index: number }

/** -1 when the payload has no row for the requested variant, so nothing matches. */
export function variantOf(graph: TripGraph, variant: TripVariant): number {
  return resolveVariant(variant, graph.hutEdges.variantNames) ?? -1
}

/** Fastest approach (dir 'approach') or exit (dir 'exit') per start point for one hut and source
 *  type. Approaches prefer rows of the requested variant and fall back to any variant, mirroring
 *  the search, which seeds from every approach row. */
export function bestStartLegs(
  graph: TripGraph, variantId: number, hutIndex: number, dir: 'approach' | 'exit', sourceType: SourceType,
): Map<number, StartLeg> {
  const all = dir === 'approach'
    ? getApproachLegs(hutIndex, graph.approaches)
    : getExitLegs(hutIndex, variantId, graph.approaches)
  const best = new Map<number, { leg: StartLeg; sameVariant: boolean }>()
  for (const leg of all) {
    if (leg.sourceType !== sourceType) continue
    const sameVariant = dir === 'exit' || leg.variant === variantId
    const current = best.get(leg.startId)
    const better = !current
      || (sameVariant && !current.sameVariant)
      || (sameVariant === current.sameVariant && leg.durationH < current.leg.durationH)
    if (better) best.set(leg.startId, { leg, sameVariant })
  }
  return new Map([...best].map(([startId, { leg }]) => [startId, leg] as const))
}

function fastestHutLeg(graph: TripGraph, variantId: number, from: number, to: number): HutLeg | null {
  let best: HutLeg | null = null
  for (const leg of getAdjacency(graph.hutEdges, variantId).get(from) ?? []) {
    if (leg.toIndex === to && (!best || leg.durationH < best.durationH)) best = leg
  }
  return best
}

/** The leg walked from `from` to `to`, or null if the graph has none. */
export function linkLeg(graph: TripGraph, variantId: number, from: Endpoint, to: Endpoint): Leg | null {
  if (from.kind === 'hut' && to.kind === 'hut') return fastestHutLeg(graph, variantId, from.index, to.index)
  if (from.kind === 'start' && to.kind === 'hut') {
    return bestStartLegs(graph, variantId, to.index, 'approach', from.sourceType).get(from.startId) ?? null
  }
  if (from.kind === 'hut' && to.kind === 'start') {
    return bestStartLegs(graph, variantId, from.index, 'exit', to.sourceType).get(to.startId) ?? null
  }
  return null
}

/** A point along a trip: which leg and how far along it (0…1), in travel direction. */
export interface ProfilePosition {
  legIndex: number
  fraction: number
}

export interface TripLegs {
  variantId: number
  /** Current payload index per trip hut, null when the GUID no longer resolves. */
  hutIndices: (number | null)[]
  /** huts.length + 1 legs: approach, hut->hut legs, exit. Null where the graph has none. */
  legs: (Leg | null)[]
  /** Per night: true when the hut is unresolved or no leg arrives at it ("changed since saved"). */
  changed: boolean[]
}

export function legsFromTrip(graph: TripGraph, trip: Trip): TripLegs {
  const variantId = variantOf(graph, trip.variant)
  const hutIndices = resolveHutGuids(graph.hutEdges.hutIds, trip.huts)
  const points: (Endpoint | null)[] = [
    { kind: 'start', ...trip.start },
    ...hutIndices.map((index): Endpoint | null => (index === null ? null : { kind: 'hut', index })),
    { kind: 'start', ...trip.exit },
  ]
  const legs = points.slice(0, -1).map((from, i) => {
    const to = points[i + 1]
    return from && to ? linkLeg(graph, variantId, from, to) : null
  })
  const last = trip.huts.length - 1
  const changed = trip.huts.map((_, i) =>
    hutIndices[i] === null || legs[i] === null || (i === last && legs[last + 1] === null))
  return { variantId, hutIndices, legs, changed }
}

export function summarizeLegs(legs: (Leg | null)[]) {
  const total = { durationH: 0, ascentM: 0, descentM: 0, distanceM: 0 }
  for (const leg of legs) {
    if (!leg) continue
    total.durationH += leg.durationH
    total.ascentM += leg.ascentM
    total.descentM += leg.descentM
    total.distanceM += leg.distanceM
  }
  return total
}
