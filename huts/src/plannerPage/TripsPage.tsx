import { useState } from 'react'
import { Alert, Box, Button, Snackbar, TextField, Typography } from '@mui/material'
import { useTrips } from '../trip/TripsProvider.js'
import { exportTripsJson, parseTripsJson } from '../trip/tripStorage.js'
import type { Trip } from '../trip/trip.js'

function dateRange(trip: Trip): string {
  if (!trip.startDate) return 'ohne Datum'
  const [y, m, d] = trip.startDate.split('-')
  return `ab ${d}.${m}.${y}`
}

export default function TripsPage() {
  const { state, dispatch } = useTrips()
  const [renaming, setRenaming] = useState<{ id: string; name: string } | null>(null)
  const [importError, setImportError] = useState(false)

  function open(id: string) {
    dispatch({ type: 'setActive', id })
    window.location.hash = ''
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
        <Button variant="outlined" color="secondary" onClick={exportBackup} disabled={state.trips.length === 0}>Sicherung exportieren</Button>
        <Button variant="outlined" color="secondary" component="label">
          Sicherung importieren
          <input
            hidden type="file" accept="application/json" aria-label="Sicherung importieren"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) void importBackup(f); e.target.value = '' }}
          />
        </Button>
      </Box>
      {importError && <Alert severity="error" sx={{ mb: 2 }}>Die Datei enthält keine gültige Sicherung.</Alert>}
      {state.trips.length === 0 && <Typography color="text.secondary">Noch keine Touren gespeichert.</Typography>}
      {state.trips.map((trip) => (
        <Box key={trip.id} data-testid={`trip-${trip.id}`} sx={{ display: 'flex', gap: 2, alignItems: 'center', py: 1.5, borderBottom: '1px solid', borderColor: 'divider' }}>
          <Box sx={{ flex: 1 }}>
            {renaming?.id === trip.id ? (
              <Box sx={{ display: 'flex', gap: 1 }}>
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
                  {trip.huts.length} Nächte · {dateRange(trip)} · {trip.partySize} Pers.{state.activeId === trip.id ? ' · aktiv' : ''}
                </Typography>
              </>
            )}
          </Box>
          <Button variant="contained" onClick={() => open(trip.id)}>Öffnen</Button>
          <Button onClick={() => setRenaming({ id: trip.id, name: trip.name })}>Umbenennen</Button>
          <Button color="secondary" onClick={() => dispatch({ type: 'delete', id: trip.id })}>Löschen</Button>
        </Box>
      ))}
      <Snackbar
        open={state.deleted !== null}
        message="Tour gelöscht"
        action={<Button color="inherit" size="small" onClick={() => dispatch({ type: 'undoDelete' })}>Rückgängig</Button>}
      />
    </Box>
  )
}
