import { Box } from '@mui/material'
import { nightText } from '../availability/nightState.js'
import type { NightAvailability } from '../availability/nightState.js'
import { tokens } from '@/ui/theme.js'

const SHAPE = { free: 'filled', few: 'half', full: 'crossed', unknown: 'question' } as const

// Shape and text always appear together: state is never conveyed by colour alone.
function Shape({ shape }: { shape: (typeof SHAPE)[keyof typeof SHAPE] }) {
  const ink = tokens.ink
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" data-shape={shape}>
      {shape === 'filled' && <circle cx="8" cy="8" r="6" fill={ink} />}
      {shape === 'half' && (
        <>
          <circle cx="8" cy="8" r="6" fill="none" stroke={ink} strokeWidth="2" />
          <path d="M8 2 A6 6 0 0 1 8 14 Z" fill={ink} />
        </>
      )}
      {shape === 'crossed' && (
        <>
          <circle cx="8" cy="8" r="6" fill="none" stroke={ink} strokeWidth="2" />
          <path d="M3.5 12.5 L12.5 3.5" stroke={ink} strokeWidth="2" />
        </>
      )}
      {shape === 'question' && (
        <>
          <circle cx="8" cy="8" r="6" fill="none" stroke={ink} strokeWidth="2" />
          <text x="8" y="11.5" textAnchor="middle" fontSize="9" fontWeight="700" fill={ink}>?</text>
        </>
      )}
    </svg>
  )
}

export default function AvailabilityMark({ availability }: { availability: NightAvailability }) {
  return (
    <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.75 }}>
      <Shape shape={SHAPE[availability.kind]} />
      <span>{nightText(availability)}</span>
    </Box>
  )
}
