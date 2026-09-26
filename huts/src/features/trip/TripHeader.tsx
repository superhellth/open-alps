import { useRef, useState } from 'react'
import { Box, Button, TextField } from '@mui/material'
import BookmarkIcon from '@mui/icons-material/Bookmark'
import BookmarkBorderIcon from '@mui/icons-material/BookmarkBorder'
import ShortcutIcon from '@mui/icons-material/Shortcut'
import type { HutOhrs } from '@/data/buildAppData.js'
import { formatMeters } from '@/format/meters.js'
import { shiftStartDate } from '@/trip/trip.js'
import type { Trip } from '@/trip/trip.js'
import { summarizeLegs } from '@/trip/tripLegs.js'
import type { TripLegs } from '@/trip/tripLegs.js'
import SaveTripDialog from './SaveTripDialog.js'
import Signpost from './Signpost.js'
import StartDateStrip from './StartDateStrip.js'
import TripDateSummary from './TripDateSummary.js'
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

/** The trip's name; a click turns it into an input (Enter/blur commit, Escape cancels). */
function TripTitle({ name, onRename }: { name: string; onRename: (name: string) => void }) {
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(name)
  const cancelled = useRef(false)

  function commit() {
    const next = text.trim()
    setEditing(false)
    if (!cancelled.current && next !== '' && next !== name) onRename(next)
  }
  if (editing) {
    return (
      <TextField
        autoFocus size="small" variant="standard" value={text} sx={styles.titleInput}
        slotProps={{ htmlInput: { 'aria-label': 'Tourname' } }}
        onChange={(e) => setText(e.target.value)} onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') commit()
          if (e.key === 'Escape') { cancelled.current = true; setEditing(false) }
        }}
      />
    )
  }
  return (
    <Box component="button" type="button" sx={styles.titleButton} onClick={() => { cancelled.current = false; setText(name); setEditing(true) }}>
      {name}
    </Box>
  )
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
        title={<TripTitle name={trip.name} onRename={(name) => onChange({ ...trip, name })} />}
        timeH={totals.durationH} subtitle={subtitle}
      />
      <SaveTripDialog
        open={saving} initialName={trip.name}
        onSave={(name) => { setSaving(false); onSave(name) }} onCancel={() => setSaving(false)}
      />
      <TripDateSummary trip={trip} onChange={onChange} />
      <StartDateStrip
        trip={trip} hutIndices={tripLegs.hutIndices} hutOhrsByIndex={hutOhrsByIndex}
        onShift={(days) => onChange(shiftStartDate(trip, days))}
      />
    </Box>
  )
}
