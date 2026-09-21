import type { ApproachRecord, HutEdgeRecord, ReverseIndexEntry } from './types.js'
import type { TripGraph } from './tripLegs.js'

// Huts: A0 B1 C2 D3 E4 X5. Hut-hut edges (variant 0): A-B, B-C, C-D, A-C, D-E, A-X, X-C.
// Start 100 / 101 are stations, 200 / 201 parking. Approaches to A and D (+ E from 100), exits from A, D, E.
export function makeTripGraph(): TripGraph {
  const edge = (fromIndex: number, toIndex: number, distanceM: number, ascentM: number, descentM: number, edgeId: number): HutEdgeRecord => ({
    fromIndex, toIndex, variant: 0, distanceM, ascentM, descentM, maxEleM: 2000, sacRank: 2,
    viaFerrata: false, roadM: 0, ungradedM: 0, inferredM: 0, snapM: 0, edgeId,
  })
  const approach = (hutIndex: number, startId: number, sourceType: 1 | 2, distanceM: number, edgeId: number): ApproachRecord => ({
    hutIndex, startId, sourceType, variant: 0, accessUnknown: false, distanceM, ascentM: 400, descentM: 50, access: null, edgeId,
  })
  const exitEntry = (hut_id: number, start_id: number, source_type: 1 | 2, distance_m: number, edge_id: number): ReverseIndexEntry => ({
    hut_id, start_id, source_type, variant: 0, distance_m, ascent_m: 50, descent_m: 400, edge_id,
  })
  return {
    hutEdges: {
      hutIds: ['{A}', '{B}', '{C}', '{D}', '{E}', '{X}'],
      variantNames: { 0: 'FAST_ANY' },
      records: [
        edge(0, 1, 8000, 700, 300, 0), edge(1, 2, 9000, 600, 500, 1), edge(2, 3, 12000, 900, 400, 2),
        edge(0, 2, 15000, 900, 900, 3), edge(3, 4, 7000, 300, 600, 4),
        edge(0, 5, 6000, 500, 200, 5), edge(5, 2, 6500, 400, 400, 6),
      ],
    },
    approaches: {
      records: [
        approach(0, 100, 1, 6000, 0), approach(0, 101, 1, 9000, 1), approach(3, 100, 1, 5000, 2),
        approach(4, 100, 1, 4000, 3), approach(0, 200, 2, 4000, 4), approach(0, 201, 2, 7000, 5),
        approach(3, 200, 2, 5000, 6), approach(3, 201, 2, 3000, 7),
      ],
      reverseIndex: {
        start_to_huts: {},
        hut_to_starts: {
          '0': [exitEntry(0, 100, 1, 6000, 0), exitEntry(0, 200, 2, 4000, 4), exitEntry(0, 201, 2, 7000, 5)],
          '3': [exitEntry(3, 100, 1, 5000, 2), exitEntry(3, 101, 1, 7000, 8), exitEntry(3, 200, 2, 5000, 6), exitEntry(3, 201, 2, 3000, 7)],
          '4': [exitEntry(4, 100, 1, 4000, 3)],
        },
      },
    },
  }
}
