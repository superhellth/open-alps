import { useEffect, useMemo, useState } from 'react'
import { fetchAvailabilityByOffset } from '../availability/fetchAvailability.js'
import { addUtcDays } from '../availability/formatDate.js'
import type { FreeByOffset } from '../availability/types.js'
import type { AppData } from '../data/buildAppData.js'
import { buildQuery } from '../plannerPage/formState.js'
import type { FormState } from '../plannerPage/formState.js'
import type { TripDraft } from '../plannerPage/plannerState.js'
import type { TourResult } from '../tourSearch/types.js'
import { SupersededError } from './searchClient.js'
import type { SearchClient } from './searchClient.js'

export interface PlannerSearch {
  status: 'idle' | 'searching' | 'done' | 'error'
  /** The latest finished result; kept while a newer search runs. */
  chains: TourResult[] | null
  /** Availability of the draft's dates, for ranking; null when no start date is set. */
  freeByOffset: FreeByOffset | null
  error: string | null
}

export function usePlannerSearch(
  { client, data, form, draft, debounceMs = 300 }:
  { client: SearchClient | null; data: AppData | null; form: FormState; draft: TripDraft; debounceMs?: number },
): PlannerSearch {
  const [state, setState] = useState<Omit<PlannerSearch, 'freeByOffset'>>({ status: 'idle', chains: null, error: null })
  const [freeByOffset, setFreeByOffset] = useState<FreeByOffset | null>(null)
  const nights = form.legCountRange[1] - 1

  // Availability for ranking and badges. Night j is read at offset j+1, so the base date is one day
  // before the first night. The fetch is cached per date, shared with the search below.
  useEffect(() => {
    if (!draft.startDate) { setFreeByOffset(null); return }
    let cancelled = false
    fetchAvailabilityByOffset(addUtcDays(new Date(draft.startDate), -1), draft.partySize, nights)
      .then((free) => { if (!cancelled) setFreeByOffset(free) })
    return () => { cancelled = true }
  }, [draft.startDate, draft.partySize, nights])

  // Only the "nur verfügbare" filter makes the availability part of the search input.
  const availabilityDraft = form.onlyAvailable ? draft : null

  useEffect(() => {
    if (!client || !data) return
    let cancelled = false
    setState((s) => ({ ...s, status: 'searching', error: null }))
    const timer = setTimeout(async () => {
      try {
        const free = availabilityDraft?.startDate
          ? await fetchAvailabilityByOffset(addUtcDays(new Date(availabilityDraft.startDate), -1), availabilityDraft.partySize, nights)
          : null
        const ohrsIdByHutIndex = new Map([...data.hutOhrsByIndex].map(([i, v]) => [i, v.ohrsHutId] as const))
        const query = buildQuery(form, data.hutsByIndex, free ? { ohrsIdByHutIndex, freeByOffset: free } : undefined)
        const chains = await client.search(query)
        if (!cancelled) setState({ status: 'done', chains, error: null })
      } catch (e) {
        if (cancelled || e instanceof SupersededError) return
        setState((s) => ({ ...s, status: 'error', error: (e as Error).message }))
      }
    }, debounceMs)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [client, data, form, availabilityDraft, nights, debounceMs])

  return useMemo(() => ({ ...state, freeByOffset }), [state, freeByOffset])
}
