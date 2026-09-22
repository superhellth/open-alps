import { useState } from 'react'
import { Alert, Box, Button, Collapse, IconButton, Menu, MenuItem, Snackbar, TextField, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material'
import { useTrips } from '../trip/TripsProvider.js'
import { exportTripsJson, parseTripsJson } from '../trip/tripStorage.js'
import type { BookingStatus, Trip } from '../trip/trip.js'

const STATUS_LABEL: Record<BookingStatus, string> = { open: 'offen', requested: 'angefragt', confirmed: 'bestätigt' }

function dateRange(trip: Trip): string {
  if (!trip.startDate) return 'ohne Datum'
  const [y, m, d] = trip.startDate.split('-')
  return `ab ${d}.${m}.${y}`
}

function bookingSummary(trip: Trip): string {
  const confirmed = trip.nights.filter((n) => n.status === 'confirmed').length
  return `${confirmed}/${trip.nights.length} Nächte bestätigt`
}

export default function TripsPage() {
  const { state, dispatch } = useTrips()
  const [renaming, setRenaming] = useState<{ id: string; name: string } | null>(null)
  const [menuFor, setMenuFor] = useState<{ id: string; anchor: HTMLElement } | null>(null)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [importError, setImportError] = useState(false)

  function open(id: string) {
    dispatch({ type: 'setActive', id })
    window.location.hash = ''
  }

  function toggleExpanded(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function setNightStatus(trip: Trip, night: number, status: BookingStatus) {
    dispatch({ type: 'update', trip: { ...trip, nights: trip.nights.map((n, i) => (i === night ? { status } : n)) } })
  }

  function setNotes(trip: Trip, notes: string) {
    dispatch({ type: 'update', trip: { ...trip, notes } })
  }

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

  return (
    <Box sx={{ flex: 1, overflowY: 'auto', p: 3, maxWidth: 800 }}>
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', mb: 2 }}>
        <Typography variant="h6" component="h2" sx={{ flex: 1 }}>Meine Touren</Typography>
        <Button variant="outlined" color="secondary" onClick={exportBackup} disabled={state.trips.length === 0}>Touren exportieren (Datei)</Button>
        <Button variant="outlined" color="secondary" component="label">
          Touren importieren
          <input
            hidden type="file" accept="application/json" aria-label="Touren importieren"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) void importBackup(f); e.target.value = '' }}
          />
        </Button>
      </Box>
      {importError && <Alert severity="error" sx={{ mb: 2 }}>Die Datei enthält keine gültigen Touren.</Alert>}
      {state.trips.length === 0 && <Typography color="text.secondary">Noch keine Touren gespeichert.</Typography>}
      {state.trips.map((trip) => (
        <Box key={trip.id} data-testid={`trip-${trip.id}`} sx={{ borderBottom: '1px solid', borderColor: 'divider' }}>
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', py: 1.5 }}>
            <Box
              role="button" tabIndex={0} onClick={() => open(trip.id)}
              onKeyDown={(e) => { if (e.key === 'Enter') open(trip.id) }}
              sx={{ flex: 1, cursor: 'pointer' }}
            >
              {renaming?.id === trip.id ? (
                <Box sx={{ display: 'flex', gap: 1 }} onClick={(e) => e.stopPropagation()}>
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
                  <Typography sx={{ fontWeight: 600 }}>{trip.name}</Typography>
                  <Typography variant="caption" color="text.secondary">
                    {trip.huts.length} Nächte · {dateRange(trip)} · {trip.partySize} Pers. · {bookingSummary(trip)}
                    {state.activeId === trip.id ? ' · aktiv' : ''}
                  </Typography>
                </>
              )}
            </Box>
            <Button size="small" onClick={() => toggleExpanded(trip.id)}>{expanded.has(trip.id) ? 'Weniger' : 'Details'}</Button>
            <IconButton aria-label="Weitere Aktionen" onClick={(e) => setMenuFor({ id: trip.id, anchor: e.currentTarget })}>
              <Typography component="span" sx={{ fontWeight: 700 }}>⋮</Typography>
            </IconButton>
          </Box>
          <Collapse in={expanded.has(trip.id)}>
            <Box sx={{ pb: 2, display: 'flex', flexDirection: 'column', gap: 1.5 }}>
              {trip.nights.map((n, i) => (
                <Box key={i} sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
                  <Typography variant="body2" sx={{ minWidth: 80 }}>Nacht {i + 1}</Typography>
                  <ToggleButtonGroup
                    size="small" exclusive value={n.status} aria-label={`Buchungsstatus Nacht ${i + 1}`}
                    onChange={(_e, next: BookingStatus | null) => { if (next) setNightStatus(trip, i, next) }}
                  >
                    {(Object.keys(STATUS_LABEL) as BookingStatus[]).map((s) => (
                      <ToggleButton key={s} value={s} sx={{ textTransform: 'none', py: 0.25 }}>{STATUS_LABEL[s]}</ToggleButton>
                    ))}
                  </ToggleButtonGroup>
                </Box>
              ))}
              <TextField
                size="small" label="Notizen" multiline minRows={2} value={trip.notes ?? ''}
                onChange={(e) => setNotes(trip, e.target.value)}
              />
            </Box>
          </Collapse>
        </Box>
      ))}
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
      <Snackbar
        open={state.deleted !== null}
        message="Tour gelöscht"
        action={<Button color="inherit" size="small" onClick={() => dispatch({ type: 'undoDelete' })}>Rückgängig</Button>}
      />
    </Box>
  )
}
