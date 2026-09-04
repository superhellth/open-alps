export interface BedCategory {
  totalPlaces: number
  occupation: string
  totalFreePlaces: number
  label: string
}

export interface CalendarDay {
  day: string
  reservationMode: string
  status: string
  bedCategoriesData: BedCategory[]
}

export interface HutDetail {
  hutId: number
  hutName: string
  calendarDays: CalendarDay[]
}

/** offsetDays (1..maxOffsetDays) -> the set of ohrsHutIds with free beds that night, or
 *  'unknown' if that offset's collectAll request failed. */
export type FreeByOffset = Map<number, Set<string> | 'unknown'>
