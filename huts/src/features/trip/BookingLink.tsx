import { Link } from '@mui/material'
import OpenInNewIcon from '@mui/icons-material/OpenInNew'
import { buildBookingLink } from '@/availability/bookingLink.js'
import { styles } from './BookingLink.styles.js'

export interface BookingLinkProps {
  hutName: string
  ohrsHutId: string
  date: Date
}

/** Books one night of one hut on hut-reservation.org, in a new tab. */
export default function BookingLink({ hutName, ohrsHutId, date }: BookingLinkProps) {
  return (
    <Link
      href={buildBookingLink(ohrsHutId, date)} target="_blank" rel="noreferrer" color="inherit" sx={styles.root}
      aria-label={`${hutName} auf hut-reservation.org buchen`}
    >
      Buchen
      <OpenInNewIcon fontSize="inherit" aria-hidden="true" />
    </Link>
  )
}
