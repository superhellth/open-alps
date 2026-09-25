import { useCallback, useEffect, useMemo, useState } from 'react'
import { Alert, Badge, Box, Button, Snackbar, Tab, Tabs, TextField } from '@mui/material'
import { useAppData } from '@/data/appDataContext.js'
import type { AppData } from '@/data/buildAppData.js'
import { useSearchClient } from '@/search/searchClientContext.js'
import type { SearchClient } from '@/search/searchClient.js'
import { usePlannerSearch } from '@/features/discover/usePlannerSearch.js'
import { groupByStart } from '@/tourSearch/groupByStart.js'
import { legsFromTrip } from '@/trip/tripLegs.js'
import { decodeTripFromHash, shareUrl } from '@/trip/shareLink.js'
import type { Trip } from '@/trip/trip.js'
import { useTrips } from '@/trip/tripsContext.js'
import { filterByAvailability } from '@/features/discover/availabilityFilter.js'
import DiscardDraftDialog from './DiscardDraftDialog.js'
import FilterBar from '@/features/discover/FilterBar.js'
import FirstVisitPrompt from './FirstVisitPrompt.js'
import PlannerLoading from './PlannerLoading.js'
import ImportTripDialog from './ImportTripDialog.js'
import PlannerMap from '@/features/map/PlannerMap.js'
import ResultsList from '@/features/discover/ResultsList.js'
import SavedTripsList from '@/features/saved/SavedTripsList.js'
import SidebarHeader from './SidebarHeader.js'
import TripPanel from '@/features/trip/TripPanel.js'
import { DEFAULT_FORM, rankTargetsFromForm } from '@/features/discover/formState.js'
import type { FormState } from '@/features/discover/formState.js'
import { makeStartLabel } from '@/data/labels.js'
import { DEFAULT_DRAFT, dayCountFromDraft, legCountRangeFromDraft } from '@/features/discover/plannerState.js'
import type { TripDraft } from '@/features/discover/plannerState.js'
import { filterOfficial, sortTours } from '@/features/discover/rankTours.js'
import type { SortDir, SortKey } from '@/features/discover/rankTours.js'
import { tourToRoute, tripToRoute } from '@/features/map/routes.js'
import type { RouteContext } from '@/features/map/routes.js'
import { officialToTour } from '@/tourSearch/plannerTour.js'
import type { PlannerTour } from '@/tourSearch/plannerTour.js'
import { inBbox } from '@/features/map/viewport.js'
import { useMapView } from '@/features/map/useMapView.js'
import { tourKey } from '@/features/map/tourKey.js'
import { tripFromTour } from '@/features/discover/tripFromTour.js'
import { useFirstVisitPrompt } from './useFirstVisitPrompt.js'
import { useTripEditor } from '@/features/trip/TripEditor.js'
import type { EditingState } from '@/features/trip/TripEditor.js'
import { useTripOverlaps } from '@/features/trip/useTripOverlaps.js'
import { useHash } from '@/lib/useHash.js'

export default function PlannerPage({ importHash }: { importHash: string | null }) {
  const app = useAppData()
  const client = useSearchClient()
  if (app.status === 'error') return <Alert severity="error">{app.message}</Alert>
  if (app.status === 'loading' || !client) return <PlannerLoading />
  return <Planner data={app.data} client={client} importHash={importHash} />
}

function Planner({ data, client, importHash }: { data: AppData; client: SearchClient; importHash: string | null }) {
  const { state, dispatch, activeTrip, isDraft, draftDirty } = useTrips()
  const prompt = useFirstVisitPrompt()
  const { mapView, setMapView, routesVisible, restoreView, fitBounds, rememberViewBeforeTrip, restoreViewAfterTrip, fitToPoints } = useMapView()

  const [form, setForm] = useState<FormState>(DEFAULT_FORM)
  const [draft, setDraft] = useState<TripDraft>(DEFAULT_DRAFT)
  const [sortKey, setSortKey] = useState<SortKey>('fit')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [discoverTab, setDiscoverTab] = useState<'filters' | 'results'>('filters')
  const [erweitertOpen, setErweitertOpen] = useState(false)
  const [focusStarts, setFocusStarts] = useState<Set<number> | null>(null)
  const [previewTour, setPreviewTour] = useState<PlannerTour | null>(null)
  const [editing, setEditing] = useState<EditingState>(null)
  const [highlightedLeg, setHighlightedLeg] = useState<number | null>(null)
  const [importDismissed, setImportDismissed] = useState(false)
  const [shareNote, setShareNote] = useState<string | null>(null)
  const [shareFallback, setShareFallback] = useState<string | null>(null)
  const [pendingPick, setPendingPick] = useState<Trip | null>(null)
  const [hoveredTourKey, setHoveredTourKey] = useState<string | null>(null)
  const [hoveredStarts, setHoveredStarts] = useState<Set<number> | null>(null)
  const [openedFrom, setOpenedFrom] = useState<'results' | 'saved'>('results')
  const [hoveredTripId, setHoveredTripId] = useState<string | null>(null)
  const hash = useHash()

  const patchForm = useCallback((patch: Partial<FormState>) => setForm((f) => ({ ...f, ...patch })), [])
  const patchDraft = useCallback((patch: Partial<TripDraft>) => setDraft((d) => ({ ...d, ...patch })), [])

  const search = usePlannerSearch({ client, data, form, draft })
  useEffect(() => { setFocusStarts(null) }, [form, draft])
  const legCountRange = useMemo(() => legCountRangeFromDraft(draft), [draft])
  const dayCountTarget = useMemo(() => dayCountFromDraft(draft), [draft])

  const startLabel = useMemo(() => makeStartLabel(data.startById), [data])
  const routeCtx = useMemo<RouteContext>(() => ({
    hutCoordsById: data.hutCoordsById, startById: data.startById,
    officialById: new Map(data.officialTours.map((t) => [t.tourId, t])),
  }), [data])
  const ohrsIdByHutIndex = useMemo(
    () => new Map([...data.hutOhrsByIndex].map(([i, v]) => [i, v.ohrsHutId] as const)), [data])

  const officialTours = useMemo(
    () => data.officialTours.map(officialToTour).filter((t): t is PlannerTour => t !== null), [data])
  const tours = useMemo<PlannerTour[]>(
    () => [...(search.chains ?? []), ...filterOfficial(officialTours, form, legCountRange, data.startById)],
    [data, search.chains, officialTours, form, legCountRange])
  const visibleTours = useMemo(
    () => filterByAvailability(tours, form.onlyAvailable, ohrsIdByHutIndex, search.freeByOffset),
    [tours, form.onlyAvailable, ohrsIdByHutIndex, search.freeByOffset])
  const groups = useMemo(() => groupByStart(visibleTours), [visibleTours])

  const rankedTours = useMemo(
    () => sortTours(visibleTours, sortKey, sortDir, { targets: rankTargetsFromForm(form, legCountRange, dayCountTarget), ohrsIdByHutIndex, freeByOffset: search.freeByOffset }),
    [visibleTours, sortKey, sortDir, form, legCountRange, dayCountTarget, ohrsIdByHutIndex, search.freeByOffset])
  const viewTours = useMemo(() => {
    if (focusStarts) return rankedTours.filter((t) => focusStarts.has(t.startId))
    if (!mapView) return rankedTours
    return rankedTours.filter((t) => {
      const s = data.startById.get(t.startId)
      return s !== undefined && inBbox(s, mapView.bbox)
    })
  }, [rankedTours, mapView, data, focusStarts])

  const showAllTours = useCallback(() => {
    setFocusStarts(null)
    fitToPoints(groups.flatMap((g) => { const s = data.startById.get(g.startId); return s ? [s] : [] }))
  }, [groups, data, fitToPoints])

  const tripLegs = useMemo(() => (activeTrip ? legsFromTrip(data.graph, activeTrip) : null), [activeTrip, data])
  const mode = activeTrip && tripLegs ? 'trip' : 'discover'
  const sidebarView: 'discover' | 'saved' | 'trip' = mode === 'trip' ? 'trip' : (hash === '#trips' ? 'saved' : 'discover')
  const overlapWarnings = useTripOverlaps(client, activeTrip, tripLegs)

  const editor = useTripEditor({
    graph: data.graph, trip: activeTrip, tripLegs,
    hutNameById: data.hutNameById, startLabel, editing, onEditing: setEditing,
    onChange: (trip) => dispatch({ type: isDraft ? 'updateDraft' : 'update', trip }),
  })

  const previewRoute = useMemo(
    () => (previewTour && routesVisible ? tourToRoute(previewTour, routeCtx) : null),
    [previewTour, routeCtx, routesVisible],
  )
  const tripRoute = useMemo(
    () => (mode === 'trip' && activeTrip && tripLegs ? tripToRoute(activeTrip, tripLegs, routeCtx) : null),
    [mode, activeTrip, tripLegs, routeCtx])

  function pick(tour: PlannerTour) {
    rememberViewBeforeTrip()
    const trip = tripFromTour(tour, {
      hutIds: data.graph.hutEdges.hutIds, startById: data.startById, hutNameById: data.hutNameById, startLabel, form, draft,
    })
    if (!trip) return
    if (draftDirty) { setPendingPick(trip); return }
    setOpenedFrom('results')
    dispatch({ type: 'openDraft', trip })
    setPreviewTour(null)
    setEditing(null)
  }

  function confirmDiscardDraft() {
    if (pendingPick) {
      setOpenedFrom('results')
      dispatch({ type: 'openDraft', trip: pendingPick })
    }
    setPendingPick(null)
    setPreviewTour(null)
    setEditing(null)
  }

  function goPlanen() { window.location.hash = '' }
  function goMeineTouren() {
    if (activeTrip) dispatch({ type: 'closeActive' })
    window.location.hash = '#trips'
  }
  function goHome() {
    dispatch({ type: 'closeActive' })
    window.location.hash = ''
  }
  function openSavedTrip(id: string) {
    setOpenedFrom('saved')
    dispatch({ type: 'setActive', id })
  }
  function openPinnedDraft() {
    setOpenedFrom('saved')
    dispatch({ type: 'reopenDraft' })
  }
  function backFromTrip() {
    setEditing(null)
    dispatch({ type: 'closeActive' })
    restoreViewAfterTrip()
    if (openedFrom === 'saved') window.location.hash = '#trips'
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

  const candidateStartCoords = useMemo(() => new Map(editor.candidates.flatMap((c) => {
    if (c.startId === undefined) return []
    const p = data.startById.get(c.startId)
    return p ? [[c.startId, { lat: p.lat, lng: p.lng }] as const] : []
  })), [data, editor.candidates])
  const candidateMarkers = editor.candidates.flatMap((c) => {
    if (c.hutIndex !== undefined) {
      const p = data.hutCoordsById.get(c.hutIndex)
      return p ? [{ ...c, name: data.hutNameById.get(c.hutIndex) ?? String(c.hutIndex) }] : []
    }
    if (c.startId !== undefined) return [{ ...c, name: startLabel(c.startId) }]
    return []
  })
  const tripHuts = tripLegs
    ? tripLegs.hutIndices.flatMap((i) => {
        const cls = i === null ? undefined : data.hutClassByIndex.get(i)
        return i !== null && cls ? [{ hutIndex: i, name: data.hutNameById.get(i) ?? String(i), operator: cls.operator, serviced: cls.serviced }] : []
      })
    : []
  const tripEnds = activeTrip
    ? [activeTrip.start, activeTrip.exit].flatMap((e) => {
        const p = data.startById.get(e.startId)
        return p ? [{ lat: p.lat, lng: p.lng, sourceType: e.sourceType as number }] : []
      })
    : []

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <SidebarHeader view={sidebarView} savedCount={state.trips.length} onWordmark={goHome} onPlanen={goPlanen} onMeineTouren={goMeineTouren} />
      <Box sx={{ display: 'flex', flex: 1, minHeight: 0 }}>
        <Box sx={{ width: 420, flexShrink: 0, overflowY: 'auto', borderRight: '2px solid', borderColor: 'secondary.main' }}>
          {/* Kept mounted (only hidden) while a trip or the saved list is showing, so "← Ergebnisse"
              restores the list's scroll position. */}
          <Box hidden={sidebarView !== 'discover'}>
            <Tabs
              value={discoverTab} onChange={(_e, v) => setDiscoverTab(v)} variant="fullWidth"
              sx={{ position: 'sticky', top: 0, zIndex: 2, bgcolor: 'background.paper' }}
            >
              <Tab value="filters" label="Filter" />
              <Tab
                value="results"
                label={<Badge color="primary" badgeContent={visibleTours.length} max={99} sx={{ pr: 1.2 }}>Ergebnisse</Badge>}
              />
            </Tabs>
            <Box hidden={discoverTab !== 'filters'} sx={{ position: 'relative' }}>
              <FilterBar
                form={form} onFormChange={patchForm} draft={draft} onDraftChange={patchDraft}
                disabled={false} searching={search.status === 'searching'}
                onErweitertOpenChange={setErweitertOpen}
              />
              {search.status === 'done' && visibleTours.length > 0 && (
                <Box sx={{
                  position: 'sticky', bottom: 0, zIndex: 1, display: 'flex', justifyContent: 'center', py: 1,
                  bgcolor: 'background.paper',
                  ...(erweitertOpen && { borderTop: '1px solid', borderColor: 'divider', boxShadow: '0 -4px 8px -4px rgba(0,0,0,0.15)' }),
                }}>
                  <Button variant="text" onClick={() => setDiscoverTab('results')}>
                    Zu den Ergebnissen ({visibleTours.length}) →
                  </Button>
                </Box>
              )}
            </Box>
            <Box hidden={discoverTab !== 'results'}>
              <ResultsList
                tours={viewTours} totalCount={visibleTours.length} onShowAll={showAllTours}
                isHighlighted={(t) => tourKey(t) === hoveredTourKey || (hoveredStarts?.has(t.startId) ?? false)}
                noMatches={search.status === 'done' && tours.length === 0}
                sortKey={sortKey} onSortChange={setSortKey}
                sortDir={sortDir} onSortDirChange={setSortDir}
                hutNameById={data.hutNameById} onPreview={setPreviewTour} onPick={pick}
                onOpenFilters={() => setDiscoverTab('filters')}
              />
            </Box>
          </Box>
          {sidebarView === 'saved' && (
            <SavedTripsList
              graph={data.graph} onOpen={openSavedTrip} onOpenDraft={openPinnedDraft} onPlanen={goPlanen}
              hoveredTripId={hoveredTripId} onHoverTrip={setHoveredTripId}
            />
          )}
          {sidebarView === 'trip' && activeTrip && tripLegs && (
            <TripPanel
              trip={activeTrip} tripLegs={tripLegs} data={data} startLabel={startLabel}
              isDraft={isDraft} onSave={() => dispatch({ type: 'saveDraft' })}
              onChange={(trip) => dispatch({ type: isDraft ? 'updateDraft' : 'update', trip })}
              onBack={backFromTrip} backLabel={openedFrom === 'saved' ? '← Meine Touren' : '← Ergebnisse'}
              onHoverLeg={setHighlightedLeg}
              renderStageControls={editor.renderRowMenu}
              endpointControls={
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                  {editor.renderEndpointMenu('start')}
                  {editor.renderEndpointMenu('exit')}
                </Box>
              }
              extendControls={editor.renderExtendButtons()}
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
            mode={sidebarView === 'saved' ? 'saved' : mode} groups={groups} dimmed={search.status === 'searching'}
            startById={data.startById} hutCoordsById={data.hutCoordsById}
            onNavigate={() => { prompt.dismiss(); setDiscoverTab('results') }}
            onHoverStarts={setHoveredStarts}
            onFocusStarts={(ids) => setFocusStarts(ids && new Set(ids))}
            onViewChange={setMapView}
            restoreView={restoreView} fitBounds={fitBounds}
            onMapClick={() => { prompt.dismiss(); setFocusStarts(null) }}
            route={mode === 'trip' ? tripRoute : previewRoute} fitRoute={mode === 'trip'} highlightedLeg={highlightedLeg}
            tripHuts={tripHuts} tripEnds={tripEnds}
            candidates={candidateMarkers} candidateStartCoords={candidateStartCoords} onPickCandidate={editor.pickCandidate}
            activeLabel={editor.activeLabel} onCancelEditing={() => setEditing(null)}
            allTours={tours} routeCtx={routeCtx}
            hoveredTourKey={hoveredTourKey} onHoverTour={setHoveredTourKey} previewStartId={previewTour?.startId ?? null} onPickRoute={pick}
            tripLegs={mode === 'trip' ? tripLegs : null} onHoverLeg={setHighlightedLeg}
            savedTrips={state.trips} savedGraph={data.graph}
            savedRouteCtx={routeCtx}
            hoveredTripId={hoveredTripId} onHoverTrip={setHoveredTripId} onOpenSavedTrip={openSavedTrip}
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
      <Snackbar
        open={state.deleted !== null} message="Tour gelöscht"
        action={<Button color="inherit" size="small" onClick={() => dispatch({ type: 'undoDelete' })}>Rückgängig</Button>}
      />
    </Box>
  )
}
