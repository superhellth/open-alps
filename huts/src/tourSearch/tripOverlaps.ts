import { hasOverlap, nearHubIds, trimSharedHubIds } from './overlap.js'
import type { EdgeIdTables, EdgeKind } from './overlap.js'
import type { TripLegs } from './tripLegs.js'

export interface OverlapLeg {
  edgeId: number
  reversed: boolean
  kind: EdgeKind
}

function sortedIds(tables: EdgeIdTables, leg: OverlapLeg): Int32Array {
  return (leg.kind === 'hut' ? tables.hut : tables.start).getSortedIds(leg.edgeId)
}

/** Pairs of legs that walk the same trail segments. Neighbouring legs may share the run out of
 *  their common hut, and on a loop closure the first and last leg the run out of the shared start
 *  point — the same exemptions the search applies. */
export function tripOverlaps(tables: EdgeIdTables, legs: OverlapLeg[], loopClosure: boolean): [number, number][] {
  const pairs: [number, number][] = []
  const ids = legs.map((leg) => sortedIds(tables, leg))
  for (let later = 1; later < legs.length; later++) {
    for (let earlier = 0; earlier < later; earlier++) {
      let exempt = new Set<number>()
      if (earlier === later - 1) {
        exempt = trimSharedHubIds(
          nearHubIds(tables, legs[earlier], 'arriving'),
          nearHubIds(tables, legs[later], 'departing'),
        )
      }
      if (loopClosure && earlier === 0 && later === legs.length - 1) {
        for (const id of trimSharedHubIds(
          tables.start.getPrefixIds(legs[earlier].edgeId),
          tables.start.getPrefixIds(legs[later].edgeId),
        )) exempt.add(id)
      }
      if (hasOverlap(ids[later], exempt, new Set(ids[earlier]))) pairs.push([earlier, later])
    }
  }
  return pairs
}

export function overlapLegsOf(tripLegs: TripLegs): OverlapLeg[] | null {
  const last = tripLegs.legs.length - 1
  const out: OverlapLeg[] = []
  for (let i = 0; i <= last; i++) {
    const leg = tripLegs.legs[i]
    if (!leg) return null
    out.push({ edgeId: leg.edgeId, reversed: leg.reversed, kind: i === 0 || i === last ? 'start' : 'hut' })
  }
  return out
}
