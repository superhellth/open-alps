import { describe, it } from 'vitest'
import { loadGraphDataFromDisk } from '@/testing/realDataFromDisk.js'
import { findTours } from './index.js'
import type { Query } from './types.js'

const enabled = process.env.MEASURE_SEARCH === '1'

const mb = (n: number) => `${(n / 1024 / 1024).toFixed(0)} MB`

describe.skipIf(!enabled)('whole-graph search measurements (MEASURE_SEARCH=1)', () => {
  it('reports load memory and search time by legCountMax', () => {
    const t0 = performance.now()
    const graph = loadGraphDataFromDisk({ withEdgeIds: true })
    const mem = process.memoryUsage()
    console.log(`load ${(performance.now() - t0).toFixed(0)} ms, heap ${mb(mem.heapUsed)}, arrayBuffers ${mb(mem.arrayBuffers)}`)

    const base = {
      mode: 'transit' as const, legCountMin: 2, sacCeiling: 3, allowUngraded: true,
      legAscentCapM: Infinity, maxEleM: null, allowViaFerrata: true,
    }
    const profiles: Record<string, Pick<Query, 'minLegTimeH' | 'maxLegTimeH'>> = {
      default: { minLegTimeH: 4, maxLegTimeH: 8 },
      permissive: { minLegTimeH: 0, maxLegTimeH: 8 },
    }
    for (const [name, times] of Object.entries(profiles)) {
      for (const legCountMax of [3, 4, 5, 6, 7]) {
        const start = performance.now()
        const { chains } = findTours({ ...base, ...times, legCountMax }, graph)
        const ms = performance.now() - start
        console.log(`${name} legCountMax=${legCountMax}: ${ms.toFixed(0)} ms, ${chains.length} chains`)
        if (ms > 60_000) break
      }
    }
  }, 900_000)
})
