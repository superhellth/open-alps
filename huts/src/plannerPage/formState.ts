import type { Query, TourMode } from '../tourSearch/types.js'
import type { HutClass, HutClassKey } from '@/data/hutClass.js'
import { hutClassKey } from '@/data/hutClass.js'
import type { RankTargets } from '../tourSearch/rankFit.js'

export interface FormState {
  mode: TourMode
  sacCeiling: number | 'any'
  allowUngraded: boolean
  legTimeCeilingH: 5 | 7 | 9
  legAscentCapM: string
  maxEleM: string
  allowViaFerrata: boolean
  allowedHutClasses: Set<HutClassKey>
  onlyAvailable: boolean
}

export const DEFAULT_FORM: FormState = {
  mode: 'transit',
  sacCeiling: 3,
  allowUngraded: false,
  legTimeCeilingH: 7,
  legAscentCapM: '',
  maxEleM: '',
  allowViaFerrata: false,
  allowedHutClasses: new Set<HutClassKey>(['av:serviced', 'sonstige:serviced']),
  onlyAvailable: false,
}

export function legTimeRangeFromCeiling(ceilingH: number): [number, number] {
  return [ceilingH / 2, ceilingH]
}

function numberOr(value: string, fallback: number): number {
  if (value === '') return fallback
  const n = Number(value)
  return Number.isFinite(n) ? n : fallback
}

function hutClassAllowed(c: HutClass, form: FormState): boolean {
  return form.allowedHutClasses.has(hutClassKey(c))
}

export function isFilterSelectionValid(form: FormState): boolean {
  return form.allowedHutClasses.size > 0
}

export function buildQuery(form: FormState, hutsByIndex: (HutClass | null)[], legCountRange: [number, number]): Query {
  const allowed = new Set<number>()
  hutsByIndex.forEach((c, i) => {
    if (c && hutClassAllowed(c, form)) allowed.add(i)
  })
  const [minLegTimeH, maxLegTimeH] = legTimeRangeFromCeiling(form.legTimeCeilingH)
  return {
    mode: form.mode,
    legCountMin: legCountRange[0],
    legCountMax: legCountRange[1],
    sacCeiling: form.sacCeiling === 'any' ? null : form.sacCeiling,
    allowUngraded: form.allowUngraded,
    minLegTimeH,
    maxLegTimeH,
    legAscentCapM: numberOr(form.legAscentCapM, Infinity),
    maxEleM: form.maxEleM === '' ? null : numberOr(form.maxEleM, Infinity),
    allowViaFerrata: form.allowViaFerrata,
    allowedHutIndices: allowed,
  }
}

export function rankTargetsFromForm(form: FormState, legCountRange: [number, number], dayCountTarget: number): RankTargets {
  const [min, max] = legCountRange
  return {
    legCountTarget: Math.min(max, Math.max(min, dayCountTarget)),
    legCountRange,
    legTimeRangeH: legTimeRangeFromCeiling(form.legTimeCeilingH),
  }
}
