import { TextField } from '@mui/material'
import type { Trip } from '@/trip/trip.js'

export default function TripFooter({ trip, onChange }: { trip: Trip; onChange: (trip: Trip) => void }) {
  return (
    <TextField
      size="small" label="Notizen" multiline minRows={2} value={trip.notes ?? ''}
      onChange={(e) => onChange({ ...trip, notes: e.target.value })}
    />
  )
}
