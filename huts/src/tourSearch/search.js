/**
 * The layered (hut, leg[, start_id]) exact DFS from spec Part 6. Both `car` and `transit`
 * carry `startId` in every state for one shared code path — the design keeps `transit`'s
 * state to (hut, n) only to shrink the state space, but at this graph's measured size
 * (2026-08-26 design addendum: mean degree 3-5 over 956 huts) that collapse is a
 * performance nicety this plan deliberately skips, not a correctness requirement. `transit`
 * simply never checks `startId` at finish time.
 */
import { resolveVariant } from './resolveVariant.js'
import { buildAdjacency } from './adjacency.js'
import { getApproachLegs, getExitLegs } from './approaches.js'
import { legPasses, createKillCounters } from './legFilters.js'

export function searchChains(query, graphData) {
  const {
    mode, legCountMin, legCountMax, sacCeiling, allowUngraded = false,
    maxLegTimeH, minLegTimeH = 0, legAscentCapM = Infinity, maxEleM = null, allowViaFerrata = true,
  } = query
  const constraints = { maxLegTimeH, minLegTimeH, legAscentCapM, maxEleM, allowViaFerrata }
  const killCounters = createKillCounters()

  const variant = resolveVariant({ sacCeiling, allowUngraded }, graphData.hutEdges.variantNames)
  const adjacency = buildAdjacency(graphData.hutEdges, variant)

  const nightsMin = legCountMin - 1
  const nightsMax = legCountMax - 1

  // layer: Map<hutIndex, State[]>, State = { path, startId, totalDurationH, totalAscentM, totalDescentM, totalDistanceM }
  let layer = new Map()
  for (let h = 0; h < graphData.hutEdges.hutIds.length; h++) {
    for (const approachLeg of getApproachLegs(h, graphData.approaches)) {
      if (!legPasses(approachLeg, constraints, killCounters)) continue
      const state = {
        path: [h], startId: approachLeg.startId,
        totalDurationH: approachLeg.durationH, totalAscentM: approachLeg.ascentM,
        totalDescentM: approachLeg.descentM, totalDistanceM: approachLeg.distanceM,
      }
      if (!layer.has(h)) layer.set(h, [])
      layer.get(h).push(state)
    }
  }

  const finished = []
  const collectFinished = (n) => {
    if (n < nightsMin) return
    for (const [h, states] of layer) {
      const exitLegs = getExitLegs(h, variant, graphData.approaches)
      for (const s of states) {
        for (const exitLeg of exitLegs) {
          if (mode === 'car' && exitLeg.startId !== s.startId) continue
          if (!legPasses(exitLeg, constraints, killCounters)) continue
          finished.push({
            huts: [...s.path], startId: s.startId, exitStartId: exitLeg.startId,
            totalDurationH: s.totalDurationH + exitLeg.durationH,
            totalAscentM: s.totalAscentM + exitLeg.ascentM,
            totalDescentM: s.totalDescentM + exitLeg.descentM,
            totalDistanceM: s.totalDistanceM + exitLeg.distanceM,
          })
        }
      }
    }
  }

  collectFinished(1)
  for (let n = 1; n < nightsMax; n++) {
    const nextLayer = new Map()
    for (const [h, states] of layer) {
      const legs = adjacency.get(h) || []
      for (const s of states) {
        for (const leg of legs) {
          const h2 = leg.toIndex
          if (s.path.includes(h2)) { killCounters.revisit++; continue }
          if (!legPasses(leg, constraints, killCounters)) continue
          const next = {
            path: [...s.path, h2], startId: s.startId,
            totalDurationH: s.totalDurationH + leg.durationH,
            totalAscentM: s.totalAscentM + leg.ascentM,
            totalDescentM: s.totalDescentM + leg.descentM,
            totalDistanceM: s.totalDistanceM + leg.distanceM,
          }
          if (!nextLayer.has(h2)) nextLayer.set(h2, [])
          nextLayer.get(h2).push(next)
        }
      }
    }
    layer = nextLayer
    collectFinished(n + 1)
  }

  finished.sort((a, b) => a.totalDurationH - b.totalDurationH)
  return { chains: finished, killCounters }
}
