import type { HutDetail } from './types.js'

export type NightAvailability =
  | { kind: 'free'; places: number }
  | { kind: 'few'; places: number }
  | { kind: 'full' }
  | { kind: 'unknown' }

const FULL_STATUSES = new Set(['HUT_CLOSED_TO_PUBLIC', 'RESERVATION_NOT_POSSIBLE'])

/** One night of one hut. `detail` null = the hut has no OHRS id or its fetch failed. */
export function classifyNight(detail: HutDetail | null, partySize: number): NightAvailability {
  const day = detail?.calendarDays[0]
  if (!day || day.status === 'TECHNICAL_ERROR') return { kind: 'unknown' }
  if (FULL_STATUSES.has(day.status)) return { kind: 'full' }
  if (day.bedCategoriesData.length === 0) return { kind: 'unknown' }
  const places = day.bedCategoriesData.reduce((sum, bc) => sum + bc.totalFreePlaces, 0)
  if (places <= 0) return { kind: 'full' }
  return places < 2 * partySize ? { kind: 'few', places } : { kind: 'free', places }
}

export function nightText(a: NightAvailability): string {
  switch (a.kind) {
    case 'free':
    case 'few':
      return a.places === 1 ? '1 Platz frei' : `${a.places} Plätze frei`
    case 'full':
      return 'ausgebucht'
    case 'unknown':
      return 'Verfügbarkeit unbekannt – direkt anfragen'
  }
}
