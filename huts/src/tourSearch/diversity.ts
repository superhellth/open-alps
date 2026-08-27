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

export function suppressSimilar<T extends { huts: number[]; startId: number; totalDurationH: number }>(
  chains: T[],
  overlapThreshold: number,
): T[] {
  const accepted: T[] = []
  for (const candidate of chains) {
    const tooSimilar = accepted.some(
      (a) => a.startId === candidate.startId || hutOverlapFraction(a, candidate) > overlapThreshold,
    )
    if (!tooSimilar) accepted.push(candidate)
  }
  return accepted
}
