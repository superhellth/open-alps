import { useState } from 'react'
import { Box, Button, Typography } from '@mui/material'
import { addUtcDays } from '@/availability/formatDate.js'
import type { HutOhrs } from '@/data/buildAppData.js'
import { formatMeters } from '@/format/meters.js'
import { formatSignpostTime } from '@/format/signpostTime.js'
import type { BookingStatus, Trip } from '@/trip/trip.js'
import type { TripLegs } from '@/trip/tripLegs.js'
import AvailabilityMark from './AvailabilityMark.js'
import CandidateList from './CandidateList.js'
import StageBooking, { STATUS_LABEL } from './StageBooking.js'
import StageRow from './StageRow.js'
import { styles as rowStyles } from './StageRow.styles.js'
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
  /** The leg hovered in the list, on the map or on the profile; its row gets the yellow bar. */
  highlightedLeg: number | null
  onHoverLeg: (index: number | null) => void
  editor: TripEditor
  editMode: boolean
  onEditModeChange: (on: boolean) => void
  onNightStatusChange: (night: number, status: BookingStatus) => void
  warnings?: string[]
}

const CHANGED_TEXT = 'Seit dem Speichern geändert – nicht mehr im Wegenetz'
const shortDate = (d: Date) => d.toLocaleDateString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit', timeZone: 'UTC' })

/** Start, one row per night (a leg and the night at its end), the descent, and the overlap warnings.
 *  Booking detail is second level (chevron); editing controls appear only in edit mode. Stage row i
 *  belongs to leg i, the descent row to leg `huts.length`; the start row has no leg. */
export default function StageList({
  trip, tripLegs, hutNameById, hutOhrsByIndex, startLabel, nightViews, highlightedLeg, onHoverLeg,
  editor, editMode, onEditModeChange, onNightStatusChange, warnings = [],
}: StageListProps) {
  const [expanded, setExpanded] = useState<ReadonlySet<number>>(new Set())
  const firstNight = trip.startDate ? new Date(trip.startDate) : null
  const nights = trip.huts.length
  const exitLeg = tripLegs.legs[nights]
  const canEdit = editMode && editor.editable
  const editing = editor.editing
  const candidates = <CandidateList editor={editor} hutNameById={hutNameById} startLabel={startLabel} />
  const toggle = (i: number) => setExpanded((prev) => {
    const next = new Set(prev)
    if (!next.delete(i)) next.add(i)
    return next
  })

  return (
    <Box sx={styles.root}>
      <Box sx={styles.heading}>
        <Typography variant="subtitle1" component="h2">Etappen</Typography>
        <Button size="small" color="secondary" onClick={() => { setExpanded(new Set()); onEditModeChange(!editMode) }}>
          {editMode ? 'Fertig' : 'Bearbeiten'}
        </Button>
      </Box>

      <Box sx={styles.rows}>
        <Box>
          <Box sx={styles.endLine}>
            <Typography variant="body2" sx={styles.endLabel}>Start: {startLabel(trip.start.startId)}</Typography>
            {canEdit && <Button size="small" color="secondary" aria-label="Start ändern" onClick={() => editor.startEndpoint('start')}>ändern</Button>}
          </Box>
          {editing?.kind === 'start' && candidates}
        </Box>

        {canEdit && (
          <>
            <Button size="small" color="secondary" sx={styles.addButton} onClick={() => editor.startExtend('first')}>+ Etappe voranstellen</Button>
            {editing?.kind === 'extend' && editing.side === 'first' && candidates}
          </>
        )}

        {trip.huts.map((_guid, i) => {
          const hutIndex = tripLegs.hutIndices[i]
          const leg = tripLegs.legs[i]
          const changed = tripLegs.changed[i]
          const ohrs = hutIndex === null ? undefined : hutOhrsByIndex.get(hutIndex)
          const date = firstNight ? addUtcDays(firstNight, i) : null
          const view = nightViews?.[i]
          const open = expanded.has(i) && !editMode && !changed
          const meta = changed ? CHANGED_TEXT : (
            <>
              {date && <span>{shortDate(date)}</span>}
              {leg && <span>↑ {formatMeters(leg.ascentM)} ↓ {formatMeters(leg.descentM)}</span>}
              {date && view && (view.loading ? <span>Verfügbarkeit lädt …</span> : <AvailabilityMark availability={view.availability} />)}
              <span>{STATUS_LABEL[trip.nights[i].status]}</span>
            </>
          )
          return (
            <StageRow
              key={i} number={i + 1}
              title={hutIndex === null ? 'Unbekannte Hütte' : hutNameById.get(hutIndex) ?? String(hutIndex)}
              timeH={!changed && leg ? leg.durationH : undefined}
              meta={meta} changed={changed} highlighted={highlightedLeg === i} editMode={editMode}
              expanded={open} onToggleExpanded={() => toggle(i)} onHover={(hovering) => onHoverLeg(hovering ? i : null)}
              edit={canEdit ? { trim: editor.trimAllowed(i), onSwap: () => editor.startSwap(i), onTrim: () => editor.trim(i) } : null}
            >
              {open && (
                <StageBooking
                  night={i} date={date} ohrs={ohrs} view={view} status={trip.nights[i].status}
                  onStatusChange={(status) => onNightStatusChange(i, status)}
                />
              )}
              {editing?.kind === 'swap' && editing.index === i && candidates}
            </StageRow>
          )
        })}

        {canEdit && (
          <>
            <Button size="small" color="secondary" sx={styles.addButton} onClick={() => editor.startExtend('last')}>+ Etappe anhängen</Button>
            {editing?.kind === 'extend' && editing.side === 'last' && candidates}
          </>
        )}

        <Box
          data-stage="exit" data-highlighted={highlightedLeg === nights} sx={rowStyles.row(highlightedLeg === nights, false)}
          onMouseEnter={() => onHoverLeg(nights)} onMouseLeave={() => onHoverLeg(null)}
        >
          <Box sx={styles.endLine}>
            <Typography variant="body2" sx={styles.endLabel}>
              {editor.car ? 'Abstieg zum Start' : `Abstieg nach ${startLabel(trip.exit.startId)}`}
            </Typography>
            {exitLeg && <Typography variant="body2" component="span" sx={styles.time}>{formatSignpostTime(exitLeg.durationH)}</Typography>}
            {canEdit && !editor.car && <Button size="small" color="secondary" aria-label="Ziel ändern" onClick={() => editor.startEndpoint('exit')}>ändern</Button>}
          </Box>
          {exitLeg && (
            <Box sx={styles.meta}>
              <span>↑ {formatMeters(exitLeg.ascentM)}</span>
              <span>↓ {formatMeters(exitLeg.descentM)}</span>
            </Box>
          )}
          {editing?.kind === 'exit' && candidates}
        </Box>

        {warnings.map((w) => <Typography key={w} variant="body2" role="alert">⚠ {w}</Typography>)}
      </Box>
    </Box>
  )
}
