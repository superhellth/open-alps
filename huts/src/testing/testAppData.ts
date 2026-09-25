import { makeTripGraph } from './tripTestGraph.js'
import type { AppData } from '@/data/buildAppData.js'

/** Huts A B C D E X of makeTripGraph with names, coordinates and OHRS ids for D ('103') and E ('104') only. */
export function makeTestAppData(): AppData {
  const graph = makeTripGraph()
  const names = ['Hütte A', 'Hütte B', 'Hütte C', 'Hütte D', 'Hütte E', 'Hütte X']
  const hutNameById = new Map(names.map((n, i) => [i, n] as const))
  const hutCoordsById = new Map(names.map((_, i) => [i, { lat: 47.3 + i * 0.01, lng: 12.0 + i * 0.01 }] as const))
  const hutsByIndex = names.map(() => ({ operator: 'av' as const, serviced: true }))
  return {
    graph, hutNameById, hutCoordsById, hutsByIndex,
    hutClassByIndex: new Map(hutsByIndex.map((c, i) => [i, c] as const)),
    hutOhrsByIndex: new Map(names.map((_, i) => [i, i === 3 || i === 4 ? { ohrsHutId: String(100 + i), tenantCode: 8 } : { ohrsHutId: null, tenantCode: null }] as const)),
    startById: new Map([
      [100, { name: 'Bahnhof X', sourceType: 1, lat: 47.29, lng: 12.0 }],
      [101, { name: 'Bahnhof Y', sourceType: 1, lat: 47.28, lng: 12.0 }],
    ]),
    officialTours: [],
  }
}
