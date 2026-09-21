import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { readColumns } from './binaryColumns.js'
import { buildEdgeIdsData } from './loadHutEdgeIds.js'
import type { HutEdgeIdsManifest } from './loadHutEdgeIds.js'
import type { ApproachesData, ApproachRecord, GraphData, HutEdgeIdsData, HutEdgeRecord, HutEdgesData } from './types.js'

export const DATA_DIR = fileURLToPath(new URL('../../public/data/', import.meta.url))

function readArrayBuffer(path: string): ArrayBuffer {
  const buf = readFileSync(path)
  if (buf.byteOffset === 0 && buf.byteLength === buf.buffer.byteLength) return buf.buffer as ArrayBuffer
  return buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength) as ArrayBuffer
}

export function loadHutEdgesFromDisk(): HutEdgesData {
  const manifest = JSON.parse(readFileSync(`${DATA_DIR}hut-edge-payload.json`, 'utf-8'))
  const buffer = readArrayBuffer(`${DATA_DIR}hut-edge-payload.bin`)
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

export function loadApproachesFromDisk(): ApproachesData {
  const manifest = JSON.parse(readFileSync(`${DATA_DIR}approaches.json`, 'utf-8'))
  const buffer = readArrayBuffer(`${DATA_DIR}approaches.bin`)
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

const EMPTY_IDS: HutEdgeIdsData = {
  getSortedIds: () => new Int32Array(0),
  getPrefixIds: () => new Int32Array(0),
  getSuffixIds: () => new Int32Array(0),
}

function loadEdgeIdsFromDisk(basename: string): HutEdgeIdsData {
  const manifest = JSON.parse(readFileSync(`${DATA_DIR}${basename}.json`, 'utf-8')) as HutEdgeIdsManifest
  return buildEdgeIdsData(manifest, readArrayBuffer(`${DATA_DIR}${basename}.bin`))
}

export function loadGraphDataFromDisk({ withEdgeIds }: { withEdgeIds: boolean }): GraphData {
  return {
    hutEdges: loadHutEdgesFromDisk(),
    approaches: loadApproachesFromDisk(),
    hutEdgeIds: withEdgeIds ? loadEdgeIdsFromDisk('hut-edge-ids') : EMPTY_IDS,
    startEdgeIds: withEdgeIds ? loadEdgeIdsFromDisk('start-edge-ids') : EMPTY_IDS,
  }
}
