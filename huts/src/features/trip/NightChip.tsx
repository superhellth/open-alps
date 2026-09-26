import { Box, Typography } from '@mui/material'
import CheckIcon from '@mui/icons-material/Check'
import HourglassEmptyIcon from '@mui/icons-material/HourglassEmpty'
import type { BookingStatus } from '@/trip/trip.js'
import AvailabilityMark from './AvailabilityMark.js'
import { STATUS_LABEL } from './StageBooking.js'
import type { NightView } from './useTripAvailability.js'
import { styles } from './NightChip.styles.js'

export interface NightChipProps {
  status: BookingStatus
  /** Availability of this night; undefined while the trip has no date or none is known yet. */
  view: NightView | undefined
}

/** The one state line of a night: its booking status once requested or confirmed, otherwise its availability. */
export default function NightChip({ status, view }: NightChipProps) {
  if (status !== 'open') {
    const Icon = status === 'confirmed' ? CheckIcon : HourglassEmptyIcon
    return (
      <Box component="span" sx={styles.status}>
        <Icon sx={styles.icon} aria-hidden="true" />
        {STATUS_LABEL[status]}
      </Box>
    )
  }
  if (!view) return <span>{STATUS_LABEL.open}</span>
  if (view.loading) return <Typography component="span" variant="inherit">Verfügbarkeit lädt …</Typography>
  return <AvailabilityMark availability={view.availability} />
}
