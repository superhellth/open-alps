import { decodeAnchors } from './anchors.js'
import type { LatLng } from './anchors.js'
import type { GeometryLayer } from './loadLegGeometry.js'
import type { OfficialTourView } from './officialTours.js'
import type { ApproachesData, HutEdgesData } from './types.js'

/** Anchors of one leg's edge in its stored direction; null when none were shipped for it. */
export type LegAnchorLookup = (layer: GeometryLayer, edgeId: number) => LatLng[] | null

export function createLegAnchorLookup({ hutEdges, approaches, hutCoordsById, officialTours }: {
  hutEdges: HutEdgesData
  approaches: ApproachesData
  hutCoordsById: ReadonlyMap<number, LatLng>
  officialTours: readonly OfficialTourView[]
}): LegAnchorLookup {
  const approachByEdge = new Map(approaches.records.map((r) => [r.edgeId, r]))
  const officialByEdge = new Map(officialTours.flatMap((t) => t.legs.map((l) => [l.edgeId, l.anchors ?? null] as const)))
  const decode = (offsets: number[] | null | undefined, hutIndex: number | undefined): LatLng[] | null => {
    const ref = hutIndex === undefined ? undefined : hutCoordsById.get(hutIndex)
    return offsets && ref ? decodeAnchors(offsets, ref) : null
  }
  return (layer, edgeId) => {
    if (edgeId < 0) return null
    if (layer === 'hut_edges') {
      const r = hutEdges.records[edgeId]
      return decode(r?.anchorOffsets, r?.fromIndex)
    }
    if (layer === 'start_edges') {
      const r = approachByEdge.get(edgeId)
      return decode(r?.anchorOffsets, r?.hutIndex)
    }
    return officialByEdge.get(edgeId) ?? null
  }
}
