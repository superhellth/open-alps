export type TourEndpointType = 'hut' | 'station' | 'parking' | 'partner_betrieb'

export interface RawTourEndpoint {
  type: TourEndpointType
  id: number
}

export interface RawTourLeg {
  legIndex: number
  from: RawTourEndpoint | null
  to: RawTourEndpoint | null
}

export interface RawTour {
  tourId: number
  name: string
  legs: RawTourLeg[]
}

export async function loadOfficialTours(baseUrl = '/data'): Promise<RawTour[]> {
  return (await fetch(`${baseUrl}/tours.json`)).json() as Promise<RawTour[]>
}
