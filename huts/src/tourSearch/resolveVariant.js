/**
 * Difficulty ceiling is a routing-relevant threshold, not a per-edge filter (spec Part 2's
 * filter/objective/variant table) — it resolves to exactly ONE variant row for the whole
 * query, never a per-edge sac_rank comparison. Filtering sac_rank on an unconstrained row
 * does not support the "every metre graded" claim (docs/tour-suggestion-payload.md §5).
 */
export function resolveVariant({ sacCeiling, allowUngraded = false } = {}, variantNames) {
  const idByName = {}
  for (const [id, name] of Object.entries(variantNames)) idByName[name] = Number(id)

  if (sacCeiling != null && sacCeiling <= 2) return idByName.FAST_T2
  if (sacCeiling != null && sacCeiling <= 3) return allowUngraded ? idByName.FAST_T3_UNGRADED : idByName.FAST_T3
  return idByName.FAST_ANY
}
