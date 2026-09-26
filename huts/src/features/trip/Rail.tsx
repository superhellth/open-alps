import type { ReactNode } from 'react'
import { Box } from '@mui/material'
import { styles } from './Rail.styles.js'

export interface RailRowProps {
  /** A dot on the rail (a place: start, hut, destination); none for the rail between places. */
  node?: 'dot' | 'hollow' | 'none'
  /** Which part of the rail this row draws: the first row starts at its dot, the last one ends there. */
  rail?: 'full' | 'from-dot' | 'to-dot' | 'none'
  /** The rail below the dot (or the whole rail of a row without one) turns signpost yellow and wider: a hovered leg. */
  highlighted?: boolean
  /** The rail above the dot is highlighted: the hovered leg arrives at this dot. */
  highlightedAbove?: boolean
  children?: ReactNode
}

/** One row of the stage timeline: a gutter with the rail (and optionally a dot), content right of it. */
export default function RailRow({ node = 'none', rail = 'full', highlighted = false, highlightedAbove = false, children }: RailRowProps) {
  const above = rail === 'full' || rail === 'to-dot'
  const below = rail === 'full' || rail === 'from-dot'
  return (
    <Box sx={styles.row}>
      <Box sx={styles.gutter} aria-hidden="true">
        {node !== 'none' && <Box data-rail="above" data-highlighted={above && highlightedAbove} sx={styles.above(above, highlightedAbove)} />}
        {node !== 'none' && <Box sx={styles.dot(node === 'hollow')} />}
        <Box data-rail="below" data-highlighted={(node === 'none' ? rail !== 'none' : below) && highlighted} sx={styles.below(node === 'none' ? rail !== 'none' : below, highlighted)} />
      </Box>
      <Box sx={styles.content}>{children}</Box>
    </Box>
  )
}
