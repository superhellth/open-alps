export type TourEndpointType = 'hut' | 'station' | 'parking' | 'partner_betrieb'

export interface RawTourEndpoint {
  type: TourEndpointType
  id: number
}

export interface RawTourLeg {
  legIndex: number
  edgeId: number
  distanceM: number
  ascentM: number
  descentM: number
  durationS: number
  maxEleM: number
  from: RawTourEndpoint
  to: RawTourEndpoint
  /** `[lat, lng]` at 25/50/75 % of the leg in walking order. */
  anchors?: [number, number][]
}

export interface RawTour {
  tourId: number
  name: string
  numDays: number
  legs: RawTourLeg[]
}

export async function loadOfficialTours(baseUrl = '/data'): Promise<RawTour[]> {
  return (await fetch(`${baseUrl}/tours.json`)).json() as Promise<RawTour[]>
}
