import { useEffect, useState } from 'react'
import { fetchHutDetail } from '@/availability/fetchHutDetail.js'
import { addUtcDays } from '@/availability/formatDate.js'
import { classifyNight } from '@/availability/nightState.js'
import type { NightAvailability } from '@/availability/nightState.js'
import type { HutOhrs } from '@/data/buildAppData.js'
import type { Trip } from '@/trip/trip.js'

export type NightView = { loading: true } | { loading: false; availability: NightAvailability }

/** Per-night availability of the active trip: one detail request per bookable hut, never a loop over
 *  the hut list. Night i is the trip's first night plus i days. Null when the trip has no start date. */
export function useTripAvailability(
  trip: Trip, hutIndices: (number | null)[], hutOhrsByIndex: Map<number, HutOhrs>,
): NightView[] | null {
  const [views, setViews] = useState<NightView[] | null>(null)
  const key = `${trip.startDate}|${trip.partySize}|${hutIndices.join(',')}`

  useEffect(() => {
    if (!trip.startDate) { setViews(null); return }
    const first = new Date(trip.startDate)
    let cancelled = false
    setViews(hutIndices.map((): NightView => ({ loading: true })))
    hutIndices.forEach((index, night) => {
      const set = (availability: NightAvailability) => {
        if (cancelled) return
        setViews((prev) => prev && prev.map((v, i) => (i === night ? { loading: false, availability } : v)))
      }
      const ohrs = index === null ? undefined : hutOhrsByIndex.get(index)
      if (!ohrs || ohrs.ohrsHutId === null || ohrs.tenantCode === null) { set({ kind: 'unknown' }); return }
      fetchHutDetail(ohrs.ohrsHutId, ohrs.tenantCode, addUtcDays(first, night), trip.partySize).then(
        (detail) => set(classifyNight(detail, trip.partySize)),
        () => set({ kind: 'unknown' }),
      )
    })
    return () => { cancelled = true }
    // hutIndices is captured through `key`.
  }, [key, hutOhrsByIndex]) // eslint-disable-line react-hooks/exhaustive-deps

  return views
}
