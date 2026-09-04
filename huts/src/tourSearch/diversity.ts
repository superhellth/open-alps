/**
 * Two separate diversity steps with two separate keys (spec Part 6, "Result diversity") —
 * this file must never merge them. Step 1: exact-duplicate removal on the ORDERED hut
 * sequence — a chain and its reverse are one tour walked two ways, and this step has no
 * threshold. Step 2: similarity suppression on the UNORDERED hut set.
 *
 * Generic over the minimal shape each function needs (not the full TourResult) so synthetic
 * test fixtures don't have to carry every TourResult field just to exercise this file.
 */
export function dedupeReversePairs<T extends { huts: number[]; totalDurationH: number }>(chains: T[]): T[] {
  const bestBySignature = new Map<string, T>()
  for (const chain of chains) {
    const forwardKey = chain.huts.join('>')
    const reverseKey = [...chain.huts].reverse().join('>')
    const canonicalKey = forwardKey < reverseKey ? forwardKey : reverseKey
    const existing = bestBySignature.get(canonicalKey)
    if (!existing || chain.totalDurationH < existing.totalDurationH) {
      bestBySignature.set(canonicalKey, chain)
    }
  }
  return [...bestBySignature.values()]
}

function hutOverlapFraction(a: { huts: number[] }, b: { huts: number[] }): number {
  const setA = new Set(a.huts)
  const setB = new Set(b.huts)
  let shared = 0
  for (const h of setA) if (setB.has(h)) shared++
  return shared / Math.min(setA.size, setB.size)
}

/** Fixed, not tunable: the "Variantenvielfalt" UI knob that used to feed this was measured to be a
 *  no-op — 0.3, 0.5 and 0.8 all returned the same chains on the shipped payload (2-4 legs, SAC 3),
 *  because the start-point rule below already caps results at one tour per start point and tours
 *  from *different* start points rarely share huts. The threshold itself is not a no-op (dropping
 *  it entirely lets ~16% more car chains through, all of them same-hut-set permutations), so it
 *  stays — as a constant. */
const HUT_OVERLAP_THRESHOLD = 0.5

export function suppressSimilar<T extends { huts: number[]; startId: number; totalDurationH: number }>(
  chains: T[],
): T[] {
  const accepted: T[] = []
  for (const candidate of chains) {
    const tooSimilar = accepted.some(
      (a) => a.startId === candidate.startId || hutOverlapFraction(a, candidate) > HUT_OVERLAP_THRESHOLD,
    )
    if (!tooSimilar) accepted.push(candidate)
  }
  return accepted
}
