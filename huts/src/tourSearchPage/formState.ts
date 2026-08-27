import type { Query, TourMode } from '../tourSearch/types.js'
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
  overlapVariety: 'wenig' | 'mittel' | 'viel'
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
  overlapVariety: 'mittel',
}

export const OVERLAP_THRESHOLD_BY_VARIETY: Record<FormState['overlapVariety'], number> = {
  wenig: 0.3,
  mittel: 0.5,
  viel: 0.8,
}

export function buildQuery(form: FormState): Query {
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
  }
}
