import { useState } from 'react'
import type { ReactNode } from 'react'
import { Box, IconButton, Typography } from '@mui/material'
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft'
import ChevronRightIcon from '@mui/icons-material/ChevronRight'
import { todayIso } from '@/format/dayMonth.js'
import { styles } from './MonthCalendar.styles.js'

const WEEKDAY_LABELS = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']

function toIso(y: number, m: number, d: number): string {
  return new Date(Date.UTC(y, m, d)).toISOString().slice(0, 10)
}

function monthLabel(y: number, m: number): string {
  return new Date(Date.UTC(y, m, 1)).toLocaleDateString('de-AT', { month: 'long', year: 'numeric', timeZone: 'UTC' })
}

function buildMonthDays(y: number, m: number): (string | null)[] {
  const firstWeekday = (new Date(Date.UTC(y, m, 1)).getUTCDay() + 6) % 7
  const daysInMonth = new Date(Date.UTC(y, m + 1, 0)).getUTCDate()
  const cells: (string | null)[] = Array(firstWeekday).fill(null)
  for (let d = 1; d <= daysInMonth; d++) cells.push(toIso(y, m, d))
  return cells
}

export interface MonthCalendarProps {
  /** ISO day whose month is shown first; today when empty. */
  initialDay: string
  /** Highlighted range; its two ends are drawn solid. Empty strings for none. */
  rangeStart: string
  rangeEnd: string
  onPickDay: (iso: string) => void
  /** Small mark under a day's number; when given, every day reserves the mark's row. */
  dayMark?: (iso: string) => ReactNode
  /** Hovered pickable day; null once the pointer leaves the days. */
  onHoverDay?: (iso: string | null) => void
  disabled?: boolean
}

/** One month of day buttons (Monday first) with month navigation. Days before today are not pickable. */
export default function MonthCalendar({ initialDay, rangeStart, rangeEnd, onPickDay, dayMark, onHoverDay, disabled = false }: MonthCalendarProps) {
  const initial = new Date(initialDay !== '' ? `${initialDay}T00:00:00Z` : Date.now())
  const [view, setView] = useState({ y: initial.getUTCFullYear(), m: initial.getUTCMonth() })
  const today = todayIso()

  const shiftMonth = (delta: number) => {
    const d = new Date(Date.UTC(view.y, view.m + delta, 1))
    setView({ y: d.getUTCFullYear(), m: d.getUTCMonth() })
  }

  return (
    <Box>
      <Box sx={styles.monthHeader}>
        <IconButton size="small" sx={styles.navButton} disabled={disabled} onClick={() => shiftMonth(-1)} aria-label="Vorheriger Monat"><ChevronLeftIcon fontSize="small" /></IconButton>
        <Typography variant="body2" sx={styles.monthLabel}>{monthLabel(view.y, view.m)}</Typography>
        <IconButton size="small" sx={styles.navButton} disabled={disabled} onClick={() => shiftMonth(1)} aria-label="Nächster Monat"><ChevronRightIcon fontSize="small" /></IconButton>
      </Box>
      <Box sx={styles.grid}>
        {WEEKDAY_LABELS.map((w) => (
          <Typography key={w} variant="caption" color="text.secondary" align="center">{w}</Typography>
        ))}
      </Box>
      <Box sx={styles.grid} onMouseLeave={() => onHoverDay?.(null)}>
        {buildMonthDays(view.y, view.m).map((iso, i) => {
          if (iso === null) return <Box key={`empty-${i}`} />
          const inRange = rangeStart !== '' && rangeEnd !== '' && iso >= rangeStart && iso <= rangeEnd
          const isEndpoint = iso === rangeStart || iso === rangeEnd
          const isPast = iso < today
          const dayDisabled = disabled || isPast
          return (
            <Box
              key={iso} role="button" aria-label={iso} aria-pressed={isEndpoint} aria-disabled={dayDisabled}
              onClick={() => !dayDisabled && onPickDay(iso)}
              onMouseEnter={() => onHoverDay?.(dayDisabled ? null : iso)}
              sx={styles.day({ disabled: dayDisabled, isEndpoint, inRange, isToday: iso === today })}
            >
              <Typography variant="body2">{Number(iso.slice(-2))}</Typography>
              {dayMark && <Box sx={styles.mark}>{dayMark(iso)}</Box>}
            </Box>
          )
        })}
      </Box>
    </Box>
  )
}
