import { useEffect, useState } from 'react'
import { fetchAvailabilityByOffset } from '@/availability/fetchAvailability.js'
import { answerWindow, shiftAnswers } from '@/availability/startDateAnswer.js'
import type { ShiftVerdict } from '@/availability/startDateAnswer.js'
import type { HutOhrs } from '@/data/buildAppData.js'
import { addIsoDays, daysBetween, todayIso } from '@/format/dayMonth.js'
import type { Trip } from '@/trip/trip.js'

export const MAX_SHIFT = 3

/** Whether the whole chain is bookable when starting on each day within ±MAX_SHIFT of the trip's first
 *  night, keyed by ISO day. Null while loading or for an undated trip. Reuses the per-date cached
 *  collectAll calls, so a neighbouring start date only adds one or two fetches. */
export function useStartDateAnswers(trip: Trip, hutIndices: (number | null)[], hutOhrsByIndex: Map<number, HutOhrs>) {
  const [verdicts, setVerdicts] = useState<Map<string, ShiftVerdict> | null>(null)
  const ohrsIds = hutIndices.map((i) => (i === null ? null : hutOhrsByIndex.get(i)?.ohrsHutId ?? null))
  const key = `${trip.startDate}|${trip.partySize}|${ohrsIds.join(',')}`

  useEffect(() => {
    setVerdicts(null)
    const startDate = trip.startDate
    if (!startDate) return
    let cancelled = false
    // Shifts landing before today are neither fetched nor marked.
    const minShift = Math.max(-MAX_SHIFT, daysBetween(startDate, todayIso()))
    if (minShift > MAX_SHIFT) { setVerdicts(new Map()); return }
    const window = answerWindow(new Date(startDate), MAX_SHIFT)
    fetchAvailabilityByOffset(window.base, trip.partySize, window.maxOffset(ohrsIds.length), minShift + MAX_SHIFT + 1).then((free) => {
      if (cancelled) return
      setVerdicts(new Map(shiftAnswers(ohrsIds, free, MAX_SHIFT, minShift).map((a) => [addIsoDays(startDate, a.shiftDays), a.verdict])))
    })
    return () => { cancelled = true }
  }, [key]) // eslint-disable-line react-hooks/exhaustive-deps

  return verdicts
}
