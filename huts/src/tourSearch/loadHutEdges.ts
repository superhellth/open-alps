import { readColumns } from './binaryColumns.js'
import type { HutEdgesData, HutEdgeRecord } from './types.js'

interface HutEdgesManifest {
  rows: number
  columns: Record<string, { dtype: string; offset: number }>
  hut_ids: string[]
  variants: Record<string, string>
}

export async function loadHutEdgesData(baseUrl = '/data'): Promise<HutEdgesData> {
  const manifest: HutEdgesManifest = await (await fetch(`${baseUrl}/hut-edge-payload.json`)).json()
  const buffer = await (await fetch(`${baseUrl}/hut-edge-payload.bin`)).arrayBuffer()
  const c = readColumns(buffer, manifest as unknown as Parameters<typeof readColumns>[1])

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
