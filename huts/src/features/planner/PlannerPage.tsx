import { useCallback, useMemo, useState } from 'react'
import { Alert, Badge, Box, Button, Snackbar, Tab, Tabs, TextField } from '@mui/material'
import { useAppData } from '@/data/appDataContext.js'
import type { AppData } from '@/data/buildAppData.js'
import { useSearchClient } from '@/search/searchClientContext.js'
import type { SearchClient } from '@/search/searchClient.js'
import { useDiscover } from '@/features/discover/useDiscover.js'
import { decodeTripFromHash } from '@/trip/shareLink.js'
import { useTrips } from '@/trip/tripsContext.js'
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
import { makeStartLabel } from '@/data/labels.js'
import { tourToRoute, tripToRoute } from '@/features/map/routes.js'
import type { RouteContext } from '@/features/map/routes.js'
import type { PlannerTour } from '@/tourSearch/plannerTour.js'
import { useMapView } from '@/features/map/useMapView.js'
import { tourKey } from '@/features/map/tourKey.js'
import { tripFromTour } from '@/features/discover/tripFromTour.js'
import { useFirstVisitPrompt } from './useFirstVisitPrompt.js'
import { useTripSession } from '@/features/trip/useTripSession.js'
import { useSidebarNavigation } from './useSidebarNavigation.js'

export default function PlannerPage({ importHash }: { importHash: string | null }) {
  const app = useAppData()
  const client = useSearchClient()
  if (app.status === 'error') return <Alert severity="error">{app.message}</Alert>
  if (app.status === 'loading' || !client) return <PlannerLoading />
  return <Planner data={app.data} client={client} importHash={importHash} />
}

function Planner({ data, client, importHash }: { data: AppData; client: SearchClient; importHash: string | null }) {
  const { state, dispatch } = useTrips()
  const prompt = useFirstVisitPrompt()
  const { mapView, setMapView, routesVisible, restoreView, fitBounds, rememberViewBeforeTrip, restoreViewAfterTrip, fitToPoints } = useMapView()

  const [importDismissed, setImportDismissed] = useState(false)
  const [hoveredTripId, setHoveredTripId] = useState<string | null>(null)

  const {
    form, patchForm, draft, patchDraft, sort, tab: discoverTab, setTab: setDiscoverTab, erweitertOpen, setErweitertOpen,
    search, tours, visibleTours, groups, groupStartPoints, viewTours, setFocusStarts,
    hoveredTourKey, setHoveredTourKey, hoveredStarts, setHoveredStarts, previewTour, setPreviewTour,
  } = useDiscover({ data, client, mapView })

  const startLabel = useMemo(() => makeStartLabel(data.startById), [data])
  const routeCtx = useMemo<RouteContext>(() => ({
    hutCoordsById: data.hutCoordsById, startById: data.startById,
    officialById: new Map(data.officialTours.map((t) => [t.tourId, t])),
  }), [data])

  const showAllTours = useCallback(() => {
    setFocusStarts(null)
    fitToPoints(groupStartPoints)
  }, [groupStartPoints, setFocusStarts, fitToPoints])

  const {
    activeTrip, isDraft, tripLegs, mode, overlapWarnings, setEditing, editor, highlightedLeg, setHighlightedLeg,
    shareNote, setShareNote, shareFallback, share, pendingPick, openDraft, confirmDiscardDraft, cancelPendingPick,
    openedFrom, setOpenedFrom, candidateMarkers, candidateStartCoords, tripHuts, tripEnds,
  } = useTripSession({ data, client, startLabel })
  const { sidebarView, goPlanen, goMeineTouren, goHome, openSavedTrip, openPinnedDraft, backFromTrip } = useSidebarNavigation({
    mode, openedFrom, setOpenedFrom, onBackFromTrip: () => { setEditing(null); restoreViewAfterTrip() },
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
    if (openDraft(trip)) setPreviewTour(null)
  }

  function confirmDiscard() {
    confirmDiscardDraft()
    setPreviewTour(null)
  }

  const importedTrip = useMemo(() => (importHash ? decodeTripFromHash(importHash) : null), [importHash])
  const closeImport = () => { setImportDismissed(true); window.location.hash = '' }

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
                sortKey={sort.key} onSortChange={sort.setKey}
                sortDir={sort.dir} onSortDirChange={sort.setDir}
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
        onDiscard={confirmDiscard}
        onCancel={cancelPendingPick}
      />
      <Snackbar open={shareNote !== null} autoHideDuration={3000} onClose={() => setShareNote(null)} message={shareNote} />
      <Snackbar
        open={state.deleted !== null} message="Tour gelöscht"
        action={<Button color="inherit" size="small" onClick={() => dispatch({ type: 'undoDelete' })}>Rückgängig</Button>}
      />
    </Box>
  )
}
