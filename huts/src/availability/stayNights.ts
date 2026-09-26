import type { FreeByOffset } from './types.js'

/** One night of a stay: its hut has beds, has none, or can't be told (direct-booking-only or request failed). */
export type NightVerdict = 'free' | 'full' | 'unclear'
export type StayVerdict = 'bookable' | 'blocked' | 'unclear'

/** Night i of a stay, hut `ohrsIds[i]`, read from offset i + 1 of a fetch based on the day before the first night. */
export function nightVerdicts(ohrsIds: (string | null)[], freeByOffset: FreeByOffset): NightVerdict[] {
  return ohrsIds.map((ohrsId, i) => {
    const free = freeByOffset.get(i + 1)
    if (ohrsId === null || free === undefined || free === 'unknown') return 'unclear'
    return free.has(ohrsId) ? 'free' : 'full'
  })
}

/** Whole stay: blocked if any night is full, unclear if any night can't be told. */
export function stayVerdict(nights: NightVerdict[]): StayVerdict {
  if (nights.includes('full')) return 'blocked'
  if (nights.includes('unclear')) return 'unclear'
  return 'bookable'
}
