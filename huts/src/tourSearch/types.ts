export const SOURCE_TYPE_STATION = 1
export const SOURCE_TYPE_PARKING = 2

export type SourceType = typeof SOURCE_TYPE_STATION | typeof SOURCE_TYPE_PARKING

export interface ApproachRecord {
  hutIndex: number
  startId: number
  sourceType: SourceType
  accessUnknown: boolean
  distanceM: number
  ascentM: number
  descentM: number
  access: string | null
  edgeId: number
}

export interface HutEdgeRecord {
  fromIndex: number
  toIndex: number
  variant: number
  distanceM: number
  ascentM: number
  descentM: number
  maxEleM: number
  sacRank: number
  viaFerrata: boolean
  roadM: number
  ungradedM: number
  inferredM: number
  snapM: number
  edgeId: number
}

/** Fields legFilters.legPasses needs, present on every leg shape (hut-hut, approach, exit). */
export interface LegBase {
  distanceM: number
  ascentM: number
  descentM: number
  durationH: number
  maxEleM?: number
  viaFerrata?: boolean
}

export interface HutLeg extends LegBase {
  fromIndex: number
  toIndex: number
  variant: number
  maxEleM: number
  sacRank: number
  viaFerrata: boolean
  roadM: number
  ungradedM: number
  inferredM: number
  snapM: number
  edgeId: number
  reversed: boolean
}

export interface StartLeg extends LegBase {
  startId: number
  sourceType: SourceType
  hutIndex?: number
  accessUnknown?: boolean
  access?: string | null
  edgeId: number
  reversed: boolean
}

export type Leg = HutLeg | StartLeg

export interface ChainState {
  path: number[]
  startId: number
  totalDurationH: number
  totalAscentM: number
  totalDescentM: number
  totalDistanceM: number
}

/** One hop's numbers, in chain order: leg 0 is startId->huts[0], leg i (0<i<huts.length) is
 *  huts[i-1]->huts[i], and the last leg is huts[huts.length-1]->exitStartId. The UI derives
 *  from/to labels itself by zipping this array against [startId, ...huts, exitStartId] —
 *  the engine stays name-agnostic. */
export interface LegSummary {
  durationH: number
  ascentM: number
  descentM: number
  distanceM: number
}

export interface TourResult {
  huts: number[]
  startId: number
  exitStartId: number
  totalDurationH: number
  totalAscentM: number
  totalDescentM: number
  totalDistanceM: number
  legs: LegSummary[]
}

export type TourMode = 'car' | 'transit'

export interface Query {
  mode: TourMode
  legCountMin: number
  legCountMax: number
  sacCeiling?: number | null
  allowUngraded?: boolean
  maxLegTimeH: number
  minLegTimeH?: number
  legAscentCapM?: number
  maxEleM?: number | null
  allowViaFerrata?: boolean
}

export interface KillCounters {
  maxLegTime: number
  minLegTime: number
  legAscentCap: number
  maxEleM: number
  viaFerrata: number
  revisit: number
}

export interface ReverseIndexEntry {
  hut_id: number
  start_id: number
  source_type: SourceType
  variant: number
  distance_m: number
  ascent_m: number
  descent_m: number
}

export interface HutEdgesData {
  hutIds: string[]
  variantNames: Record<string, string>
  records: HutEdgeRecord[]
}

export interface ApproachesData {
  records: ApproachRecord[]
  reverseIndex: {
    hut_to_starts: Record<string, ReverseIndexEntry[]>
    start_to_huts: Record<string, ReverseIndexEntry[]>
  }
}

export interface GraphData {
  hutEdges: HutEdgesData
  approaches: ApproachesData
}

export interface SearchResult {
  chains: TourResult[]
  killCounters: KillCounters
}
