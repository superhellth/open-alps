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
import type { MapCommands, MapMode } from '@/features/map/PlannerMap.js'
import ResultsList from '@/features/discover/ResultsList.js'
import SavedTripsList from '@/features/saved/SavedTripsList.js'
import SidebarHeader from './SidebarHeader.js'
import TripPanel from '@/features/trip/TripPanel.js'
import { makeStartLabel } from '@/data/labels.js'
import { tourMapPoint, tourWaypoints, tripToRoute } from '@/features/map/routes.js'
import type { RouteContext } from '@/features/map/routes.js'
import type { PlannerTour } from '@/tourSearch/plannerTour.js'
import { useMapView } from '@/features/map/useMapView.js'
import { NO_TOURS, tourKey } from '@/tourSearch/tourKey.js'
import { createLegAnchorLookup } from '@/tourSearch/legAnchors.js'
import type { Trip } from '@/trip/trip.js'
import { autoTripName, tripFromTour } from '@/features/discover/tripFromTour.js'
import { useFirstVisitPrompt } from './useFirstVisitPrompt.js'
import { useTripSession } from '@/features/trip/useTripSession.js'
import { useSidebarNavigation } from './useSidebarNavigation.js'
import { styles } from './PlannerPage.styles.js'

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
  const dismissPrompt = prompt.dismiss
  const { mapView, setMapView, restoreView, fitBounds, rememberViewBeforeTrip, restoreViewAfterTrip, fitToPoints } = useMapView()

  const [importDismissed, setImportDismissed] = useState(false)
  const [hoveredTripId, setHoveredTripId] = useState<string | null>(null)

  const routeCtx = useMemo<RouteContext>(() => ({
    hutCoordsById: data.hutCoordsById, startById: data.startById,
    officialById: new Map(data.officialTours.map((t) => [t.tourId, t])),
    hutClassByIndex: data.hutClassByIndex,
    legAnchors: createLegAnchorLookup({
      hutEdges: data.graph.hutEdges, approaches: data.graph.approaches,
      hutCoordsById: data.hutCoordsById, officialTours: data.officialTours,
    }),
  }), [data])
  const tourPoint = useCallback((tour: PlannerTour) => tourMapPoint(tour, routeCtx), [routeCtx])

  const {
    form, patchForm, draft, patchDraft, sort, tab: discoverTab, setTab: setDiscoverTab, erweitertOpen, setErweitertOpen,
    search, tours, visibleTours, groups, viewTours, focusTours, setFocusTours,
    hoveredTourKeys, setHoveredTourKeys,
  } = useDiscover({ data, client, mapView, pointOf: tourPoint })

  const startLabel = useMemo(() => makeStartLabel(data.startById), [data])

  const showAllTours = useCallback(() => {
    setFocusTours(null)
    fitToPoints(tourWaypoints(visibleTours, routeCtx))
  }, [visibleTours, routeCtx, setFocusTours, fitToPoints])

  const {
    activeTrip, isDraft, tripLegs, mode, overlapWarnings, setEditing, editMode, setEditMode, editor, highlightedLeg, setHighlightedLeg,
    shareNote, setShareNote, shareFallback, share, pendingPick, openDraft, confirmDiscardDraft, cancelPendingPick,
    openedFrom, setOpenedFrom, candidateMarkers, candidateStartCoords, tripHuts, tripEnds, tripStopNames,
  } = useTripSession({ data, client, startLabel })
  const { sidebarView, goPlanen, goMeineTouren, goHome, openSavedTrip, openPinnedDraft, backFromTrip } = useSidebarNavigation({
    mode, openedFrom, setOpenedFrom, onBackFromTrip: () => { setEditing(null); restoreViewAfterTrip() },
  })

  const tripRoute = useMemo(
    () => (mode === 'trip' && activeTrip && tripLegs ? tripToRoute(activeTrip, tripLegs, routeCtx) : null),
    [mode, activeTrip, tripLegs, routeCtx])

  const pick = useCallback((tour: PlannerTour) => {
    rememberViewBeforeTrip()
    const trip = tripFromTour(tour, {
      hutIds: data.graph.hutEdges.hutIds, startById: data.startById, hutNameById: data.hutNameById, form, draft,
    })
    if (!trip) return
    if (openDraft(trip)) setHoveredTourKeys(NO_TOURS)
  }, [rememberViewBeforeTrip, data, form, draft, openDraft, setHoveredTourKeys])

  function resetName(trip: Trip): string {
    const hutIds = data.graph.hutEdges.hutIds
    const nameOf = (guid: string) => data.hutNameById.get(hutIds.indexOf(guid)) ?? '?'
    const official = trip.source ? data.officialTours.find((t) => t.tourId === trip.source?.tourId) : undefined
    return autoTripName({ first: nameOf(trip.huts[0]), last: nameOf(trip.huts[trip.huts.length - 1]) }, official)
  }

  function confirmDiscard() {
    confirmDiscardDraft()
    setHoveredTourKeys(NO_TOURS)
  }

  const mapMode = useMemo<MapMode>(() => {
    if (sidebarView === 'saved') {
      return { kind: 'saved', trips: state.trips, graph: data.graph, routeCtx, hoveredTripId, onHoverTrip: setHoveredTripId, onOpen: openSavedTrip }
    }
    if (mode === 'trip' && tripLegs) {
      return {
        kind: 'trip', tripLegs, tripHuts, tripEnds, stopNames: tripStopNames, candidates: candidateMarkers,
        hutCoordsById: data.hutCoordsById, candidateStartCoords,
        activeLabel: editor.activeLabel, onPickCandidate: editor.pickCandidate,
        onCancelEditing: () => setEditing(null), onHoverLeg: setHighlightedLeg,
      }
    }
    return {
      kind: 'discover', groups, dimmed: search.status === 'searching', startById: data.startById,
      allTours: visibleTours, routeCtx, hutNameById: data.hutNameById, hoveredTourKeys, focusTours,
      onNavigate: () => { dismissPrompt(); setDiscoverTab('results') },
      onFocusTours: (keys) => setFocusTours(keys && new Set(keys)),
      onViewChange: setMapView, onHoverTours: setHoveredTourKeys, onPickRoute: pick,
    }
  }, [sidebarView, mode, tripLegs, state.trips, data, routeCtx, hoveredTripId, openSavedTrip, tripHuts, tripEnds, tripStopNames, candidateMarkers, candidateStartCoords,
    editor.activeLabel, editor.pickCandidate, setEditing, setHighlightedLeg, groups, search.status, visibleTours, hoveredTourKeys, focusTours,
    dismissPrompt, setDiscoverTab, setFocusTours, setMapView, setHoveredTourKeys, pick])
  const mapCommands = useMemo<MapCommands>(() => ({
    route: mode === 'trip' ? tripRoute : null, fitRoute: mode === 'trip', highlightedLeg, restoreView, fitBounds,
    onMapClick: () => { dismissPrompt(); setFocusTours(null) },
  }), [mode, tripRoute, highlightedLeg, restoreView, fitBounds, dismissPrompt, setFocusTours])

  const importedTrip = useMemo(() => (importHash ? decodeTripFromHash(importHash) : null), [importHash])
  const closeImport = () => { setImportDismissed(true); window.location.hash = '' }

  return (
    <Box sx={styles.root}>
      <SidebarHeader view={sidebarView} savedCount={state.trips.length} onWordmark={goHome} onPlanen={goPlanen} onMeineTouren={goMeineTouren} />
      <Box sx={styles.body}>
        <Box sx={styles.sidebar}>
          {/* Kept mounted (only hidden) while a trip or the saved list is showing, so "← Ergebnisse"
              restores the list's scroll position. */}
          <Box hidden={sidebarView !== 'discover'}>
            <Tabs
              value={discoverTab} onChange={(_e, v) => setDiscoverTab(v)} variant="fullWidth"
              sx={styles.discoverTabs}
            >
              <Tab value="filters" label="Filter" />
              <Tab
                value="results"
                label={<Badge color="primary" badgeContent={visibleTours.length} max={99} sx={styles.resultsBadge}>Ergebnisse</Badge>}
              />
            </Tabs>
            <Box hidden={discoverTab !== 'filters'} sx={{ position: 'relative' }}>
              <FilterBar
                form={form} onFormChange={patchForm} draft={draft} onDraftChange={patchDraft}
                disabled={false} searching={search.status === 'searching'}
                onErweitertOpenChange={setErweitertOpen}
              />
              {search.status === 'done' && visibleTours.length > 0 && (
                <Box sx={styles.resultsBar(erweitertOpen)}>
                  <Button variant="text" onClick={() => setDiscoverTab('results')}>
                    Zu den Ergebnissen ({visibleTours.length}) →
                  </Button>
                </Box>
              )}
            </Box>
            <Box hidden={discoverTab !== 'results'}>
              <ResultsList
                tours={viewTours} totalCount={visibleTours.length} onShowAll={showAllTours}
                isHighlighted={(t) => hoveredTourKeys.has(tourKey(t))}
                noMatches={search.status === 'done' && tours.length === 0}
                sortKey={sort.key} onSortChange={sort.setKey}
                sortDir={sort.dir} onSortDirChange={sort.setDir}
                hutNameById={data.hutNameById} onPreview={(t) => setHoveredTourKeys(t ? new Set([tourKey(t)]) : NO_TOURS)} onPick={pick}
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
              isDraft={isDraft} onSave={(name) => dispatch({ type: 'saveDraft', name })}
              onUnsave={() => dispatch({ type: 'unsave', id: activeTrip.id, name: resetName(activeTrip) })}
              onChange={(trip) => dispatch({ type: isDraft ? 'updateDraft' : 'update', trip })}
              onBack={backFromTrip} backLabel={openedFrom === 'saved' ? '← Meine Touren' : '← Ergebnisse'}
              highlightedLeg={highlightedLeg} onHoverLeg={setHighlightedLeg}
              editor={editor} editMode={editMode} onEditModeChange={setEditMode}
              warnings={overlapWarnings} onShare={share}
            />
          )}
          {shareFallback && (
            <Box sx={styles.shareFallback}>
              <TextField size="small" fullWidth label="Link zum Teilen" value={shareFallback} slotProps={{ htmlInput: { readOnly: true } }} onFocus={(e) => e.target.select()} />
            </Box>
          )}
        </Box>

        <Box sx={styles.mapPane}>
          <PlannerMap mode={mapMode} commands={mapCommands} />
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
      <Snackbar
        open={state.unsaved !== null} message="Aus Meine Touren entfernt" autoHideDuration={6000}
        onClose={(_, reason) => { if (reason !== 'clickaway') dispatch({ type: 'dismissUnsave' }) }}
        action={<Button color="inherit" size="small" onClick={() => dispatch({ type: 'undoUnsave' })}>Rückgängig</Button>}
      />
    </Box>
  )
}
