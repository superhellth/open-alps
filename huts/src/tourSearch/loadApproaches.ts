import { readColumns } from './binaryColumns.js'
import type { ApproachesData, ApproachRecord } from './types.js'

interface ApproachesManifest {
  rows: number
  columns: Record<string, { dtype: string; offset: number }>
  access_values?: (string | null)[]
  reverse_index: ApproachesData['reverseIndex']
}

export async function loadApproachesData(baseUrl = '/data'): Promise<ApproachesData> {
  const manifest: ApproachesManifest = await (await fetch(`${baseUrl}/approaches.json`)).json()
  const buffer = await (await fetch(`${baseUrl}/approaches.bin`)).arrayBuffer()
  const c = readColumns(buffer, manifest as unknown as Parameters<typeof readColumns>[1])

  const records = new Array<ApproachRecord>(manifest.rows)
  for (let i = 0; i < manifest.rows; i++) {
    records[i] = {
      hutIndex: c.hut_id[i], startId: c.start_id[i], sourceType: c.source_type[i] as ApproachRecord['sourceType'],
      accessUnknown: c.access_unknown[i] === 1, distanceM: c.distance_m[i],
      ascentM: c.ascent_m[i], descentM: c.descent_m[i],
      access: manifest.access_values ? manifest.access_values[i] : null,
      edgeId: c.edge_id[i],
    }
  }
  return { records, reverseIndex: manifest.reverse_index }
}
