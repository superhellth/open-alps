import type { ReactNode } from 'react'
import { Box, Button, TextField, Typography } from '@mui/material'
import type { AppData } from '../data/buildAppData.js'
import { formatSignpostTime } from '../format/signpostTime.js'
import { summarizeLegs } from '../tourSearch/tripLegs.js'
import type { TripLegs } from '../tourSearch/tripLegs.js'
import { shiftStartDate } from '../trip/trip.js'
import type { BookingStatus, Trip } from '../trip/trip.js'
import StageList from './StageList.js'
import StartDateStrip from './StartDateStrip.js'
import { useTripAvailability } from './useTripAvailability.js'

export interface TripPanelProps {
  trip: Trip
  tripLegs: TripLegs
  data: AppData
  startLabel: (startId: number) => string
  onChange: (trip: Trip) => void
  onBack: () => void
  onHoverLeg: (index: number | null) => void
  renderStageControls?: (night: number) => ReactNode
  /** Rendered between the header and the stages (start/exit pickers, candidate list). */
  extra?: ReactNode
  warnings?: string[]
  onShare?: () => void
}

export default function TripPanel({
  trip, tripLegs, data, startLabel, onChange, onBack, onHoverLeg, renderStageControls, extra, warnings, onShare,
}: TripPanelProps) {
  const nightViews = useTripAvailability(trip, tripLegs.hutIndices, data.hutOhrsByIndex)
  const totals = summarizeLegs(tripLegs.legs)

  const setStatus = (night: number, status: BookingStatus) =>
    onChange({ ...trip, nights: trip.nights.map((n, i) => (i === night ? { status } : n)) })

  return (
    <Box sx={{ p: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
        <Button size="small" color="secondary" onClick={onBack}>← Ergebnisse</Button>
        {onShare && <Button size="small" color="secondary" onClick={onShare}>Link teilen</Button>}
      </Box>

      <TextField size="small" label="Name" value={trip.name} onChange={(e) => onChange({ ...trip, name: e.target.value })} />
      <Typography variant="body2" color="text.secondary">
        {trip.huts.length} Nächte · {formatSignpostTime(totals.durationH)} · ↑ {Math.round(totals.ascentM).toLocaleString('de-DE')} m
      </Typography>

      <Box sx={{ display: 'flex', gap: 1 }}>
        <TextField
          size="small" type="date" label="Startdatum (erste Nacht)" value={trip.startDate ?? ''}
          slotProps={{ inputLabel: { shrink: true } }}
          onChange={(e) => onChange({ ...trip, startDate: e.target.value || null })}
        />
        <TextField
          size="small" type="number" label="Personen" value={trip.partySize} sx={{ width: 100 }}
          slotProps={{ htmlInput: { min: 1, max: 9 } }}
          onChange={(e) => onChange({ ...trip, partySize: Math.min(9, Math.max(1, Number(e.target.value) || 1)) })}
        />
      </Box>

      <StartDateStrip
        trip={trip} hutIndices={tripLegs.hutIndices} hutOhrsByIndex={data.hutOhrsByIndex}
        onShift={(days) => onChange(shiftStartDate(trip, days))}
      />

      {extra}

      <StageList
        trip={trip} tripLegs={tripLegs} hutNameById={data.hutNameById} hutOhrsByIndex={data.hutOhrsByIndex}
        startLabel={startLabel} nightViews={nightViews} onStatusChange={setStatus} onHoverLeg={onHoverLeg}
        renderStageControls={renderStageControls} warnings={warnings}
      />

      <TextField
        size="small" label="Notizen" multiline minRows={2} value={trip.notes ?? ''}
        onChange={(e) => onChange({ ...trip, notes: e.target.value })}
      />
    </Box>
  )
}
