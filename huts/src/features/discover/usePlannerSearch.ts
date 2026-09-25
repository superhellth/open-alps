import { useEffect, useMemo, useState } from 'react'
import { fetchAvailabilityByOffset } from '@/availability/fetchAvailability.js'
import { addUtcDays } from '@/availability/formatDate.js'
import type { FreeByOffset } from '@/availability/types.js'
import type { AppData } from '@/data/buildAppData.js'
import { buildQuery } from './formState.js'
import type { FormState } from './formState.js'
import { legCountRangeFromDraft } from './plannerState.js'
import type { TripDraft } from './plannerState.js'
import type { TourResult } from '@/tourSearch/types.js'
import { SupersededError } from '@/search/searchClient.js'
import type { SearchClient } from '@/search/searchClient.js'

export interface PlannerSearch {
  status: 'idle' | 'searching' | 'done' | 'error'
  /** The latest finished result; kept while a newer search runs. */
  chains: TourResult[] | null
  /** Availability of the draft's dates, for ranking and the availability filter; null when no
   *  start date is set. */
  freeByOffset: FreeByOffset | null
  error: string | null
}

export function usePlannerSearch(
  { client, data, form, draft, debounceMs = 300 }:
  { client: SearchClient | null; data: AppData | null; form: FormState; draft: TripDraft; debounceMs?: number },
): PlannerSearch {
  const [state, setState] = useState<Omit<PlannerSearch, 'freeByOffset'>>({ status: 'idle', chains: null, error: null })
  const [freeByOffset, setFreeByOffset] = useState<FreeByOffset | null>(null)
  const legCountRange = legCountRangeFromDraft(draft)
  const [legCountMin, legCountMax] = legCountRange
  const nights = legCountMax - 1

  // Availability for ranking and badges. Night j is read at offset j+1, so the base date is one day
  // before the first night.
  useEffect(() => {
    if (!draft.startDate) { setFreeByOffset(null); return }
    let cancelled = false
    fetchAvailabilityByOffset(addUtcDays(new Date(draft.startDate), -1), draft.partySize, nights)
      .then((free) => { if (!cancelled) setFreeByOffset(free) })
    return () => { cancelled = true }
  }, [draft.startDate, draft.partySize, nights])

  useEffect(() => {
    if (!client || !data) return
    let cancelled = false
    setState((s) => ({ ...s, status: 'searching', error: null }))
    const timer = setTimeout(async () => {
      try {
        const query = buildQuery(form, data.hutsByIndex, legCountRange)
        const chains = await client.search(query)
        if (!cancelled) setState({ status: 'done', chains, error: null })
      } catch (e) {
        if (cancelled || e instanceof SupersededError) return
        setState((s) => ({ ...s, status: 'error', error: (e as Error).message }))
      }
    }, debounceMs)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [client, data, form, legCountMin, legCountMax, debounceMs])

  return useMemo(() => ({ ...state, freeByOffset }), [state, freeByOffset])
}
