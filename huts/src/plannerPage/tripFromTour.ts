import { newTrip } from '../trip/trip.js'
import type { Trip } from '../trip/trip.js'
import type { SourceType } from '../tourSearch/types.js'
import type { FormState } from '@/features/discover/formState.js'
import type { TripDraft } from '@/features/discover/plannerState.js'
import type { PlannerTour } from '@/tourSearch/plannerTour.js'
import type { StartPoint } from '@/data/types.js'

export function tripFromTour(tour: PlannerTour, ctx: {
  hutIds: readonly string[]
  startById: Map<number, StartPoint>
  hutNameById: Map<number, string>
  startLabel: (startId: number) => string
  form: Pick<FormState, 'sacCeiling' | 'allowUngraded'>
  draft: TripDraft
}): Trip | null {
  const start = ctx.startById.get(tour.startId)
  const exit = ctx.startById.get(tour.exitStartId)
  if (!start || !exit) return null
  const first = ctx.hutNameById.get(tour.huts[0]) ?? '?'
  const last = ctx.hutNameById.get(tour.huts[tour.huts.length - 1]) ?? '?'
  const official = tour.official
  return newTrip({
    name: official ? official.name : `${ctx.startLabel(tour.startId)}: ${first} – ${last}`,
    startDate: ctx.draft.startDate || null,
    partySize: ctx.draft.partySize,
    start: { startId: tour.startId, sourceType: start.sourceType as SourceType },
    huts: tour.huts.map((h) => ctx.hutIds[h]),
    exit: { startId: tour.exitStartId, sourceType: exit.sourceType as SourceType },
    variant: official
      ? { sacCeiling: null, allowUngraded: true }
      : { sacCeiling: ctx.form.sacCeiling === 'any' ? null : ctx.form.sacCeiling, allowUngraded: ctx.form.allowUngraded },
    ...(official ? { source: { kind: 'official' as const, tourId: official.tourId } } : {}),
  })
}
