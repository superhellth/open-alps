import type { ReactNode } from 'react'
import { Box } from '@mui/material'
import type { SvgIcon } from '@mui/material'
import BlockIcon from '@mui/icons-material/Block'
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutlined'
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutlineOutlined'
import HelpOutlineIcon from '@mui/icons-material/HelpOutlineOutlined'
import PhoneOutlinedIcon from '@mui/icons-material/PhoneOutlined'
import { nightText } from '@/availability/nightState.js'
import type { NightAvailability } from '@/availability/nightState.js'
import { fontSize, rem, space } from '@/ui/tokens.js'

/** One outlined icon per state, drawn in the surrounding text colour: state is never conveyed by colour alone. */
const ICON: Record<NightAvailability['kind'], typeof SvgIcon> = {
  free: CheckCircleOutlineIcon,
  few: ErrorOutlineIcon,
  full: BlockIcon,
  unknown: HelpOutlineIcon,
}

const iconSx = { fontSize: rem(fontSize.md) }

/** The icon of one availability state, shared by the stage list and the trip calendar. `size` defaults to the body text's. */
export function NightIcon({ kind, size = 'md' }: { kind: NightAvailability['kind']; size?: keyof typeof fontSize }) {
  const Icon = ICON[kind]
  return <Icon aria-hidden="true" data-shape={kind} sx={{ fontSize: rem(fontSize[size]) }} />
}

function Mark({ icon, text }: { icon: ReactNode; text: string }) {
  return (
    <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: space.inline }}>
      {icon}
      <span>{text}</span>
    </Box>
  )
}

export default function AvailabilityMark({ availability }: { availability: NightAvailability }) {
  return <Mark icon={<NightIcon kind={availability.kind} />} text={nightText(availability)} />
}

/** A hut without online booking: contact it directly. */
export function DirectBookingMark() {
  return <Mark icon={<PhoneOutlinedIcon aria-hidden="true" data-shape="phone" sx={iconSx} />} text="Direktbuchung – Hütte kontaktieren" />
}
