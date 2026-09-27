import { useState } from 'react'
import type { MouseEvent, ReactNode } from 'react'
import { Box, Button, Popover } from '@mui/material'
import CalendarMonthIcon from '@mui/icons-material/CalendarMonth'
import { styles } from './CalendarField.styles.js'

export interface CalendarFieldProps {
  /** Text shown in the field, e.g. the chosen range. */
  label: string
  disabled?: boolean
  onOpen?: () => void
  /** Popover content; `close` dismisses the popover. */
  children: (close: () => void) => ReactNode
}

/** Outlined field-style button with a calendar icon that opens its content in a popover. */
export default function CalendarField({ label, disabled = false, onOpen, children }: CalendarFieldProps) {
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null)
  const close = () => setAnchorEl(null)
  const open = (e: MouseEvent<HTMLElement>) => { onOpen?.(); setAnchorEl(e.currentTarget) }
  return (
    <>
      <Button size="small" variant="outlined" color="secondary" disabled={disabled} onClick={open} sx={styles.trigger}>
        {label}
        <CalendarMonthIcon fontSize="small" sx={styles.icon} aria-hidden />
      </Button>
      <Popover open={anchorEl !== null} anchorEl={anchorEl} onClose={close} anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}>
        <Box sx={styles.popover}>{children(close)}</Box>
      </Popover>
    </>
  )
}
