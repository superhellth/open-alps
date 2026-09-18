export interface LonLat {
  lon: number
  lat: number
}

export type HubType = 'hut' | 'station' | 'parking' | 'partner_betrieb'

export interface Hub {
  id: number
  type: HubType
  lon: number
  lat: number
  name: string
}
