import type { ReactNode } from 'react'
import { Box, IconButton, Tooltip, Typography } from '@mui/material'
import { formatSignpostTime } from '@/format/signpostTime.js'
import type { TrimCheck } from '@/trip/tripEdit.js'
import { styles } from './StageRow.styles.js'

export interface StageRowProps {
  /** 1-based stage number shown to the user; the row's leg is number - 1. */
  number: number
  title: string
  timeH?: number
  /** Second line: date, ascent/descent, availability, booking status. */
  meta: ReactNode
  changed: boolean
  highlighted: boolean
  editMode: boolean
  expanded: boolean
  onToggleExpanded: () => void
  onHover: (hovering: boolean) => void
  /** Swap/remove controls; null outside edit mode or when the trip cannot be edited. */
  edit: { trim: TrimCheck; onSwap: () => void; onTrim: () => void } | null
  /** Expanded booking detail or the candidate list of an active edit. */
  children?: ReactNode
}

export default function StageRow({
  number, title, timeH, meta, changed, highlighted, editMode, expanded, onToggleExpanded, onHover, edit, children,
}: StageRowProps) {
  return (
    <Box
      data-stage={number - 1} data-highlighted={highlighted} data-variant={changed ? 'outline' : undefined}
      sx={styles.row(highlighted, changed)} onMouseEnter={() => onHover(true)} onMouseLeave={() => onHover(false)}
    >
      <Box sx={styles.line}>
        <Typography component="span" sx={styles.number}>{number}</Typography>
        <Typography component="span" sx={styles.title}>{title}</Typography>
        {timeH !== undefined && <Typography component="span" sx={styles.time}>{formatSignpostTime(timeH)}</Typography>}
        {!editMode && !changed && (
          <IconButton size="small" aria-label={`Details Etappe ${number}`} aria-expanded={expanded} onClick={onToggleExpanded}>
            {expanded ? '▾' : '▸'}
          </IconButton>
        )}
        {edit && (
          <>
            <IconButton size="small" aria-label={`Hütte tauschen Etappe ${number}`} onClick={edit.onSwap}>⇄</IconButton>
            <Tooltip title={edit.trim.ok ? '' : edit.trim.reason}>
              <span>
                <IconButton size="small" aria-label={`Hütte entfernen Etappe ${number}`} disabled={!edit.trim.ok} onClick={edit.onTrim}>✕</IconButton>
              </span>
            </Tooltip>
          </>
        )}
      </Box>
      <Box sx={styles.meta}>{meta}</Box>
      {children}
    </Box>
  )
}
