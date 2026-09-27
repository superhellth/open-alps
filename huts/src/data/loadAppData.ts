import { loadTripGraph } from '../tourSearch/index.js'
import { buildAppData } from './buildAppData.js'
import type { AppData } from './buildAppData.js'

const HUTS_URL = '/data/huts.geojson'
const PARKING_URL = '/data/parking.geojson'
const STATIONS_URL = '/data/stations.geojson'
const PARTNER_URL = '/data/partner_betriebe.geojson'

const emptyCollection = (): GeoJSON.FeatureCollection => ({ type: 'FeatureCollection', features: [] })

export async function loadAppData(): Promise<AppData> {
  const json = (url: string) => fetch(url).then((r) => r.json() as Promise<GeoJSON.FeatureCollection>)
  const [graph, huts, parking, stations, partner] = await Promise.all([
    loadTripGraph(),
    json(HUTS_URL),
    json(PARKING_URL),
    json(STATIONS_URL),
    json(PARTNER_URL).catch(emptyCollection), // partner businesses are best-effort: a 404 degrades to none
  ])
  return buildAppData({ graph, huts, parking, stations, partner })
}
