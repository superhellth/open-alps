import type { Query, TourMode } from '../tourSearch/types.js'
import type { HutClass, HutOperator } from '../hutClass.js'
import { toNumberOrDefault } from './helpers.js'

export interface FormState {
  mode: TourMode
  legCountRange: [number, number]
  sacCeiling: number | 'any'
  allowUngraded: boolean
  legTimeRange: [number, number]
  legAscentCapM: string
  maxEleM: string
  allowViaFerrata: boolean
  allowedOperators: Set<HutOperator>
  allowServiced: boolean
  allowSelfService: boolean
  startDate: string
  numOfPeople: number
  onlyAvailable: boolean
}

export const DEFAULT_FORM: FormState = {
  mode: 'transit',
  legCountRange: [2, 4],
  sacCeiling: 3,
  allowUngraded: true,
  legTimeRange: [4, 8],
  legAscentCapM: '',
  maxEleM: '',
  allowViaFerrata: true,
  allowedOperators: new Set(['av', 'sonstige']),
  allowServiced: true,
  allowSelfService: false,
  startDate: '',
  numOfPeople: 1,
  onlyAvailable: false,
}

function hutClassAllowed(c: HutClass, form: FormState): boolean {
  if (!form.allowedOperators.has(c.operator)) return false
  return c.serviced ? form.allowServiced : form.allowSelfService
}

function allowedHutIndices(form: FormState, hutsByIndex: (HutClass | null)[]): Set<number> {
  const allowed = new Set<number>()
  hutsByIndex.forEach((c, i) => {
    if (c && hutClassAllowed(c, form)) allowed.add(i)
  })
  return allowed
}

export function isFilterSelectionValid(form: FormState): boolean {
  if (form.allowedOperators.size === 0) return false
  if (!form.allowServiced && !form.allowSelfService) return false
  return true
}

export function buildQuery(
  form: FormState,
  hutsByIndex: (HutClass | null)[],
  availability?: Query['availability'],
): Query {
  return {
    mode: form.mode,
    legCountMin: form.legCountRange[0],
    legCountMax: form.legCountRange[1],
    sacCeiling: form.sacCeiling === 'any' ? null : form.sacCeiling,
    allowUngraded: form.allowUngraded,
    minLegTimeH: form.legTimeRange[0],
    maxLegTimeH: form.legTimeRange[1],
    legAscentCapM: toNumberOrDefault(form.legAscentCapM, Infinity),
    maxEleM: form.maxEleM === '' ? null : toNumberOrDefault(form.maxEleM, Infinity),
    allowViaFerrata: form.allowViaFerrata,
    allowedHutIndices: allowedHutIndices(form, hutsByIndex),
    availability: form.onlyAvailable ? availability : undefined,
  }
}
