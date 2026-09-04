import { useEffect, useState } from 'react'
import { Box, Link, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material'
import { fetchHutDetail } from '../availability/fetchHutDetail.js'
import { buildBookingLink } from '../availability/bookingLink.js'
import type { HutDetail } from '../availability/types.js'
import type { TourResult } from '../tourSearch/types.js'

const STATUS_REASON: Record<string, string> = {
  HUT_CLOSED_TO_PUBLIC: 'Hütte geschlossen (Saison)',
  RESERVATION_NOT_POSSIBLE: 'ausgebucht',
  TECHNICAL_ERROR: 'dzt. nicht möglich',
}

type DetailState = 'loading' | HutDetail | 'error'

function addDays(date: Date, days: number): Date {
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate() + days))
}

// One request per hut, per already-expanded chain (root CLAUDE.md / spec §2, §4) — never looped
// over more than the single chain a user opened this panel for.
function AvailabilityDetailPanel({
  chain, hutNameById, hutOhrsByIndex, startDate, numOfPeople,
}: {
  chain: TourResult
  hutNameById: Map<number, string>
  hutOhrsByIndex: Map<number, { ohrsHutId: string | null; tenantCode: number | null }>
  startDate: Date
  numOfPeople: number
}) {
  const [details, setDetails] = useState<Map<number, DetailState>>(new Map())

  useEffect(() => {
    let cancelled = false
    const bookableHuts = chain.huts
      .map((h, idx) => ({ h, idx, ohrs: hutOhrsByIndex.get(h) }))
      .filter((entry): entry is { h: number; idx: number; ohrs: { ohrsHutId: string; tenantCode: number } } =>
        entry.ohrs?.ohrsHutId != null && entry.ohrs?.tenantCode != null)

    setDetails(new Map(bookableHuts.map(({ h }) => [h, 'loading'] as const)))

    for (const { h, idx, ohrs } of bookableHuts) {
      fetchHutDetail(ohrs.ohrsHutId, ohrs.tenantCode, addDays(startDate, idx), numOfPeople)
        .then((detail) => { if (!cancelled) setDetails((prev) => new Map(prev).set(h, detail)) })
        .catch(() => { if (!cancelled) setDetails((prev) => new Map(prev).set(h, 'error')) })
    }
    return () => { cancelled = true }
  }, [chain, hutOhrsByIndex, startDate, numOfPeople])

  const bookableHuts = chain.huts
    .map((h, idx) => ({ h, idx, ohrs: hutOhrsByIndex.get(h) }))
    .filter((entry): entry is { h: number; idx: number; ohrs: { ohrsHutId: string; tenantCode: number } } =>
      entry.ohrs?.ohrsHutId != null && entry.ohrs?.tenantCode != null)

  if (bookableHuts.length === 0) return null

  return (
    <Box sx={{ mt: 2 }}>
      <Typography variant="subtitle2">Verfügbarkeit im Detail</Typography>
      {bookableHuts.map(({ h, idx, ohrs }) => {
        const state = details.get(h)
        const nightDate = addDays(startDate, idx)
        return (
          <Box key={h} sx={{ mb: 1 }}>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              {hutNameById.get(h) ?? h}
            </Typography>
            {state === 'loading' && <Typography variant="caption">lädt…</Typography>}
            {state === 'error' && <Typography variant="caption" color="error">Details nicht verfügbar.</Typography>}
            {state && state !== 'loading' && state !== 'error' && (
              <>
                {state.calendarDays.map((day) => (
                  <Box key={day.day}>
                    {day.bedCategoriesData.length > 0 ? (
                      <Table size="small">
                        <TableHead>
                          <TableRow>
                            <TableCell>Kategorie</TableCell>
                            <TableCell align="right">frei</TableCell>
                            <TableCell align="right">gesamt</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {day.bedCategoriesData.map((bc, i) => (
                            <TableRow key={i}>
                              <TableCell>{bc.label}</TableCell>
                              <TableCell align="right">{bc.totalFreePlaces}</TableCell>
                              <TableCell align="right">{bc.totalPlaces}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    ) : (
                      <Typography variant="caption">{STATUS_REASON[day.status] ?? day.status}</Typography>
                    )}
                  </Box>
                ))}
                <Link href={buildBookingLink(ohrs.ohrsHutId, nightDate)} target="_blank" rel="noreferrer" variant="caption">
                  Auf hut-reservation.org buchen
                </Link>
              </>
            )}
          </Box>
        )
      })}
    </Box>
  )
}

export default AvailabilityDetailPanel
