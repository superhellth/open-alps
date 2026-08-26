/**
 * Two separate diversity steps with two separate keys (spec Part 6, "Result diversity") —
 * this file must never merge them. Step 1 (this task): exact-duplicate removal on the
 * ORDERED hut sequence — a chain and its reverse are one tour walked two ways, and this
 * step has no threshold. Step 2 (Task 13): similarity suppression on the UNORDERED hut set.
 */
export function dedupeReversePairs(chains) {
  const bestBySignature = new Map()
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
