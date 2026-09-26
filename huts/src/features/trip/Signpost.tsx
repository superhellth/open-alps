import type { ReactNode } from 'react'
import { Box } from '@mui/material'
import { formatSignpostTime } from '@/format/signpostTime.js'
import { formatAscent, formatDescent } from '@/format/meters.js'
import StatLine from '@/ui/StatLine.js'
import { styles } from './Signpost.styles.js'

export interface SignpostProps {
  title: ReactNode
  /** Stats shown under the title row, before the ascent/descent figures, e.g. ["4 Nächte", "58 km"]. */
  stats?: string[]
  timeH?: number
  ascentM?: number
  descentM?: number
  /** 'outline' = ink outline on paper, no yellow fill (a night that no longer resolves). */
  variant?: 'plate' | 'outline'
  children?: ReactNode
}


// The trail signpost: an arrow-shaped plate, destination left, walking time right. The one bold
// element of the UI; everything around it stays flat.
export default function Signpost({ title, stats = [], timeH, ascentM, descentM, variant = 'plate', children }: SignpostProps) {
  const outline = variant === 'outline'
  const body = (
    <Box sx={styles.body}>
      <Box sx={styles.titleRow}>
        <Box component="span" sx={styles.title}>{title}</Box>
        {timeH !== undefined && <Box component="span" sx={styles.time}>{formatSignpostTime(timeH)}</Box>}
      </Box>
      {(stats.length > 0 || ascentM !== undefined || descentM !== undefined) && (
        <Box sx={styles.stats}>
          <StatLine>
            {stats.map((stat) => <span key={stat}>{stat}</span>)}
            {ascentM !== undefined && <span>{formatAscent(ascentM)}</span>}
            {descentM !== undefined && <span>{formatDescent(descentM)}</span>}
          </StatLine>
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
