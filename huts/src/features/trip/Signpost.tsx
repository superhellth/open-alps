import type { ReactNode } from 'react'
import { Box } from '@mui/material'
import { formatSignpostTime } from '@/format/signpostTime.js'
import { SIGNPOST_FONT, tokens } from '@/ui/theme.js'

export interface SignpostProps {
  title: string
  timeH?: number
  ascentM?: number
  descentM?: number
  /** 'outline' = ink outline on paper, no yellow fill (a night that no longer resolves). */
  variant?: 'plate' | 'outline'
  children?: ReactNode
}

const ARROW = 'polygon(0 0, calc(100% - 14px) 0, 100% 50%, calc(100% - 14px) 100%, 0 100%)'
const meters = (m: number) => `${Math.round(m).toLocaleString('de-DE')} m`

// The trail signpost: an arrow-shaped plate, destination left, walking time right. The one bold
// element of the UI; everything around it stays flat.
export default function Signpost({ title, timeH, ascentM, descentM, variant = 'plate', children }: SignpostProps) {
  const outline = variant === 'outline'
  const body = (
    <Box sx={{ px: 1.5, py: 1, pr: 3, fontFamily: SIGNPOST_FONT, color: tokens.ink }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 2 }}>
        <Box component="span" sx={{ fontWeight: 700, fontSize: '1.05rem' }}>{title}</Box>
        {timeH !== undefined && <Box component="span" sx={{ fontWeight: 600 }}>{formatSignpostTime(timeH)}</Box>}
      </Box>
      {(ascentM !== undefined || descentM !== undefined) && (
        <Box sx={{ fontSize: '0.85rem', display: 'flex', gap: 1.5 }}>
          {ascentM !== undefined && <span>↑ {meters(ascentM)}</span>}
          {descentM !== undefined && <span>↓ {meters(descentM)}</span>}
        </Box>
      )}
      {children}
    </Box>
  )
  return (
    <Box data-variant={variant} sx={{ background: outline ? tokens.ink : tokens.signpost, clipPath: ARROW, p: outline ? '2px' : 0 }}>
      {outline ? <Box sx={{ background: tokens.paper, clipPath: ARROW }}>{body}</Box> : body}
    </Box>
  )
}
