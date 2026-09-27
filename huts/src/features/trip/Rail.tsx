import type { ReactNode } from 'react'
import { Box } from '@mui/material'
import { StopSymbol } from '@/ui/StopSymbol.js'
import type { StopMark } from '@/ui/StopSymbol.js'
import { styles } from './Rail.styles.js'

export interface RailRowProps {
  /** The stop's symbol on the rail (start, hut, destination), as the map draws it; none for the rail between places. */
  node?: StopMark | null
  /** Which part of the rail this row draws: the first row starts at its stop, the last one ends there. */
  rail?: 'full' | 'from-stop' | 'to-stop' | 'none'
  /** The rail below the stop (or the whole rail of a row without one) turns signpost yellow and wider: a hovered leg. */
  highlighted?: boolean
  /** The rail above the stop is highlighted: the hovered leg arrives at this stop. */
  highlightedAbove?: boolean
  children?: ReactNode
}

/** One row of the stage timeline: a gutter with the rail (and optionally a stop symbol), content right of it. */
export default function RailRow({ node = null, rail = 'full', highlighted = false, highlightedAbove = false, children }: RailRowProps) {
  const above = rail === 'full' || rail === 'to-stop'
  const below = rail === 'full' || rail === 'from-stop'
  return (
    <Box sx={styles.row}>
      <Box sx={styles.gutter} aria-hidden="true">
        {node && <Box data-rail="above" data-highlighted={above && highlightedAbove} sx={styles.above(above, highlightedAbove)} />}
        {node && <Box data-stop={node.type} sx={styles.symbol}><StopSymbol mark={node} /></Box>}
        <Box data-rail="below" data-highlighted={(node ? below : rail !== 'none') && highlighted} sx={styles.below(node ? below : rail !== 'none', highlighted)} />
      </Box>
      <Box sx={styles.content}>{children}</Box>
    </Box>
  )
}
