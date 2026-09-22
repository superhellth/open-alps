import type { ReactNode } from 'react'
import { Box, Button, Chip, TextField, Typography } from '@mui/material'
import type { AppData } from '../data/buildAppData.js'
import { formatSignpostTime } from '../format/signpostTime.js'
import { summarizeLegs } from '../tourSearch/tripLegs.js'
import type { TripLegs } from '../tourSearch/tripLegs.js'
import { shiftStartDate } from '../trip/trip.js'
import type { Trip } from '../trip/trip.js'
import StageList from './StageList.js'
import StartDateStrip from './StartDateStrip.js'
import TripDateSummary from './TripDateSummary.js'
import { useTripAvailability } from './useTripAvailability.js'

export interface TripPanelProps {
  trip: Trip
  tripLegs: TripLegs
  data: AppData
  startLabel: (startId: number) => string
  isDraft: boolean
  onChange: (trip: Trip) => void
  onSave: () => void
  onBack: () => void
  onHoverLeg: (index: number | null) => void
  renderStageControls?: (night: number) => ReactNode
  /** Rendered between the header and the stages (start/exit pickers, candidate list). */
  extra?: ReactNode
  warnings?: string[]
  onShare?: () => void
}

export default function TripPanel({
  trip, tripLegs, data, startLabel, isDraft, onChange, onSave, onBack, onHoverLeg, renderStageControls, extra, warnings, onShare,
}: TripPanelProps) {
  const nightViews = useTripAvailability(trip, tripLegs.hutIndices, data.hutOhrsByIndex)
  const totals = summarizeLegs(tripLegs.legs)

  return (
    <Box sx={{ p: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
        <Button size="small" color="secondary" onClick={onBack}>← Ergebnisse</Button>
        {onShare && <Button size="small" color="secondary" onClick={onShare}>Link teilen</Button>}
      </Box>

      {isDraft ? (
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
          <Chip label="Entwurf" size="small" color="secondary" />
          <Button size="small" variant="contained" onClick={onSave}>Speichern</Button>
        </Box>
      ) : (
        <TextField size="small" label="Name" value={trip.name} onChange={(e) => onChange({ ...trip, name: e.target.value })} />
      )}

      <Typography variant="body2" color="text.secondary">
        {trip.huts.length} Nächte · {formatSignpostTime(totals.durationH)} · ↑ {Math.round(totals.ascentM).toLocaleString('de-DE')} m
      </Typography>

      <TripDateSummary trip={trip} onChange={onChange} />

      <StartDateStrip
        trip={trip} hutIndices={tripLegs.hutIndices} hutOhrsByIndex={data.hutOhrsByIndex}
        onShift={(days) => onChange(shiftStartDate(trip, days))}
      />

      {extra}

      <StageList
        trip={trip} tripLegs={tripLegs} hutNameById={data.hutNameById} hutOhrsByIndex={data.hutOhrsByIndex}
        startLabel={startLabel} nightViews={nightViews} onHoverLeg={onHoverLeg}
        renderStageControls={renderStageControls} warnings={warnings}
      />
    </Box>
  )
}
