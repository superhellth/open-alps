import { useState } from 'react'
import type { MouseEvent } from 'react'
import { Box, Button, IconButton, Popover, Typography } from '@mui/material'
import CalendarMonthIcon from '@mui/icons-material/CalendarMonth'

interface RangeCalendarProps {
  startDate: string
  endDate: string
  onChange: (range: { startDate: string; endDate: string }) => void
  disabled: boolean
}

const WEEKDAY_LABELS = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']

function toIso(y: number, m: number, d: number): string {
  return new Date(Date.UTC(y, m, d)).toISOString().slice(0, 10)
}

function parseIso(iso: string): { y: number; m: number; d: number } {
  const [y, m, d] = iso.split('-').map(Number)
  return { y, m: m - 1, d }
}

function monthLabel(y: number, m: number): string {
  return new Date(Date.UTC(y, m, 1)).toLocaleDateString('de-AT', { month: 'long', year: 'numeric' })
}

function buildMonthDays(y: number, m: number): (string | null)[] {
  const firstWeekday = (new Date(Date.UTC(y, m, 1)).getUTCDay() + 6) % 7
  const daysInMonth = new Date(Date.UTC(y, m + 1, 0)).getUTCDate()
  const cells: (string | null)[] = Array(firstWeekday).fill(null)
  for (let d = 1; d <= daysInMonth; d++) cells.push(toIso(y, m, d))
  return cells
}

function fmtIso(iso: string): string {
  const { y, m, d } = parseIso(iso)
  return new Date(Date.UTC(y, m, d)).toLocaleDateString('de-AT', { day: '2-digit', month: '2-digit' })
}

function summaryLabel(startDate: string, endDate: string): string {
  if (startDate === '' || endDate === '') return 'Zeitraum wählen'
  return `${fmtIso(startDate)} – ${fmtIso(endDate)}`
}

export default function RangeCalendar({ startDate, endDate, onChange, disabled }: RangeCalendarProps) {
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null)
  const initial = startDate !== '' ? parseIso(startDate) : { y: new Date().getUTCFullYear(), m: new Date().getUTCMonth() }
  const [view, setView] = useState({ y: initial.y, m: initial.m })
  // Holds the first click of a new range until the second click completes it,
  // so a single click never reports an empty endDate to the parent.
  const [pendingStart, setPendingStart] = useState<string | null>(null)

  const todayIso = new Date().toISOString().slice(0, 10)
  const cells = buildMonthDays(view.y, view.m)

  const shownStart = pendingStart ?? startDate
  const shownEnd = pendingStart !== null ? pendingStart : endDate

  const shiftMonth = (delta: number) => {
    const d = new Date(Date.UTC(view.y, view.m + delta, 1))
    setView({ y: d.getUTCFullYear(), m: d.getUTCMonth() })
  }

  const pickDay = (iso: string) => {
    if (pendingStart === null) {
      setPendingStart(iso)
    } else if (iso < pendingStart) {
      onChange({ startDate: iso, endDate: pendingStart })
      setPendingStart(null)
      setAnchorEl(null)
    } else {
      onChange({ startDate: pendingStart, endDate: iso })
      setPendingStart(null)
      setAnchorEl(null)
    }
  }

  const openCalendar = (e: MouseEvent<HTMLElement>) => {
    setView({ y: initial.y, m: initial.m })
    setPendingStart(null)
    setAnchorEl(e.currentTarget)
  }

  return (
    <>
      <Button
        size="small" variant="outlined" color="secondary" disabled={disabled} onClick={openCalendar}
        sx={{
          textTransform: 'none', justifyContent: 'space-between', width: '100%', height: 40,
          fontSize: '1rem', fontWeight: 400, color: 'text.primary', borderColor: 'rgba(0, 0, 0, 0.23)',
          '&:hover': { borderColor: 'text.primary' },
        }}
      >
        {summaryLabel(startDate, endDate)}
        <CalendarMonthIcon fontSize="small" sx={{ ml: 1, color: 'action.active' }} aria-hidden />
      </Button>
      <Popover
        open={anchorEl !== null} anchorEl={anchorEl} onClose={() => setAnchorEl(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}
      >
        <Box sx={{ width: 280, p: 1.5 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <IconButton size="small" disabled={disabled} onClick={() => shiftMonth(-1)} aria-label="Vorheriger Monat">‹</IconButton>
            <Typography variant="body2" sx={{ textTransform: 'capitalize' }}>{monthLabel(view.y, view.m)}</Typography>
            <IconButton size="small" disabled={disabled} onClick={() => shiftMonth(1)} aria-label="Nächster Monat">›</IconButton>
          </Box>
          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', mt: 0.5 }}>
            {WEEKDAY_LABELS.map((w) => (
              <Typography key={w} variant="caption" color="text.secondary" align="center">{w}</Typography>
            ))}
          </Box>
          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)' }}>
            {cells.map((iso, i) => {
              if (iso === null) return <Box key={`empty-${i}`} />
              const inRange = shownStart !== '' && shownEnd !== '' && iso >= shownStart && iso <= shownEnd
              const isEndpoint = iso === shownStart || iso === shownEnd
              const isToday = iso === todayIso
              return (
                <Box
                  key={iso} role="button" aria-label={iso} aria-pressed={isEndpoint}
                  onClick={() => !disabled && pickDay(iso)}
                  sx={{
                    textAlign: 'center', py: 0.5, borderRadius: 1, cursor: disabled ? 'default' : 'pointer',
                    bgcolor: isEndpoint ? 'primary.main' : inRange ? 'primary.light' : 'transparent',
                    color: isEndpoint ? 'primary.contrastText' : 'text.primary',
                    outline: isToday && !isEndpoint ? '1px solid' : 'none',
                    outlineColor: 'primary.main',
                    opacity: disabled ? 0.5 : 1,
                    '&:hover': disabled ? undefined : { bgcolor: isEndpoint ? 'primary.main' : 'action.hover' },
                  }}
                >
                  <Typography variant="body2">{Number(iso.slice(-2))}</Typography>
                </Box>
              )
            })}
          </Box>
        </Box>
      </Popover>
    </>
  )
}
