import { Box, Link, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material'
import { buildBookingLink } from '@/availability/bookingLink.js'
import type { HutOhrs } from '@/data/buildAppData.js'
import type { BookingStatus } from '@/trip/trip.js'
import AvailabilityMark from './AvailabilityMark.js'
import type { NightView } from './useTripAvailability.js'
import { styles } from './StageBooking.styles.js'

export const STATUS_LABEL: Record<BookingStatus, string> = { open: 'offen', requested: 'angefragt', confirmed: 'bestätigt' }

export interface StageBookingProps {
  /** 0-based night index. */
  night: number
  /** The date of this night; null while the trip has no start date. */
  date: Date | null
  ohrs: HutOhrs | undefined
  view: NightView | undefined
  status: BookingStatus
  onStatusChange: (status: BookingStatus) => void
}

/** Second-level booking detail of one night: availability, where to book, and the hand-set status. */
export default function StageBooking({ night, date, ohrs, view, status, onStatusChange }: StageBookingProps) {
  return (
    <Box sx={styles.root}>
      {date && view && (view.loading ? <Typography variant="body2">Verfügbarkeit lädt …</Typography> : <AvailabilityMark availability={view.availability} />)}
      {ohrs?.ohrsHutId ? (
        date && (
          <Link href={buildBookingLink(ohrs.ohrsHutId, date)} target="_blank" rel="noreferrer" color="inherit">
            Auf hut-reservation.org buchen
          </Link>
        )
      ) : (
        <Typography variant="body2">Direktbuchung: die Hütte selbst kontaktieren.</Typography>
      )}
      <ToggleButtonGroup
        size="small" exclusive value={status} aria-label={`Buchungsstatus Nacht ${night + 1}`}
        onChange={(_e, next: BookingStatus | null) => { if (next) onStatusChange(next) }}
      >
        {(Object.keys(STATUS_LABEL) as BookingStatus[]).map((s) => (
          <ToggleButton key={s} value={s} sx={styles.statusButton}>{STATUS_LABEL[s]}</ToggleButton>
        ))}
      </ToggleButtonGroup>
    </Box>
  )
}
