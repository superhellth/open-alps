import type { Query, TourMode } from '../tourSearch/types.js'
import type { HutClass, HutOperator } from '../hutClass.js'
import type { RankTargets } from '../tourSearch/rankFit.js'

export interface FormState {
  mode: TourMode
  legCountRange: [number, number]
  /** Preferred day count for ranking; null = middle of legCountRange. */
  targetLegCount: number | null
  sacCeiling: number | 'any'
  allowUngraded: boolean
  legTimeRange: [number, number]
  legAscentCapM: string
  maxEleM: string
  allowViaFerrata: boolean
  allowedOperators: Set<HutOperator>
  allowServiced: boolean
  allowSelfService: boolean
  onlyAvailable: boolean
}

export const DEFAULT_FORM: FormState = {
  mode: 'transit',
  legCountRange: [2, 4],
  targetLegCount: null,
  sacCeiling: 3,
  allowUngraded: true,
  legTimeRange: [4, 8],
  legAscentCapM: '',
  maxEleM: '',
  allowViaFerrata: true,
  allowedOperators: new Set(['av', 'sonstige']),
  allowServiced: true,
  allowSelfService: false,
  onlyAvailable: false,
}

function numberOr(value: string, fallback: number): number {
  if (value === '') return fallback
  const n = Number(value)
  return Number.isFinite(n) ? n : fallback
}

function hutClassAllowed(c: HutClass, form: FormState): boolean {
  if (!form.allowedOperators.has(c.operator)) return false
  return c.serviced ? form.allowServiced : form.allowSelfService
}

export function isFilterSelectionValid(form: FormState): boolean {
  if (form.allowedOperators.size === 0) return false
  return form.allowServiced || form.allowSelfService
}

export function buildQuery(
  form: FormState, hutsByIndex: (HutClass | null)[], availability?: Query['availability'],
): Query {
  const allowed = new Set<number>()
  hutsByIndex.forEach((c, i) => {
    if (c && hutClassAllowed(c, form)) allowed.add(i)
  })
  return {
    mode: form.mode,
    legCountMin: form.legCountRange[0],
    legCountMax: form.legCountRange[1],
    sacCeiling: form.sacCeiling === 'any' ? null : form.sacCeiling,
    allowUngraded: form.allowUngraded,
    minLegTimeH: form.legTimeRange[0],
    maxLegTimeH: form.legTimeRange[1],
    legAscentCapM: numberOr(form.legAscentCapM, Infinity),
    maxEleM: form.maxEleM === '' ? null : numberOr(form.maxEleM, Infinity),
    allowViaFerrata: form.allowViaFerrata,
    allowedHutIndices: allowed,
    availability: form.onlyAvailable ? availability : undefined,
  }
}

export function rankTargetsFromForm(form: FormState): RankTargets {
  const [min, max] = form.legCountRange
  const target = form.targetLegCount ?? Math.round((min + max) / 2)
  return {
    legCountTarget: Math.min(max, Math.max(min, target)),
    legCountRange: form.legCountRange,
    legTimeRangeH: form.legTimeRange,
  }
}
