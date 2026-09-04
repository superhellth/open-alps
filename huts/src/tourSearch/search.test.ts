import { describe, it, expect } from 'vitest'
import { searchChains } from './search.js'
import { resolveVariant } from './resolveVariant.js'
import { buildAdjacency } from './adjacency.js'
import { getApproachLegs, getExitLegs } from './approaches.js'
import { legPasses, createKillCounters } from './legFilters.js'
import { SOURCE_TYPE_PARKING, SOURCE_TYPE_STATION } from './types.js'
import type { GraphData, LegSummary, Query, TourResult } from './types.js'

// A tiny 3-hut chain: start1 -> A -> B -> C -> start2, all within budget, all FAST_ANY.
function edge(fromIndex: number, toIndex: number, distanceM: number) {
  return { fromIndex, toIndex, variant: 0, distanceM, ascentM: 200, descentM: 200, maxEleM: 2000, sacRank: 1, viaFerrata: false, roadM: 0, ungradedM: 0, inferredM: 0, snapM: 0, edgeId: fromIndex * 100 + toIndex }
}

function emptyHutEdgeIdsStub(): GraphData['hutEdgeIds'] {
  return {
    getSortedIds: () => new Int32Array(0),
    getPrefixIds: () => new Int32Array(0),
    getSuffixIds: () => new Int32Array(0),
  }
}

// This fixture's approach/exit are station-type (SOURCE_TYPE_STATION = 1), matching the
// "(transit)" describe block below; the "(car)" describe block overrides source types to
// SOURCE_TYPE_PARKING (2) on its own graph copies where mode-gating requires it.
const graphData: GraphData = {
  hutEdgeIds: emptyHutEdgeIdsStub(),
  startEdgeIds: emptyHutEdgeIdsStub(),
  hutEdges: {
    hutIds: ['A', 'B', 'C'],
    variantNames: { 0: 'FAST_ANY' },
    records: [edge(0, 1, 5000), edge(1, 2, 5000)],
  },
  approaches: {
    records: [
      { hutIndex: 0, startId: 100, sourceType: 1, variant: 0, accessUnknown: false, distanceM: 2000, ascentM: 100, descentM: 50, access: null, edgeId: 9000 },
    ],
    reverseIndex: {
      hut_to_starts: {
        2: [{ hut_id: 2, start_id: 200, source_type: 1, variant: 0, distance_m: 2000, ascent_m: 50, descent_m: 100, edge_id: 9001 }],
      },
      start_to_huts: {},
    },
  },
}

const generousConstraints = { maxLegTimeH: 10, minLegTimeH: 0, legAscentCapM: 9999, maxEleM: null, allowViaFerrata: true }

describe('searchChains (transit)', () => {
  it('finds the A->B->C chain within a 3-4 leg budget', () => {
    const { chains } = searchChains(
      { mode: 'transit', legCountMin: 3, legCountMax: 4, ...generousConstraints },
      graphData,
    )
    const full = chains.find((c) => c.huts.length === 3)
    expect(full).toBeDefined()
    expect(full!.huts).toEqual([0, 1, 2])
    expect(full!.startId).toBe(100)
    expect(full!.exitStartId).toBe(200)
  })

  it('never revisits a hut within one chain', () => {
    const { chains } = searchChains(
      { mode: 'transit', legCountMin: 2, legCountMax: 6, ...generousConstraints },
      graphData,
    )
    for (const chain of chains) {
      expect(new Set(chain.huts).size).toBe(chain.huts.length)
    }
  })

  it('respects legCountMax: a 2-leg budget cannot reach the 3-hut chain', () => {
    const { chains } = searchChains(
      { mode: 'transit', legCountMin: 2, legCountMax: 2, ...generousConstraints },
      graphData,
    )
    expect(chains.some((c) => c.huts.length === 3)).toBe(false)
  })

  it('a maxLegTimeH too tight for any leg returns no chains and records why', () => {
    const { chains, killCounters } = searchChains(
      { mode: 'transit', legCountMin: 2, legCountMax: 4, ...generousConstraints, maxLegTimeH: 0.01 },
      graphData,
    )
    expect(chains).toEqual([])
    expect(killCounters.maxLegTime).toBeGreaterThan(0)
  })

  it('sorts results by ascending total duration', () => {
    const { chains } = searchChains(
      { mode: 'transit', legCountMin: 2, legCountMax: 4, ...generousConstraints },
      graphData,
    )
    const durations = chains.map((c) => c.totalDurationH)
    expect(durations).toEqual([...durations].sort((a, b) => a - b))
  })
})

describe('searchChains (car)', () => {
  it('only finishes a chain whose exit start point matches the entry start point', () => {
    const { chains } = searchChains(
      { mode: 'car', legCountMin: 2, legCountMax: 4, ...generousConstraints },
      graphData,
    )
    // graphData's only exit from hut 2 is start_id 200, but the only approach is start_id 100 ->
    // no car chain can close, regardless of leg budget.
    expect(chains).toEqual([])
  })

  it('finds a closing loop when an exit back to the entry start point exists', () => {
    const loopGraphData: GraphData = {
      ...graphData,
      approaches: {
        records: [{ ...graphData.approaches.records[0], sourceType: 2 }],
        reverseIndex: {
          hut_to_starts: {
            2: [{ hut_id: 2, start_id: 100, source_type: 2, variant: 0, distance_m: 2000, ascent_m: 50, descent_m: 100, edge_id: 8002 }],
          },
          start_to_huts: {},
        },
      },
    }
    const { chains } = searchChains(
      { mode: 'car', legCountMin: 2, legCountMax: 4, ...generousConstraints },
      loopGraphData,
    )
    const full = chains.find((c) => c.huts.length === 3)
    expect(full).toBeDefined()
    expect(full!.startId).toBe(100)
    expect(full!.exitStartId).toBe(100)
  })
})

describe('searchChains (overlap avoidance)', () => {
  const overlapEdge = (fromIndex: number, toIndex: number, edgeId: number) => ({
    fromIndex, toIndex, variant: 0, distanceM: 5000, ascentM: 200, descentM: 200, maxEleM: 2000,
    sacRank: 1, viaFerrata: false, roadM: 0, ungradedM: 0, inferredM: 0, snapM: 0, edgeId,
  })

  // Chain 0 -[e01]-> 1 -[e12]-> 2 -[e23]-> 3. e01 and e12 share base-edge id 100, but ONLY in the
  // run leaving their common hut 1 - spec §4's exemption should keep a chain using just those two.
  // e01 and e23 independently share id 200, with NO common hut between them - spec §4's hard rule
  // should exclude any chain using both.
  const SORTED: Record<number, number[]> = { 1: [100, 200], 2: [100, 300], 3: [200, 400] }
  const PREFIX: Record<number, number[]> = { 1: [200], 2: [100], 3: [400] }  // near from_id
  const SUFFIX: Record<number, number[]> = { 1: [100], 2: [300], 3: [200] }  // near to_id

  const overlapGraphData: GraphData = {
    hutEdges: {
      hutIds: ['A', 'B', 'C', 'D'],
      variantNames: { 0: 'FAST_ANY' },
      records: [overlapEdge(0, 1, 1), overlapEdge(1, 2, 2), overlapEdge(2, 3, 3)],
    },
    approaches: {
      records: [
        { hutIndex: 0, startId: 100, sourceType: 1, variant: 0, accessUnknown: false, distanceM: 2000, ascentM: 100, descentM: 50, access: null, edgeId: 9000 },
      ],
      reverseIndex: {
        hut_to_starts: {
          2: [{ hut_id: 2, start_id: 300, source_type: 1, variant: 0, distance_m: 2000, ascent_m: 50, descent_m: 100, edge_id: 9002 }],
          3: [{ hut_id: 3, start_id: 200, source_type: 1, variant: 0, distance_m: 2000, ascent_m: 50, descent_m: 100, edge_id: 9001 }],
        },
        start_to_huts: {},
      },
    },
    hutEdgeIds: {
      getSortedIds: (edgeId) => Int32Array.from(SORTED[edgeId] ?? []),
      getPrefixIds: (edgeId) => Int32Array.from(PREFIX[edgeId] ?? []),
      getSuffixIds: (edgeId) => Int32Array.from(SUFFIX[edgeId] ?? []),
    },
    startEdgeIds: emptyHutEdgeIdsStub(),
  }

  it('excludes a chain whose non-adjacent legs share a base-edge id', () => {
    const { chains, killCounters } = searchChains(
      { mode: 'transit', legCountMin: 2, legCountMax: 6, ...generousConstraints },
      overlapGraphData,
    )
    expect(chains.some((c) => c.huts.length === 4)).toBe(false)
    expect(killCounters.trackOverlap).toBeGreaterThan(0)
  })

  it('keeps a chain whose adjacent legs only share the run out of their common hut', () => {
    const { chains } = searchChains(
      { mode: 'transit', legCountMin: 2, legCountMax: 6, ...generousConstraints },
      overlapGraphData,
    )
    const kept = chains.find((c) => c.huts.length === 3 && c.exitStartId === 300)
    expect(kept).toBeDefined()
    expect(kept!.huts).toEqual([0, 1, 2])
  })
})

describe('searchChains (approach-leg overlap avoidance)', () => {
  // Chain A -[e01]-> B -[e12]-> C. Approach (start 500 -> A, edgeId 700) shares base-edge id 200
  // with e01 ONLY in the run leaving their common hut A - should be exempted, same rule as two
  // adjacent hut-hut legs. Approach also carries id 999, which e12 independently carries too, with
  // NO hut in common with the approach (e12 connects B and C, the approach touches only A) - a
  // genuine overlap that must exclude any chain using both.
  const approachOverlapEdge = (fromIndex: number, toIndex: number, edgeId: number) => ({
    fromIndex, toIndex, variant: 0, distanceM: 5000, ascentM: 200, descentM: 200, maxEleM: 2000,
    sacRank: 1, viaFerrata: false, roadM: 0, ungradedM: 0, inferredM: 0, snapM: 0, edgeId,
  })

  const SORTED_HUT: Record<number, number[]> = { 1: [100, 200], 2: [100, 300, 999] }
  const PREFIX_HUT: Record<number, number[]> = { 1: [200], 2: [100] } // near from_id
  const SUFFIX_HUT: Record<number, number[]> = { 1: [100], 2: [300] } // near to_id
  const SORTED_START: Record<number, number[]> = { 700: [200, 999] }
  const SUFFIX_START: Record<number, number[]> = { 700: [200] } // near hut A (the approach's arrival end)

  const approachOverlapGraphData: GraphData = {
    hutEdges: {
      hutIds: ['A', 'B', 'C'],
      variantNames: { 0: 'FAST_ANY' },
      records: [approachOverlapEdge(0, 1, 1), approachOverlapEdge(1, 2, 2)],
    },
    approaches: {
      records: [
        { hutIndex: 0, startId: 500, sourceType: SOURCE_TYPE_STATION, variant: 0, accessUnknown: false, distanceM: 2000, ascentM: 100, descentM: 50, access: null, edgeId: 700 },
      ],
      reverseIndex: {
        hut_to_starts: {
          1: [{ hut_id: 1, start_id: 601, source_type: SOURCE_TYPE_STATION, variant: 0, distance_m: 2000, ascent_m: 50, descent_m: 100, edge_id: 800 }],
          2: [{ hut_id: 2, start_id: 602, source_type: SOURCE_TYPE_STATION, variant: 0, distance_m: 2000, ascent_m: 50, descent_m: 100, edge_id: 801 }],
        },
        start_to_huts: {},
      },
    },
    hutEdgeIds: {
      getSortedIds: (edgeId) => Int32Array.from(SORTED_HUT[edgeId] ?? []),
      getPrefixIds: (edgeId) => Int32Array.from(PREFIX_HUT[edgeId] ?? []),
      getSuffixIds: (edgeId) => Int32Array.from(SUFFIX_HUT[edgeId] ?? []),
    },
    startEdgeIds: {
      getSortedIds: (edgeId) => Int32Array.from(SORTED_START[edgeId] ?? []),
      getPrefixIds: () => new Int32Array(0),
      getSuffixIds: (edgeId) => Int32Array.from(SUFFIX_START[edgeId] ?? []),
    },
  }

  it('excludes a chain whose approach leg overlaps a later, non-adjacent hut-hut leg', () => {
    const { chains, killCounters } = searchChains(
      { mode: 'transit', legCountMin: 2, legCountMax: 6, ...generousConstraints },
      approachOverlapGraphData,
    )
    expect(chains.some((c) => c.huts.length >= 3)).toBe(false)
    expect(killCounters.trackOverlap).toBeGreaterThan(0)
  })

  it('keeps a chain whose approach and first hut-hut leg only share the run out of their common hut', () => {
    const { chains } = searchChains(
      { mode: 'transit', legCountMin: 3, legCountMax: 3, ...generousConstraints },
      approachOverlapGraphData,
    )
    const kept = chains.find((c) => c.huts.length === 2)
    expect(kept).toBeDefined()
    expect(kept!.huts).toEqual([0, 1])
  })
})

describe('searchChains (car-loop shared-start overlap avoidance)', () => {
  const loopEdge = { fromIndex: 0, toIndex: 1, variant: 0, distanceM: 5000, ascentM: 200, descentM: 200, maxEleM: 2000, sacRank: 1, viaFerrata: false, roadM: 0, ungradedM: 0, inferredM: 0, snapM: 0, edgeId: 1 }
  const PREFIX_START: Record<number, number[]> = { 900: [555], 901: [555] } // near the shared start point, both directions

  function buildLoopGraphData(exitSharesNonExemptId: boolean): GraphData {
    const SORTED_START: Record<number, number[]> = {
      900: [555, 111],
      901: exitSharesNonExemptId ? [555, 111] : [555, 222],
    }
    return {
      hutEdges: { hutIds: ['A', 'B'], variantNames: { 0: 'FAST_ANY' }, records: [loopEdge] },
      approaches: {
        records: [{ hutIndex: 0, startId: 999, sourceType: SOURCE_TYPE_PARKING, variant: 0, accessUnknown: false, distanceM: 2000, ascentM: 100, descentM: 50, access: null, edgeId: 900 }],
        reverseIndex: {
          hut_to_starts: {
            1: [{ hut_id: 1, start_id: 999, source_type: SOURCE_TYPE_PARKING, variant: 0, distance_m: 2000, ascent_m: 50, descent_m: 100, edge_id: 901 }],
          },
          start_to_huts: {},
        },
      },
      hutEdgeIds: { getSortedIds: () => new Int32Array(0), getPrefixIds: () => new Int32Array(0), getSuffixIds: () => new Int32Array(0) },
      startEdgeIds: {
        getSortedIds: (edgeId) => Int32Array.from(SORTED_START[edgeId] ?? []),
        getPrefixIds: (edgeId) => Int32Array.from(PREFIX_START[edgeId] ?? []),
        getSuffixIds: () => new Int32Array(0),
      },
    }
  }

  it('keeps a car-mode loop that only shares the run near the common start point', () => {
    const { chains } = searchChains(
      { mode: 'car', legCountMin: 3, legCountMax: 3, ...generousConstraints },
      buildLoopGraphData(false),
    )
    const kept = chains.find((c) => c.huts.length === 2)
    expect(kept).toBeDefined()
    expect(kept!.startId).toBe(999)
    expect(kept!.exitStartId).toBe(999)
  })

  it('excludes a car-mode loop with a genuine overlap away from the shared start point', () => {
    const { chains, killCounters } = searchChains(
      { mode: 'car', legCountMin: 3, legCountMax: 3, ...generousConstraints },
      buildLoopGraphData(true),
    )
    expect(chains.some((c) => c.huts.length === 2)).toBe(false)
    expect(killCounters.trackOverlap).toBeGreaterThan(0)
  })
})

describe('searchChains (single-hut approach/exit trim)', () => {
  const graphDataSingleHutTrim: GraphData = {
    hutEdges: { hutIds: ['A'], variantNames: { 0: 'FAST_ANY' }, records: [] },
    approaches: {
      records: [{ hutIndex: 0, startId: 300, sourceType: SOURCE_TYPE_STATION, variant: 0, accessUnknown: false, distanceM: 2000, ascentM: 100, descentM: 50, access: null, edgeId: 950 }],
      reverseIndex: {
        hut_to_starts: {
          0: [{ hut_id: 0, start_id: 301, source_type: SOURCE_TYPE_STATION, variant: 0, distance_m: 2000, ascent_m: 50, descent_m: 100, edge_id: 951 }],
        },
        start_to_huts: {},
      },
    },
    hutEdgeIds: { getSortedIds: () => new Int32Array(0), getPrefixIds: () => new Int32Array(0), getSuffixIds: () => new Int32Array(0) },
    startEdgeIds: {
      getSortedIds: (edgeId) => Int32Array.from(({ 950: [321, 111], 951: [321, 222] } as Record<number, number[]>)[edgeId] ?? []),
      getPrefixIds: () => new Int32Array(0),
      getSuffixIds: (edgeId) => Int32Array.from(({ 950: [321], 951: [321] } as Record<number, number[]>)[edgeId] ?? []),
    },
  }

  it('trims the run shared out of a single hut between the approach and exit legs', () => {
    const { chains } = searchChains(
      { mode: 'transit', legCountMin: 2, legCountMax: 2, ...generousConstraints },
      graphDataSingleHutTrim,
    )
    const kept = chains.find((c) => c.huts.length === 1)
    expect(kept).toBeDefined()
    expect(kept!.startId).toBe(300)
    expect(kept!.exitStartId).toBe(301)
  })
})

describe('mode-gated source types (Section A fixes)', () => {
  // graphData's approach/exit are already station-type (see fixture comment above); this
  // parking-only variant is the negative case for the transit-seeding test below.
  const parkingGraphData: GraphData = {
    ...graphData,
    approaches: {
      records: [{ ...graphData.approaches.records[0], sourceType: 2 }],
      reverseIndex: {
        hut_to_starts: {
          2: [{ ...graphData.approaches.reverseIndex.hut_to_starts[2][0], source_type: 2 }],
        },
        start_to_huts: {},
      },
    },
  }

  it('transit mode seeds only from station-type approaches, rejecting a parking-only approach', () => {
    const { chains } = searchChains(
      { mode: 'transit', legCountMin: 3, legCountMax: 4, ...generousConstraints },
      parkingGraphData,
    )
    expect(chains.some((c) => c.huts.length === 3)).toBe(false)
  })

  it('transit mode finds the chain once approach and exit are both station-type', () => {
    const { chains } = searchChains(
      { mode: 'transit', legCountMin: 3, legCountMax: 4, ...generousConstraints },
      graphData,
    )
    const full = chains.find((c) => c.huts.length === 3)
    expect(full).toBeDefined()
    expect(full?.startId).toBe(100)
    expect(full?.exitStartId).toBe(200)
    // legs = [start->A, A->B, B->C, C->exit] = 4 entries for a 3-hut chain.
    expect(full?.legs).toHaveLength(4)
    expect(full?.legs[0]).toMatchObject({ edgeId: 9000, reversed: false })
    const summedDuration = full!.legs.reduce((sum, l) => sum + l.durationH, 0)
    expect(summedDuration).toBeCloseTo(full!.totalDurationH, 6)
  })

  it('car mode rejects a loop closure at a station even when the start id matches the entry', () => {
    const loopStationGraphData: GraphData = {
      ...graphData,
      approaches: {
        ...graphData.approaches,
        reverseIndex: {
          hut_to_starts: {
            2: [{ hut_id: 2, start_id: 100, source_type: SOURCE_TYPE_STATION, variant: 0, distance_m: 2000, ascent_m: 50, descent_m: 100, edge_id: 8001 }],
          },
          start_to_huts: {},
        },
      },
    }
    const { chains } = searchChains(
      { mode: 'car', legCountMin: 3, legCountMax: 4, ...generousConstraints },
      loopStationGraphData,
    )
    // start ids match (100 == 100) but both are SOURCE_TYPE_STATION, not SOURCE_TYPE_PARKING —
    // car must still reject.
    expect(chains.some((c) => c.huts.length === 3)).toBe(false)
  })
})

/**
 * Pre-pruning reference implementation (Task 12's fixed mode-gating, no dominance collapsing) —
 * exists ONLY in this test file, to prove Task 13's pruning never drops a distinct final result.
 * Do not import this into production code.
 */
function bruteForceSearchChains(query: Query, graphData: GraphData) {
  const {
    mode, legCountMin, legCountMax, sacCeiling, allowUngraded = false,
    maxLegTimeH, minLegTimeH = 0, legAscentCapM = Infinity, maxEleM = null, allowViaFerrata = true,
  } = query
  const constraints = { maxLegTimeH, minLegTimeH, legAscentCapM, maxEleM, allowViaFerrata }
  const killCounters = createKillCounters()
  const gateSourceType = mode === 'transit' ? SOURCE_TYPE_STATION : mode === 'car' ? SOURCE_TYPE_PARKING : null

  const variant = resolveVariant({ sacCeiling, allowUngraded }, graphData.hutEdges.variantNames)
  const adjacency = buildAdjacency(graphData.hutEdges, variant)
  const nightsMin = legCountMin - 1
  const nightsMax = legCountMax - 1

  interface State { path: number[]; startId: number; totalDurationH: number; totalAscentM: number; totalDescentM: number; totalDistanceM: number; legs: LegSummary[] }
  function legSummary(leg: { durationH: number; ascentM: number; descentM: number; distanceM: number; edgeId: number; reversed: boolean }): LegSummary {
    return { durationH: leg.durationH, ascentM: leg.ascentM, descentM: leg.descentM, distanceM: leg.distanceM, edgeId: leg.edgeId, reversed: leg.reversed }
  }
  let layer = new Map<number, State[]>()
  for (let h = 0; h < graphData.hutEdges.hutIds.length; h++) {
    for (const approachLeg of getApproachLegs(h, graphData.approaches)) {
      if (gateSourceType != null && approachLeg.sourceType !== gateSourceType) continue
      if (!legPasses(approachLeg, constraints, killCounters)) continue
      const state: State = { path: [h], startId: approachLeg.startId, totalDurationH: approachLeg.durationH, totalAscentM: approachLeg.ascentM, totalDescentM: approachLeg.descentM, totalDistanceM: approachLeg.distanceM, legs: [legSummary(approachLeg)] }
      if (!layer.has(h)) layer.set(h, [])
      layer.get(h)!.push(state)
    }
  }

  const finished: TourResult[] = []
  const collectFinished = (n: number) => {
    if (n < nightsMin) return
    for (const [h, states] of layer) {
      const exitLegs = getExitLegs(h, variant, graphData.approaches)
      for (const s of states) {
        for (const exitLeg of exitLegs) {
          if (mode === 'car' && exitLeg.startId !== s.startId) continue
          if (gateSourceType != null && exitLeg.sourceType !== gateSourceType) continue
          if (!legPasses(exitLeg, constraints, killCounters)) continue
          finished.push({ huts: [...s.path], startId: s.startId, exitStartId: exitLeg.startId, totalDurationH: s.totalDurationH + exitLeg.durationH, totalAscentM: s.totalAscentM + exitLeg.ascentM, totalDescentM: s.totalDescentM + exitLeg.descentM, totalDistanceM: s.totalDistanceM + exitLeg.distanceM, legs: [...s.legs, legSummary(exitLeg)] })
        }
      }
    }
  }

  collectFinished(1)
  for (let n = 1; n < nightsMax; n++) {
    const nextLayer = new Map<number, State[]>()
    for (const [h, states] of layer) {
      const legs = adjacency.get(h) || []
      for (const s of states) {
        for (const leg of legs) {
          const h2 = leg.toIndex
          if (s.path.includes(h2)) { killCounters.revisit++; continue }
          if (!legPasses(leg, constraints, killCounters)) continue
          const next: State = { path: [...s.path, h2], startId: s.startId, totalDurationH: s.totalDurationH + leg.durationH, totalAscentM: s.totalAscentM + leg.ascentM, totalDescentM: s.totalDescentM + leg.descentM, totalDistanceM: s.totalDistanceM + leg.distanceM, legs: [...s.legs, legSummary(leg)] }
          if (!nextLayer.has(h2)) nextLayer.set(h2, [])
          nextLayer.get(h2)!.push(next)
        }
      }
    }
    layer = nextLayer
    collectFinished(n + 1)
  }

  finished.sort((a, b) => a.totalDurationH - b.totalDurationH)
  return { chains: finished, killCounters }
}

function normalizeForComparison(chains: TourResult[]): string[] {
  const best = new Map<string, number>()
  for (const c of chains) {
    const key = `${[...c.huts].sort((a, b) => a - b).join(',')}|${c.startId}|${c.exitStartId}`
    const prev = best.get(key)
    if (prev === undefined || c.totalDurationH < prev) best.set(key, c.totalDurationH)
  }
  return [...best.entries()].map(([k, d]) => `${k}=${d.toFixed(4)}`).sort()
}

describe('dominance pruning (Section B) is exact', () => {
  // Diamond graph: A(seed)->B, A->C, B->C, B->D, C->D, all variant 0. A->B->C->D and A->C->B->D
  // both visit {A,B,C,D} and finish at D - exactly the case dominance pruning collapses.
  function edge(fromIndex: number, toIndex: number, distanceM: number) {
    return { fromIndex, toIndex, variant: 0, distanceM, ascentM: 100, descentM: 100, maxEleM: 2000, sacRank: 1, viaFerrata: false, roadM: 0, ungradedM: 0, inferredM: 0, snapM: 0, edgeId: fromIndex * 100 + toIndex }
  }
  const diamondGraph: GraphData = {
    hutEdgeIds: emptyHutEdgeIdsStub(),
    startEdgeIds: emptyHutEdgeIdsStub(),
    hutEdges: {
      hutIds: ['A', 'B', 'C', 'D'],
      variantNames: { 0: 'FAST_ANY' },
      records: [edge(0, 1, 3000), edge(0, 2, 4000), edge(1, 2, 2000), edge(1, 3, 3500), edge(2, 3, 3000)],
    },
    approaches: {
      records: [{ hutIndex: 0, startId: 100, sourceType: SOURCE_TYPE_STATION, variant: 0, accessUnknown: false, distanceM: 1000, ascentM: 50, descentM: 20, access: null, edgeId: 8000 }],
      reverseIndex: {
        hut_to_starts: {
          3: [{ hut_id: 3, start_id: 200, source_type: SOURCE_TYPE_STATION, variant: 0, distance_m: 1000, ascent_m: 20, descent_m: 50, edge_id: 8001 }],
        },
        start_to_huts: {},
      },
    },
  }
  const query: Query = { mode: 'transit', legCountMin: 1, legCountMax: 6, maxLegTimeH: 10, minLegTimeH: 0, legAscentCapM: 9999, maxEleM: null, allowViaFerrata: true }

  it('produces the same normalized (hut-set, start, exit, best-duration) results as an unpruned reference', () => {
    const pruned = searchChains(query, diamondGraph)
    const unpruned = bruteForceSearchChains(query, diamondGraph)
    expect(normalizeForComparison(pruned.chains)).toEqual(normalizeForComparison(unpruned.chains))
  })
})

describe('searchChains hut filtering', () => {
  it('excludes a hut from every position in a chain, including mid-route, when its index is not allowed', () => {
    const { chains } = searchChains(
      { mode: 'transit', legCountMin: 2, legCountMax: 4, ...generousConstraints, allowedHutIndices: new Set([0, 2]) },
      graphData,
    )
    for (const chain of chains) {
      expect(chain.huts).not.toContain(1)
    }
  })

  it('increments hutFiltered when the allow-set prunes a hut', () => {
    const { killCounters } = searchChains(
      { mode: 'transit', legCountMin: 2, legCountMax: 4, ...generousConstraints, allowedHutIndices: new Set([0, 2]) },
      graphData,
    )
    expect(killCounters.hutFiltered).toBeGreaterThan(0)
  })

  it('an undefined allowedHutIndices allows every hut, unchanged from before this feature', () => {
    const { chains } = searchChains(
      { mode: 'transit', legCountMin: 3, legCountMax: 4, ...generousConstraints },
      graphData,
    )
    expect(chains.some((c) => c.huts.length === 3)).toBe(true)
  })

  it('every returned chain has at least one hut night (huts.length >= 1), including at legCountMin = 1', () => {
    const { chains } = searchChains(
      { mode: 'transit', legCountMin: 1, legCountMax: 4, ...generousConstraints },
      graphData,
    )
    for (const chain of chains) {
      expect(chain.huts.length).toBeGreaterThanOrEqual(1)
    }
  })
})

describe('searchChains village mode', () => {
  const villageGraphData: GraphData = {
    ...graphData,
    approaches: {
      records: [
        { hutIndex: 0, startId: 300, sourceType: 3, variant: 0, accessUnknown: false, distanceM: 1500, ascentM: 80, descentM: 40, access: null, edgeId: 9100 },
      ],
      reverseIndex: {
        hut_to_starts: {
          2: [{ hut_id: 2, start_id: 400, source_type: 3, variant: 0, distance_m: 1500, ascent_m: 40, descent_m: 80, edge_id: 9101 }],
        },
        start_to_huts: {},
      },
    },
  }

  it('gates approach/exit legs to SOURCE_TYPE_PARTNER, like transit gates to stations', () => {
    const { chains } = searchChains(
      { mode: 'village', legCountMin: 3, legCountMax: 4, ...generousConstraints },
      villageGraphData,
    )
    const full = chains.find((c) => c.huts.length === 3)
    expect(full).toBeDefined()
    expect(full!.startId).toBe(300)
    expect(full!.exitStartId).toBe(400)
  })

  it('behaves like transit (open point-to-point), not like car (no same-start round-trip check)', () => {
    const { chains } = searchChains(
      { mode: 'village', legCountMin: 3, legCountMax: 4, ...generousConstraints },
      villageGraphData,
    )
    expect(chains.some((c) => c.startId !== c.exitStartId)).toBe(true)
  })
})

describe('searchChains availability pruning', () => {
  const availability = (ohrsIdByHutIndex: Map<number, string | null>, freeByOffset: Map<number, Set<string> | 'unknown'>) =>
    ({ ohrsIdByHutIndex, freeByOffset })

  it('rejects the whole chain when the seed hut has no free beds on night 1', () => {
    const { chains, killCounters } = searchChains(
      {
        mode: 'transit', legCountMin: 2, legCountMax: 4, ...generousConstraints,
        availability: availability(new Map([[0, 'ohrsA']]), new Map([[1, new Set<string>()]])),
      },
      graphData,
    )
    expect(chains).toHaveLength(0)
    expect(killCounters.availability).toBeGreaterThan(0)
  })

  it('a hut with ohrsHutId null (direct-booking-only) always passes, regardless of freeByOffset', () => {
    const { chains } = searchChains(
      {
        mode: 'transit', legCountMin: 3, legCountMax: 4, ...generousConstraints,
        availability: availability(new Map([[0, null]]), new Map([[1, new Set<string>()]])),
      },
      graphData,
    )
    expect(chains.some((c) => c.huts.length === 3)).toBe(true)
  })

  it("an 'unknown' offset always passes", () => {
    const { chains } = searchChains(
      {
        mode: 'transit', legCountMin: 3, legCountMax: 4, ...generousConstraints,
        availability: availability(new Map([[0, 'ohrsA']]), new Map<number, Set<string> | 'unknown'>([[1, 'unknown']])),
      },
      graphData,
    )
    expect(chains.some((c) => c.huts.length === 3)).toBe(true)
  })

  it('rejects an expansion hut with no free beds on its own night, without killing earlier huts', () => {
    const { chains, killCounters } = searchChains(
      {
        mode: 'transit', legCountMin: 2, legCountMax: 4, ...generousConstraints,
        availability: availability(
          new Map([[0, 'ohrsA'], [1, 'ohrsB']]),
          new Map<number, Set<string> | 'unknown'>([[1, new Set(['ohrsA'])], [2, new Set<string>()]]),
        ),
      },
      graphData,
    )
    expect(chains.some((c) => c.huts.includes(1))).toBe(false)
    expect(chains.some((c) => c.huts.length === 3)).toBe(false)
    expect(killCounters.availability).toBeGreaterThan(0)
  })

  it('is byte-for-byte identical to an unconstrained search when availability is absent', () => {
    const withoutAvailability = searchChains({ mode: 'transit', legCountMin: 2, legCountMax: 4, ...generousConstraints }, graphData)
    const withUndefinedAvailability = searchChains({ mode: 'transit', legCountMin: 2, legCountMax: 4, ...generousConstraints, availability: undefined }, graphData)
    expect(withUndefinedAvailability.chains).toEqual(withoutAvailability.chains)
  })
})
