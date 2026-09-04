import { readColumns, type ColumnManifest } from './binaryColumns.js'

export interface TourEdgeRecord {
  distanceM: number
  ascentM: number
  descentM: number
  maxEleM: number
  sacRank: number
  viaFerrata: boolean
  edgeId: number
}

export async function loadTourEdgesData(baseUrl = '/data'): Promise<Map<string, TourEdgeRecord>> {
  const manifest: ColumnManifest = await (await fetch(`${baseUrl}/tour-edge-payload.json`)).json()
  const buffer = await (await fetch(`${baseUrl}/tour-edge-payload.bin`)).arrayBuffer()
  const c = readColumns(buffer, manifest)

  const records = new Map<string, TourEdgeRecord>()
  for (let i = 0; i < manifest.rows; i++) {
    records.set(`${c.tour_id[i]}:${c.leg_index[i]}`, {
      distanceM: c.distance_m[i], ascentM: c.ascent_m[i], descentM: c.descent_m[i],
      maxEleM: c.max_ele_m[i], sacRank: c.sac_rank[i], viaFerrata: c.via_ferrata[i] === 1,
      edgeId: i,
    })
  }
  return records
}
