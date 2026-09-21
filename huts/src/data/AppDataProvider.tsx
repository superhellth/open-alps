import { createContext, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { loadTripGraph } from '../tourSearch/index.js'
import { loadOfficialTours } from '../tourSearch/loadOfficialTours.js'
import { buildAppData } from './buildAppData.js'
import type { AppData } from './buildAppData.js'

export type AppDataState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; data: AppData }

const HUTS_URL = '/data/huts.geojson'
const PARKING_URL = '/data/parking.geojson'
const STATIONS_URL = '/data/stations.geojson'
const PARTNER_URL = '/data/partner_betriebe.geojson'

const emptyCollection = (): GeoJSON.FeatureCollection => ({ type: 'FeatureCollection', features: [] })

export async function loadAppData(): Promise<AppData> {
  const json = (url: string) => fetch(url).then((r) => r.json() as Promise<GeoJSON.FeatureCollection>)
  const [graph, huts, parking, stations, partner, tours] = await Promise.all([
    loadTripGraph(),
    json(HUTS_URL),
    json(PARKING_URL),
    json(STATIONS_URL),
    json(PARTNER_URL).catch(emptyCollection), // partner businesses are best-effort: a 404 degrades to none
    loadOfficialTours(),
  ])
  return buildAppData({ graph, huts, parking, stations, partner, tours })
}

const AppDataContext = createContext<AppDataState>({ status: 'loading' })

export function AppDataProvider({ children, load = loadAppData }: { children: ReactNode; load?: () => Promise<AppData> }) {
  const [state, setState] = useState<AppDataState>({ status: 'loading' })
  useEffect(() => {
    let cancelled = false
    load().then(
      (data) => { if (!cancelled) setState({ status: 'ready', data }) },
      (e: Error) => { if (!cancelled) setState({ status: 'error', message: e.message }) },
    )
    return () => { cancelled = true }
  }, [load])
  return <AppDataContext.Provider value={state}>{children}</AppDataContext.Provider>
}

export function useAppData(): AppDataState {
  return useContext(AppDataContext)
}
