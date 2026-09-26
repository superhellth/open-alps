import { useState } from 'react'
import { Box, Typography } from '@mui/material'
import { stayVerdict } from '@/availability/stayNights.js'
import type { NightVerdict, StayVerdict } from '@/availability/stayNights.js'
import type { HutOhrs } from '@/data/buildAppData.js'
import { addIsoDays, daysBetween, formatDayMonthRange } from '@/format/dayMonth.js'
import type { Trip } from '@/trip/trip.js'
import CalendarField from '@/ui/CalendarField.js'
import MonthCalendar from '@/ui/MonthCalendar.js'
import { usePrefetchAround, useStayNights } from './useStayNights.js'
import { styles } from './TripDatePicker.styles.js'

const NIGHT_TEXT: Record<NightVerdict, string> = { free: 'frei', full: 'belegt', unclear: 'unklar' }
const NIGHT_MARK: Record<NightVerdict, string> = { free: '●', full: '✕', unclear: '?' }
const NIGHTS: NightVerdict[] = ['free', 'full', 'unclear']
const STAY_TEXT: Record<StayVerdict, string> = { bookable: '● alles frei', blocked: '✕ belegt', unclear: '? unklar' }

interface TripDatePickerProps {
  trip: Trip
  hutIndices: (number | null)[]
  hutOhrsByIndex: Map<number, HutOhrs>
  onChange: (trip: Trip) => void
}

/** Mounted only while the popover is open, so availability is fetched on demand. Hovering a day moves
 *  the drawn stay onto it; each night of the shown stay is marked with its own hut's availability. */
function TripCalendar({ trip, hutIndices, hutOhrsByIndex, onChange, close }: TripDatePickerProps & { close: () => void }) {
  const [hovered, setHovered] = useState<string | null>(null)
  const nights = trip.huts.length
  const ohrsIds = hutIndices.map((i) => (i === null ? null : hutOhrsByIndex.get(i)?.ohrsHutId ?? null))
  usePrefetchAround(trip.startDate, nights, trip.partySize)
  const shown = hovered ?? trip.startDate
  const verdicts = useStayNights(shown, ohrsIds, trip.partySize, hovered !== null)
  const start = shown ?? ''
  const end = shown ? addIsoDays(shown, nights) : ''
  const mark = (iso: string) => {
    const verdict = shown ? verdicts?.[daysBetween(shown, iso)] : undefined
    return verdict && <span data-night={verdict} aria-label={NIGHT_TEXT[verdict]}>{NIGHT_MARK[verdict]}</span>
  }
  return (
    <>
      <Typography variant="subtitle2">Anreisetag wählen · {nights} {nights === 1 ? 'Nacht' : 'Nächte'}</Typography>
      <MonthCalendar
        initialDay={trip.startDate ?? ''} rangeStart={start} rangeEnd={end} dayMark={mark} onHoverDay={setHovered}
        onPickDay={(iso) => { onChange({ ...trip, startDate: iso }); close() }}
      />
      <Typography variant="caption" color="text.secondary">
        {!shown
          ? 'Der Aufenthalt folgt dem Anreisetag.'
          : `${formatDayMonthRange(start, end)}: ${verdicts === null ? 'wird geladen …' : STAY_TEXT[stayVerdict(verdicts)]}`}
      </Typography>
      {shown && (
        <Typography variant="caption" color="text.secondary" sx={styles.legend}>
          {NIGHTS.map((v) => <span key={v}>{NIGHT_MARK[v]} {NIGHT_TEXT[v]}</span>)}
        </Typography>
      )}
    </>
  )
}

/** "Wann?" field of a trip: picks the arrival day and shows the stay with each night's availability. */
export default function TripDatePicker(props: TripDatePickerProps) {
  const { trip } = props
  const label = trip.startDate ? formatDayMonthRange(trip.startDate, addIsoDays(trip.startDate, trip.huts.length)) : 'Datum wählen'
  return (
    <CalendarField label={label}>
      {(close) => <TripCalendar {...props} close={close} />}
    </CalendarField>
  )
}
