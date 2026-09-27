import { Button, Dialog, DialogActions, DialogContent, DialogTitle, Typography } from '@mui/material'
import type { Trip } from '@/trip/trip.js'

export default function ImportTripDialog({ trip, onImport, onDiscard }: { trip: Trip | null; onImport: () => void; onDiscard: () => void }) {
  return (
    <Dialog open={trip !== null} onClose={onDiscard}>
      <DialogTitle>Geteilte Tour übernehmen?</DialogTitle>
      <DialogContent>
        {trip && (
          <>
            <Typography sx={{ fontWeight: 600 }}>{trip.name}</Typography>
            <Typography variant="body2" color="text.secondary">
              {trip.huts.length} Nächte{trip.startDate ? ` · ab ${trip.startDate.split('-').reverse().join('.')}` : ''} · {trip.partySize} Pers.
            </Typography>
          </>
        )}
      </DialogContent>
      <DialogActions>
        <Button color="secondary" onClick={onDiscard}>Verwerfen</Button>
        <Button variant="contained" onClick={onImport}>In meine Touren übernehmen</Button>
      </DialogActions>
    </Dialog>
  )
}
