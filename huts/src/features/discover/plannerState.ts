/** Values the filter bar collects for a trip that does not exist yet; copied into the trip on pick. */
export interface TripDraft {
  startDate: string
  endDate: string
  partySize: number
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

function addDaysIso(iso: string, days: number): string {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10)
}

export const DEFAULT_DRAFT: TripDraft = { startDate: todayIso(), endDate: addDaysIso(todayIso(), 2), partySize: 1 }

function daysBetween(fromIso: string, toIso: string): number {
  const [fy, fm, fd] = fromIso.split('-').map(Number)
  const [ty, tm, td] = toIso.split('-').map(Number)
  const from = Date.UTC(fy, fm - 1, fd)
  const to = Date.UTC(ty, tm - 1, td)
  return Math.round((to - from) / 86_400_000) + 1
}

/** The exact day count the ranking code aims for. */
export function dayCountFromDraft(draft: TripDraft): number {
  return daysBetween(draft.startDate, draft.endDate)
}

/** [min, max] days for the search query: always exact, since the trip is always dated. */
export function legCountRangeFromDraft(draft: TripDraft): [number, number] {
  const days = daysBetween(draft.startDate, draft.endDate)
  return [days, days]
}
