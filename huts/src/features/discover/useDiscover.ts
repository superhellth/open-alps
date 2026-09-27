import { useCallback, useEffect, useMemo, useState } from 'react'
import type { AppData } from '@/data/buildAppData.js'
import type { SearchClient } from '@/search/searchClient.js'
import { groupByStart } from '@/tourSearch/groupByStart.js'
import { NO_TOURS, tourKey } from '@/tourSearch/tourKey.js'
import type { PlannerTour } from '@/tourSearch/plannerTour.js'
import { inBbox } from '@/lib/viewport.js'
import type { View } from '@/lib/viewport.js'
import { filterByAvailability } from './availabilityFilter.js'
import { DEFAULT_FORM, rankTargetsFromForm } from './formState.js'
import type { FormState } from './formState.js'
import { DEFAULT_DRAFT, dayCountFromDraft, legCountRangeFromDraft } from './plannerState.js'
import type { TripDraft } from './plannerState.js'
import { sortTours } from './rankTours.js'
import type { SortDir, SortKey } from './rankTours.js'
import { usePlannerSearch } from './usePlannerSearch.js'

/** Discover state: filter form, search, ranking, and the result lists derived from them. `pointOf` places a tour on the map
 *  for the results list's viewport filter, the same point its count bubble clusters at. */
export function useDiscover({ data, client, mapView, pointOf }: {
  data: AppData
  client: SearchClient
  mapView: View | null
  pointOf: (tour: PlannerTour) => { lat: number; lng: number } | null
}) {
  const [form, setForm] = useState<FormState>(DEFAULT_FORM)
  const [draft, setDraft] = useState<TripDraft>(DEFAULT_DRAFT)
  const [sortKey, setSortKey] = useState<SortKey>('fit')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [tab, setTab] = useState<'filters' | 'results'>('filters')
  const [erweitertOpen, setErweitertOpen] = useState(false)
  const [focusTours, setFocusTours] = useState<Set<string> | null>(null)
  const [hoveredTourKeys, setHoveredTourKeys] = useState<ReadonlySet<string>>(NO_TOURS)

  const patchForm = useCallback((patch: Partial<FormState>) => setForm((f) => ({ ...f, ...patch })), [])
  const patchDraft = useCallback((patch: Partial<TripDraft>) => setDraft((d) => ({ ...d, ...patch })), [])

  const search = usePlannerSearch({ client, data, form, draft })
  useEffect(() => { setFocusTours(null) }, [form, draft])
  const legCountRange = useMemo(() => legCountRangeFromDraft(draft), [draft])
  const dayCountTarget = useMemo(() => dayCountFromDraft(draft), [draft])

  const ohrsIdByHutIndex = useMemo(
    () => new Map([...data.hutOhrsByIndex].map(([i, v]) => [i, v.ohrsHutId] as const)), [data])
  const tours = useMemo<PlannerTour[]>(() => search.chains ?? [], [search.chains])
  const visibleTours = useMemo(
    () => filterByAvailability(tours, form.onlyAvailable, ohrsIdByHutIndex, search.freeByOffset),
    [tours, form.onlyAvailable, ohrsIdByHutIndex, search.freeByOffset])
  const groups = useMemo(() => groupByStart(visibleTours), [visibleTours])

  const rankedTours = useMemo(
    () => sortTours(visibleTours, sortKey, sortDir, { targets: rankTargetsFromForm(form, legCountRange, dayCountTarget), ohrsIdByHutIndex, freeByOffset: search.freeByOffset }),
    [visibleTours, sortKey, sortDir, form, legCountRange, dayCountTarget, ohrsIdByHutIndex, search.freeByOffset])
  const pointByKey = useMemo(() => new Map(visibleTours.map((t) => [tourKey(t), pointOf(t)])), [visibleTours, pointOf])
  const viewTours = useMemo(() => {
    if (focusTours) return rankedTours.filter((t) => focusTours.has(tourKey(t)))
    if (!mapView) return rankedTours
    return rankedTours.filter((t) => {
      const p = pointByKey.get(tourKey(t))
      return p != null && inBbox(p, mapView.bbox)
    })
  }, [rankedTours, mapView, pointByKey, focusTours])

  return {
    form, patchForm, draft, patchDraft,
    sort: { key: sortKey, dir: sortDir, setKey: setSortKey, setDir: setSortDir },
    tab, setTab, erweitertOpen, setErweitertOpen,
    search, tours, visibleTours, groups, viewTours,
    focusTours, setFocusTours, hoveredTourKeys, setHoveredTourKeys,
  }
}
