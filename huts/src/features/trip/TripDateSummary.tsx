import { useState } from 'react'
import type { MouseEvent } from 'react'
import { Box, Button, Popover, TextField } from '@mui/material'
import type { Trip } from '@/trip/trip.js'

function summaryText(trip: Trip): string {
  const party = `${trip.partySize} Pers.`
  if (!trip.startDate) return `ohne Datum · ${party}`
  const [y, m, d] = trip.startDate.split('-').map(Number)
  const last = new Date(Date.UTC(y, m - 1, d + trip.huts.length))
  const fmt = (dt: Date) => dt.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', timeZone: 'UTC' })
  return `${fmt(new Date(Date.UTC(y, m - 1, d)))}–${fmt(last)} · ${party}`
}

export default function TripDateSummary({ trip, onChange }: { trip: Trip; onChange: (trip: Trip) => void }) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null)
  return (
    <>
      <Button
        size="small" color="secondary" onClick={(e: MouseEvent<HTMLElement>) => setAnchor(e.currentTarget)}
        sx={{ textTransform: 'none', justifyContent: 'flex-start' }}
      >
        {summaryText(trip)}
      </Button>
      <Popover open={anchor !== null} anchorEl={anchor} onClose={() => setAnchor(null)} anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}>
        <Box sx={{ p: 2, display: 'flex', gap: 1 }}>
          <TextField
            size="small" type="date" label="Startdatum (erste Nacht)" value={trip.startDate ?? ''}
            slotProps={{ inputLabel: { shrink: true } }}
            onChange={(e) => onChange({ ...trip, startDate: e.target.value || null })}
          />
          <TextField
            size="small" type="number" label="Personen" value={trip.partySize} sx={{ width: 100 }}
            slotProps={{ htmlInput: { min: 1, max: 25 } }}
            onChange={(e) => onChange({ ...trip, partySize: Math.min(25, Math.max(1, Number(e.target.value) || 1)) })}
          />
        </Box>
      </Popover>
    </>
  )
}
