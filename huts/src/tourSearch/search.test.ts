import { describe, it, expect } from 'vitest'
import { searchChains } from './search.js'
import { SOURCE_TYPE_STATION } from './types.js'
import type { GraphData } from './types.js'

// A tiny 3-hut chain: start1 -> A -> B -> C -> start2, all within budget, all FAST_ANY.
function edge(fromIndex: number, toIndex: number, distanceM: number) {
  return { fromIndex, toIndex, variant: 0, distanceM, ascentM: 200, descentM: 200, maxEleM: 2000, sacRank: 1, viaFerrata: false, roadM: 0, ungradedM: 0, inferredM: 0, snapM: 0 }
}

// This fixture's approach/exit are station-type (SOURCE_TYPE_STATION = 1), matching the
// "(transit)" describe block below; the "(car)" describe block overrides source types to
// SOURCE_TYPE_PARKING (2) on its own graph copies where mode-gating requires it.
const graphData: GraphData = {
  hutEdges: {
    hutIds: ['A', 'B', 'C'],
    variantNames: { 0: 'FAST_ANY' },
    records: [edge(0, 1, 5000), edge(1, 2, 5000)],
  },
  approaches: {
    records: [
      { hutIndex: 0, startId: 100, sourceType: 1, accessUnknown: false, distanceM: 2000, ascentM: 100, descentM: 50, access: null },
    ],
    reverseIndex: {
      hut_to_starts: {
        2: [{ hut_id: 2, start_id: 200, source_type: 1, variant: 0, distance_m: 2000, ascent_m: 50, descent_m: 100 }],
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
            2: [{ hut_id: 2, start_id: 100, source_type: 2, variant: 0, distance_m: 2000, ascent_m: 50, descent_m: 100 }],
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
            2: [{ hut_id: 2, start_id: 100, source_type: SOURCE_TYPE_STATION, variant: 0, distance_m: 2000, ascent_m: 50, descent_m: 100 }],
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
