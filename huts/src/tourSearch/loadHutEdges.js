import { readColumns } from './binaryColumns.js'

/** @typedef {{ fromIndex:number, toIndex:number, variant:number, distanceM:number, ascentM:number,
 *  descentM:number, maxEleM:number, sacRank:number, viaFerrata:boolean, roadM:number,
 *  ungradedM:number, inferredM:number, snapM:number }} HutEdgeRecord */

export async function loadHutEdgesData(baseUrl = '/data') {
  const manifest = await (await fetch(`${baseUrl}/hut-edge-payload.json`)).json()
  const buffer = await (await fetch(`${baseUrl}/hut-edge-payload.bin`)).arrayBuffer()
  const c = readColumns(buffer, manifest)

  const records = new Array(manifest.rows)
  for (let i = 0; i < manifest.rows; i++) {
    records[i] = {
      fromIndex: c.from_id[i], toIndex: c.to_id[i], variant: c.variant[i],
      distanceM: c.distance_m[i], ascentM: c.ascent_m[i], descentM: c.descent_m[i],
      maxEleM: c.max_ele_m[i], sacRank: c.sac_rank[i], viaFerrata: c.via_ferrata[i] === 1,
      roadM: c.road_m[i], ungradedM: c.ungraded_m[i], inferredM: c.inferred_m[i], snapM: c.snap_m[i],
    }
  }
  return { hutIds: manifest.hut_ids, variantNames: manifest.variants, records }
}
