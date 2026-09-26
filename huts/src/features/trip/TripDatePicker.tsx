import { Box, Typography } from '@mui/material'
import type { ShiftVerdict } from '@/availability/startDateAnswer.js'
import type { HutOhrs } from '@/data/buildAppData.js'
import { addIsoDays, formatDayMonthRange } from '@/format/dayMonth.js'
import type { Trip } from '@/trip/trip.js'
import CalendarField from '@/ui/CalendarField.js'
import MonthCalendar from '@/ui/MonthCalendar.js'
import { MAX_SHIFT, useStartDateAnswers } from './useStartDateAnswers.js'
import { styles } from './TripDatePicker.styles.js'

const VERDICT_TEXT: Record<ShiftVerdict, string> = { bookable: 'alles frei', blocked: 'belegt', unclear: 'unklar' }
const VERDICT_MARK: Record<ShiftVerdict, string> = { bookable: '●', blocked: '✕', unclear: '?' }
const VERDICTS: ShiftVerdict[] = ['bookable', 'blocked', 'unclear']

interface TripDatePickerProps {
  trip: Trip
  hutIndices: (number | null)[]
  hutOhrsByIndex: Map<number, HutOhrs>
  onChange: (trip: Trip) => void
}

/** Mounted only while the popover is open, so availability is fetched on demand. */
function TripCalendar({ trip, hutIndices, hutOhrsByIndex, onChange, close }: TripDatePickerProps & { close: () => void }) {
  const verdicts = useStartDateAnswers(trip, hutIndices, hutOhrsByIndex)
  const start = trip.startDate ?? ''
  const end = trip.startDate ? addIsoDays(trip.startDate, trip.huts.length) : ''
  const mark = (iso: string) => {
    const verdict = verdicts?.get(iso)
    return verdict && <span data-verdict={verdict} aria-label={VERDICT_TEXT[verdict]}>{VERDICT_MARK[verdict]}</span>
  }
  return (
    <>
      <MonthCalendar
        initialDay={start} rangeStart={start} rangeEnd={end} dayMark={trip.startDate ? mark : undefined}
        onPickDay={(iso) => { onChange({ ...trip, startDate: iso }); close() }}
      />
      <Typography variant="caption" color="text.secondary">
        {!trip.startDate
          ? 'Tag der ersten Nacht wählen'
          : verdicts === null
            ? 'Verfügbarkeit wird geladen …'
            : `Startdatum ±${MAX_SHIFT} Tage: `}
        {trip.startDate && verdicts !== null && (
          <Box component="span" sx={styles.legend}>
            {VERDICTS.map((v) => <span key={v}>{VERDICT_MARK[v]} {VERDICT_TEXT[v]}</span>)}
          </Box>
        )}
      </Typography>
    </>
  )
}

/** "Wann?" field of a trip: picks the first night and shows the stay; the calendar marks which nearby
 *  start dates keep the whole chain bookable. */
export default function TripDatePicker(props: TripDatePickerProps) {
  const { trip } = props
  const label = trip.startDate ? formatDayMonthRange(trip.startDate, addIsoDays(trip.startDate, trip.huts.length)) : 'Datum wählen'
  return (
    <CalendarField label={label}>
      {(close) => <TripCalendar {...props} close={close} />}
    </CalendarField>
  )
}
