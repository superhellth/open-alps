import type { ReactNode } from 'react'
import { Box, IconButton, Tooltip, Typography } from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import SwapHorizIcon from '@mui/icons-material/SwapHoriz'
import type { TrimCheck } from '@/trip/tripEdit.js'
import RailRow from './Rail.js'
import { styles } from './StageNode.styles.js'

export interface StageNodeProps {
  /** 1-based stage number shown to the user; the node's night is number - 1. */
  number: number
  title: string
  /** The night's date, muted at the end of the title row; null while the trip has no start date. */
  date: string | null
  /** Second line: the night's state and its booking link; omitted while nothing is known about it. */
  meta?: ReactNode
  changed: boolean
  /** Highlights the rail above the dot (the leg arriving here) and below it (the leg leaving). */
  railHighlight?: { above: boolean; below: boolean }
  /** Swap/remove controls; null outside edit mode or when the trip cannot be edited. */
  edit: { trim: TrimCheck; onSwap: () => void; onTrim: () => void } | null
  /** The candidate list of an active edit. */
  children?: ReactNode
}

/** One night on the timeline: a dot on the rail, the hut, its date and its state. */
export default function StageNode({ number, title, date, meta, changed, railHighlight, edit, children }: StageNodeProps) {
  return (
    <RailRow node={changed ? 'hollow' : 'dot'} highlightedAbove={railHighlight?.above} highlighted={railHighlight?.below}>
      <Box data-night={number - 1} data-variant={changed ? 'outline' : undefined} sx={styles.root}>
        <Box sx={styles.head}>
          <Box sx={styles.face}>
            <Box sx={styles.titleLine}>
              <Typography component="span" sx={styles.number}>{number}</Typography>
              <Typography component="span" sx={styles.title}>{title}</Typography>
              {date && <Typography component="span" sx={styles.date}>{date}</Typography>}
            </Box>
            {meta && <Box sx={styles.meta}>{meta}</Box>}
          </Box>
          {edit && (
            <>
              <IconButton aria-label={`Hütte tauschen Etappe ${number}`} onClick={edit.onSwap}><SwapHorizIcon /></IconButton>
              <Tooltip title={edit.trim.ok ? '' : edit.trim.reason}>
                <span>
                  <IconButton aria-label={`Hütte entfernen Etappe ${number}`} disabled={!edit.trim.ok} onClick={edit.onTrim}><CloseIcon /></IconButton>
                </span>
              </Tooltip>
            </>
          )}
        </Box>
        {children && <Box sx={styles.candidates}>{children}</Box>}
      </Box>
    </RailRow>
  )
}
