import type { ReactNode } from 'react'
import { Box } from '@mui/material'
import { formatMeters } from '@/format/meters.js'
import { formatSignpostTime } from '@/format/signpostTime.js'
import type { Leg } from '@/tourSearch/types.js'
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

/** The walk between two places on the timeline: signpost time and ascent/descent on the rail. Hovering it highlights the leg. */
export default function StageLeg({ index, leg, highlighted, onHover, children }: StageLegProps) {
  return (
    <RailRow highlighted={highlighted}>
      <Box
        data-leg={index} data-highlighted={highlighted} sx={styles.root(highlighted)}
        onMouseEnter={() => onHover(index)} onMouseLeave={() => onHover(null)}
      >
        {leg && (
          <Box sx={styles.line}>
            <Box component="span" sx={styles.time}>{formatSignpostTime(leg.durationH)}</Box>
            <Box component="span" sx={styles.stats}>
              <span>↑ {formatMeters(leg.ascentM)}</span>
              <span>↓ {formatMeters(leg.descentM)}</span>
            </Box>
          </Box>
        )}
      </Box>
      {children}
    </RailRow>
  )
}
