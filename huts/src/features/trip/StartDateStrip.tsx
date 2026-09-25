import { useEffect, useState } from 'react'
import { Box, Button, Typography } from '@mui/material'
import { fetchAvailabilityByOffset } from '@/availability/fetchAvailability.js'
import { addUtcDays } from '@/availability/formatDate.js'
import { answerWindow, shiftAnswers } from '@/availability/startDateAnswer.js'
import type { ShiftAnswer } from '@/availability/startDateAnswer.js'
import type { HutOhrs } from '@/data/buildAppData.js'
import type { Trip } from '@/trip/trip.js'

const MAX_SHIFT = 3
const VERDICT_TEXT = { bookable: '● alles frei', blocked: '✕ belegt', unclear: '? unklar' } as const

/** Which start dates make the whole chain bookable. Reuses the per-date cached collectAll calls,
 *  so shifting by one more day only adds one or two fetches. */
export default function StartDateStrip({ trip, hutIndices, hutOhrsByIndex, onShift }: {
  trip: Trip
  hutIndices: (number | null)[]
  hutOhrsByIndex: Map<number, HutOhrs>
  onShift: (days: number) => void
}) {
  const [answers, setAnswers] = useState<ShiftAnswer[] | null>(null)
  const ohrsIds = hutIndices.map((i) => (i === null ? null : hutOhrsByIndex.get(i)?.ohrsHutId ?? null))
  const key = `${trip.startDate}|${trip.partySize}|${ohrsIds.join(',')}`

  useEffect(() => {
    if (!trip.startDate) { setAnswers(null); return }
    let cancelled = false
    const window = answerWindow(new Date(trip.startDate), MAX_SHIFT)
    fetchAvailabilityByOffset(window.base, trip.partySize, window.maxOffset(ohrsIds.length))
      .then((free) => { if (!cancelled) setAnswers(shiftAnswers(ohrsIds, free, MAX_SHIFT)) })
    return () => { cancelled = true }
  }, [key]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!trip.startDate) return null
  const first = new Date(trip.startDate)
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
        <Typography variant="subtitle2" sx={{ flex: 1 }}>Startdatum verschieben</Typography>
        <Button size="small" variant="outlined" color="secondary" onClick={() => onShift(-1)}>−1 Tag</Button>
        <Button size="small" variant="outlined" color="secondary" onClick={() => onShift(1)}>+1 Tag</Button>
      </Box>
      <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
        {answers?.map((a) => (
          <Button
            key={a.shiftDays} size="small" variant={a.shiftDays === 0 ? 'contained' : 'outlined'} color={a.shiftDays === 0 ? 'primary' : 'secondary'}
            onClick={() => onShift(a.shiftDays)} disabled={a.shiftDays === 0}
            sx={{ textTransform: 'none', flexDirection: 'column', lineHeight: 1.2 }}
          >
            <span>{addUtcDays(first, a.shiftDays).toLocaleDateString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit', timeZone: 'UTC' })}</span>
            <span>{VERDICT_TEXT[a.verdict]}</span>
          </Button>
        ))}
      </Box>
    </Box>
  )
}
