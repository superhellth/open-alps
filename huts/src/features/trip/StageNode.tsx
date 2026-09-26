import type { ReactNode } from 'react'
import { Box, ButtonBase, Collapse, IconButton, Tooltip, Typography } from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
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
  /** Second line: the night's state; omitted while nothing is known about it. */
  meta?: ReactNode
  changed: boolean
  editMode: boolean
  expanded: boolean
  onToggleExpanded: () => void
  /** Swap/remove controls; null outside edit mode or when the trip cannot be edited. */
  edit: { trim: TrimCheck; onSwap: () => void; onTrim: () => void } | null
  /** Booking detail, unfolded inside the node's own surface while `expanded`. */
  detail?: ReactNode
  /** The candidate list of an active edit. */
  children?: ReactNode
}

/** One night on the timeline: a dot on the rail, the hut and its state. Outside edit mode the whole face toggles the booking detail, which unfolds below it on one shared surface. */
export default function StageNode({ number, title, date, meta, changed, editMode, expanded, onToggleExpanded, edit, detail, children }: StageNodeProps) {
  const expandable = !editMode && !changed
  const text = (
    <Box sx={styles.text}>
      <Box sx={styles.titleLine}>
        <Typography component="span" sx={styles.number}>{number}</Typography>
        <Typography component="span" sx={styles.title}>{title}</Typography>
        {date && <Typography component="span" sx={styles.date}>{date}</Typography>}
        {expandable && <ExpandMoreIcon sx={styles.chevron(expanded)} aria-hidden="true" />}
      </Box>
      {meta && <Box sx={styles.meta}>{meta}</Box>}
    </Box>
  )
  return (
    <RailRow node={changed ? 'hollow' : 'dot'}>
      <Box data-night={number - 1} data-variant={changed ? 'outline' : undefined} sx={styles.root(expandable && expanded)}>
        <Box sx={styles.head}>
          {expandable ? (
            <ButtonBase sx={styles.toggle} aria-label={`Details Etappe ${number}`} aria-expanded={expanded} onClick={onToggleExpanded}>
              {text}
            </ButtonBase>
          ) : (
            <Box sx={styles.face}>{text}</Box>
          )}
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
        {expandable && (
          <Collapse in={expanded} unmountOnExit>
            <Box sx={styles.detail}>{detail}</Box>
          </Collapse>
        )}
        {children && <Box sx={styles.candidates}>{children}</Box>}
      </Box>
    </RailRow>
  )
}
