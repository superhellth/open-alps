import type { ReactNode } from 'react'
import { Box } from '@mui/material'
import { formatDistanceKm } from '@/format/distance.js'
import { formatAscent, formatDescent } from '@/format/meters.js'
import { formatSignpostTime } from '@/format/signpostTime.js'
import type { Leg } from '@/tourSearch/types.js'
import StatLine from '@/ui/StatLine.js'
import RailRow from './Rail.js'
import { styles } from './StageLeg.styles.js'

export interface StageLegProps {
  /** 0-based leg index; the exit leg is `huts.length`. */
  index: number
  leg: Leg | null | undefined
  highlighted: boolean
  onHover: (index: number | null) => void
  /** Editing controls placed on this stretch of the rail (e.g. adding a stage). */
  children?: ReactNode
}

/** The walk between two places on the timeline: signpost time, distance and ascent/descent on the rail. The whole row, rail included, is the hover target of the leg. */
export default function StageLeg({ index, leg, highlighted, onHover, children }: StageLegProps) {
  return (
    <Box
      data-leg={index} data-highlighted={highlighted} sx={styles.root(highlighted)}
      onMouseEnter={() => onHover(index)} onMouseLeave={() => onHover(null)}
    >
      <RailRow highlighted={highlighted}>
        <Box sx={styles.line}>
          {leg && (
            <>
              <Box component="span" sx={styles.time}>{formatSignpostTime(leg.durationH)}</Box>
              <Box component="span" sx={styles.stats}>
                <StatLine>
                  <span>{formatDistanceKm(leg.distanceM)}</span>
                  <span>{formatAscent(leg.ascentM)}</span>
                  <span>{formatDescent(leg.descentM)}</span>
                </StatLine>
              </Box>
            </>
          )}
        </Box>
        {children}
      </RailRow>
    </Box>
  )
}
