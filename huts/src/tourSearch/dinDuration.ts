/**
 * DIN 33466 hiking duration. Mirrors pipeline/lib/speed.py's din_duration_h() exactly —
 * this is the client-side half of a formula the pipeline deliberately does not ship a
 * precomputed value for (docs/tour-suggestion-payload.md §2).
 */
export function dinDurationH(distanceM: number, ascentM: number, descentM: number): number {
  const tHorizontal = distanceM / 4000
  const tVertical = ascentM / 300 + descentM / 500
  return Math.max(tHorizontal, tVertical) + Math.min(tHorizontal, tVertical) / 2
}
