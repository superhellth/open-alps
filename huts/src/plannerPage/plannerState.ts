/** Values the filter bar collects for a trip that does not exist yet; copied into the trip on pick. */
export interface TripDraft {
  /** ISO date of the first night, '' = undated. */
  startDate: string
  partySize: number
}

export const DEFAULT_DRAFT: TripDraft = { startDate: '', partySize: 1 }
