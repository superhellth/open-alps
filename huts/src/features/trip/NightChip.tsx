import { Typography } from '@mui/material'
import AvailabilityMark from './AvailabilityMark.js'
import type { NightView } from './useTripAvailability.js'

export interface NightChipProps {
  view: NightView
}

/** The one state line of a night: its availability. */
export default function NightChip({ view }: NightChipProps) {
  if (view.loading) return <Typography component="span" variant="inherit">Verfügbarkeit lädt …</Typography>
  return <AvailabilityMark availability={view.availability} />
}
