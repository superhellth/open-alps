import { Box, Link, Typography } from '@mui/material'
import { buildBookingLink } from '@/availability/bookingLink.js'
import type { HutOhrs } from '@/data/buildAppData.js'
import { styles } from './StageBooking.styles.js'

export interface StageBookingProps {
  /** The date of this night; null while the trip has no start date. */
  date: Date | null
  ohrs: HutOhrs | undefined
}

/** Second-level booking detail of one night: where to book it. */
export default function StageBooking({ date, ohrs }: StageBookingProps) {
  return (
    <Box sx={styles.root}>
      {ohrs?.ohrsHutId ? (
        date ? (
          <Link href={buildBookingLink(ohrs.ohrsHutId, date)} target="_blank" rel="noreferrer" color="inherit">
            Auf hut-reservation.org buchen
          </Link>
        ) : (
          <Typography variant="body2">Datum wählen, um zu buchen.</Typography>
        )
      ) : (
        <Typography variant="body2">Direktbuchung: die Hütte selbst kontaktieren.</Typography>
      )}
    </Box>
  )
}
