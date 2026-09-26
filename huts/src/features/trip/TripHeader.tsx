import { useState } from 'react'
import { Box, Button, Typography } from '@mui/material'
import BookmarkIcon from '@mui/icons-material/Bookmark'
import BookmarkBorderIcon from '@mui/icons-material/BookmarkBorder'
import ShortcutIcon from '@mui/icons-material/Shortcut'
import type { HutOhrs } from '@/data/buildAppData.js'
import { formatMeters } from '@/format/meters.js'
import type { Trip } from '@/trip/trip.js'
import { summarizeLegs } from '@/trip/tripLegs.js'
import type { TripLegs } from '@/trip/tripLegs.js'
import PartySizeStepper from '@/ui/PartySizeStepper.js'
import SaveTripDialog from './SaveTripDialog.js'
import Signpost from './Signpost.js'
import TripDatePicker from './TripDatePicker.js'
import { styles } from './TripHeader.styles.js'

const DRAFT_MARK = 'nicht gespeichert'

export interface TripHeaderProps {
  trip: Trip
  tripLegs: TripLegs
  hutOhrsByIndex: Map<number, HutOhrs>
  isDraft: boolean
  onChange: (trip: Trip) => void
  /** Called with the name entered in the save dialog. */
  onSave: (name: string) => void
  /** Removes a saved trip from Meine Touren; the planner offers undo. */
  onUnsave: () => void
  onBack: () => void
  backLabel: string
  onShare?: () => void
}

export default function TripHeader({ trip, tripLegs, hutOhrsByIndex, isDraft, onChange, onSave, onUnsave, onBack, backLabel, onShare }: TripHeaderProps) {
  const totals = summarizeLegs(tripLegs.legs)
  const km = Math.round(totals.distanceM / 1000).toLocaleString('de-DE')
  const stats = `${trip.huts.length} Nächte · ${km} km · ↑ ${formatMeters(totals.ascentM)} ↓ ${formatMeters(totals.descentM)}`
  const [saving, setSaving] = useState(false)
  const subtitle = isDraft ? `${DRAFT_MARK} · ${stats}` : stats

  return (
    <Box sx={styles.root}>
      <Box sx={styles.topRow}>
        <Button size="small" color="secondary" onClick={onBack}>{backLabel}</Button>
        <Box sx={styles.actions}>
          {onShare && <Button size="small" color="secondary" startIcon={<ShortcutIcon />} onClick={onShare}>Teilen</Button>}
          {isDraft
            ? <Button size="small" color="secondary" startIcon={<BookmarkBorderIcon />} onClick={() => setSaving(true)}>Merken</Button>
            : <Button size="small" color="secondary" startIcon={<BookmarkIcon />} onClick={onUnsave}>Gespeichert</Button>}
        </Box>
      </Box>
      <Signpost
        title={trip.name}
        timeH={totals.durationH} subtitle={subtitle}
      />
      <SaveTripDialog
        open={saving} initialName={trip.name}
        onSave={(name) => { setSaving(false); onSave(name) }} onCancel={() => setSaving(false)}
      />
      <Box sx={styles.twoColumns}>
        <Box sx={styles.dateColumn}>
          <Typography variant="subtitle2">Wann?</Typography>
          <TripDatePicker trip={trip} hutIndices={tripLegs.hutIndices} hutOhrsByIndex={hutOhrsByIndex} onChange={onChange} />
        </Box>
        <Box>
          <Typography variant="subtitle2">Wie viele?</Typography>
          <PartySizeStepper value={trip.partySize} onChange={(partySize) => onChange({ ...trip, partySize })} />
        </Box>
      </Box>
    </Box>
  )
}
