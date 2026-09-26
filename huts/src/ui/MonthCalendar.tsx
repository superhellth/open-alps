import { useState } from 'react'
import type { ReactNode } from 'react'
import { Box, IconButton, Typography } from '@mui/material'
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
  disabled?: boolean
}

/** One month of day buttons (Monday first) with month navigation. */
export default function MonthCalendar({ initialDay, rangeStart, rangeEnd, onPickDay, dayMark, disabled = false }: MonthCalendarProps) {
  const initial = new Date(initialDay !== '' ? `${initialDay}T00:00:00Z` : Date.now())
  const [view, setView] = useState({ y: initial.getUTCFullYear(), m: initial.getUTCMonth() })
  const todayIso = new Date().toISOString().slice(0, 10)

  const shiftMonth = (delta: number) => {
    const d = new Date(Date.UTC(view.y, view.m + delta, 1))
    setView({ y: d.getUTCFullYear(), m: d.getUTCMonth() })
  }

  return (
    <Box>
      <Box sx={styles.monthHeader}>
        <IconButton size="small" disabled={disabled} onClick={() => shiftMonth(-1)} aria-label="Vorheriger Monat">‹</IconButton>
        <Typography variant="body2" sx={styles.monthLabel}>{monthLabel(view.y, view.m)}</Typography>
        <IconButton size="small" disabled={disabled} onClick={() => shiftMonth(1)} aria-label="Nächster Monat">›</IconButton>
      </Box>
      <Box sx={styles.grid}>
        {WEEKDAY_LABELS.map((w) => (
          <Typography key={w} variant="caption" color="text.secondary" align="center">{w}</Typography>
        ))}
      </Box>
      <Box sx={styles.grid}>
        {buildMonthDays(view.y, view.m).map((iso, i) => {
          if (iso === null) return <Box key={`empty-${i}`} />
          const inRange = rangeStart !== '' && rangeEnd !== '' && iso >= rangeStart && iso <= rangeEnd
          const isEndpoint = iso === rangeStart || iso === rangeEnd
          return (
            <Box
              key={iso} role="button" aria-label={iso} aria-pressed={isEndpoint}
              onClick={() => !disabled && onPickDay(iso)}
              sx={styles.day({ disabled, isEndpoint, inRange, isToday: iso === todayIso })}
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
