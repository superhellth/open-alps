import { readColumns } from './binaryColumns.js'

/** @typedef {{ hutIndex:number, startId:number, sourceType:number, accessUnknown:boolean,
 *  distanceM:number, ascentM:number, descentM:number, access:string|null }} ApproachRecord */

export async function loadApproachesData(baseUrl = '/data') {
  const manifest = await (await fetch(`${baseUrl}/approaches.json`)).json()
  const buffer = await (await fetch(`${baseUrl}/approaches.bin`)).arrayBuffer()
  const c = readColumns(buffer, manifest)

  const records = new Array(manifest.rows)
  for (let i = 0; i < manifest.rows; i++) {
    records[i] = {
      hutIndex: c.hut_id[i], startId: c.start_id[i], sourceType: c.source_type[i],
      accessUnknown: c.access_unknown[i] === 1, distanceM: c.distance_m[i],
      ascentM: c.ascent_m[i], descentM: c.descent_m[i],
      access: manifest.access_values ? manifest.access_values[i] : null,
    }
  }
  return { records, reverseIndex: manifest.reverse_index }
}
