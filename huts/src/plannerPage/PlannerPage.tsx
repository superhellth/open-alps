import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import L from 'leaflet'
import { Alert, Badge, Box, Button, Snackbar, Tab, Tabs, TextField } from '@mui/material'
import { useAppData } from '../data/AppDataProvider.js'
import { useSearchClient } from '../search/SearchClientProvider.js'
import { usePlannerSearch } from '@/features/discover/usePlannerSearch.js'
import { groupByStart } from '../tourSearch/groupByStart.js'
import { legsFromTrip } from '@/trip/tripLegs.js'
import type { TripLegs } from '@/trip/tripLegs.js'
import type { TripGraph } from '@/tourSearch/types.js'
import { decodeTripFromHash, shareUrl } from '../trip/shareLink.js'
import type { Trip } from '../trip/trip.js'
import { useTrips } from '../trip/TripsProvider.js'
import { filterByAvailability } from './availabilityFilter.js'
import DiscardDraftDialog from './DiscardDraftDialog.js'
import FilterBar from './FilterBar.js'
import FirstVisitPrompt from './FirstVisitPrompt.js'
import ImportTripDialog from './ImportTripDialog.js'
import PlannerMap from './PlannerMap.js'
import ResultsList from './ResultsList.js'
import SavedTripsList from './SavedTripsList.js'
import SidebarHeader from './SidebarHeader.js'
import TripPanel from './TripPanel.js'
import { DEFAULT_FORM, rankTargetsFromForm } from '@/features/discover/formState.js'
import type { FormState } from '@/features/discover/formState.js'
import { makeStartLabel } from '@/data/labels.js'
import { DEFAULT_DRAFT, dayCountFromDraft, legCountRangeFromDraft } from '@/features/discover/plannerState.js'
import type { TripDraft } from '@/features/discover/plannerState.js'
import { filterOfficial, sortTours } from './rankTours.js'
import type { SortDir, SortKey } from './rankTours.js'
import { tourToRoute, tripToRoute } from './routes.js'
import type { RouteContext } from './routes.js'
import { officialToTour } from '@/tourSearch/plannerTour.js'
import type { PlannerTour } from '@/tourSearch/plannerTour.js'
import { inBbox } from './map/viewport.js'
import { ROUTE_REVEAL_ZOOM, tourKey } from './map/DiscoverLayer.js'
import type { View } from './map/viewport.js'
import { tripFromTour } from './tripFromTour.js'
import { useFirstVisitPrompt } from './useFirstVisitPrompt.js'
import { useTripEditor } from './TripEditor.js'
import type { EditingState } from './TripEditor.js'
import { useTripOverlaps } from './useTripOverlaps.js'
import { useHash } from '@/lib/useHash.js'

const EMPTY_GRAPH: TripGraph = { hutEdges: { hutIds: [], variantNames: {}, records: [] }, approaches: { records: [], reverseIndex: { hut_to_starts: {}, start_to_huts: {} } } }
const PLACEHOLDER_TRIP: Trip = { id: '', name: '', createdAt: '', updatedAt: '', startDate: null, partySize: 1, start: { startId: 0, sourceType: 1 }, huts: [], exit: { startId: 0, sourceType: 1 }, variant: { sacCeiling: null, allowUngraded: false }, nights: [] }
const PLACEHOLDER_LEGS: TripLegs = { variantId: -1, hutIndices: [], legs: [], changed: [] }

export default function PlannerPage({ importHash }: { importHash: string | null }) {
  const app = useAppData()
  const data = app.status === 'ready' ? app.data : null
  const client = useSearchClient()
  const { state, dispatch, activeTrip, isDraft, draftDirty } = useTrips()
  const prompt = useFirstVisitPrompt()

  const [form, setForm] = useState<FormState>(DEFAULT_FORM)
  const [draft, setDraft] = useState<TripDraft>(DEFAULT_DRAFT)
  const [sortKey, setSortKey] = useState<SortKey>('fit')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [discoverTab, setDiscoverTab] = useState<'filters' | 'results'>('filters')
  const [erweitertOpen, setErweitertOpen] = useState(false)
  const [focusStarts, setFocusStarts] = useState<Set<number> | null>(null)
  const [mapView, setMapView] = useState<View | null>(null)
  const [restoreView, setRestoreView] = useState<{ lat: number; lng: number; zoom: number } | null>(null)
  const [fitBounds, setFitBounds] = useState<[[number, number], [number, number]] | null>(null)
  const preTripView = useRef<{ lat: number; lng: number; zoom: number } | null>(null)
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
    () => filterByAvailability(tours, form.onlyAvailable, ohrsIdByHutIndex, search.freeByOffset),
    [tours, form.onlyAvailable, ohrsIdByHutIndex, search.freeByOffset])
  const groups = useMemo(() => groupByStart(visibleTours), [visibleTours])

  const rankedTours = useMemo(
    () => sortTours(visibleTours, sortKey, sortDir, { targets: rankTargetsFromForm(form, legCountRange, dayCountTarget), ohrsIdByHutIndex, freeByOffset: search.freeByOffset }),
    [visibleTours, sortKey, sortDir, form, legCountRange, dayCountTarget, ohrsIdByHutIndex, search.freeByOffset])
  const viewTours = useMemo(() => {
    if (focusStarts) return rankedTours.filter((t) => focusStarts.has(t.startId))
    if (!mapView || !data) return rankedTours
    return rankedTours.filter((t) => {
      const s = data.startById.get(t.startId)
      return s !== undefined && inBbox(s, mapView.bbox)
    })
  }, [rankedTours, mapView, data, focusStarts])

  const showAllTours = useCallback(() => {
    setFocusStarts(null)
    const bounds = L.latLngBounds([])
    for (const g of groups) {
      const s = data?.startById.get(g.startId)
      if (s) bounds.extend([s.lat, s.lng])
    }
    if (bounds.isValid()) setFitBounds([[bounds.getSouth(), bounds.getWest()], [bounds.getNorth(), bounds.getEast()]])
  }, [groups, data])

  const tripLegs = useMemo(() => (activeTrip && data ? legsFromTrip(data.graph, activeTrip) : null), [activeTrip, data])
  const mode = activeTrip && data && tripLegs ? 'trip' : 'discover'
  const sidebarView: 'discover' | 'saved' | 'trip' = mode === 'trip' ? 'trip' : (hash === '#trips' ? 'saved' : 'discover')
  const overlapWarnings = useTripOverlaps(client, activeTrip ?? PLACEHOLDER_TRIP, tripLegs ?? PLACEHOLDER_LEGS)

  const editor = useTripEditor({
    graph: data?.graph ?? EMPTY_GRAPH, trip: activeTrip ?? PLACEHOLDER_TRIP, tripLegs: tripLegs ?? PLACEHOLDER_LEGS,
    hutNameById: data?.hutNameById ?? new Map(), startLabel, editing, onEditing: setEditing,
    onChange: (trip) => dispatch({ type: isDraft ? 'updateDraft' : 'update', trip }),
  })

  // Below ROUTE_REVEAL_ZOOM the map shows only count markers, so a hovered tour highlights its bubble instead of drawing a route.
  const routesVisible = mapView !== null && mapView.zoom >= ROUTE_REVEAL_ZOOM
  const previewRoute = useMemo(
    () => (previewTour && routeCtx && routesVisible ? tourToRoute(previewTour, routeCtx) : null),
    [previewTour, routeCtx, routesVisible],
  )
  const tripRoute = useMemo(
    () => (mode === 'trip' && activeTrip && tripLegs && routeCtx ? tripToRoute(activeTrip, tripLegs, routeCtx) : null),
    [mode, activeTrip, tripLegs, routeCtx])

  function pick(tour: PlannerTour) {
    if (!data) return
    if (mapView) {
      preTripView.current = {
        lat: (mapView.bbox[1] + mapView.bbox[3]) / 2, lng: (mapView.bbox[0] + mapView.bbox[2]) / 2, zoom: mapView.zoom,
      }
    }
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
    if (preTripView.current) setRestoreView({ ...preTripView.current })
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

  const candidateStartCoords = useMemo(() => (data
    ? new Map(editor.candidates.flatMap((c) => {
        if (c.startId === undefined) return []
        const p = data.startById.get(c.startId)
        return p ? [[c.startId, { lat: p.lat, lng: p.lng }] as const] : []
      }))
    : new Map()), [data, editor.candidates])
  const candidateMarkers = data
    ? editor.candidates.flatMap((c) => {
        if (c.hutIndex !== undefined) {
          const p = data.hutCoordsById.get(c.hutIndex)
          return p ? [{ ...c, name: data.hutNameById.get(c.hutIndex) ?? String(c.hutIndex) }] : []
        }
        if (c.startId !== undefined) return [{ ...c, name: startLabel(c.startId) }]
        return []
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

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <SidebarHeader view={sidebarView} savedCount={state.trips.length} onWordmark={goHome} onPlanen={goPlanen} onMeineTouren={goMeineTouren} />
      <Box sx={{ display: 'flex', flex: 1, minHeight: 0 }}>
        <Box sx={{ width: 420, flexShrink: 0, overflowY: 'auto', borderRight: '2px solid', borderColor: 'secondary.main' }}>
          {app.status === 'error' && <Alert severity="error">{app.message}</Alert>}
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
                disabled={!data || !client} searching={search.status === 'searching'}
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
                hutNameById={data?.hutNameById ?? new Map()} onPreview={setPreviewTour} onPick={pick}
                onOpenFilters={() => setDiscoverTab('filters')}
              />
            </Box>
          </Box>
          {sidebarView === 'saved' && (
            <SavedTripsList
              graph={data?.graph ?? EMPTY_GRAPH} onOpen={openSavedTrip} onOpenDraft={openPinnedDraft} onPlanen={goPlanen}
              hoveredTripId={hoveredTripId} onHoverTrip={setHoveredTripId}
            />
          )}
          {sidebarView === 'trip' && activeTrip && tripLegs && data && (
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
            startById={data?.startById ?? new Map()} hutCoordsById={data?.hutCoordsById ?? new Map()}
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
            savedTrips={state.trips} savedGraph={data?.graph ?? EMPTY_GRAPH}
            savedRouteCtx={routeCtx ?? { hutCoordsById: new Map(), startById: new Map(), officialById: new Map() }}
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
