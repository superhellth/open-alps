import { useState } from 'react'
import { Alert, Box, Button, IconButton, Menu, MenuItem, TextField, Typography } from '@mui/material'
import { legsFromTrip } from '@/trip/tripLegs.js'
import type { TripGraph } from '@/tourSearch/types.js'
import { useTrips } from '@/trip/tripsContext.js'
import { exportTripsJson, parseTripsJson } from '@/trip/tripStorage.js'
import type { Trip } from '@/trip/trip.js'
import { styles } from './SavedTripsList.styles.js'

function dateRange(trip: Trip): string {
  if (!trip.startDate) return 'ohne Datum'
  const [y, m, d] = trip.startDate.split('-')
  return `ab ${d}.${m}.${y}`
}

function bookingSummary(trip: Trip): string {
  const confirmed = trip.nights.filter((n) => n.status === 'confirmed').length
  return `${confirmed}/${trip.nights.length} bestätigt`
}

export interface SavedTripsListProps {
  graph: TripGraph
  onOpen: (id: string) => void
  onOpenDraft: () => void
  onPlanen: () => void
  hoveredTripId: string | null
  onHoverTrip: (id: string | null) => void
}

// Carries over TripsPage's list/export/import/rename/delete logic; per-night editing (booking
// status, notes) moved to TripPanel/StageList, where the trip is visible on the map.
export default function SavedTripsList({ graph, onOpen, onOpenDraft, onPlanen, hoveredTripId, onHoverTrip }: SavedTripsListProps) {
  const { state, dispatch } = useTrips()
  const [renaming, setRenaming] = useState<{ id: string; name: string } | null>(null)
  const [menuFor, setMenuFor] = useState<{ id: string; anchor: HTMLElement } | null>(null)
  const [headerMenuAnchor, setHeaderMenuAnchor] = useState<HTMLElement | null>(null)
  const [importError, setImportError] = useState(false)

  function exportBackup() {
    const blob = new Blob([exportTripsJson(state)], { type: 'application/json' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = 'open-alps-touren.json'
    link.click()
    URL.revokeObjectURL(link.href)
  }

  async function importBackup(file: File) {
    const trips = parseTripsJson(await file.text())
    if (trips === null) { setImportError(true); return }
    setImportError(false)
    dispatch({ type: 'import', trips })
  }

  const rows = [...state.trips].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))

  return (
    <Box sx={styles.root}>
      <Box sx={styles.header}>
        <Typography variant="h6" component="h2" sx={{ flex: 1 }}>Meine Touren</Typography>
        <IconButton aria-label="Weitere Aktionen" onClick={(e) => setHeaderMenuAnchor(e.currentTarget)}>
          <Typography component="span" sx={styles.menuGlyph}>⋮</Typography>
        </IconButton>
        <Menu open={headerMenuAnchor !== null} anchorEl={headerMenuAnchor} onClose={() => setHeaderMenuAnchor(null)}>
          <MenuItem disabled={state.trips.length === 0} onClick={() => { exportBackup(); setHeaderMenuAnchor(null) }}>
            Exportieren (Datei)
          </MenuItem>
          <MenuItem component="label">
            Importieren
            <input
              hidden type="file" accept="application/json" aria-label="Touren importieren"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) void importBackup(f); e.target.value = ''; setHeaderMenuAnchor(null) }}
            />
          </MenuItem>
        </Menu>
      </Box>
      {importError && <Alert severity="error">Die Datei enthält keine gültigen Touren.</Alert>}

      {state.draft && (
        <Box
          role="button" tabIndex={0} onClick={onOpenDraft} onKeyDown={(e) => { if (e.key === 'Enter') onOpenDraft() }}
          sx={styles.draftRow}
        >
          <Typography sx={styles.strong}>Entwurf · nicht gespeichert</Typography>
        </Box>
      )}

      {rows.length === 0 && !state.draft && (
        <Typography color="text.secondary">
          Noch keine Touren gespeichert.{' '}
          <Box component="a" href="#" onClick={(e) => { e.preventDefault(); onPlanen() }}>Tour planen</Box>
        </Typography>
      )}

      {rows.map((trip) => {
        const changed = legsFromTrip(graph, trip).changed.some(Boolean)
        return (
          <Box
            key={trip.id} data-testid={`trip-${trip.id}`}
            onMouseEnter={() => onHoverTrip(trip.id)} onMouseLeave={() => onHoverTrip(null)}
            sx={styles.tripCard(hoveredTripId === trip.id)}
          >
            <Box sx={styles.tripRow}>
              <Box
                role="button" tabIndex={0} onClick={() => onOpen(trip.id)}
                onKeyDown={(e) => { if (e.key === 'Enter') onOpen(trip.id) }}
                sx={styles.tripBody}
              >
                {renaming?.id === trip.id ? (
                  <Box sx={styles.renameRow} onClick={(e) => e.stopPropagation()}>
                    <TextField size="small" label="Name" value={renaming.name} onChange={(e) => setRenaming({ id: trip.id, name: e.target.value })} />
                    <Button
                      variant="contained"
                      onClick={() => { dispatch({ type: 'update', trip: { ...trip, name: renaming.name.trim() || trip.name } }); setRenaming(null) }}
                    >
                      Speichern
                    </Button>
                  </Box>
                ) : (
                  <>
                    <Box sx={styles.tripTitleRow}>
                      <Typography sx={styles.strong}>{trip.name}</Typography>
                      {changed && <Typography variant="caption" sx={styles.strong}>geändert</Typography>}
                    </Box>
                    <Typography variant="caption" color="text.secondary">
                      {trip.huts.length} Nächte · {dateRange(trip)} · {trip.partySize} Pers. · {bookingSummary(trip)}
                    </Typography>
                  </>
                )}
              </Box>
              <IconButton aria-label="Weitere Aktionen" onClick={(e) => setMenuFor({ id: trip.id, anchor: e.currentTarget })}>
                <Typography component="span" sx={styles.menuGlyph}>⋮</Typography>
              </IconButton>
            </Box>
          </Box>
        )
      })}

      <Menu open={menuFor !== null} anchorEl={menuFor?.anchor ?? null} onClose={() => setMenuFor(null)}>
        <MenuItem onClick={() => {
          if (menuFor) setRenaming({ id: menuFor.id, name: state.trips.find((t) => t.id === menuFor.id)?.name ?? '' })
          setMenuFor(null)
        }}>
          Umbenennen
        </MenuItem>
        <MenuItem onClick={() => { if (menuFor) dispatch({ type: 'delete', id: menuFor.id }); setMenuFor(null) }}>
          Löschen
        </MenuItem>
      </Menu>
    </Box>
  )
}
