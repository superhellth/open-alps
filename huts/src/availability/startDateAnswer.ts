import { addUtcDays } from './formatDate.js'
import type { FreeByOffset } from './types.js'

export type ShiftVerdict = 'bookable' | 'blocked' | 'unclear'

export interface ShiftAnswer {
  shiftDays: number
  verdict: ShiftVerdict
}

/** Date range to fetch with `fetchAvailabilityByOffset(base, partySize, maxOffset(nights))` so that
 *  every start date shifted by -maxShift..+maxShift is answerable from the same cached per-date calls. */
export function answerWindow(firstNight: Date, maxShift: number) {
  return {
    base: addUtcDays(firstNight, -maxShift - 1),
    maxOffset: (nights: number) => 2 * maxShift + nights,
  }
}

/** For each shifted first night, whether every hut has beds. Hut i on shift s reads offset s + maxShift + i + 1
 *  of the `answerWindow` fetch. Shifts below `minShift` are left out. "unclear" = nothing is full but some hut is direct-booking-only or its night is unknown. */
export function shiftAnswers(ohrsIds: (string | null)[], freeByOffset: FreeByOffset, maxShift: number, minShift = -maxShift): ShiftAnswer[] {
  const answers: ShiftAnswer[] = []
  for (let shift = minShift; shift <= maxShift; shift++) {
    let blocked = false
    let unclear = false
    ohrsIds.forEach((ohrsId, i) => {
      const free = freeByOffset.get(shift + maxShift + i + 1)
      if (ohrsId === null || free === undefined || free === 'unknown') unclear = true
      else if (!free.has(ohrsId)) blocked = true
    })
    answers.push({ shiftDays: shift, verdict: blocked ? 'blocked' : unclear ? 'unclear' : 'bookable' })
  }
  return answers
}
