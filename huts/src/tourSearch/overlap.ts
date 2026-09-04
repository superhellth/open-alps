import type { HutEdgeIdsData } from './types.js'

export type EdgeKind = 'hut' | 'start'

export interface EdgeIdTables {
  hut: HutEdgeIdsData
  start: HutEdgeIdsData
}

/** Given the shared hut's outward-ordered base-edge-id runs for two adjacent legs (spec §4 of
 *  docs/superpowers/specs/2026-08-29-avoid-overlapping-tracks-design.md), returns the ids exempt
 *  from the overlap check because they're the unavoidable stretch of trail leaving the shared
 *  hut. Walks both arrays from the hut outward and keeps the matching run; a mismatch anywhere
 *  stops the walk immediately - only a CONTIGUOUS run out of the hut is the innocent case, a
 *  later coincidental match further out is a real (excludable) overlap. */
export function trimSharedHubIds(
  prevNear: ArrayLike<number>,
  newNear: ArrayLike<number>,
): Set<number> {
  const exempt = new Set<number>()
  const n = Math.min(prevNear.length, newNear.length)
  for (let i = 0; i < n; i++) {
    if (prevNear[i] !== newNear[i]) break
    exempt.add(prevNear[i])
  }
  return exempt
}

/** True if any id in idsNew, other than the exempted shared-hub run, is already in usedIds. */
export function hasOverlap(
  idsNew: ArrayLike<number>,
  exempt: Set<number>,
  usedIds: Set<number>,
): boolean {
  for (let i = 0; i < idsNew.length; i++) {
    const id = idsNew[i]
    if (exempt.has(id)) continue
    if (usedIds.has(id)) return true
  }
  return false
}

/** Picks the id array "near" a leg's shared endpoint, dispatching to the hut- or start-edge-ids
 *  table by the leg's kind (hut-hut vs approach/exit both share the same from->to, prefix-near-
 *  from/suffix-near-to storage convention - spec §4 of docs/superpowers/specs/
 *  2026-08-29-avoid-overlapping-tracks-design.md, extended to start-legs by §4 of
 *  docs/superpowers/specs/2026-09-04-approach-exit-overlap-avoidance-design.md). role:
 *  'arriving' means the leg arrives at the shared point (its near-end is prefix if reversed, else
 *  suffix); 'departing' means it departs from the shared point (near-end is suffix if reversed,
 *  else prefix). */
export function nearHubIds(
  tables: EdgeIdTables,
  leg: { edgeId: number; reversed: boolean; kind: EdgeKind },
  role: 'arriving' | 'departing',
): Int32Array {
  const table = leg.kind === 'hut' ? tables.hut : tables.start
  const wantSuffix = role === 'arriving' ? !leg.reversed : leg.reversed
  return wantSuffix ? table.getSuffixIds(leg.edgeId) : table.getPrefixIds(leg.edgeId)
}
