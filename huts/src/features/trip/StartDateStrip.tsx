import { useEffect, useState } from 'react'
import { Box, Button } from '@mui/material'
import { fetchAvailabilityByOffset } from '@/availability/fetchAvailability.js'
import { addUtcDays } from '@/availability/formatDate.js'
import { answerWindow, shiftAnswers } from '@/availability/startDateAnswer.js'
import type { ShiftAnswer } from '@/availability/startDateAnswer.js'
import type { HutOhrs } from '@/data/buildAppData.js'
import type { Trip } from '@/trip/trip.js'
import { styles } from './StartDateStrip.styles.js'

const MAX_SHIFT = 3
const VERDICT_TEXT = { bookable: 'alles frei', blocked: 'belegt', unclear: 'unklar' } as const
const VERDICT_MARK = { bookable: '●', blocked: '✕', unclear: '?' } as const

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
    <Box role="group" aria-label="Startdatum verschieben" sx={styles.chips}>
      {answers?.map((a) => {
        const day = addUtcDays(first, a.shiftDays).toLocaleDateString('de-DE', { weekday: 'short', day: 'numeric', timeZone: 'UTC' })
        const current = a.shiftDays === 0
        return (
          <Button
            key={a.shiftDays} data-shift={a.shiftDays} size="small" sx={styles.chip}
            variant={current ? 'contained' : 'outlined'} color={current ? 'primary' : 'secondary'}
            disabled={current} onClick={() => onShift(a.shiftDays)}
            aria-label={`${day}: ${VERDICT_TEXT[a.verdict]}`}
          >
            <span>{day}</span>
            <span aria-hidden="true">{VERDICT_MARK[a.verdict]}</span>
          </Button>
        )
      })}
    </Box>
  )
}
