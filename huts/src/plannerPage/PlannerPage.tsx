import { useCallback, useMemo, useState } from 'react'
import { Alert, Box, Snackbar, TextField } from '@mui/material'
import AppShell from '../AppShell.js'
import { useAppData } from '../data/AppDataProvider.js'
import { useSearchClient } from '../search/SearchClientProvider.js'
import { usePlannerSearch } from '../search/usePlannerSearch.js'
import { groupByStart } from '../tourSearch/groupByStart.js'
import { legsFromTrip } from '../tourSearch/tripLegs.js'
import type { TripGraph, TripLegs } from '../tourSearch/tripLegs.js'
import { decodeTripFromHash, shareUrl } from '../trip/shareLink.js'
import type { Trip } from '../trip/trip.js'
import { useTrips } from '../trip/TripsProvider.js'
import { filterByAvailability, tourHasFullNight } from './availabilityFilter.js'
import DiscardDraftDialog from './DiscardDraftDialog.js'
import FilterBar from './FilterBar.js'
import FirstVisitPrompt from './FirstVisitPrompt.js'
import ImportTripDialog from './ImportTripDialog.js'
import PlannerMap from './PlannerMap.js'
import ResultsList from './ResultsList.js'
import TripPanel from './TripPanel.js'
import { DEFAULT_FORM, rankTargetsFromForm } from './formState.js'
import type { FormState } from './formState.js'
import { makeStartLabel } from './labels.js'
import { DEFAULT_DRAFT, dayCountFromDraft, legCountRangeFromDraft } from './plannerState.js'
import type { TripDraft } from './plannerState.js'
import { filterOfficial, sortTours } from './rankTours.js'
import type { SortKey } from './rankTours.js'
import { tourToRoute, tripToRoute } from './routes.js'
import type { RouteContext } from './routes.js'
import { officialToTour } from './tours.js'
import type { PlannerTour } from './tours.js'
import { tripFromTour } from './tripFromTour.js'
import { useFirstVisitPrompt } from './useFirstVisitPrompt.js'
import { useTripEditor } from './TripEditor.js'
import type { EditingState } from './TripEditor.js'
import { useTripOverlaps } from './useTripOverlaps.js'

const EMPTY_GRAPH: TripGraph = { hutEdges: { hutIds: [], variantNames: {}, records: [] }, approaches: { records: [], reverseIndex: { hut_to_starts: {}, start_to_huts: {} } } }
const PLACEHOLDER_TRIP: Trip = { id: '', name: '', createdAt: '', updatedAt: '', startDate: null, partySize: 1, start: { startId: 0, sourceType: 1 }, huts: [], exit: { startId: 0, sourceType: 1 }, variant: { sacCeiling: null, allowUngraded: false }, nights: [] }
const PLACEHOLDER_LEGS: TripLegs = { variantId: -1, hutIndices: [], legs: [], changed: [] }

export default function PlannerPage({ importHash }: { importHash: string | null }) {
  const app = useAppData()
  const data = app.status === 'ready' ? app.data : null
  const client = useSearchClient()
  const { dispatch, activeTrip, isDraft, draftDirty } = useTrips()
  const prompt = useFirstVisitPrompt()

  const [form, setForm] = useState<FormState>(DEFAULT_FORM)
  const [draft, setDraft] = useState<TripDraft>(DEFAULT_DRAFT)
  const [sortKey, setSortKey] = useState<SortKey>('fit')
  const [selectedStartIds, setSelectedStartIds] = useState<number[] | null>(null)
  const [previewTour, setPreviewTour] = useState<PlannerTour | null>(null)
  const [editing, setEditing] = useState<EditingState>(null)
  const [highlightedLeg, setHighlightedLeg] = useState<number | null>(null)
  const [importDismissed, setImportDismissed] = useState(false)
  const [shareNote, setShareNote] = useState<string | null>(null)
  const [shareFallback, setShareFallback] = useState<string | null>(null)
  const [pendingPick, setPendingPick] = useState<Trip | null>(null)

  const patchForm = useCallback((patch: Partial<FormState>) => setForm((f) => ({ ...f, ...patch })), [])
  const patchDraft = useCallback((patch: Partial<TripDraft>) => setDraft((d) => ({ ...d, ...patch })), [])

  const search = usePlannerSearch({ client, data, form, draft })
  const legCountRange = useMemo(() => legCountRangeFromDraft(draft), [draft])
  const dayCountTarget = useMemo(() => dayCountFromDraft(draft), [draft])

  const startLabel = useMemo(() => makeStartLabel(data?.startById ?? new Map()), [data])
  const routeCtx = useMemo<RouteContext | null>(() => data && ({
    hutCoordsById: data.hutCoordsById, startById: data.startById,
    officialById: new Map(data.officialTours.map((t) => [t.tourId, t])),
  }), [data])
  const ohrsIdByHutIndex = useMemo(
    () => new Map([...(data?.hutOhrsByIndex ?? [])].map(([i, v]) => [i, v.ohrsHutId] as const)), [data])

  const officialTours = useMemo(
    () => (data?.officialTours ?? []).map(officialToTour).filter((t): t is PlannerTour => t !== null), [data])
  const tours = useMemo<PlannerTour[]>(
    () => (data ? [...(search.chains ?? []), ...filterOfficial(officialTours, form, legCountRange, data.startById)] : []),
    [data, search.chains, officialTours, form, legCountRange])
  const visibleTours = useMemo(
    () => filterByAvailability(tours, form.onlyAvailable, form.showFullToo, ohrsIdByHutIndex, search.freeByOffset),
    [tours, form.onlyAvailable, form.showFullToo, ohrsIdByHutIndex, search.freeByOffset])
  const groups = useMemo(() => groupByStart(visibleTours), [visibleTours])

  const selectedTours = useMemo(() => {
    if (!selectedStartIds) return []
    const wanted = new Set(selectedStartIds)
    const inArea = groups.filter((g) => wanted.has(g.startId)).flatMap((g) => g.tours)
    return sortTours(inArea, sortKey, { targets: rankTargetsFromForm(form, legCountRange, dayCountTarget), ohrsIdByHutIndex, freeByOffset: search.freeByOffset })
  }, [selectedStartIds, groups, sortKey, form, legCountRange, dayCountTarget, ohrsIdByHutIndex, search.freeByOffset])

  const tripLegs = useMemo(() => (activeTrip && data ? legsFromTrip(data.graph, activeTrip) : null), [activeTrip, data])
  const mode = activeTrip && data && tripLegs ? 'trip' : 'discover'
  const overlapWarnings = useTripOverlaps(client, activeTrip ?? PLACEHOLDER_TRIP, tripLegs ?? PLACEHOLDER_LEGS)

  const editor = useTripEditor({
    graph: data?.graph ?? EMPTY_GRAPH, trip: activeTrip ?? PLACEHOLDER_TRIP, tripLegs: tripLegs ?? PLACEHOLDER_LEGS,
    hutNameById: data?.hutNameById ?? new Map(), startLabel, editing, onEditing: setEditing,
    onChange: (trip) => dispatch({ type: isDraft ? 'updateDraft' : 'update', trip }),
  })

  const previewRoute = useMemo(() => (previewTour && routeCtx ? tourToRoute(previewTour, routeCtx) : null), [previewTour, routeCtx])
  const tripRoute = useMemo(
    () => (mode === 'trip' && activeTrip && tripLegs && routeCtx ? tripToRoute(activeTrip, tripLegs, routeCtx) : null),
    [mode, activeTrip, tripLegs, routeCtx])

  function pick(tour: PlannerTour) {
    if (!data) return
    const trip = tripFromTour(tour, {
      hutIds: data.graph.hutEdges.hutIds, startById: data.startById, hutNameById: data.hutNameById, startLabel, form, draft,
    })
    if (!trip) return
    if (draftDirty) { setPendingPick(trip); return }
    dispatch({ type: 'openDraft', trip })
    setPreviewTour(null)
    setEditing(null)
  }

  function confirmDiscardDraft() {
    if (pendingPick) dispatch({ type: 'openDraft', trip: pendingPick })
    setPendingPick(null)
    setPreviewTour(null)
    setEditing(null)
  }

  async function share() {
    if (!activeTrip) return
    const url = shareUrl(activeTrip, window.location)
    try {
      await navigator.clipboard.writeText(url)
      setShareNote('Link kopiert')
    } catch {
      setShareFallback(url)
    }
  }

  const importedTrip = useMemo(() => (importHash ? decodeTripFromHash(importHash) : null), [importHash])
  const closeImport = () => { setImportDismissed(true); window.location.hash = '' }

  const candidateMarkers = data
    ? editor.candidates.flatMap((c) => {
        const p = data.hutCoordsById.get(c.hutIndex)
        return p ? [{ ...c, lat: p.lat, lng: p.lng, name: data.hutNameById.get(c.hutIndex) ?? String(c.hutIndex) }] : []
      })
    : []
  const tripHuts = data && tripLegs
    ? tripLegs.hutIndices.flatMap((i) => {
        const cls = i === null ? undefined : data.hutClassByIndex.get(i)
        return i !== null && cls ? [{ hutIndex: i, name: data.hutNameById.get(i) ?? String(i), operator: cls.operator, serviced: cls.serviced }] : []
      })
    : []
  const tripEnds = data && activeTrip
    ? [activeTrip.start, activeTrip.exit].flatMap((e) => {
        const p = data.startById.get(e.startId)
        return p ? [{ lat: p.lat, lng: p.lng, sourceType: e.sourceType as number }] : []
      })
    : []

  const status = app.status === 'error' ? `Fehler: ${app.message}` : data ? 'Daten geladen' : 'Lade Daten…'

  return (
    <AppShell title="Hüttentouren" status={status}>
      <Box sx={{ display: 'flex', flex: 1, minHeight: 0 }}>
        <Box sx={{ width: 420, flexShrink: 0, overflowY: 'auto', borderRight: '2px solid', borderColor: 'secondary.main' }}>
          {app.status === 'error' && <Alert severity="error">{app.message}</Alert>}
          {/* Kept mounted (only hidden) while a trip is open, so "← Ergebnisse" restores the list's scroll position. */}
          <Box hidden={mode === 'trip'}>
            <FilterBar
              form={form} onFormChange={patchForm} draft={draft} onDraftChange={patchDraft}
              disabled={!data || !client} searching={search.status === 'searching'}
            />
            <ResultsList
              tours={selectedTours} selectionActive={selectedStartIds !== null} totalMatches={visibleTours.length}
              noMatches={search.status === 'done' && tours.length === 0}
              sortKey={sortKey} onSortChange={setSortKey}
              hutNameById={data?.hutNameById ?? new Map()} hutClassByIndex={data?.hutClassByIndex ?? new Map()}
              startLabel={startLabel} onPreview={setPreviewTour} onPick={pick}
              isFull={(t) => (form.onlyAvailable && form.showFullToo ? tourHasFullNight(t, ohrsIdByHutIndex, search.freeByOffset ?? new Map()) : false)}
            />
          </Box>
          {mode === 'trip' && activeTrip && tripLegs && data && (
            <TripPanel
              trip={activeTrip} tripLegs={tripLegs} data={data} startLabel={startLabel}
              isDraft={isDraft} onSave={() => dispatch({ type: 'saveDraft' })}
              onChange={(trip) => dispatch({ type: isDraft ? 'updateDraft' : 'update', trip })}
              onBack={() => { setEditing(null); dispatch({ type: 'closeActive' }) }}
              onHoverLeg={setHighlightedLeg}
              renderStageControls={editor.renderStageControls} extra={editor.extra}
              warnings={overlapWarnings} onShare={share}
            />
          )}
          {shareFallback && (
            <Box sx={{ p: 2 }}>
              <TextField size="small" fullWidth label="Link zum Teilen" value={shareFallback} slotProps={{ htmlInput: { readOnly: true } }} onFocus={(e) => e.target.select()} />
            </Box>
          )}
        </Box>

        <Box sx={{ flex: 1, minWidth: 0, position: 'relative' }}>
          <PlannerMap
            mode={mode} groups={groups} dimmed={search.status === 'searching'}
            startById={data?.startById ?? new Map()} hutCoordsById={data?.hutCoordsById ?? new Map()}
            onSelectStarts={(ids) => { prompt.dismiss(); setSelectedStartIds(ids) }}
            onMapClick={prompt.dismiss}
            route={mode === 'trip' ? tripRoute : previewRoute} fitRoute={mode === 'trip'} highlightedLeg={highlightedLeg}
            tripHuts={tripHuts} tripEnds={tripEnds} candidates={candidateMarkers} onPickCandidate={editor.pickCandidate}
          />
          {mode === 'discover' && prompt.visible && <FirstVisitPrompt />}
        </Box>
      </Box>

      <ImportTripDialog
        trip={importDismissed ? null : importedTrip}
        onImport={() => { if (importedTrip) dispatch({ type: 'create', trip: importedTrip }); closeImport() }}
        onDiscard={closeImport}
      />
      <DiscardDraftDialog
        open={pendingPick !== null}
        onDiscard={confirmDiscardDraft}
        onCancel={() => setPendingPick(null)}
      />
      <Snackbar open={shareNote !== null} autoHideDuration={3000} onClose={() => setShareNote(null)} message={shareNote} />
    </AppShell>
  )
}
