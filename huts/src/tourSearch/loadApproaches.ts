import { readAnchorOffsets } from './anchors.js'
import { readColumns } from './binaryColumns.js'
import type { ApproachesData, ApproachRecord, ExitAnchor } from './types.js'

export interface ApproachesManifest {
  rows: number
  columns: Record<string, { dtype: string; offset: number }>
  access_values?: (string | null)[]
  reverse_index: ApproachesData['reverseIndex']
  exit_anchors?: { rows: number; columns: Record<string, { dtype: string; offset: number }> }
}

/** The exit-anchor side table, sharing the buffer of the approach columns; empty when the manifest lists none. */
export function readExitAnchors(buffer: ArrayBuffer, manifest: ApproachesManifest): Map<number, ExitAnchor> {
  const out = new Map<number, ExitAnchor>()
  if (!manifest.exit_anchors) return out
  const c = readColumns(buffer, manifest.exit_anchors as unknown as Parameters<typeof readColumns>[1])
  for (let i = 0; i < manifest.exit_anchors.rows; i++) {
    const anchorOffsets = readAnchorOffsets(c, i)
    if (anchorOffsets) out.set(c.edge_id[i], { hutIndex: c.hut_id[i], anchorOffsets })
  }
  return out
}

export async function loadApproachesData(baseUrl = '/data'): Promise<ApproachesData> {
  const manifest: ApproachesManifest = await (await fetch(`${baseUrl}/approaches.json`)).json()
  const buffer = await (await fetch(`${baseUrl}/approaches.bin`)).arrayBuffer()
  const c = readColumns(buffer, manifest as unknown as Parameters<typeof readColumns>[1])

  const records = new Array<ApproachRecord>(manifest.rows)
  for (let i = 0; i < manifest.rows; i++) {
    records[i] = {
      hutIndex: c.hut_id[i], startId: c.start_id[i], sourceType: c.source_type[i] as ApproachRecord['sourceType'],
      variant: c.variant[i],
      accessUnknown: c.access_unknown[i] === 1, distanceM: c.distance_m[i],
      ascentM: c.ascent_m[i], descentM: c.descent_m[i],
      access: manifest.access_values ? manifest.access_values[i] : null,
      edgeId: c.edge_id[i], anchorOffsets: readAnchorOffsets(c, i),
    }
  }
  return { records, exitAnchors: readExitAnchors(buffer, manifest), reverseIndex: manifest.reverse_index }
}
