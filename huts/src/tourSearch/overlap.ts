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
