import type { ReactNode } from 'react'
import { Box, Link, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material'
import { addUtcDays } from '@/availability/formatDate.js'
import { buildBookingLink } from '@/availability/bookingLink.js'
import type { HutOhrs } from '@/data/buildAppData.js'
import type { TripLegs } from '@/trip/tripLegs.js'
import type { BookingStatus, Trip } from '@/trip/trip.js'
import AvailabilityMark from './AvailabilityMark.js'
import Signpost from './Signpost.js'
import type { NightView } from './useTripAvailability.js'
import { styles } from './StageList.styles.js'

export interface StageListProps {
  trip: Trip
  tripLegs: TripLegs
  hutNameById: Map<number, string>
  hutOhrsByIndex: Map<number, HutOhrs>
  startLabel: (startId: number) => string
  nightViews: NightView[] | null
  onHoverLeg: (index: number | null) => void
  renderStageControls?: (night: number) => ReactNode
  onNightStatusChange?: (night: number, status: BookingStatus) => void
  warnings?: string[]
}

const CHANGED_TEXT = 'Seit dem Speichern geändert – nicht mehr im Wegenetz'
const STATUS_LABEL: Record<BookingStatus, string> = { open: 'offen', requested: 'angefragt', confirmed: 'bestätigt' }

export default function StageList({
  trip, tripLegs, hutNameById, hutOhrsByIndex, startLabel, nightViews, onHoverLeg, renderStageControls, onNightStatusChange, warnings = [],
}: StageListProps) {
  const firstNight = trip.startDate ? new Date(trip.startDate) : null
  const exitLeg = tripLegs.legs[trip.huts.length]

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
      {trip.huts.map((_guid, i) => {
        const hutIndex = tripLegs.hutIndices[i]
        const leg = tripLegs.legs[i]
        const changed = tripLegs.changed[i]
        const ohrs = hutIndex === null ? undefined : hutOhrsByIndex.get(hutIndex)
        const view = nightViews?.[i]
        return (
          <Box key={i} data-stage={i} onMouseEnter={() => onHoverLeg(i)} onMouseLeave={() => onHoverLeg(null)}>
            <Typography variant="caption" color="text.secondary">
              Etappe {i + 1}{firstNight ? ` · Nacht ${addUtcDays(firstNight, i).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', timeZone: 'UTC' })}` : ''}
            </Typography>
            <Signpost
              variant={changed ? 'outline' : 'plate'}
              title={hutIndex === null ? 'Unbekannte Hütte' : hutNameById.get(hutIndex) ?? String(hutIndex)}
              timeH={!changed && leg ? leg.durationH : undefined}
              ascentM={!changed && leg ? leg.ascentM : undefined}
              descentM={!changed && leg ? leg.descentM : undefined}
            >
              {changed ? (
                <Typography variant="body2" sx={{ mt: 0.5 }}>{CHANGED_TEXT}</Typography>
              ) : (
                <Box sx={styles.nightDetails}>
                  {firstNight && view && (view.loading ? <Typography variant="body2">Verfügbarkeit lädt …</Typography> : <AvailabilityMark availability={view.availability} />)}
                  {ohrs?.ohrsHutId && firstNight ? (
                    <Link href={buildBookingLink(ohrs.ohrsHutId, addUtcDays(firstNight, i))} target="_blank" rel="noreferrer" color="inherit">
                      Auf hut-reservation.org buchen
                    </Link>
                  ) : !ohrs?.ohrsHutId ? (
                    <Typography variant="body2">Direktbuchung: die Hütte selbst kontaktieren.</Typography>
                  ) : null}
                </Box>
              )}
            </Signpost>
            {onNightStatusChange && (
              <ToggleButtonGroup
                size="small" exclusive value={trip.nights[i].status} aria-label={`Buchungsstatus Nacht ${i + 1}`}
                onChange={(_e, next: BookingStatus | null) => { if (next) onNightStatusChange(i, next) }}
                sx={{ mt: 0.5 }}
              >
                {(Object.keys(STATUS_LABEL) as BookingStatus[]).map((s) => (
                  <ToggleButton key={s} value={s} sx={{ textTransform: 'none', py: 0.25 }}>{STATUS_LABEL[s]}</ToggleButton>
                ))}
              </ToggleButtonGroup>
            )}
            {renderStageControls?.(i)}
          </Box>
        )
      })}
      {exitLeg && (
        <Box>
          <Typography variant="caption" color="text.secondary">Etappe {trip.huts.length + 1}</Typography>
          <Signpost
            title={`Abstieg: ${startLabel(trip.exit.startId)}`}
            timeH={exitLeg.durationH} ascentM={exitLeg.ascentM} descentM={exitLeg.descentM}
          />
        </Box>
      )}
      {warnings.map((w) => <Typography key={w} variant="body2" role="alert">⚠ {w}</Typography>)}
    </Box>
  )
}
