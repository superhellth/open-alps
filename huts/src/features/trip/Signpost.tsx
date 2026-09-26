import type { ReactNode } from 'react'
import { Box } from '@mui/material'
import { formatSignpostTime } from '@/format/signpostTime.js'
import { formatMeters } from '@/format/meters.js'
import { styles } from './Signpost.styles.js'

export interface SignpostProps {
  title: string
  timeH?: number
  ascentM?: number
  descentM?: number
  /** 'outline' = ink outline on paper, no yellow fill (a night that no longer resolves). */
  variant?: 'plate' | 'outline'
  children?: ReactNode
}


// The trail signpost: an arrow-shaped plate, destination left, walking time right. The one bold
// element of the UI; everything around it stays flat.
export default function Signpost({ title, timeH, ascentM, descentM, variant = 'plate', children }: SignpostProps) {
  const outline = variant === 'outline'
  const body = (
    <Box sx={styles.body}>
      <Box sx={styles.titleRow}>
        <Box component="span" sx={styles.title}>{title}</Box>
        {timeH !== undefined && <Box component="span" sx={{ fontWeight: 600 }}>{formatSignpostTime(timeH)}</Box>}
      </Box>
      {(ascentM !== undefined || descentM !== undefined) && (
        <Box sx={styles.stats}>
          {ascentM !== undefined && <span>↑ {formatMeters(ascentM)}</span>}
          {descentM !== undefined && <span>↓ {formatMeters(descentM)}</span>}
        </Box>
      )}
      {children}
    </Box>
  )
  return (
    <Box data-variant={variant} sx={styles.plate(outline)}>
      {outline ? <Box sx={styles.plateInner}>{body}</Box> : body}
    </Box>
  )
}
