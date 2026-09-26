import { useEffect, useState } from 'react'
import { fetchAvailabilityByOffset } from '@/availability/fetchAvailability.js'
import { addUtcDays } from '@/availability/formatDate.js'
import { nightVerdicts } from '@/availability/stayNights.js'
import type { NightVerdict } from '@/availability/stayNights.js'
import { daysBetween, todayIso } from '@/format/dayMonth.js'

/** Arrival days around the saved one whose nights are fetched as soon as the calendar opens. */
export const PREFETCH_SHIFT = 3
/** Hovered arrival days wait this long before fetching, so sweeping across the month stays quiet. */
const HOVER_DELAY_MS = 150

function dayBefore(iso: string): Date {
  return addUtcDays(new Date(`${iso}T00:00:00Z`), -1)
}

/** Warms the per-date cache for every night of arrival days within ±PREFETCH_SHIFT of `savedStart`, skipping past nights. */
export function usePrefetchAround(savedStart: string | null, nights: number, partySize: number) {
  useEffect(() => {
    if (!savedStart) return
    const base = dayBefore(savedStart)
    const shiftedBase = addUtcDays(base, -PREFETCH_SHIFT)
    const from = Math.max(1, daysBetween(shiftedBase.toISOString().slice(0, 10), todayIso()))
    const to = 2 * PREFETCH_SHIFT + nights
    if (from <= to) void fetchAvailabilityByOffset(shiftedBase, partySize, to, from)
  }, [savedStart, nights, partySize])
}

/** Per-night verdicts of the stay arriving on `start` (night i = hut i), or null while loading or without a start.
 *  `hovered` delays the fetch; cached nights still resolve right after the delay. */
export function useStayNights(start: string | null, ohrsIds: (string | null)[], partySize: number, hovered: boolean) {
  const [result, setResult] = useState<{ key: string; nights: NightVerdict[] } | null>(null)
  const key = `${start}|${partySize}|${ohrsIds.join(',')}`

  useEffect(() => {
    if (!start) return
    let cancelled = false
    const timer = setTimeout(() => {
      void fetchAvailabilityByOffset(dayBefore(start), partySize, ohrsIds.length).then((free) => {
        if (!cancelled) setResult({ key, nights: nightVerdicts(ohrsIds, free) })
      })
    }, hovered ? HOVER_DELAY_MS : 0)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [key]) // eslint-disable-line react-hooks/exhaustive-deps

  return result?.key === key ? result.nights : null
}
