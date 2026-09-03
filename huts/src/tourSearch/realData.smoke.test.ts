import { describe, it, expect, beforeAll } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { readColumns } from './binaryColumns.js'
import { buildAdjacency } from './adjacency.js'
import { resolveVariant } from './resolveVariant.js'
import { findTours } from './index.js'
import type { ApproachesData, ApproachRecord, GraphData, HutEdgeRecord, HutEdgesData } from './types.js'

const DATA_DIR = fileURLToPath(new URL('../../public/data/', import.meta.url))

function loadHutEdgesFromDisk(): HutEdgesData {
  const manifest = JSON.parse(readFileSync(`${DATA_DIR}hut-edge-payload.json`, 'utf-8'))
  const buffer = readFileSync(`${DATA_DIR}hut-edge-payload.bin`).buffer as ArrayBuffer
  const c = readColumns(buffer, manifest)
  const records = new Array<HutEdgeRecord>(manifest.rows)
  for (let i = 0; i < manifest.rows; i++) {
    records[i] = {
      fromIndex: c.from_id[i], toIndex: c.to_id[i], variant: c.variant[i],
      distanceM: c.distance_m[i], ascentM: c.ascent_m[i], descentM: c.descent_m[i],
      maxEleM: c.max_ele_m[i], sacRank: c.sac_rank[i], viaFerrata: c.via_ferrata[i] === 1,
      roadM: c.road_m[i], ungradedM: c.ungraded_m[i], inferredM: c.inferred_m[i], snapM: c.snap_m[i],
      edgeId: i,
    }
  }
  return { hutIds: manifest.hut_ids, variantNames: manifest.variants, records }
}

function loadApproachesFromDisk(): ApproachesData {
  const manifest = JSON.parse(readFileSync(`${DATA_DIR}approaches.json`, 'utf-8'))
  const buffer = readFileSync(`${DATA_DIR}approaches.bin`).buffer as ArrayBuffer
  const c = readColumns(buffer, manifest)
  const records = new Array<ApproachRecord>(manifest.rows)
  for (let i = 0; i < manifest.rows; i++) {
    records[i] = {
      hutIndex: c.hut_id[i], startId: c.start_id[i], sourceType: c.source_type[i] as ApproachRecord['sourceType'],
      variant: c.variant[i],
      accessUnknown: c.access_unknown[i] === 1, distanceM: c.distance_m[i],
      ascentM: c.ascent_m[i], descentM: c.descent_m[i],
      access: manifest.access_values ? manifest.access_values[i] : null,
      // approaches.bin predating this plan's Task 2 has no edge_id column - guard until
      // huts/public/data/ is rebuilt by a (separately gated) doit run.
      edgeId: c.edge_id ? c.edge_id[i] : -1,
    }
  }
  return { records, reverseIndex: manifest.reverse_index }
}

describe('real shipped payload (huts/public/data)', () => {
  let graphData: GraphData

  beforeAll(() => {
    // hutEdgeIds is a stub until Task 12 (docs/superpowers/plans/
    // 2026-08-29-avoid-overlapping-tracks-plan.md) regenerates huts/public/data/hut-edge-ids.*
    // via a confirmed pipeline run and wires a real loadHutEdgeIdsFromDisk() here.
    graphData = {
      hutEdges: loadHutEdgesFromDisk(), approaches: loadApproachesFromDisk(),
      hutEdgeIds: {
        getSortedIds: () => new Int32Array(0),
        getPrefixIds: () => new Int32Array(0),
        getSuffixIds: () => new Int32Array(0),
      },
    }
  })

  it('resolves every difficulty ceiling to a variant the payload actually has', () => {
    for (const query of [{ sacCeiling: 2 }, { sacCeiling: 3, allowUngraded: false }, { sacCeiling: 3, allowUngraded: true }, {}]) {
      const variant = resolveVariant(query, graphData.hutEdges.variantNames)
      expect(graphData.hutEdges.variantNames[variant]).toBeDefined()
    }
  })

  it('builds adjacency for every variant without throwing, and every hut in it is a valid index', () => {
    for (const variantId of Object.keys(graphData.hutEdges.variantNames)) {
      const adjacency = buildAdjacency(graphData.hutEdges, Number(variantId))
      for (const [hutIndex, legs] of adjacency) {
        expect(hutIndex).toBeGreaterThanOrEqual(0)
        expect(hutIndex).toBeLessThan(graphData.hutEdges.hutIds.length)
        for (const leg of legs) {
          expect(leg.toIndex).toBeGreaterThanOrEqual(0)
          expect(leg.toIndex).toBeLessThan(graphData.hutEdges.hutIds.length)
        }
      }
    }
  })

  it('every constrained-row (FAST_T2/FAST_T3) edge has zero ungraded metres, matching the shipped guarantee', () => {
    const idByName: Record<string, number> = {}
    for (const [id, name] of Object.entries(graphData.hutEdges.variantNames)) idByName[name] = Number(id)
    const constrained = graphData.hutEdges.records.filter(
      (r) => r.variant === idByName.FAST_T2 || r.variant === idByName.FAST_T3,
    )
    expect(constrained.length).toBeGreaterThan(0)
    for (const r of constrained) expect(r.ungradedM).toBe(0)
  })

  it('an unanchored transit search with a generous budget runs end to end and returns well-formed chains', () => {
    const { chains } = findTours(
      {
        mode: 'transit', legCountMin: 2, legCountMax: 4,
        maxLegTimeH: 8, minLegTimeH: 0, legAscentCapM: 2000, allowViaFerrata: true,
        sacCeiling: 3, allowUngraded: true,
      },
      graphData,
    )
    for (const chain of chains) {
      expect(chain.huts.length).toBeGreaterThanOrEqual(1)
      expect(new Set(chain.huts).size).toBe(chain.huts.length) // no revisits
      expect(chain.totalDurationH).toBeGreaterThan(0)
    }
  })

  it('an unanchored transit search stays usable up to legCountMax 6 (Section B target, revised)', () => {
    // Dominance pruning (this task) is exact and removes redundant-path duplication, but on the
    // real shipped graph (956 huts, avg out-degree ~10, ~2100 approach seeds) with permissive
    // constraints the number of *distinct* (hut, startId, visitedSet) states still grows ~7-10x
    // per leg: measured 4->0.2s, 5->1.4s, 6->9.8s, 7->101s on this machine. legCountMax 14 (the
    // plan's original target) is not reachable by exact search alone - it OOMs. legCountMax 6 is
    // the revised, measured-tractable UI ceiling (see TourSearchPage's slider max, Task 20).
    const start = performance.now()
    const { chains } = findTours(
      {
        mode: 'transit', legCountMin: 2, legCountMax: 6,
        maxLegTimeH: 8, minLegTimeH: 0, legAscentCapM: 2000, allowViaFerrata: true,
        sacCeiling: 3, allowUngraded: true,
      },
      graphData,
    )
    const elapsedMs = performance.now() - start
    console.log(`legCountMax=6 search took ${elapsedMs.toFixed(0)}ms, ${chains.length} chains`)
    for (const chain of chains) {
      expect(new Set(chain.huts).size).toBe(chain.huts.length)
    }
  }, 30000)
})
