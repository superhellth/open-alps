import { useState } from 'react'
import { Box, Button, Typography } from '@mui/material'
import { addUtcDays } from '@/availability/formatDate.js'
import type { HutOhrs } from '@/data/buildAppData.js'
import type { Trip } from '@/trip/trip.js'
import type { TripLegs } from '@/trip/tripLegs.js'
import CandidateList from './CandidateList.js'
import NightChip from './NightChip.js'
import RailRow from './Rail.js'
import StageBooking from './StageBooking.js'
import StageLeg from './StageLeg.js'
import StageNode from './StageNode.js'
import type { TripEditor } from './TripEditor.js'
import type { NightView } from './useTripAvailability.js'
import { styles } from './StageList.styles.js'

export interface StageListProps {
  trip: Trip
  tripLegs: TripLegs
  hutNameById: Map<number, string>
  hutOhrsByIndex: Map<number, HutOhrs>
  startLabel: (startId: number) => string
  nightViews: NightView[] | null
  /** The leg hovered in the list, on the map or on the profile; its stretch of the rail turns yellow. */
  highlightedLeg: number | null
  onHoverLeg: (index: number | null) => void
  editor: TripEditor
  editMode: boolean
  onEditModeChange: (on: boolean) => void
  warnings?: string[]
}

const CHANGED_TEXT = 'Seit dem Speichern geändert – nicht mehr im Wegenetz'
const shortDate = (d: Date) => d.toLocaleDateString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit', timeZone: 'UTC' })

/** The trip as a timeline: start, then per night the leg walked to it and the hut, then the exit leg and
 *  the destination. Legs are the hover targets; a hut's face opens its booking detail; editing controls
 *  appear only in edit mode. Leg i arrives at night i, leg `huts.length` is the exit. */
export default function StageList({
  trip, tripLegs, hutNameById, hutOhrsByIndex, startLabel, nightViews, highlightedLeg, onHoverLeg,
  editor, editMode, onEditModeChange, warnings = [],
}: StageListProps) {
  const [expanded, setExpanded] = useState<ReadonlySet<number>>(new Set())
  const firstNight = trip.startDate ? new Date(trip.startDate) : null
  const nights = trip.huts.length
  const canEdit = editMode && editor.editable
  const editing = editor.editing
  const candidates = <CandidateList editor={editor} hutNameById={hutNameById} startLabel={startLabel} />
  const toggle = (i: number) => setExpanded((prev) => {
    const next = new Set(prev)
    if (!next.delete(i)) next.add(i)
    return next
  })
  const leg = (i: number) => (
    <StageLeg index={i} leg={tripLegs.legs[i]} highlighted={highlightedLeg === i} onHover={onHoverLeg} />
  )
  const addButton = (side: 'first' | 'last', label: string) => canEdit && (
    <RailRow>
      <Button size="small" color="secondary" sx={styles.addButton} onClick={() => editor.startExtend(side)}>{label}</Button>
      {editing?.kind === 'extend' && editing.side === side && candidates}
    </RailRow>
  )

  return (
    <Box sx={styles.root}>
      <Box sx={styles.heading}>
        <Typography variant="subtitle1" component="h2">Etappen</Typography>
        <Button size="small" color="secondary" onClick={() => { setExpanded(new Set()); onEditModeChange(!editMode) }}>
          {editMode ? 'Fertig' : 'Bearbeiten'}
        </Button>
      </Box>

      <Box>
        <RailRow node="dot" rail="from-dot">
          <Box data-node="start" sx={styles.endLine}>
            <Typography variant="body2" sx={styles.endLabel}>Start: {startLabel(trip.start.startId)}</Typography>
            {canEdit && <Button size="small" color="secondary" aria-label="Start ändern" onClick={() => editor.startEndpoint('start')}>ändern</Button>}
          </Box>
          {editing?.kind === 'start' && candidates}
        </RailRow>

        {addButton('first', '+ Etappe voranstellen')}

        {trip.huts.map((_guid, i) => {
          const hutIndex = tripLegs.hutIndices[i]
          const changed = tripLegs.changed[i]
          const ohrs = hutIndex === null ? undefined : hutOhrsByIndex.get(hutIndex)
          const date = firstNight ? addUtcDays(firstNight, i) : null
          const view = date ? nightViews?.[i] : undefined
          const open = expanded.has(i) && !editMode && !changed
          const meta = changed ? CHANGED_TEXT : view && <NightChip view={view} />
          return (
            <Box key={i}>
              {leg(i)}
              <StageNode
                number={i + 1}
                title={hutIndex === null ? 'Unbekannte Hütte' : hutNameById.get(hutIndex) ?? String(hutIndex)}
                date={date && shortDate(date)} meta={meta} changed={changed} editMode={editMode} expanded={open} onToggleExpanded={() => toggle(i)}
                edit={canEdit ? { trim: editor.trimAllowed(i), onSwap: () => editor.startSwap(i), onTrim: () => editor.trim(i) } : null}
                detail={<StageBooking date={date} ohrs={ohrs} />}
              >
                {editing?.kind === 'swap' && editing.index === i && candidates}
              </StageNode>
            </Box>
          )
        })}

        {addButton('last', '+ Etappe anhängen')}
        {leg(nights)}

        <RailRow node="dot" rail="to-dot">
          <Box data-node="exit" sx={styles.endLine}>
            <Typography variant="body2" sx={styles.endLabel}>
              {editor.car ? 'Zurück am Start' : `Ziel: ${startLabel(trip.exit.startId)}`}
            </Typography>
            {canEdit && !editor.car && <Button size="small" color="secondary" aria-label="Ziel ändern" onClick={() => editor.startEndpoint('exit')}>ändern</Button>}
          </Box>
          {editing?.kind === 'exit' && candidates}
        </RailRow>
      </Box>

      {warnings.map((w) => <Typography key={w} variant="body2" role="alert">⚠ {w}</Typography>)}
    </Box>
  )
}
