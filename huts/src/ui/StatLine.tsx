import type { ReactNode } from 'react'
import { Box } from '@mui/material'
import { styles } from './StatLine.styles.js'

/** One line of stats (time, distance, ascent/descent, counts), one child per stat. Each stat carries its own unit or arrow, so stats are separated by a gap, never by a separator character. */
export default function StatLine({ children }: { children: ReactNode }) {
  return <Box sx={styles.root}>{children}</Box>
}
