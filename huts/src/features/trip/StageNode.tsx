import type { ReactNode } from 'react'
import { Box, ButtonBase, IconButton, Tooltip, Typography } from '@mui/material'
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
  /** Second line: date and the night's state. */
  meta: ReactNode
  changed: boolean
  editMode: boolean
  expanded: boolean
  onToggleExpanded: () => void
  /** Swap/remove controls; null outside edit mode or when the trip cannot be edited. */
  edit: { trim: TrimCheck; onSwap: () => void; onTrim: () => void } | null
  /** Expanded booking detail or the candidate list of an active edit. */
  children?: ReactNode
}

/** One night on the timeline: a dot on the rail, the hut and its state. Outside edit mode the whole face toggles the booking detail. */
export default function StageNode({ number, title, meta, changed, editMode, expanded, onToggleExpanded, edit, children }: StageNodeProps) {
  const text = (
    <Box sx={styles.text}>
      <Box sx={styles.titleLine}>
        <Typography component="span" sx={styles.number}>{number}</Typography>
        <Typography component="span" sx={styles.title}>{title}</Typography>
      </Box>
      <Box sx={styles.meta}>{meta}</Box>
    </Box>
  )
  const expandable = !editMode && !changed
  return (
    <RailRow node={changed ? 'hollow' : 'dot'}>
      <Box data-night={number - 1} data-variant={changed ? 'outline' : undefined} sx={styles.root}>
        <Box sx={styles.head}>
          {expandable ? (
            <ButtonBase sx={styles.toggle} aria-label={`Details Etappe ${number}`} aria-expanded={expanded} onClick={onToggleExpanded}>
              {text}
              <ExpandMoreIcon sx={styles.chevron(expanded)} aria-hidden="true" />
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
        {children && <Box sx={styles.detail}>{children}</Box>}
      </Box>
    </RailRow>
  )
}
