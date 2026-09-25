import { SOURCE_TYPE_PARKING, SOURCE_TYPE_PARTNER, SOURCE_TYPE_STATION } from '../tourSearch/types.js'
import { buildOfficialTourViews } from '../tourSearch/officialTours.js'
import type { OfficialTourView } from '../tourSearch/officialTours.js'
import type { RawTour } from '../tourSearch/loadOfficialTours.js'
import type { TripGraph } from '@/tourSearch/types.js'
import type { HutClass } from './hutClass.js'
import { idFromOsmFeatureId } from './labels.js'
import type { StartPoint } from './types.js'

export interface HutOhrs {
  ohrsHutId: string | null
  tenantCode: number | null
}

export interface AppData {
  graph: TripGraph
  hutNameById: Map<number, string>
  hutCoordsById: Map<number, { lat: number; lng: number }>
  hutsByIndex: (HutClass | null)[]
  hutClassByIndex: Map<number, HutClass>
  hutOhrsByIndex: Map<number, HutOhrs>
  startById: Map<number, StartPoint>
  officialTours: OfficialTourView[]
}

interface BuildInput {
  graph: TripGraph
  huts: GeoJSON.FeatureCollection
  parking: GeoJSON.FeatureCollection
  stations: GeoJSON.FeatureCollection
  partner: GeoJSON.FeatureCollection
  tours: RawTour[]
}

function classOf(props: { hutType?: string; serviced?: boolean }): HutClass | null {
  if (props.hutType !== 'av' && props.hutType !== 'sonstige') return null
  return { operator: props.hutType, serviced: props.serviced ?? true }
}

export function buildAppData({ graph, huts, parking, stations, partner, tours }: BuildInput): AppData {
  const featureByGuid = new Map(huts.features.map((f) => [(f.properties as { id: string }).id, f]))
  const features = graph.hutEdges.hutIds.map((guid) => featureByGuid.get(guid) ?? null)

  const hutNameById = new Map<number, string>()
  const hutCoordsById = new Map<number, { lat: number; lng: number }>()
  const hutOhrsByIndex = new Map<number, HutOhrs>()
  const hutsByIndex = features.map((f, i) => {
    if (!f) return null
    const props = f.properties as { name: string; hutType?: string; serviced?: boolean; ohrsHutId?: string | null; tenantCode?: number | null }
    const [lng, lat] = (f.geometry as GeoJSON.Point).coordinates
    hutNameById.set(i, props.name)
    hutCoordsById.set(i, { lat, lng })
    hutOhrsByIndex.set(i, { ohrsHutId: props.ohrsHutId ?? null, tenantCode: props.tenantCode ?? null })
    return classOf(props)
  })
  const hutClassByIndex = new Map(
    hutsByIndex.map((c, i) => [i, c] as const).filter((entry): entry is [number, HutClass] => entry[1] !== null),
  )

  const startById = new Map<number, StartPoint>()
  const addOsm = (fc: GeoJSON.FeatureCollection, sourceType: number) => {
    for (const f of fc.features) {
      const id = idFromOsmFeatureId(f.id as string | number)
      if (id === null) continue
      const [lng, lat] = (f.geometry as GeoJSON.Point).coordinates
      startById.set(id, { name: (f.properties as { name?: string })?.name ?? null, sourceType, lat, lng })
    }
  }
  addOsm(stations, SOURCE_TYPE_STATION)
  addOsm(parking, SOURCE_TYPE_PARKING)
  // Partner points carry no top-level f.id (the ArcGIS OBJECTID lives in properties.id); running it
  // through idFromOsmFeatureId would reduce Number("") to 0 and collapse every point.
  for (const f of partner.features) {
    const id = (f.properties as { id?: number })?.id
    if (id == null) continue
    const [lng, lat] = (f.geometry as GeoJSON.Point).coordinates
    startById.set(id, { name: (f.properties as { name?: string })?.name ?? null, sourceType: SOURCE_TYPE_PARTNER, lat, lng })
  }

  return {
    graph, hutNameById, hutCoordsById, hutsByIndex, hutClassByIndex, hutOhrsByIndex, startById,
    officialTours: buildOfficialTourViews(tours),
  }
}
