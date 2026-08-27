/**
 * The layered (hut, leg[, start_id]) exact DFS from spec Part 6, with dominance pruning by
 * visited-set (Task 13 adds this on top) and mode-gated source types (this task): transit
 * tours must start and finish at a station; car tours must start and finish at the same
 * parking lot.
 */
import { resolveVariant } from './resolveVariant.js'
import { buildAdjacency } from './adjacency.js'
import { getApproachLegs, getExitLegs } from './approaches.js'
import { legPasses, createKillCounters } from './legFilters.js'
import { SOURCE_TYPE_PARKING, SOURCE_TYPE_STATION } from './types.js'
import type { GraphData, LegSummary, Query, SearchResult, SourceType, TourResult } from './types.js'

function requiredSourceType(mode: Query['mode']): SourceType | null {
  if (mode === 'transit') return SOURCE_TYPE_STATION
  if (mode === 'car') return SOURCE_TYPE_PARKING
  return null
}

export function searchChains(query: Query, graphData: GraphData): SearchResult {
  const {
    mode, legCountMin, legCountMax, sacCeiling, allowUngraded = false,
    maxLegTimeH, minLegTimeH = 0, legAscentCapM = Infinity, maxEleM = null, allowViaFerrata = true,
  } = query
  const constraints = { maxLegTimeH, minLegTimeH, legAscentCapM, maxEleM, allowViaFerrata }
  const killCounters = createKillCounters()
  const gateSourceType = requiredSourceType(mode)

  const variant = resolveVariant({ sacCeiling, allowUngraded }, graphData.hutEdges.variantNames)
  const adjacency = buildAdjacency(graphData.hutEdges, variant)

  const nightsMin = legCountMin - 1
  const nightsMax = legCountMax - 1

  interface State {
    path: number[]
    startId: number
    totalDurationH: number
    totalAscentM: number
    totalDescentM: number
    totalDistanceM: number
    legs: LegSummary[]
    visitedKey: bigint
  }
  function legSummary(leg: { durationH: number; ascentM: number; descentM: number; distanceM: number }): LegSummary {
    return { durationH: leg.durationH, ascentM: leg.ascentM, descentM: leg.descentM, distanceM: leg.distanceM }
  }

  function insertDominant(bucket: Map<string, State>, key: string, state: State) {
    const existing = bucket.get(key)
    if (!existing || state.totalDurationH < existing.totalDurationH) bucket.set(key, state)
  }

  // layer: Map<hutIndex, Map<"startId|visitedKey", State>> — the inner map is the dominance
  // structure: at most one surviving state per (hutIndex, startId, visitedSet), the one with
  // the lower totalDurationH. hutIndex stays the outer key (unchanged from before) purely so
  // getExitLegs/adjacency.get(h) are still looked up once per hut, not once per state.
  let layer = new Map<number, Map<string, State>>()
  for (let h = 0; h < graphData.hutEdges.hutIds.length; h++) {
    for (const approachLeg of getApproachLegs(h, graphData.approaches)) {
      if (gateSourceType != null && approachLeg.sourceType !== gateSourceType) continue
      if (!legPasses(approachLeg, constraints, killCounters)) continue
      const visitedKey = 1n << BigInt(h)
      const state: State = {
        path: [h], startId: approachLeg.startId,
        totalDurationH: approachLeg.durationH, totalAscentM: approachLeg.ascentM,
        totalDescentM: approachLeg.descentM, totalDistanceM: approachLeg.distanceM,
        legs: [legSummary(approachLeg)],
        visitedKey,
      }
      if (!layer.has(h)) layer.set(h, new Map())
      insertDominant(layer.get(h)!, `${state.startId}|${visitedKey}`, state)
    }
  }

  const finished: TourResult[] = []
  const collectFinished = (n: number) => {
    if (n < nightsMin) return
    for (const [h, states] of layer) {
      const exitLegs = getExitLegs(h, variant, graphData.approaches)
      for (const s of states.values()) {
        for (const exitLeg of exitLegs) {
          if (mode === 'car' && exitLeg.startId !== s.startId) continue
          if (gateSourceType != null && exitLeg.sourceType !== gateSourceType) continue
          if (!legPasses(exitLeg, constraints, killCounters)) continue
          finished.push({
            huts: [...s.path], startId: s.startId, exitStartId: exitLeg.startId,
            totalDurationH: s.totalDurationH + exitLeg.durationH,
            totalAscentM: s.totalAscentM + exitLeg.ascentM,
            totalDescentM: s.totalDescentM + exitLeg.descentM,
            totalDistanceM: s.totalDistanceM + exitLeg.distanceM,
            legs: [...s.legs, legSummary(exitLeg)],
          })
        }
      }
    }
  }

  collectFinished(1)
  for (let n = 1; n < nightsMax; n++) {
    const nextLayer = new Map<number, Map<string, State>>()
    for (const [h, states] of layer) {
      const legs = adjacency.get(h) || []
      for (const s of states.values()) {
        for (const leg of legs) {
          const h2 = leg.toIndex
          if (s.path.includes(h2)) { killCounters.revisit++; continue }
          if (!legPasses(leg, constraints, killCounters)) continue
          const nextVisitedKey = s.visitedKey | (1n << BigInt(h2))
          const next: State = {
            path: [...s.path, h2], startId: s.startId,
            totalDurationH: s.totalDurationH + leg.durationH,
            totalAscentM: s.totalAscentM + leg.ascentM,
            totalDescentM: s.totalDescentM + leg.descentM,
            totalDistanceM: s.totalDistanceM + leg.distanceM,
            legs: [...s.legs, legSummary(leg)],
            visitedKey: nextVisitedKey,
          }
          if (!nextLayer.has(h2)) nextLayer.set(h2, new Map())
          insertDominant(nextLayer.get(h2)!, `${next.startId}|${nextVisitedKey}`, next)
        }
      }
    }
    layer = nextLayer
    collectFinished(n + 1)
  }

  finished.sort((a, b) => a.totalDurationH - b.totalDurationH)
  return { chains: finished, killCounters }
}
