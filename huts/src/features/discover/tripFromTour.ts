import { newTrip } from '@/trip/trip.js'
import type { Trip } from '@/trip/trip.js'
import type { SourceType } from '@/tourSearch/types.js'
import type { FormState } from './formState.js'
import type { TripDraft } from './plannerState.js'
import type { PlannerTour } from '@/tourSearch/plannerTour.js'
import type { StartPoint } from '@/data/types.js'

/** The name a trip gets without user input: "first hut – last hut". */
export function autoTripName(huts: { first: string; last: string }): string {
  return `${huts.first} – ${huts.last}`
}

export function tripFromTour(tour: PlannerTour, ctx: {
  hutIds: readonly string[]
  startById: Map<number, StartPoint>
  hutNameById: Map<number, string>
  form: Pick<FormState, 'sacCeiling' | 'allowUngraded'>
  draft: TripDraft
}): Trip | null {
  const start = ctx.startById.get(tour.startId)
  const exit = ctx.startById.get(tour.exitStartId)
  if (!start || !exit) return null
  const first = ctx.hutNameById.get(tour.huts[0]) ?? '?'
  const last = ctx.hutNameById.get(tour.huts[tour.huts.length - 1]) ?? '?'
  return newTrip({
    name: autoTripName({ first, last }),
    startDate: ctx.draft.startDate || null,
    partySize: ctx.draft.partySize,
    start: { startId: tour.startId, sourceType: start.sourceType as SourceType },
    huts: tour.huts.map((h) => ctx.hutIds[h]),
    exit: { startId: tour.exitStartId, sourceType: exit.sourceType as SourceType },
    variant: { sacCeiling: ctx.form.sacCeiling === 'any' ? null : ctx.form.sacCeiling, allowUngraded: ctx.form.allowUngraded },
  })
}
